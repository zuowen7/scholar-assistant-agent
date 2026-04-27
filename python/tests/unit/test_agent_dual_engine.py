"""Agent 双引擎测试 — Ollama / Cloud 路由与格式适配。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.agent import AgentLoop
from src.agent.llm_client import LLMClient, extract_tool_calls
from src.agent.models import Message, ToolCall


def _make_ollama_response(content: str = "", tool_calls: list | None = None) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls,
        },
    }


def _make_openai_response(content: str = "", tool_calls: list | None = None) -> dict:
    openai_tool_calls = []
    if tool_calls:
        for tc in tool_calls:
            func = tc.get("function", {})
            openai_tool_calls.append({
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": json.dumps(func.get("arguments", {})),
                },
            })
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": openai_tool_calls or None,
                },
            },
        ],
    }


class TestAgentDualEngine:

    def test_default_is_ollama(self):
        agent = AgentLoop()
        assert agent.llm.use_cloud is False
        assert agent.cloud_base_url == ""
        assert agent.cloud_api_key == ""

    def test_cloud_mode_when_credentials_provided(self):
        agent = AgentLoop(
            cloud_base_url="https://api.openai.com/v1",
            cloud_api_key="sk-test",
            cloud_model="gpt-4o",
        )
        assert agent.llm.use_cloud is True
        assert agent.cloud_base_url == "https://api.openai.com/v1"
        assert agent.cloud_api_key == "sk-test"

    @pytest.mark.anyio
    async def test_call_ollama(self):
        client = LLMClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_ollama_response("你好")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http_client = mock_http

        result = await client.call([Message(role="user", content="hi")])
        assert result["message"]["content"] == "你好"

    @pytest.mark.anyio
    async def test_call_cloud_routes_to_openai_endpoint(self):
        client = LLMClient(
            cloud_base_url="https://api.openai.com/v1",
            cloud_api_key="sk-test",
            cloud_model="gpt-4o",
            model="gpt-4o",
        )

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_openai_response("Hello!")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http_client = mock_http

        result = await client.call([Message(role="user", content="hi")])

        call_args = mock_http.post.call_args
        assert "chat/completions" in call_args[0][0]
        assert "Bearer sk-test" in str(call_args[1]["headers"])
        assert result["message"]["content"] == "Hello!"

    @pytest.mark.anyio
    async def test_cloud_tool_calls_normalized(self):
        client = LLMClient(
            cloud_base_url="https://api.openai.com/v1",
            cloud_api_key="sk-test",
            cloud_model="gpt-4o",
            model="gpt-4o",
        )

        ollama_tc = [{"function": {"name": "translate_text", "arguments": {"text": "hello"}}}]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_openai_response("", ollama_tc)
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http_client = mock_http

        result = await client.call([Message(role="user", content="翻译")])

        tc_list = result["message"]["tool_calls"]
        assert len(tc_list) == 1
        assert tc_list[0]["function"]["name"] == "translate_text"
        assert tc_list[0]["function"]["arguments"]["text"] == "hello"

    def test_extract_tool_calls_works_with_cloud_response(self):
        ollama_tc = [{"function": {"name": "crawl_arxiv", "arguments": {"query": "AI"}}}]
        normalized = _make_ollama_response("thinking...", ollama_tc)

        tool_calls = extract_tool_calls(normalized)
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "crawl_arxiv"
        assert tool_calls[0].arguments == {"query": "AI"}
