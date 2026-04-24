"""翻译管道异常处理 — Graceful Fallback 体系

异常分类:
- TRANSIENT: 临时性错误（网络超时、GPU 显存不足）→ 重试后降级
- PERMANENT: 持久性错误（格式不支持、内容为空）→ 跳过或保留原文
- FATAL: 致命错误（文件损坏、内存溢出）→ 终止管道

降级策略:
1. Ollama 失败 → 自动切换云端（若配置了 API Key）
2. 单块翻译失败 → 保留原文，继续下一块
3. 云端也失败 → 标记 chunk_error，前端可提示用户定位
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """异常分类"""
    TRANSIENT = "transient"      # 临时性，可重试
    PERMANENT = "permanent"       # 持久性，跳过
    FATAL = "fatal"              # 致命，终止管道


# Ollama 临时错误状态码/关键词
_TRANSIENT_PATTERNS = [
    "connection refused",
    "connection reset",
    "connection timeout",
    "timed out",
    "temporary failure",
    "load model",
    "gpu",
    "out of memory",
    "oom",
    "context length",
    "429",
    "503",
    "rate limit",
]

# 永久性错误关键词
_PERMANENT_PATTERNS = [
    "invalid request",
    "bad request",
    "400",
    "401",
    "403",
    "404",
    "model not found",
    "unsupported",
]

# 致命错误关键词
_FATAL_PATTERNS = [
    "out of memory",
    "oom",
    "memory error",
    "segmentation fault",
    "core dump",
    "fatal error",
]


def classify_error(error: Exception | str) -> ErrorCategory:
    """将异常分类为 TRANSIENT / PERMANENT / FATAL

    Args:
        error: 异常对象或字符串

    Returns:
        ErrorCategory 枚举值
    """
    msg = str(error).lower()

    for pattern in _FATAL_PATTERNS:
        if pattern in msg:
            logger.warning("致命错误分类: %s", error)
            return ErrorCategory.FATAL

    for pattern in _TRANSIENT_PATTERNS:
        if pattern in msg:
            logger.info("临时错误分类: %s", error)
            return ErrorCategory.TRANSIENT

    for pattern in _PERMANENT_PATTERNS:
        if pattern in msg:
            logger.info("持久错误分类: %s", error)
            return ErrorCategory.PERMANENT

    # 默认按临时错误处理（网络波动最常见）
    logger.info("默认按临时错误分类: %s", error)
    return ErrorCategory.TRANSIENT


def get_fallback_strategy(
    error: Exception | str,
    chunk_index: int,
    total_chunks: int,
    has_cloud_fallback: bool = False,
) -> dict[str, Any]:
    """根据错误类型和上下文返回降级策略

    Args:
        error: 异常对象或字符串
        chunk_index: 当前块索引（从0开始）
        total_chunks: 总块数
        has_cloud_fallback: 是否配置了云端 API 作为备选

    Returns:
        策略字典，包含:
        - action: "retry" | "retry_cloud" | "skip" | "abort"
        - delay: 重试等待秒数
        - message: 人类可读的原因
    """
    category = classify_error(error)
    msg = str(error)

    if category == ErrorCategory.FATAL:
        return {
            "action": "abort",
            "delay": 0,
            "message": f"遇到致命错误，翻译管道终止: {msg}",
            "recoverable": False,
        }

    if category == ErrorCategory.TRANSIENT:
        # 网络/Ollama 临时错误：先重试本地，再考虑云端降级
        if has_cloud_fallback and ("ollama" in msg.lower() or "connection" in msg.lower() or "gpu" in msg.lower()):
            return {
                "action": "retry_cloud",
                "delay": 1.0,
                "message": f"Ollama 临时故障，切换云端 API 继续翻译",
                "recoverable": True,
            }

        # 最后一块失败，可以接受跳过
        if chunk_index >= total_chunks - 1:
            return {
                "action": "skip",
                "delay": 0,
                "message": f"最后一块翻译失败，保留原文继续",
                "recoverable": True,
            }

        return {
            "action": "retry",
            "delay": 3.0,
            "message": f"临时错误，{3}秒后重试: {msg}",
            "recoverable": True,
        }

    # PERMANENT: 跳过当前块，保留原文
    return {
        "action": "skip",
        "delay": 0,
        "message": f"持久错误，跳过当前块: {msg}",
        "recoverable": True,
    }


def format_error_for_user(error: Exception | str, category: ErrorCategory | None = None) -> str:
    """将错误格式化为用户友好的提示信息

    Args:
        error: 异常对象或字符串
        category: 可选，提前分类以节省开销

    Returns:
        用户友好的错误提示
    """
    if category is None:
        category = classify_error(error)

    msg = str(error).lower()

    if category == ErrorCategory.FATAL:
        return "翻译遇到致命错误，建议重启应用后重试。"

    if category == ErrorCategory.PERMANENT:
        if "format" in msg or "unsupported" in msg:
            return "文档格式不支持，建议使用 PDF/TXT/DOCX 格式。"
        if "empty" in msg or "null" in msg:
            return "文档内容为空或无法提取文字。"
        return "文档处理失败，建议检查文件内容是否正常。"

    # TRANSIENT
    if "timeout" in msg:
        return "翻译超时，可能是网络或 Ollama 响应慢，稍后重试。"
    if "connection" in msg:
        return "无法连接 Ollama，请检查 Ollama 服务是否运行。"
    if "gpu" in msg or "memory" in msg:
        return "GPU 显存不足，建议使用更小的模型或减少并发。"
    if "rate limit" in msg or "429" in msg:
        return "API 频率超限，稍后重试。"
    return f"翻译遇到问题: {error}，请重试。"


def build_fallback_result(chunk_text: str, error: str, chunk_index: int) -> dict:
    """为翻译失败的 chunk 构建降级结果

    Args:
        chunk_text: 原始块文本
        error: 错误信息
        chunk_index: 块索引

    Returns:
        符合翻译结果格式的字典，包含原文作为译文 + 错误元数据
    """
    return {
        "original": chunk_text,
        "translated": chunk_text,  # 降级：返回原文
        "model": "",
        "error": error,
        "fallback": True,
        "chunk_index": chunk_index,
    }