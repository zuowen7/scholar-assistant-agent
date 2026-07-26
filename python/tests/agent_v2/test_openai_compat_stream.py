"""Regression tests for OpenAI-compatible streaming failures."""

from __future__ import annotations

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
