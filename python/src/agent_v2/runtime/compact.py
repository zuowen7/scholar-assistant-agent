"""上下文压缩 — token 超阈值时压缩旧消息为摘要。

参考 claw-code runtime/compact.rs:
  - compact_session: 将旧消息压缩为摘要
  - estimate_session_tokens: 估算 token 数量
  - should_compact: 判断是否需要压缩
"""
from __future__ import annotations

from src.agent_v2.types import Message, MessageRole, TextBlock, TokenUsage


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数。英文约 char/4，中文约 char/2。"""
    if not text:
        return 0
    chars = len(text)
    # Count CJK characters (U+4E00-U+9FFF, U+3400-U+4DBF)
    cjk = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
    ascii_chars = chars - cjk
    return ascii_chars // 4 + cjk // 2


def estimate_session_tokens(messages: list[Message]) -> int:
    """估算会话总 token 数。"""
    total = 0
    for msg in messages:
        for block in msg.blocks:
            if isinstance(block, TextBlock):
                total += estimate_tokens(block.text)
        if msg.usage:
            total += msg.usage.total()
    return total


def should_compact(messages: list[Message], threshold: int = 950_000) -> bool:
    """是否需要压缩。"""
    return estimate_session_tokens(messages) >= threshold


def compact_session(
    messages: list[Message],
    threshold: int = 100_000,
    keep_last: int = 6,
) -> list[Message]:
    """压缩会话 — 保留最近 N 条消息，旧消息合并为系统摘要。

    参考 claw-code compact.rs compact_session:
      - 计算需要压缩的消息数
      - 生成摘要消息
      - 返回精简后的消息列表
    """
    if not should_compact(messages, threshold):
        return messages

    total = len(messages)
    if total <= keep_last:
        return messages

    split_at = total - keep_last
    old = messages[:split_at]
    recent = messages[split_at:]

    summary = _build_summary(old)
    return [summary] + recent


def _build_summary(messages: list[Message]) -> Message:
    """将旧消息压缩为一个系统摘要。"""
    parts = ["[Conversation summary — earlier messages compressed]"]

    user_msgs = 0
    assistant_msgs = 0
    tool_calls = 0
    topics = set()

    for msg in messages:
        if msg.role == MessageRole.USER:
            user_msgs += 1
            text = msg.text_content().strip()
            if text:
                # Extract first sentence as topic hint
                first = text.split(".")[0].split("。")[0].split("\n")[0]
                if len(first) < 100:
                    topics.add(first)
        elif msg.role == MessageRole.ASSISTANT:
            assistant_msgs += 1
            for block in msg.blocks:
                from src.agent_v2.types import ToolUseBlock
                if isinstance(block, ToolUseBlock):
                    tool_calls += 1

    parts.append(f"User messages: {user_msgs}, Assistant messages: {assistant_msgs}, Tool calls: {tool_calls}")

    if topics:
        parts.append("Topics discussed: " + "; ".join(sorted(topics)[:10]))

    parts.append("[End of summary]")

    return Message(role=MessageRole.SYSTEM, blocks=[TextBlock(text="\n".join(parts))])


class CompactionConfig:
    """压缩配置。"""
    def __init__(self, input_token_threshold: int = 950_000, keep_last_messages: int = 8):
        self.input_token_threshold = input_token_threshold
        self.keep_last_messages = keep_last_messages
