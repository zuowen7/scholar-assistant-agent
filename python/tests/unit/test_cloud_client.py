"""CloudClient 单元测试 — 覆盖 OpenAI/Anthropic 格式、错误路径、速率限制"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.translator.cloud_client import (
    CloudClient,
    _ProviderRateLimiter,
    _get_limiter,
    _rate_limiters,
    _RATE_LIMIT_INTERVAL,
    PROVIDER_PRESETS,
)


def _make_openai_response(text: str, model: str = "gpt-4o") -> MagicMock:
    """构造 OpenAI 兼容格式的 httpx.Response mock"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    return mock_resp


def _make_anthropic_response(text: str) -> MagicMock:
    """构造 Anthropic Messages API 格式的 httpx.Response mock"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "model": "claude-sonnet-4-20250514",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return mock_resp


def _make_client(provider: str = "openai", **kwargs) -> CloudClient:
    preset = PROVIDER_PRESETS.get(provider, {})
    return CloudClient(
        provider=provider,
        base_url=preset.get("base_url", "https://api.openai.com/v1"),
        api_key="sk-test",
        model=preset.get("models", ["gpt-4o"])[0],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# OpenAI 兼容 API
# ---------------------------------------------------------------------------

class TestOpenAIFormat:

    def test_successful_translation(self):
        client = _make_client("openai")
        mock_resp = _make_openai_response("翻译结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            result = client.translate("Hello world")

        assert result.translated == "翻译结果"
        assert result.original == "Hello world"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    def test_sends_to_correct_url(self):
        client = _make_client("openai")
        mock_resp = _make_openai_response("翻译结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            client.translate("Hello")
            call_url = mock_http.post.call_args[0][0]

        assert call_url.endswith("/chat/completions")

    def test_bearer_auth_header(self):
        client = _make_client("openai")
        mock_resp = _make_openai_response("结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            client.translate("Test")
            _, call_kwargs = mock_http.post.call_args
            headers = call_kwargs.get("headers", {})

        assert headers.get("Authorization") == "Bearer sk-test"


# ---------------------------------------------------------------------------
# Anthropic API
# ---------------------------------------------------------------------------

class TestAnthropicFormat:

    def test_successful_translation(self):
        client = _make_client("anthropic")
        mock_resp = _make_anthropic_response("翻译结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            result = client.translate("Hello world")

        assert result.translated == "翻译结果"

    def test_sends_to_messages_endpoint(self):
        client = _make_client("anthropic")
        mock_resp = _make_anthropic_response("结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            client.translate("Test")
            call_url = mock_http.post.call_args[0][0]

        assert "/messages" in call_url

    def test_uses_x_api_key_header(self):
        client = _make_client("anthropic")
        mock_resp = _make_anthropic_response("结果")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.return_value = mock_resp
            mock_get.return_value = mock_http

            client.translate("Test")
            _, call_kwargs = mock_http.post.call_args
            headers = call_kwargs.get("headers", {})

        assert headers.get("x-api-key") == "sk-test"
        assert "anthropic-version" in headers


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------

class TestErrorPaths:

    def test_connection_error_retries_then_raises(self):
        client = _make_client("openai")
        call_count = 0

        def raise_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("connection refused", request=MagicMock())

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = raise_connect
            mock_get.return_value = mock_http
            with patch("src.translator.cloud_client.time.sleep"):
                with pytest.raises(ConnectionError, match="无法连接云端 API"):
                    client.translate("Test")

        assert call_count == 3  # 1 initial + 2 retries (MAX_RETRIES=2)

    def test_http_4xx_raises_value_error(self):
        client = _make_client("openai")

        mock_error_resp = MagicMock()
        mock_error_resp.status_code = 401
        mock_error_resp.json.return_value = {"error": {"message": "Invalid API key"}}
        mock_error_resp.text = "Unauthorized"

        http_err = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_error_resp)

        def raise_http(*args, **kwargs):
            raise http_err

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = raise_http
            mock_get.return_value = mock_http
            with patch("src.translator.cloud_client.time.sleep"):
                with pytest.raises(ValueError, match="HTTP 401"):
                    client.translate("Test")

    def test_timeout_raises_connection_error(self):
        client = _make_client("openai")

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = httpx.TimeoutException("timeout", request=MagicMock())
            mock_get.return_value = mock_http
            with patch("src.translator.cloud_client.time.sleep"):
                with pytest.raises(ConnectionError, match="超时"):
                    client.translate("Test")

    def test_empty_translation_triggers_retry(self):
        client = _make_client("openai")
        call_count = 0

        def short_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            # Return empty string — fails _validate_translation
            mock_resp.json.return_value = {
                "model": "gpt-4o",
                "choices": [{"message": {"content": ""}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            }
            return mock_resp

        with patch.object(client, "_get_http_client") as mock_get:
            mock_http = MagicMock()
            mock_http.post.side_effect = short_response
            mock_get.return_value = mock_http
            with patch("src.translator.cloud_client.time.sleep"):
                result = client.translate("Hello world, this is a test.")

        # After MAX_RETRIES exhausted it should return the (empty) result on last try
        assert call_count == 3


# ---------------------------------------------------------------------------
# 模块级速率限制器
# ---------------------------------------------------------------------------

class TestRateLimiter:

    def test_same_key_returns_same_limiter(self):
        key = "https://api.test.com:sk-testxx"
        l1 = _get_limiter(key)
        l2 = _get_limiter(key)
        assert l1 is l2

    def test_different_key_returns_different_limiter(self):
        l1 = _get_limiter("url1:key1")
        l2 = _get_limiter("url2:key2")
        assert l1 is not l2

    def test_rate_limit_persists_across_clients(self):
        """两个不同 CloudClient 实例共享同一速率限制器"""
        url = "https://api.ratelimit-test.com/v1"
        key = "sk-rltest1234"

        c1 = CloudClient(provider="custom", base_url=url, api_key=key, model="gpt-4o")
        c2 = CloudClient(provider="custom", base_url=url, api_key=key, model="gpt-4o")

        assert c1._rate_limiter_key == c2._rate_limiter_key
        limiter_c1 = _get_limiter(c1._rate_limiter_key)
        limiter_c2 = _get_limiter(c2._rate_limiter_key)
        assert limiter_c1 is limiter_c2

    def test_rate_limit_enforces_interval(self):
        """连续两次调用之间至少间隔 _RATE_LIMIT_INTERVAL 秒"""
        key = "__test_interval__"
        limiter = _get_limiter(key)
        limiter.last_time = 0.0

        client = CloudClient(provider="custom", base_url="http://x", api_key="k12345678")
        client._rate_limiter_key = key

        slept: list[float] = []

        def fake_sleep(secs: float):
            slept.append(secs)

        # Set last_time to "just now" so the next call should sleep
        limiter.last_time = time.monotonic()

        with patch("src.translator.cloud_client.time.sleep", fake_sleep):
            client._rate_limit_wait()

        assert slept, "Expected at least one sleep call"
        assert slept[0] > 0
        assert slept[0] <= _RATE_LIMIT_INTERVAL + 0.01
