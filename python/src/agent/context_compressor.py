"""比例阈值上下文压缩器 — Agent 子系统的上下文管理核心。

取代原有的滑动窗口裁剪策略，采用 Hermes/GA 风格的比例阈值压缩：
- 按上下文占模型窗口的比例触发压缩（默认 50%），而非固定 token 数
- 头部保护：system prompt + 首轮任务定义（绝不被压缩）
- 尾部保护：最近 N 轮对话（承载最终结论和短期记忆）
- 中间压缩：将冗长的中间步骤替换为 LLM 生成的精炼摘要

设计参考：
- Hermes Agent 的 context_compressor.py（比例阈值 + 头尾保护 + 中间摘要）
- Generic Agent 的"上下文信息密度最大化"原则
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.agent.llm_client import LLMClient
from src.agent.models import Message, message_to_ollama_dict

logger = logging.getLogger(__name__)

# 估算 token 的字符系数：英文 ~4 chars/token, 中文 ~1.5, 混合取 2.5
_CHARS_PER_TOKEN: float = 2.5


@dataclass
class CompressionResult:
    """压缩操作的结果。

    Attributes:
        messages: 压缩后的消息列表。
        original_count: 压缩前的消息条数。
        compressed_count: 压缩后的消息条数。
        original_tokens: 压缩前的估算 token 数。
        compressed_tokens: 压缩后的估算 token 数。
        was_compressed: 是否实际执行了压缩。
        summary: 中间区域生成的摘要文本（未压缩时为空）。
    """

    messages: list[dict]
    original_count: int = 0
    compressed_count: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0
    was_compressed: bool = False
    summary: str = ""


class ContextCompressor:
    """比例阈值上下文压缩器。

    核心思想：不关注具体的 token 绝对数量，而是监控当前上下文
    占用总窗口容量的比例。无论底层是 32K 的 Qwen3:8B 还是 128K
    的云端 API，都能根据"健康度"灵活决定何时压缩。

    压缩流程：
    1. 计算当前上下文 token 数
    2. 若未超过 threshold_percent × max_window_tokens，直接返回
    3. 划分三个区域：头部保护区 / 中间压缩区 / 尾部保护区
    4. 对中间区域生成摘要（调用 LLM 或简单截断）
    5. 拼接：头部 + [摘要] + 尾部

    Attributes:
        max_window_tokens: 模型的最大上下文窗口 token 数。
        threshold_percent: 触发压缩的比例阈值（0.0 ~ 1.0）。
        protect_head_count: 头部保护的消息条数。
        protect_tail_turns: 尾部保护的对话轮数。
        summary_max_tokens: 摘要的目标 token 预算。
        ollama_base_url: Ollama API 地址（用于 LLM 摘要生成）。
        summary_model: 用于生成摘要的模型名称（Ollama 本地模型名）。
        cloud_base_url: 云端 API 地址（优先于 Ollama）。
        cloud_api_key: 云端 API Key。
        cloud_model: 云端模型名。
    """

    def __init__(
        self,
        max_window_tokens: int = 32_000,
        threshold_percent: float = 0.50,
        protect_head_count: int = 1,
        protect_tail_turns: int = 4,
        summary_max_tokens: int = 500,
        ollama_base_url: str = "http://localhost:11434",
        summary_model: str | None = None,
        cloud_base_url: str = "",
        cloud_api_key: str = "",
        cloud_model: str = "",
    ) -> None:
        self.max_window_tokens = max_window_tokens
        self.threshold_percent = threshold_percent
        self.protect_head_count = protect_head_count
        self.protect_tail_turns = protect_tail_turns
        self.summary_max_tokens = summary_max_tokens
        self.summary_model = summary_model

        self._llm = LLMClient(
            ollama_base_url=ollama_base_url,
            model=summary_model or "qwen3:8b",
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
            temperature=0.1,
            num_predict=summary_max_tokens,
        )

    async def close(self) -> None:
        await self._llm.close()

    # ------------------------------------------------------------------
    # Token 估算
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(messages: list[dict | Message]) -> int:
        """粗略估算消息列表的总 token 数。

        Args:
            messages: 消息列表（dict 或 Message 均可）。

        Returns:
            估算的总 token 数。
        """
        total_chars = 0
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                # 工具调用参数也计入
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    content += json.dumps(func.get("arguments", {}), ensure_ascii=False)
            elif hasattr(msg, "content"):
                content = msg.content or ""
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        content += json.dumps(tc.arguments, ensure_ascii=False)
            else:
                content = str(msg)
            total_chars += len(content)
            total_chars += 4  # 元数据开销

        return max(1, int(total_chars / _CHARS_PER_TOKEN))

    # ------------------------------------------------------------------
    # 压缩主逻辑
    # ------------------------------------------------------------------

    def should_compress(self, messages: list[dict | Message]) -> bool:
        """判断是否需要压缩。

        Args:
            messages: 当前消息列表。

        Returns:
            True 表示需要压缩。
        """
        current_tokens = self.estimate_tokens(messages)
        threshold = int(self.max_window_tokens * self.threshold_percent)
        return current_tokens >= threshold

    async def compress(self, messages: list[dict]) -> CompressionResult:
        """执行上下文压缩。

        Args:
            messages: Ollama 格式的消息字典列表。

        Returns:
            CompressionResult 包含压缩后的消息和统计信息。
        """
        original_tokens = self.estimate_tokens(messages)

        if not self.should_compress(messages):
            return CompressionResult(
                messages=messages,
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                was_compressed=False,
            )

        logger.info(
            "上下文压缩触发: %d tokens >= %d (%.0f%% of %d)",
            original_tokens,
            int(self.max_window_tokens * self.threshold_percent),
            self.threshold_percent * 100,
            self.max_window_tokens,
        )

        # 划分区域
        head, middle, tail = self._partition(messages)

        if not middle:
            # 没有中间区域可压缩（消息条数太少），直接返回
            return CompressionResult(
                messages=messages,
                original_count=len(messages),
                compressed_count=len(messages),
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                was_compressed=False,
            )

        # 对中间区域生成摘要
        summary = await self._summarize_middle(middle)

        # 构造摘要消息
        summary_msg: dict[str, str] = {
            "role": "system",
            "content": f"[CONTEXT SUMMARY]: {summary}",
        }

        # 拼接：头部 + 摘要 + 尾部
        compressed = head + [summary_msg] + tail

        compressed_tokens = self.estimate_tokens(compressed)

        logger.info(
            "上下文压缩完成: %d → %d 条消息, %d → %d tokens (节省 %d%%)",
            len(messages),
            len(compressed),
            original_tokens,
            compressed_tokens,
            int((1 - compressed_tokens / original_tokens) * 100) if original_tokens > 0 else 0,
        )

        return CompressionResult(
            messages=compressed,
            original_count=len(messages),
            compressed_count=len(compressed),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            was_compressed=True,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # 区域划分
    # ------------------------------------------------------------------

    def _partition(self, messages: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
        """将消息列表划分为头部/中间/尾部三个区域。

        划分策略：
        - 头部：前 protect_head_count 条消息（system prompt 等）
        - 尾部：最后 protect_tail_turns * 2 条消息（每轮约 2 条：user + assistant/tool）
        - 中间：剩余的消息

        Args:
            messages: 消息列表。

        Returns:
            (head, middle, tail) 三元组。
        """
        total = len(messages)
        head_end = min(self.protect_head_count, total)

        # 尾部按轮数计算（每轮约 2 条消息）
        tail_count = min(self.protect_tail_turns * 2, total - head_end)
        tail_start = total - tail_count

        if tail_start <= head_end:
            return messages, [], []

        # Never split assistant(tool_calls) -> tool pairs across the
        # middle/tail boundary.  OpenAI / DeepSeek reject a tool message
        # that is not immediately preceded by an assistant with tool_calls.
        while tail_start > head_end and messages[tail_start].get("role") == "tool":
            tail_start -= 1

        head = messages[:head_end]
        middle = messages[head_end:tail_start]
        tail = messages[tail_start:]

        return head, middle, tail

    # ------------------------------------------------------------------
    # 中间区域摘要
    # ------------------------------------------------------------------

    async def _summarize_middle(self, middle: list[dict]) -> str:
        """对中间区域的消息生成摘要。

        优先使用 LLM 生成高质量摘要；若 LLM 不可用则降级为关键信息提取。

        Args:
            middle: 中间区域的消息列表。

        Returns:
            摘要文本。
        """
        # 将中间消息格式化为文本
        middle_text = self._format_middle_for_summary(middle)

        # 尝试 LLM 摘要
        if self.summary_model:
            summary = await self._llm_summarize(middle_text)
            if summary:
                return summary

        # 降级：提取关键信息（工具调用 + 最终结果）
        return self._extract_key_points(middle)

    def _format_middle_for_summary(self, middle: list[dict]) -> str:
        """将中间区域消息格式化为摘要请求的文本。

        Args:
            middle: 中间区域消息列表。

        Returns:
            格式化后的文本。
        """
        parts: list[str] = []
        for msg in middle:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "assistant":
                # 检查是否有工具调用
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        parts.append(f"调用工具 {func.get('name', '?')} 参数: {json.dumps(func.get('arguments', {}), ensure_ascii=False)[:200]}")
                elif content:
                    parts.append(f"助手: {content[:300]}")

            elif role == "tool":
                parts.append(f"工具结果: {content[:200]}")

            elif role == "user":
                parts.append(f"用户: {content[:200]}")

        return "\n".join(parts)

    async def _llm_summarize(self, text: str) -> str | None:
        """调用 LLM 生成中间区域摘要。

        Args:
            text: 中间区域的格式化文本。

        Returns:
            摘要文本，失败时返回 None。
        """
        if not self.summary_model:
            return None

        prompt = (
            "请用简洁的中文总结以下 Agent 执行过程的中间步骤，"
            "保留关键决策、工具调用结果和重要结论，"
            "省略重复的试错细节。控制在 200 字以内。\n\n"
            f"--- 执行记录 ---\n{text}\n--- 结束 ---"
        )

        try:
            return await self._llm.call_simple([Message(role="user", content=prompt)])
        except Exception as e:
            logger.warning("LLM 摘要生成失败，降级为关键信息提取: %s", e)
            return None

    def _extract_key_points(self, middle: list[dict]) -> str:
        """降级摘要策略：从中间区域提取关键信息点。

        提取规则：
        - 保留每个工具调用的名称和简要结果
        - 保留助手的最终结论性陈述
        - 跳过冗余的中间推理过程

        Args:
            middle: 中间区域消息列表。

        Returns:
            关键信息摘要。
        """
        points: list[str] = []

        for msg in middle:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "tool" and content:
                # 工具结果：截取前 150 字符
                points.append(f"- 工具返回: {content[:150]}{'...' if len(content) > 150 else ''}")

            elif role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "?")
                    args_str = json.dumps(func.get("arguments", {}), ensure_ascii=False)[:100]
                    points.append(f"- 调用 {name}({args_str})")

        if not points:
            return "（中间过程无可提取的关键信息）"

        summary = "执行摘要: " + "; ".join(points)
        # 最终截断
        max_chars = self.summary_max_tokens * int(_CHARS_PER_TOKEN)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "..."
        return summary
