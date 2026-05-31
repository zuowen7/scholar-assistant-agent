"""call_simple_sync Anthropic 路径测试。

验证当 api_format="anthropic" 时：
- URL 指向 /v1/messages
- 使用 x-api-key 认证（非 Bearer）
- 多 text block 响应正确拼接
- 空 content 返回兜底文本
- OpenAI/Ollama 路径不受影响
"""
import json
from unittest.mock import MagicMock, patch, call

import pytest

from src.agent.llm_client import LLMClient
from src.agent.models import Message


def _make_anthropic_client() -> LLMClient:
    return LLMClient(
        cloud_base_url="https://api.anthropic.com",
        cloud_api_key="sk-ant-test",
        cloud_model="claude-sonnet-4-20250514",
        api_format="anthropic",
    )


def _make_openai_client() -> LLMClient:
    return LLMClient(
        cloud_base_url="https://api.openai.com/v1",
        cloud_api_key="sk-openai-test",
        cloud_model="gpt-4o",
        api_format="openai",
    )


def _make_ollama_client() -> LLMClient:
    return LLMClient(
        ollama_base_url="http://localhost:11434",
        model="qwen3:8b",
    )


def _mock_httpx_client_cls(post_return=None):
    """Create a mock httpx.Client class that works as context manager.

    Usage: with httpx.Client(...) as client:
        client.post(...) -> post_return
    """
    mock_instance = MagicMock()
    mock_instance.post.return_value = post_return
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls, mock_instance


class TestCallSimpleSyncAnthropic:
    """H1: call_simple_sync Anthropic 路径"""

    def test_t1_url_points_to_messages(self):
        """URL 使用 /v1/messages 而非 /chat/completions。"""
        client = _make_anthropic_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "hello"}]
        }
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            client.call_simple_sync("test prompt")

        url = mock_inst.post.call_args[0][0]
        assert "/v1/messages" in url
        assert "/chat/completions" not in url

    def test_t2_uses_x_api_key_header(self):
        """使用 x-api-key 认证，不用 Authorization: Bearer。"""
        client = _make_anthropic_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "hello"}]
        }
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            client.call_simple_sync("test")

        headers = mock_inst.post.call_args[1]["headers"]
        assert "x-api-key" in headers
        assert headers["x-api-key"] == "sk-ant-test"
        assert "Authorization" not in headers

    def test_t3_multiple_text_blocks_joined(self):
        """多个 text block 全部拼接。"""
        client = _make_anthropic_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "World"},
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
            ]
        }
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            result = client.call_simple_sync("test")

        assert "Hello" in result
        assert "World" in result

    def test_t4_empty_content_returns_fallback(self):
        """空 content 返回兜底文本。"""
        client = _make_anthropic_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"content": []}
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            result = client.call_simple_sync("test")

        assert "空" in result or "LLM" in result

    def test_t5_openai_format_unaffected(self):
        """OpenAI 格式行为不变（回归）。"""
        client = _make_openai_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "gpt response"}}]
        }
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            result = client.call_simple_sync("test")

        assert result == "gpt response"
        url = mock_inst.post.call_args[0][0]
        assert "/chat/completions" in url

    def test_t6_ollama_format_unaffected(self):
        """Ollama 格式行为不变（回归）。"""
        client = _make_ollama_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": "ollama response"}
        }
        mock_cls, mock_inst = _mock_httpx_client_cls(post_return=mock_resp)

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            result = client.call_simple_sync("test")

        assert result == "ollama response"
        url = mock_inst.post.call_args[0][0]
        assert "/api/chat" in url

    def test_t7_anthropic_exception_returns_error_string(self):
        """Anthropic 异常返回错误字符串而不抛出。"""
        client = _make_anthropic_client()
        mock_cls, mock_inst = _mock_httpx_client_cls()
        mock_inst.post.side_effect = Exception("connection failed")

        with patch("src.agent.llm_client.httpx.Client", mock_cls):
            result = client.call_simple_sync("test")

        assert "LLM" in result or "失败" in result or "connection" in result
