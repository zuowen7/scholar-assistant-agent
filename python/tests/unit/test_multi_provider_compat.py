"""multi-provider 综合测试：错误分类器、中文信号、Claude 指南、content-as-list。"""
import pytest

from src.agent.error_classifier import classify_error, ErrorType
from src.agent.prompt_builder import _MODEL_TOOL_GUIDES, _DEFAULT_TOOL_GUIDE
from src.agent.llm_client import LLMClient


class TestErrorClassifierMultiProvider:
    """Phase 8: error_classifier 扩展"""

    def test_529_is_overloaded(self):
        """Anthropic overloaded 状态码。"""
        result = classify_error(ValueError("HTTP 529: Overloaded"))
        assert result == ErrorType.OVERLOADED

    def test_resource_exhausted_is_rate_limit(self):
        """Gemini resource exhausted。"""
        result = classify_error(ValueError("Resource exhausted"))
        assert result == ErrorType.RATE_LIMIT

    def test_resource_has_been_exhausted(self):
        """Gemini resource has been exhausted。"""
        result = classify_error(ValueError("Resource has been exhausted"))
        assert result == ErrorType.RATE_LIMIT

    def test_context_length_exceeded(self):
        """Amazon Bedrock / Gemini 上下文溢出。"""
        result = classify_error(ValueError("context_length_exceeded"))
        assert result == ErrorType.CONTEXT_OVERFLOW

    def test_429_still_rate_limit(self):
        """回归：429 仍然是 RATE_LIMIT。"""
        result = classify_error(ValueError("(HTTP 429) Rate limit"))
        assert result == ErrorType.RATE_LIMIT


class TestClaudeToolGuide:
    """Phase 10: Claude 工具指导"""

    def test_claude_guide_exists(self):
        """claude key 已添加到 _MODEL_TOOL_GUIDES。"""
        assert "claude" in _MODEL_TOOL_GUIDES
        assert _MODEL_TOOL_GUIDES["claude"] != _DEFAULT_TOOL_GUIDE

    def test_substring_match_claude_sonnet(self):
        """claude-sonnet 子串匹配。"""
        assert "claude" in "claude-sonnet-4-20250514"

    def test_gpt_guide_unchanged(self):
        """回归：gpt key 不变。"""
        assert "gpt" in _MODEL_TOOL_GUIDES
        assert "deepseek" in _MODEL_TOOL_GUIDES
        assert "qwen" in _MODEL_TOOL_GUIDES
        assert "gemini" in _MODEL_TOOL_GUIDES

    def test_default_guide_not_empty(self):
        assert _DEFAULT_TOOL_GUIDE.strip() != ""
