"""ContextCompressor 单元测试。

覆盖范围：
- token 估算（dict 和 Message 两种输入）
- should_compress 判断逻辑
- _partition 区域划分（头部/中间/尾部）
- _extract_key_points 降级摘要
- compress 完整流程（未触发/触发/消息过少）
- LLM 摘要 mock 验证
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.context_compressor import (
    CompressionResult,
    ContextCompressor,
    _CHARS_PER_TOKEN,
)
from src.agent.models import Message, ToolCall


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_messages(n: int, chars_per_msg: int = 200) -> list[dict]:
    """生成 n 条测试消息，每条约 chars_per_msg 字符。"""
    msgs: list[dict] = [{"role": "system", "content": "你是助手"}]
    for i in range(n - 1):
        msgs.append({"role": "user", "content": f"消息{i}: " + "x" * chars_per_msg})
    return msgs


def _run(coro):
    """在同步测试中运行异步协程。"""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Token 估算
# ---------------------------------------------------------------------------

class TestEstimateTokens:

    def test_dict_input(self):
        msgs = [
            {"role": "system", "content": "hello"},
            {"role": "user", "content": "world"},
        ]
        tokens = ContextCompressor.estimate_tokens(msgs)
        assert tokens > 0
        expected = max(1, int((5 + 5 + 4 * 2) / _CHARS_PER_TOKEN))
        assert tokens == expected

    def test_message_input(self):
        msgs = [
            Message(role="user", content="test content here"),
        ]
        tokens = ContextCompressor.estimate_tokens(msgs)
        assert tokens > 0

    def test_empty_messages(self):
        tokens = ContextCompressor.estimate_tokens([])
        assert tokens >= 1

    def test_tool_calls_included(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "test", "arguments": {"key": "a" * 100}}}
                ],
            }
        ]
        tokens = ContextCompressor.estimate_tokens(msgs)
        assert tokens > 0

    def test_message_with_tool_calls(self):
        msgs = [
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="1", name="test", arguments={"key": "value"})],
            )
        ]
        tokens = ContextCompressor.estimate_tokens(msgs)
        assert tokens > 0


# ---------------------------------------------------------------------------
# should_compress
# ---------------------------------------------------------------------------

class TestShouldCompress:

    def test_below_threshold(self):
        comp = ContextCompressor(max_window_tokens=1000, threshold_percent=0.50)
        msgs = [{"role": "system", "content": "short"}]
        assert comp.should_compress(msgs) is False

    def test_above_threshold(self):
        comp = ContextCompressor(max_window_tokens=100, threshold_percent=0.50)
        # 生成足够长的消息触发阈值
        msgs = _make_messages(20, chars_per_msg=200)
        assert comp.should_compress(msgs) is True

    def test_exact_threshold(self):
        comp = ContextCompressor(max_window_tokens=1000, threshold_percent=0.50)
        # 精确构造刚好达到阈值的消息
        target_chars = int(500 * _CHARS_PER_TOKEN)
        msgs = [{"role": "system", "content": "x" * target_chars}]
        assert comp.should_compress(msgs) is True


# ---------------------------------------------------------------------------
# _partition
# ---------------------------------------------------------------------------

class TestPartition:

    def test_normal_partition(self):
        comp = ContextCompressor(protect_head_count=1, protect_tail_turns=2)
        msgs = _make_messages(10)
        head, middle, tail = comp._partition(msgs)
        assert len(head) == 1
        assert len(tail) == 4  # 2 turns * 2 msgs
        assert len(middle) == 5

    def test_too_few_messages(self):
        comp = ContextCompressor(protect_head_count=1, protect_tail_turns=4)
        msgs = _make_messages(3)
        head, middle, tail = comp._partition(msgs)
        # 消息太少，中间区域为空
        assert len(middle) == 0

    def test_single_message(self):
        comp = ContextCompressor()
        msgs = [{"role": "system", "content": "hello"}]
        head, middle, tail = comp._partition(msgs)
        assert len(middle) == 0

    def test_head_equals_total(self):
        comp = ContextCompressor(protect_head_count=5, protect_tail_turns=1)
        msgs = _make_messages(4)
        head, middle, tail = comp._partition(msgs)
        assert len(middle) == 0


# ---------------------------------------------------------------------------
# _extract_key_points（降级摘要）
# ---------------------------------------------------------------------------

class TestExtractKeyPoints:

    def test_tool_result_extraction(self):
        comp = ContextCompressor()
        middle = [
            {"role": "tool", "content": "翻译结果: Hello World"},
        ]
        result = comp._extract_key_points(middle)
        assert "翻译结果" in result
        assert "工具返回" in result

    def test_tool_call_extraction(self):
        comp = ContextCompressor()
        middle = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "translate_text", "arguments": {"text": "hello"}}}],
            }
        ]
        result = comp._extract_key_points(middle)
        assert "translate_text" in result

    def test_empty_middle(self):
        comp = ContextCompressor()
        result = comp._extract_key_points([])
        assert "无" in result

    def test_long_result_truncated(self):
        comp = ContextCompressor(summary_max_tokens=50)
        middle = [
            {"role": "tool", "content": "x" * 5000},
        ]
        result = comp._extract_key_points(middle)
        assert len(result) < 5000


# ---------------------------------------------------------------------------
# compress 完整流程
# ---------------------------------------------------------------------------

class TestCompress:

    @pytest.mark.anyio
    async def test_no_compression_needed(self):
        comp = ContextCompressor(max_window_tokens=10000, threshold_percent=0.50)
        msgs = [{"role": "system", "content": "hello"}]
        result = await comp.compress(msgs)
        assert result.was_compressed is False
        assert len(result.messages) == len(msgs)

    @pytest.mark.anyio
    async def test_compression_triggered(self):
        comp = ContextCompressor(
            max_window_tokens=200,
            threshold_percent=0.50,
            summary_model=None,  # 强制降级摘要
        )
        msgs = _make_messages(30, chars_per_msg=100)
        result = await comp.compress(msgs)
        assert result.was_compressed is True
        assert result.compressed_count < result.original_count
        assert result.compressed_tokens < result.original_tokens
        assert any("[CONTEXT SUMMARY]" in m.get("content", "") for m in result.messages)

    @pytest.mark.anyio
    async def test_too_few_messages_no_compression(self):
        comp = ContextCompressor(
            max_window_tokens=50,
            threshold_percent=0.50,
        )
        msgs = _make_messages(2, chars_per_msg=100)
        result = await comp.compress(msgs)
        assert result.was_compressed is False

    @pytest.mark.anyio
    async def test_compression_preserves_head(self):
        comp = ContextCompressor(
            max_window_tokens=200,
            threshold_percent=0.50,
            protect_head_count=1,
            summary_model=None,
        )
        msgs = _make_messages(20, chars_per_msg=100)
        result = await comp.compress(msgs)
        assert result.messages[0]["role"] == "system"
        assert result.messages[0]["content"] == "你是助手"

    @pytest.mark.anyio
    async def test_compression_preserves_tail(self):
        comp = ContextCompressor(
            max_window_tokens=200,
            threshold_percent=0.50,
            protect_tail_turns=2,
            summary_model=None,
        )
        msgs = _make_messages(20, chars_per_msg=100)
        last_content = msgs[-1]["content"]
        result = await comp.compress(msgs)
        assert result.messages[-1]["content"] == last_content

    @pytest.mark.anyio
    async def test_llm_summary_success(self):
        comp = ContextCompressor(
            max_window_tokens=200,
            threshold_percent=0.50,
            summary_model="test-model",
        )
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"content": "这是LLM生成的摘要"}
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        comp._get_http_client = AsyncMock(return_value=mock_client)

        msgs = _make_messages(20, chars_per_msg=100)
        result = await comp.compress(msgs)
        assert result.was_compressed is True
        assert "这是LLM生成的摘要" in result.summary

    @pytest.mark.anyio
    async def test_llm_failure_fallback(self):
        comp = ContextCompressor(
            max_window_tokens=200,
            threshold_percent=0.50,
            summary_model="test-model",
        )
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("LLM 不可用"))
        comp._get_http_client = AsyncMock(return_value=mock_client)

        msgs = _make_messages(20, chars_per_msg=100)
        result = await comp.compress(msgs)
        assert result.was_compressed is True
        assert len(result.summary) > 0
