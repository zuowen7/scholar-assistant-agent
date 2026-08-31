"""Regression tests for the lightweight Argument Companion LLM client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.argument.llm_client import _direct_cloud_chat, call_llm_chat


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _openai_response(
    content: str,
    *,
    reasoning: str = "",
    finish_reason: str = "stop",
    model: str = "deepseek-v4-pro",
) -> dict:
    return {
        "model": model,
        "choices": [
            {
                "message": {
                    "content": content,
                    "reasoning_content": reasoning,
                },
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }


class _FakeAsyncClient:
    responses: list[dict] = []
    requests: list[dict] = []
    enter_count = 0

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        type(self).enter_count += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers, json):
        type(self).requests.append({"url": url, "headers": headers, "json": json})
        return _Response(type(self).responses.pop(0))


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch):
    import httpx

    _FakeAsyncClient.responses = []
    _FakeAsyncClient.requests = []
    _FakeAsyncClient.enter_count = 0
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


def _client(
    model: str,
    *,
    configured_max_tokens: int = 16384,
    base_url: str = "https://example.invalid/v1",
    thinking_mode: str = "auto",
    reasoning_effort: str | None = None,
    request_audit_hook=None,
):
    return SimpleNamespace(
        api_format="openai",
        api_key="secret",
        model=model,
        base_url=base_url,
        timeout=60.0,
        max_tokens=configured_max_tokens,
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
        request_audit_hook=request_audit_hook,
    )


@pytest.mark.asyncio
async def test_deepseek_v4_disables_default_thinking_and_preserves_requested_budget():
    _FakeAsyncClient.responses = [_openai_response('[{"ok": true}]')]

    result = await _direct_cloud_chat(
        "review this",
        _client(
            "deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
        ),
        max_tokens=1024,
        temperature=0.3,
    )

    assert result == '[{"ok": true}]'
    assert [request["json"]["max_tokens"] for request in _FakeAsyncClient.requests] == [1024]
    assert _FakeAsyncClient.requests[0]["json"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_explicit_deepseek_thinking_mode_is_respected():
    _FakeAsyncClient.responses = [_openai_response("done")]

    await _direct_cloud_chat(
        "review this",
        _client(
            "deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            thinking_mode="enabled",
        ),
        max_tokens=1024,
        temperature=0.3,
    )

    assert _FakeAsyncClient.requests[0]["json"]["thinking"] == {"type": "enabled"}
    assert _FakeAsyncClient.requests[0]["json"]["max_tokens"] == 16384


@pytest.mark.asyncio
async def test_explicit_deepseek_reasoning_effort_is_emitted():
    _FakeAsyncClient.responses = [_openai_response("done")]

    await _direct_cloud_chat(
        "review this",
        _client(
            "deepseek-v4-pro",
            base_url="https://api.deepseek.com/v1",
            thinking_mode="enabled",
            reasoning_effort="high",
        ),
        max_tokens=1024,
        temperature=0.3,
    )

    payload = _FakeAsyncClient.requests[0]["json"]
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_reasoning_effort_is_omitted_when_thinking_is_disabled():
    _FakeAsyncClient.responses = [_openai_response("done")]

    await _direct_cloud_chat(
        "review this",
        _client(
            "deepseek-v4-pro",
            base_url="https://api.deepseek.com/v1",
            thinking_mode="disabled",
            reasoning_effort="high",
        ),
        max_tokens=1024,
        temperature=0.3,
    )

    assert "reasoning_effort" not in _FakeAsyncClient.requests[0]["json"]


@pytest.mark.asyncio
async def test_request_audit_records_actual_payload_without_headers():
    _FakeAsyncClient.responses = [_openai_response("done")]
    events: list[dict] = []

    await _direct_cloud_chat(
        "review this",
        _client(
            "deepseek-v4-pro",
            base_url="https://api.deepseek.com/v1",
            thinking_mode="enabled",
            reasoning_effort="high",
            request_audit_hook=events.append,
        ),
        max_tokens=2048,
        temperature=0.5,
    )

    assert [event["event"] for event in events] == [
        "request_started",
        "response_received",
    ]
    request = events[0]["payload"]
    assert request["max_tokens"] == 16384
    assert request["thinking"] == {"type": "enabled"}
    assert request["reasoning_effort"] == "high"
    assert "headers" not in events[0]
    assert "secret" not in str(events)
    assert events[1]["usage"] == {"prompt_tokens": 12, "completion_tokens": 34}
    assert events[1]["response_model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_request_audit_hook_can_block_before_http_send():
    _FakeAsyncClient.responses = [_openai_response("must not be sent")]

    def reject(_event: dict) -> None:
        raise RuntimeError("pre-send invariant failed")

    with pytest.raises(RuntimeError, match="pre-send invariant failed"):
        await _direct_cloud_chat(
            "review this",
            _client(
                "deepseek-v4-pro",
                base_url="https://api.deepseek.com/v1",
                thinking_mode="enabled",
                reasoning_effort="high",
                request_audit_hook=reject,
            ),
            max_tokens=2048,
            temperature=0.5,
        )

    assert _FakeAsyncClient.requests == []


@pytest.mark.asyncio
async def test_non_reasoning_model_preserves_requested_budget():
    _FakeAsyncClient.responses = [_openai_response("done")]

    result = await _direct_cloud_chat(
        "review this",
        _client("gpt-4o"),
        max_tokens=1024,
        temperature=0.3,
    )

    assert result == "done"
    assert [request["json"]["max_tokens"] for request in _FakeAsyncClient.requests] == [1024]


@pytest.mark.asyncio
async def test_reasoning_retry_reuses_one_http_client():
    _FakeAsyncClient.responses = [
        _openai_response("", reasoning="thinking", finish_reason="length"),
        _openai_response("final"),
    ]

    result = await _direct_cloud_chat(
        "review this",
        _client("deepseek-reasoner"),
        max_tokens=1024,
        temperature=0.3,
    )

    assert result == "final"
    assert [request["json"]["max_tokens"] for request in _FakeAsyncClient.requests] == [
        16384,
        32768,
    ]
    assert _FakeAsyncClient.enter_count == 1


@pytest.mark.asyncio
async def test_json_mode_sends_response_format():
    _FakeAsyncClient.responses = [_openai_response('[{"ok": true}]')]

    result = await _direct_cloud_chat(
        "输出 JSON 格式的分析结果",
        _client("deepseek-v4-flash", base_url="https://api.deepseek.com/v1"),
        max_tokens=1024,
        temperature=0.3,
        json_mode=True,
    )

    assert result == '[{"ok": true}]'
    assert _FakeAsyncClient.requests[0]["json"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_json_mode_off_by_default():
    _FakeAsyncClient.responses = [_openai_response("plain")]

    await _direct_cloud_chat(
        "normal chat",
        _client("deepseek-v4-flash", base_url="https://api.deepseek.com/v1"),
        max_tokens=1024,
        temperature=0.3,
    )

    assert "response_format" not in _FakeAsyncClient.requests[0]["json"]


@pytest.mark.asyncio
async def test_cloud_failure_without_fallback_is_propagated(monkeypatch):
    failure = RuntimeError("provider timeout")
    monkeypatch.setattr(
        "src.argument.llm_client._direct_cloud_chat",
        AsyncMock(side_effect=failure),
    )

    with pytest.raises(RuntimeError, match="provider timeout"):
        await call_llm_chat("review", cloud_client=object())
