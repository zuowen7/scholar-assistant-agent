"""Phase 0 tests: ReAct planning step + scratchpad recovery.

Tests the real AgentLoop.plan(), scratchpad_read(), and _verify_answer().
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# Planning step — unit tests for _parse_plan_result (no LLM call needed)
# ---------------------------------------------------------------------------

class TestPlanParsing:
    """AgentLoop._parse_plan_result() — deterministic JSON parsing."""

    def test_parse_valid_json_with_tools(self, mock_agent):
        """Valid JSON with needs_tools=true."""
        result = mock_agent._parse_plan_result(
            '{"needs_tools": true, "plan": "read file", "tools": ["read_file"]}'
        )
        assert result.needs_tools is True
        assert "read_file" in result.estimated_tools

    def test_parse_valid_json_without_tools(self, mock_agent):
        """Valid JSON with needs_tools=false."""
        result = mock_agent._parse_plan_result(
            '{"needs_tools": false, "plan": "just chat", "tools": []}'
        )
        assert result.needs_tools is False
        assert result.estimated_tools == []

    def test_parse_json_with_think_tags(self, mock_agent):
        """JSON wrapped in <think/> tags (reasoning models)."""
        result = mock_agent._parse_plan_result(
            '<think hmm let me think</think >{"needs_tools": true, "plan": "translate", "tools": ["translate_text"]}'
        )
        assert result.needs_tools is True

    def test_parse_plain_text_true(self, mock_agent):
        """Fallback: plain text containing 'true' or tool-related words."""
        result = mock_agent._parse_plan_result(
            "The user wants to write a file, so needs_tools = true."
        )
        assert result.needs_tools is True

    def test_parse_plain_text_false(self, mock_agent):
        """Fallback: plain text indicating no tools needed."""
        result = mock_agent._parse_plan_result(
            "This is a simple greeting. No tools needed. needs_tools: false"
        )
        assert result.needs_tools is False

    def test_parse_garbage_defaults_to_true(self, mock_agent):
        """Garbage input defaults to needs_tools=True (safe side)."""
        result = mock_agent._parse_plan_result("xyzzy!!!###")
        assert result.needs_tools is True


# ---------------------------------------------------------------------------
# Planning step — integration with mock LLM
# ---------------------------------------------------------------------------

class TestPlanningIntegration:
    """AgentLoop.plan() with mocked LLM client."""

    @pytest.mark.anyio
    async def test_plan_with_tool_intent(self, mock_agent):
        """User wants to write a file → plan returns needs_tools=True."""
        mock_agent.llm.call_simple_sync = MagicMock(return_value=(
            '{"needs_tools": true, "plan": "need to write file", '
            '"tools": ["write_file", "str_replace"]}'
        ))
        result = await mock_agent.plan(
            messages=[_msg("user", "帮我写一个 Python 脚本")],
        )
        assert result.needs_tools is True

    @pytest.mark.anyio
    async def test_plan_without_tool_intent(self, mock_agent):
        """User asks a conceptual question → plan returns needs_tools=False."""
        mock_agent.llm.call_simple_sync = MagicMock(return_value=(
            '{"needs_tools": false, "plan": "direct answer", "tools": []}'
        ))
        result = await mock_agent.plan(
            messages=[_msg("user", "什么是过拟合？")],
        )
        assert result.needs_tools is False

    @pytest.mark.anyio
    async def test_plan_with_ambiguous_intent(self, mock_agent):
        """Ambiguous intent → defaults to needs_tools=True."""
        mock_agent.llm.call_simple_sync = MagicMock(return_value=(
            '{"needs_tools": true, "plan": "may need tools", "tools": ["read_file"]}'
        ))
        result = await mock_agent.plan(
            messages=[_msg("user", "分析一下这段文字")],
        )
        assert result.needs_tools is True

    @pytest.mark.anyio
    async def test_plan_empty_query(self, mock_agent):
        """Empty messages → plan returns needs_tools=False."""
        result = await mock_agent.plan(messages=[])
        assert result.needs_tools is False

    @pytest.mark.anyio
    async def test_plan_llm_failure_safe_default(self, mock_agent):
        """LLM call fails → defaults to needs_tools=True (safe side)."""
        mock_agent.llm.call_simple_sync = MagicMock(side_effect=Exception("LLM down"))
        result = await mock_agent.plan(
            messages=[_msg("user", "翻译")],
        )
        assert result.needs_tools is True


# ---------------------------------------------------------------------------
# Scratchpad recovery
# ---------------------------------------------------------------------------

class TestScratchpad:
    """Scratchpad: write large results → read back via scratchpad_read."""

    def test_write_and_read(self, mock_agent):
        """After storing, reading the same key returns full content."""
        key = "read_file_1"
        content = "x" * 5000
        mock_agent._scratchpad_store(key, content)

        result = mock_agent.scratchpad_read(key)
        assert result == content

    def test_read_nonexistent(self, mock_agent):
        """Reading a key that doesn't exist returns None."""
        result = mock_agent.scratchpad_read("no_such_key")
        assert result is None

    def test_eviction(self, mock_agent):
        """When scratchpad exceeds max_entries, oldest entry is evicted."""
        max_entries = mock_agent._SCRATCHPAD_MAX_ENTRIES  # 32
        first_key = "key_000"
        mock_agent._scratchpad_store(first_key, "first_value")

        for i in range(1, max_entries + 5):
            mock_agent._scratchpad_store(f"key_{i:03d}", f"value_{i}")

        # First key should have been evicted
        assert mock_agent.scratchpad_read(first_key) is None
        assert len(mock_agent._scratchpad) <= max_entries

    def test_truncated_result_recovery(self, mock_agent):
        """A tool result truncated to 2000 chars is recoverable."""
        full_content = "A" * 5000
        key = "large_result"
        mock_agent._scratchpad_store(key, full_content)

        truncated = full_content[:2000] + f"\n...[full result in scratchpad[{key}]]"
        recovered = mock_agent.scratchpad_read(key)

        assert recovered == full_content
        assert len(recovered) > len(truncated)


# ---------------------------------------------------------------------------
# Answer verification
# ---------------------------------------------------------------------------

class TestAnswerVerification:
    """AgentLoop._verify_answer() quality checks."""

    @pytest.mark.anyio
    async def test_empty_answer_rejected(self, mock_agent):
        result = await mock_agent._verify_answer("复杂问题", "")
        assert result.should_retry is True
        assert result.confidence == 0.0

    @pytest.mark.anyio
    async def test_short_answer_for_complex_query(self, mock_agent):
        result = await mock_agent._verify_answer(
            "请详细分析这篇论文的方法论，包括实验设计、统计方法和局限性",
            "方法论不错。",
        )
        assert result.confidence < 0.5

    @pytest.mark.anyio
    async def test_well_structured_answer(self, mock_agent):
        answer = "梯度下降是一种优化算法。" * 20  # ~200 chars
        result = await mock_agent._verify_answer("什么是梯度下降？", answer)
        assert result.confidence > 0.5
        assert result.should_retry is False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _msg(role: str, content: str):
    from src.agent.models import Message
    return Message(role=role, content=content)


@pytest.fixture
def mock_agent():
    """Real AgentLoop with mocked LLM client (no network calls)."""
    from src.agent.agent import AgentLoop

    agent = AgentLoop(
        ollama_base_url="http://localhost:11434",
        model="test-model",
        tool_registry=None,
    )
    return agent
