"""Native Ollama provider regression tests."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agent_v2.providers.ollama import OllamaProvider
from src.agent_v2.types import (
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    TokenUsage,
    ToolDefinition,
    ToolUseBlock,
)


def _messages() -> list[Message]:
    return [Message(role=MessageRole.USER, blocks=[TextBlock(text="Use the tool")])]


def _tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="read_file",
            description="Read a file",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_native_chat_sends_context_length_and_parses_tool_call():
    request_body: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "read_file", "arguments": {"path": "main.md"}}}
                    ],
                },
                "done": True,
                "prompt_eval_count": 123,
                "eval_count": 7,
            },
        )

    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3:8b",
        context_length=32_768,
        thinking_mode="disabled",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    response = await provider.chat(_messages(), tools=_tools())

    assert request_body["options"]["num_ctx"] == 32_768
    assert request_body["think"] is False
    assert request_body["tools"][0]["function"]["name"] == "read_file"
    assert response.stop_reason == "tool_use"
    assert response.usage.input_tokens == 123
    call = next(block for block in response.blocks if isinstance(block, ToolUseBlock))
    assert call.name == "read_file"
    assert json.loads(call.input) == {"path": "main.md"}
    await provider.close()


@pytest.mark.asyncio
async def test_native_stream_yields_text_tool_usage_and_terminal_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        return httpx.Response(
            200,
            text=(
                '{"message":{"role":"assistant","content":"checking"},"done":false}\n'
                '{"message":{"role":"assistant","content":"","tool_calls":'
                '[{"function":{"name":"read_file","arguments":{"path":"main.md"}}}]},'
                '"done":true,"prompt_eval_count":55,"eval_count":4}\n'
            ),
        )

    provider = OllamaProvider(model="qwen3:8b", context_length=16_384)
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    chunks = [chunk async for chunk in provider.chat_stream(_messages(), tools=_tools())]

    assert any(isinstance(chunk, TextBlock) and chunk.text == "checking" for chunk in chunks)
    assert any(isinstance(chunk, ToolUseBlock) and chunk.name == "read_file" for chunk in chunks)
    assert any(isinstance(chunk, TokenUsage) and chunk.input_tokens == 55 for chunk in chunks)
    terminal = next(chunk for chunk in chunks if isinstance(chunk, ProviderResponse))
    assert terminal.stop_reason == "tool_use"
    await provider.close()
