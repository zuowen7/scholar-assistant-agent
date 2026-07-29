"""Regression tests for OpenAI-compatible streaming failures."""

from __future__ import annotations

import json

import httpx
import pytest

from src.agent_v2.providers.openai_compat import OpenAiCompatProvider
from src.agent_v2.types import ApiError, Message, MessageRole, TextBlock


def _message(text: str = "hello") -> list[Message]:
    return [Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])]


@pytest.mark.asyncio
async def test_stream_http_error_preserves_upstream_message():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(
                b'{"error":{"message":"The supported API model names are '
                b'deepseek-v4-pro or deepseek-v4-flash."}}'
            ),
        )

    provider = OpenAiCompatProvider(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="obsolete-model",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ApiError) as exc_info:
        async for _ in provider.chat_stream(_message()):
            pass

    assert exc_info.value.status_code == 400
    assert "deepseek-v4-flash" in str(exc_info.value)
    assert "ResponseNotRead" not in str(exc_info.value)
    await provider.close()


@pytest.mark.asyncio
async def test_stream_error_payload_is_not_reported_as_empty_response():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"error":{"message":"provider stream failed","code":"bad_request"}}\n\n',
        )

    provider = OpenAiCompatProvider(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="test-model",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(ApiError) as exc_info:
        async for _ in provider.chat_stream(_message()):
            pass

    assert "provider stream failed" in str(exc_info.value)
    await provider.close()


@pytest.mark.asyncio
async def test_deepseek_v4_stream_disables_default_thinking_mode():
    request_body: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=(
                'data: {"choices":[{"delta":{"content":"ready"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    provider = OpenAiCompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async for _ in provider.chat_stream(_message()):
        pass

    assert request_body["thinking"] == {"type": "disabled"}
    await provider.close()


@pytest.mark.asyncio
async def test_deepseek_v4_explicit_thinking_mode_is_respected():
    request_body: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = OpenAiCompatProvider(
        base_url="https://api.deepseek.com/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
        thinking_mode="enabled",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async for _ in provider.chat_stream(_message()):
        pass

    assert request_body["thinking"] == {"type": "enabled"}
    await provider.close()


@pytest.mark.asyncio
async def test_non_deepseek_provider_never_receives_vendor_thinking_field():
    request_body: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body.update(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text='data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    provider = OpenAiCompatProvider(
        base_url="https://api.openai.com/v1",
        api_key="test-key",
        model="gpt-4o",
        thinking_mode="enabled",
    )
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async for _ in provider.chat_stream(_message()):
        pass

    assert "thinking" not in request_body
    await provider.close()
