"""MockProvider 测试 — MP-001 ~ MP-033。

全部使用 MockProvider（确定性），不依赖网络，毫秒级完成。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src.agent_v2.providers.mock_provider import MockProvider, Scenario, _text_response, _tool_response
from src.agent_v2.types import (
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from tests.agent_v2.conftest import make_user_message


# ============================================================================
# 1.1 基础场景 (Happy Path)
# ============================================================================

class TestBasicScenarios:

    @pytest.mark.asyncio
    async def test_mp001_text_reply(self, mock_provider: MockProvider):
        """MP-001: 纯文本回复"""
        messages = [make_user_message("hello")]
        resp = await mock_provider.chat(messages)
        assert len(resp.blocks) == 1
        assert isinstance(resp.blocks[0], TextBlock)
        assert resp.blocks[0].text == "Hello! How can I help you today?"
        assert not resp.has_tool_calls()

    @pytest.mark.asyncio
    async def test_mp002_single_tool_call(self, mock_provider: MockProvider):
        """MP-002: 单工具调用"""
        messages = [make_user_message("read the file")]
        resp = await mock_provider.chat(messages)
        assert resp.has_tool_calls()
        tc = resp.tool_calls()
        assert len(tc) == 1
        assert tc[0].name == "read_file"
        inp = json.loads(tc[0].input)
        assert inp["file_path"] == "main.md"

    @pytest.mark.asyncio
    async def test_mp003_multi_tool_call(self, mock_provider: MockProvider):
        """MP-003: 多工具并行调用"""
        messages = [make_user_message("read both files")]
        resp = await mock_provider.chat(messages)
        tc = resp.tool_calls()
        assert len(tc) == 2
        assert tc[0].name == "read_file"
        assert tc[1].name == "read_file"
        assert tc[0].id != tc[1].id  # 独立 id

    @pytest.mark.asyncio
    async def test_mp004_thinking_then_text(self, mock_provider: MockProvider):
        """MP-004: 思考 + 文本"""
        messages = [make_user_message("explain this")]
        resp = await mock_provider.chat(messages)
        assert len(resp.blocks) == 2
        assert isinstance(resp.blocks[0], ThinkingBlock)
        assert isinstance(resp.blocks[1], TextBlock)
        assert "think" in resp.blocks[0].thinking.lower()

    @pytest.mark.asyncio
    async def test_mp005_thinking_then_tool(self, mock_provider: MockProvider):
        """MP-005: 思考 + 工具调用"""
        messages = [make_user_message("analyze this")]
        resp = await mock_provider.chat(messages)
        assert len(resp.blocks) == 2
        assert isinstance(resp.blocks[0], ThinkingBlock)
        assert isinstance(resp.blocks[1], ToolUseBlock)
        assert resp.blocks[1].name == "read_file"


# ============================================================================
# 1.2 多轮对话场景
# ============================================================================

class TestMultiTurnScenarios:

    @pytest.mark.asyncio
    async def test_mp010_read_then_summarize(self, mock_provider: MockProvider):
        """MP-010: read_file → 回复摘要"""
        messages = [make_user_message("read and summarize the file")]
        # Turn 0: tool call
        resp0 = await mock_provider.chat(messages)
        assert resp0.has_tool_calls()
        tc = resp0.tool_calls()[0]
        assert tc.name == "read_file"

        # 模拟 tool_result 追加
        from src.agent_v2.types import ToolResultBlock
        messages.append(Message(role=MessageRole.ASSISTANT, blocks=resp0.blocks))
        messages.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id=tc.id, tool_name="read_file", output="file content here")
        ]))

        # Turn 1: 文本摘要
        resp1 = await mock_provider.chat(messages)
        assert not resp1.has_tool_calls()
        assert "summary" in resp1.text_content().lower()

    @pytest.mark.asyncio
    async def test_mp012_three_step_chain(self, mock_provider: MockProvider):
        """MP-012: 3 轮工具链 read → grep → str_replace"""
        messages = [make_user_message("find and fix the TODO")]

        # Turn 0: read_file
        resp0 = await mock_provider.chat(messages)
        assert resp0.tool_calls()[0].name == "read_file"

        # Turn 1: grep
        from src.agent_v2.types import ToolResultBlock
        tc0 = resp0.tool_calls()[0]
        messages.append(Message(role=MessageRole.ASSISTANT, blocks=resp0.blocks))
        messages.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id=tc0.id, tool_name="read_file", output="file content")
        ]))
        resp1 = await mock_provider.chat(messages)
        assert resp1.tool_calls()[0].name == "grep_files"

        # Turn 2: str_replace
        tc1 = resp1.tool_calls()[0]
        messages.append(Message(role=MessageRole.ASSISTANT, blocks=resp1.blocks))
        messages.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id=tc1.id, tool_name="grep_files", output="main.py:3:    # TODO: fix")
        ]))
        resp2 = await mock_provider.chat(messages)
        assert resp2.tool_calls()[0].name == "str_replace"

    @pytest.mark.asyncio
    async def test_mp013_max_steps_terminates(self):
        """MP-013: 超过 max_steps 后应被 ConversationRuntime 终止。
        这里只验证 MockProvider 的 turn counter 正常递增。"""
        provider = MockProvider(scenarios=[
            Scenario(name="always_tool", trigger_patterns=[],
                     response_factory=lambda msgs, turn: _tool_response("read_file", {"file_path": "loop.txt"})),
        ])
        for i in range(20):
            resp = await provider.chat([make_user_message("keep going")])
            assert resp.has_tool_calls()
        assert provider.turn_counter == 20


# ============================================================================
# 1.3 边缘测试
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_mp020_empty_message(self, mock_provider: MockProvider):
        """MP-020: 空字符串消息不崩溃"""
        messages = [make_user_message("")]
        resp = await mock_provider.chat(messages)
        assert isinstance(resp.blocks[0], TextBlock)

    @pytest.mark.asyncio
    async def test_mp021_very_long_message(self, mock_provider: MockProvider):
        """MP-021: 100K 字符消息不崩溃"""
        messages = [make_user_message("x" * 100_000)]
        resp = await mock_provider.chat(messages)
        assert len(resp.blocks) > 0

    @pytest.mark.asyncio
    async def test_mp022_special_characters(self, mock_provider: MockProvider):
        """MP-022: 特殊字符消息不崩溃"""
        messages = [make_user_message("test \x00 null \U0001f600 emoji 中文 العربية")]
        resp = await mock_provider.chat(messages)
        assert len(resp.blocks) > 0

    @pytest.mark.asyncio
    async def test_mp023_concurrent_requests(self, mock_provider: MockProvider):
        """MP-023: 并发请求各自返回正确响应"""
        async def single_call(text: str):
            return await mock_provider.chat([make_user_message(text)])

        results = await asyncio.gather(*[single_call("hello") for _ in range(10)])
        for resp in results:
            assert isinstance(resp.blocks[0], TextBlock)
        assert mock_provider.turn_counter == 10

    @pytest.mark.asyncio
    async def test_mp024_unmatched_scenario_returns_default(self, mock_provider: MockProvider):
        """MP-024: 无匹配场景时返回默认文本回复"""
        messages = [make_user_message("xyzzy_no_match_12345")]
        resp = await mock_provider.chat(messages)
        assert isinstance(resp.blocks[0], TextBlock)
        assert resp.text_content() == mock_provider.default_response


# ============================================================================
# 1.4 故障注入
# ============================================================================

class TestFaultInjection:

    @pytest.mark.asyncio
    async def test_mp030_simulated_timeout(self):
        """MP-030: 模拟超时 — provider.chat() 在 delay 后返回"""
        provider = MockProvider(delay_seconds=0.1)
        resp = await provider.chat([make_user_message("hello")])
        assert isinstance(resp.blocks[0], TextBlock)

    @pytest.mark.asyncio
    async def test_mp031_simulated_500_error(self):
        """MP-031: 模拟 500 错误"""
        provider = MockProvider(error_on_turn={0: ApiError("Internal Server Error", status_code=500)})
        with pytest.raises(ApiError) as exc_info:
            await provider.chat([make_user_message("hello")])
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_mp031b_error_on_specific_turn(self):
        """MP-031b: 第 2 轮出错"""
        provider = MockProvider(error_on_turn={1: ApiError("fail on turn 1", status_code=500)})
        # Turn 0 成功
        resp0 = await provider.chat([make_user_message("hello")])
        assert isinstance(resp0.blocks[0], TextBlock)
        # Turn 1 失败
        with pytest.raises(ApiError):
            await provider.chat([make_user_message("hello")])

    @pytest.mark.asyncio
    async def test_mp033_rate_limit(self):
        """MP-033: 模拟 rate limit (429)"""
        provider = MockProvider(error_on_turn={0: ApiError("Rate limited", status_code=429, retry_after=2.0)})
        with pytest.raises(ApiError) as exc_info:
            await provider.chat([make_user_message("hello")])
        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 2.0


# ============================================================================
# 类型系统辅助测试
# ============================================================================

class TestProviderResponseHelpers:

    def test_has_tool_calls_true(self):
        resp = ProviderResponse(blocks=[ToolUseBlock(id="1", name="read_file", input="{}")])
        assert resp.has_tool_calls()

    def test_has_tool_calls_false(self):
        resp = ProviderResponse(blocks=[TextBlock(text="hello")])
        assert not resp.has_tool_calls()

    def test_text_content(self):
        resp = ProviderResponse(blocks=[TextBlock(text="hello "), TextBlock(text="world")])
        assert resp.text_content() == "hello world"

    def test_tool_calls_extracts_only_tool_use(self):
        resp = ProviderResponse(blocks=[
            TextBlock(text="thinking..."),
            ToolUseBlock(id="1", name="read_file", input="{}"),
            ToolUseBlock(id="2", name="write_file", input="{}"),
        ])
        tc = resp.tool_calls()
        assert len(tc) == 2
        assert tc[0].name == "read_file"
        assert tc[1].name == "write_file"

    def test_stop_reason(self):
        resp = ProviderResponse(stop_reason="tool_use")
        assert resp.stop_reason == "tool_use"

    def test_usage_default(self):
        from src.agent_v2.types import TokenUsage
        resp = ProviderResponse()
        assert resp.usage == TokenUsage()
