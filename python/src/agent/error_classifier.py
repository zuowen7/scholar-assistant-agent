"""结构化错误分类与自动恢复策略。

设计参考 Hermes Agent 的 14 种错误分类体系：
- 不再笼统处理 "Error"，而是标准化定义每种异常
- 每种错误类型对应自动恢复策略（重试/降级/修正）
- 指数退避重试，避免无限循环

错误分类:
├── auth — 认证失败（API Key 无效）
├── auth_permanent — 永久认证失败（账号封禁）
├── billing — 账单问题（额度用完）
├── rate_limit — 请求过多（被限流）
├── overloaded — 服务器过载
├── server_error — 服务器错误（5xx）
├── timeout — 请求超时
├── context_overflow — 上下文溢出
├── payload_too_large — 请求体太大
├── model_not_found — 模型不存在
├── format_error — 请求格式错误
├── tool_error — 工具执行失败
├── max_steps — 超过最大推理步数
└── unknown — 未知错误
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型枚举。"""

    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    MODEL_NOT_FOUND = "model_not_found"
    FORMAT_ERROR = "format_error"
    TOOL_ERROR = "tool_error"
    MAX_STEPS = "max_steps"
    UNKNOWN = "unknown"


@dataclass
class RecoveryAction:
    """恢复动作。

    Attributes:
        action: 动作类型（retry/skip/abort/rephrase）。
        delay_seconds: 重试延迟秒数。
        max_retries: 最大重试次数。
        message: 返回给 LLM 的反馈消息。
    """

    action: str = "skip"  # retry | skip | abort | rephrase
    delay_seconds: float = 0.0
    max_retries: int = 1
    message: str = ""


# 每种错误类型对应的恢复策略
_RECOVERY_STRATEGIES: dict[ErrorType, RecoveryAction] = {
    ErrorType.AUTH: RecoveryAction(
        action="abort", message="认证失败，请检查 API Key 配置。",
    ),
    ErrorType.AUTH_PERMANENT: RecoveryAction(
        action="abort", message="认证永久失败，账号可能被封禁。",
    ),
    ErrorType.BILLING: RecoveryAction(
        action="abort", message="API 额度已用完，请充值或更换 Key。",
    ),
    ErrorType.RATE_LIMIT: RecoveryAction(
        action="retry", delay_seconds=5.0, max_retries=3,
        message="请求被限流，等待 {delay}s 后重试...",
    ),
    ErrorType.OVERLOADED: RecoveryAction(
        action="retry", delay_seconds=10.0, max_retries=2,
        message="服务器过载，等待 {delay}s 后重试...",
    ),
    ErrorType.SERVER_ERROR: RecoveryAction(
        action="retry", delay_seconds=3.0, max_retries=2,
        message="服务器错误，等待 {delay}s 后重试...",
    ),
    ErrorType.TIMEOUT: RecoveryAction(
        action="retry", delay_seconds=2.0, max_retries=2,
        message="请求超时，等待 {delay}s 后重试...",
    ),
    ErrorType.CONTEXT_OVERFLOW: RecoveryAction(
        action="rephrase",
        message="上下文过长，已自动压缩。请简化问题。",
    ),
    ErrorType.PAYLOAD_TOO_LARGE: RecoveryAction(
        action="rephrase",
        message="请求体过大，请减少输入文本长度。",
    ),
    ErrorType.MODEL_NOT_FOUND: RecoveryAction(
        action="abort", message="模型不存在，请检查模型名称。",
    ),
    ErrorType.FORMAT_ERROR: RecoveryAction(
        action="rephrase", max_retries=1,
        message="请求格式错误，请检查参数。",
    ),
    ErrorType.TOOL_ERROR: RecoveryAction(
        action="skip",
        message="工具执行失败: {detail}",
    ),
    ErrorType.MAX_STEPS: RecoveryAction(
        action="abort",
        message="推理步数超过上限，请简化问题或分步提问。",
    ),
    ErrorType.UNKNOWN: RecoveryAction(
        action="retry", delay_seconds=3.0, max_retries=1,
        message="未知错误，请检查 API 配置和网络连接",
    ),
}


def classify_error(exception: Exception) -> ErrorType:
    """根据异常信息自动分类错误类型。

    Args:
        exception: 捕获的异常对象。

    Returns:
        对应的 ErrorType。
    """
    msg = str(exception).lower()
    response = getattr(exception, "response", None)
    status_code = getattr(response, "status_code", None) if response is not None else None

    # 从错误消息中提取 HTTP 状态码（如 "HTTP 400" 或 "(HTTP 429)"）
    if status_code is None:
        import re as _re
        m = _re.search(r"(?i)\(http (\d+)\)", msg)
        if m:
            status_code = int(m.group(1))

    # 按状态码分类
    if status_code == 401:
        return ErrorType.AUTH
    if status_code == 403:
        return ErrorType.AUTH_PERMANENT
    if status_code == 402:
        return ErrorType.BILLING
    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if status_code == 413:
        return ErrorType.PAYLOAD_TOO_LARGE
    if status_code == 404:
        return ErrorType.MODEL_NOT_FOUND
    if status_code == 400:
        return ErrorType.FORMAT_ERROR
    if status_code == 529:
        return ErrorType.OVERLOADED
    if status_code and status_code >= 500:
        return ErrorType.SERVER_ERROR if status_code < 503 else ErrorType.OVERLOADED

    # 按消息内容分类
    if "timeout" in msg or "timed out" in msg:
        return ErrorType.TIMEOUT
    if "connection" in msg or "connect" in msg or "连接" in msg:
        return ErrorType.TIMEOUT
    if "context" in msg and ("overflow" in msg or "too long" in msg or "length" in msg):
        return ErrorType.CONTEXT_OVERFLOW
    if "input too long" in msg or "input is too long" in msg:
        return ErrorType.CONTEXT_OVERFLOW
    if "context_length_exceeded" in msg:
        return ErrorType.CONTEXT_OVERFLOW
    if "maximum context length" in msg or "max_tokens_exceed" in msg or "tokens exceed" in msg:
        return ErrorType.CONTEXT_OVERFLOW
    if "rate" in msg and ("limit" in msg or "exceeded" in msg):
        return ErrorType.RATE_LIMIT
    if "resource exhausted" in msg or "resource has been exhausted" in msg:
        return ErrorType.RATE_LIMIT
    if "too many requests" in msg or "请求过多" in msg:
        return ErrorType.RATE_LIMIT
    if "auth" in msg or "api key" in msg or "unauthorized" in msg:
        return ErrorType.AUTH
    if "model" in msg and ("not found" in msg or "does not exist" in msg):
        return ErrorType.MODEL_NOT_FOUND
    if "billing" in msg or "quota" in msg or "insufficient" in msg:
        return ErrorType.BILLING
    if "overload" in msg or "capacity" in msg:
        return ErrorType.OVERLOADED
    # 中文错误消息匹配
    if "api 错误" in msg or "api错误" in msg or "服务器" in msg:
        return ErrorType.SERVER_ERROR
    if "限流" in msg or "频率" in msg or "请求过多" in msg:
        return ErrorType.RATE_LIMIT
    if "认证" in msg or "密钥" in msg or "api key" in msg:
        return ErrorType.AUTH
    if "超时" in msg:
        return ErrorType.TIMEOUT
    if "模型" in msg and "不存在" in msg:
        return ErrorType.MODEL_NOT_FOUND
    # 流式响应不完整（Ollama 未发送 done=true 等）
    if "未返回完整" in msg or "未返回" in msg or "empty response" in msg:
        return ErrorType.TIMEOUT
    # 通用 httpx / json 解析错误
    if "json" in msg and "decode" in msg:
        return ErrorType.FORMAT_ERROR

    # 云端 API 流式错误: 提取内层消息重新分类，避免前缀干扰
    # 格式: "云端 API 流式错误: <实际错误消息>"
    if "流式错误" in msg or "streaming error" in msg:
        colon_idx = msg.find(":")
        if colon_idx != -1:
            inner = msg[colon_idx + 1:].strip()
            if inner:
                inner_type = classify_error(Exception(inner))
                if inner_type != ErrorType.UNKNOWN:
                    return inner_type

    return ErrorType.UNKNOWN


def get_recovery(error_type: ErrorType) -> RecoveryAction:
    """获取错误类型对应的恢复策略。

    Args:
        error_type: 错误类型。

    Returns:
        RecoveryAction 实例。
    """
    return _RECOVERY_STRATEGIES.get(error_type, _RECOVERY_STRATEGIES[ErrorType.UNKNOWN])


class RetryManager:
    """带指数退避的重试管理器。

    用于对 LLM 调用和工具执行进行受控的重试。

    Attributes:
        base_delay: 基础延迟秒数。
        max_delay: 最大延迟秒数。
        max_total_retries: 全局最大重试次数。
    """

    def __init__(
        self,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        max_total_retries: int = 5,
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_total_retries = max_total_retries
        self._attempt_counts: dict[ErrorType, int] = {}

    def get_delay(self, error_type: ErrorType) -> float:
        """计算当前错误类型的指数退避延迟。

        Args:
            error_type: 错误类型。

        Returns:
            延迟秒数。
        """
        attempt = self._attempt_counts.get(error_type, 0)
        recovery = get_recovery(error_type)
        base = recovery.delay_seconds or self.base_delay
        delay = base * (2 ** attempt)
        return min(delay, self.max_delay)

    def can_retry(self, error_type: ErrorType) -> bool:
        """判断是否还可以重试。

        Args:
            error_type: 错误类型。

        Returns:
            True 表示可以重试。
        """
        recovery = get_recovery(error_type)
        if recovery.action not in ("retry", "rephrase"):
            return False

        attempts = self._attempt_counts.get(error_type, 0)
        return attempts < recovery.max_retries

    def record_attempt(self, error_type: ErrorType) -> None:
        """记录一次重试尝试。

        Args:
            error_type: 错误类型。
        """
        self._attempt_counts[error_type] = self._attempt_counts.get(error_type, 0) + 1

    def reset(self) -> None:
        """重置所有重试计数。"""
        self._attempt_counts.clear()

    def get_feedback_message(self, error_type: ErrorType, detail: str = "") -> str:
        """生成返回给 LLM 的错误反馈消息。

        Args:
            error_type: 错误类型。
            detail: 错误详情。

        Returns:
            格式化的反馈消息。
        """
        recovery = get_recovery(error_type)
        msg = recovery.message
        if "{delay}" in msg:
            msg = msg.format(delay=self.get_delay(error_type))
        if "{detail}" in msg:
            msg = msg.format(detail=detail[:200])
        return msg
