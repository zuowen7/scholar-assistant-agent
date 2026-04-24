"""Phase 3 单元测试 — error_classifier, hooks。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.agent.error_classifier import (
    ErrorType,
    RecoveryAction,
    RetryManager,
    classify_error,
    get_recovery,
)
from src.agent.hooks import HookContext, HookManager, HookPoint


# ---------------------------------------------------------------------------
# ErrorType 分类
# ---------------------------------------------------------------------------

class TestClassifyError:

    def test_timeout_message(self):
        err = Exception("request timeout after 30s")
        assert classify_error(err) == ErrorType.TIMEOUT

    def test_connection_error(self):
        err = Exception("Connection refused")
        assert classify_error(err) == ErrorType.TIMEOUT

    def test_rate_limit_message(self):
        err = Exception("rate limit exceeded")
        assert classify_error(err) == ErrorType.RATE_LIMIT

    def test_auth_message(self):
        err = Exception("Invalid API Key")
        assert classify_error(err) == ErrorType.AUTH

    def test_model_not_found(self):
        err = Exception("model not found: xyz")
        assert classify_error(err) == ErrorType.MODEL_NOT_FOUND

    def test_billing_message(self):
        err = Exception("insufficient billing quota")
        assert classify_error(err) == ErrorType.BILLING

    def test_overload_message(self):
        err = Exception("server at capacity, overloaded")
        assert classify_error(err) == ErrorType.OVERLOADED

    def test_context_overflow(self):
        err = Exception("context length too long")
        assert classify_error(err) == ErrorType.CONTEXT_OVERFLOW

    def test_unknown_error(self):
        err = Exception("something went wrong")
        assert classify_error(err) == ErrorType.UNKNOWN

    def test_http_status_401(self):
        err = Exception("Unauthorized")
        resp = MagicMock()
        resp.status_code = 401
        err.response = resp
        assert classify_error(err) == ErrorType.AUTH

    def test_http_status_429(self):
        err = Exception("Too Many Requests")
        resp = MagicMock()
        resp.status_code = 429
        err.response = resp
        assert classify_error(err) == ErrorType.RATE_LIMIT

    def test_http_status_500(self):
        err = Exception("Internal Server Error")
        resp = MagicMock()
        resp.status_code = 500
        err.response = resp
        assert classify_error(err) == ErrorType.SERVER_ERROR

    def test_http_status_503(self):
        err = Exception("Service Unavailable")
        resp = MagicMock()
        resp.status_code = 503
        err.response = resp
        assert classify_error(err) == ErrorType.OVERLOADED

    def test_http_status_404(self):
        err = Exception("Not Found")
        resp = MagicMock()
        resp.status_code = 404
        err.response = resp
        assert classify_error(err) == ErrorType.MODEL_NOT_FOUND

    def test_http_status_413(self):
        err = Exception("Payload Too Large")
        resp = MagicMock()
        resp.status_code = 413
        err.response = resp
        assert classify_error(err) == ErrorType.PAYLOAD_TOO_LARGE


# ---------------------------------------------------------------------------
# Recovery 策略
# ---------------------------------------------------------------------------

class TestGetRecovery:

    def test_auth_is_abort(self):
        r = get_recovery(ErrorType.AUTH)
        assert r.action == "abort"

    def test_rate_limit_is_retry(self):
        r = get_recovery(ErrorType.RATE_LIMIT)
        assert r.action == "retry"
        assert r.max_retries >= 2

    def test_timeout_is_retry(self):
        r = get_recovery(ErrorType.TIMEOUT)
        assert r.action == "retry"

    def test_context_overflow_is_rephrase(self):
        r = get_recovery(ErrorType.CONTEXT_OVERFLOW)
        assert r.action == "rephrase"

    def test_all_types_have_strategy(self):
        for et in ErrorType:
            r = get_recovery(et)
            assert r.action in ("retry", "skip", "abort", "rephrase")
            assert r.message


# ---------------------------------------------------------------------------
# RetryManager
# ---------------------------------------------------------------------------

class TestRetryManager:

    def test_can_retry_rate_limit(self):
        mgr = RetryManager()
        assert mgr.can_retry(ErrorType.RATE_LIMIT) is True

    def test_cannot_retry_auth(self):
        mgr = RetryManager()
        assert mgr.can_retry(ErrorType.AUTH) is False

    def test_cannot_retry_after_max(self):
        mgr = RetryManager()
        recovery = get_recovery(ErrorType.RATE_LIMIT)
        for _ in range(recovery.max_retries):
            mgr.record_attempt(ErrorType.RATE_LIMIT)
        assert mgr.can_retry(ErrorType.RATE_LIMIT) is False

    def test_exponential_backoff(self):
        mgr = RetryManager(base_delay=1.0)
        d0 = mgr.get_delay(ErrorType.RATE_LIMIT)
        mgr.record_attempt(ErrorType.RATE_LIMIT)
        d1 = mgr.get_delay(ErrorType.RATE_LIMIT)
        mgr.record_attempt(ErrorType.RATE_LIMIT)
        d2 = mgr.get_delay(ErrorType.RATE_LIMIT)
        assert d0 < d1 < d2

    def test_reset(self):
        mgr = RetryManager()
        mgr.record_attempt(ErrorType.TIMEOUT)
        mgr.reset()
        assert mgr.can_retry(ErrorType.TIMEOUT) is True

    def test_feedback_message(self):
        mgr = RetryManager()
        msg = mgr.get_feedback_message(ErrorType.AUTH)
        assert "API Key" in msg

    def test_feedback_with_delay_placeholder(self):
        mgr = RetryManager()
        msg = mgr.get_feedback_message(ErrorType.RATE_LIMIT)
        assert "等待" in msg
        assert "重试" in msg

    def test_feedback_with_detail(self):
        mgr = RetryManager()
        msg = mgr.get_feedback_message(ErrorType.TOOL_ERROR, detail="翻译客户端未注入")
        assert "翻译客户端未注入" in msg


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------

class TestHookManager:

    def test_register_and_trigger(self):
        mgr = HookManager()
        calls = []

        @mgr.register(HookPoint.ON_TOOL_CALL)
        def on_call(ctx: HookContext):
            calls.append(ctx.data.get("tool_name"))

        ctx = HookContext(point=HookPoint.ON_TOOL_CALL, data={"tool_name": "test"})
        mgr.trigger_sync(ctx)
        assert calls == ["test"]

    @pytest.mark.anyio
    async def test_async_hook(self):
        mgr = HookManager()
        calls = []

        @mgr.register(HookPoint.ON_ERROR)
        async def on_error(ctx: HookContext):
            calls.append(ctx.data.get("error_type"))

        ctx = HookContext(point=HookPoint.ON_ERROR, data={"error_type": "timeout"})
        await mgr.trigger(ctx)
        assert calls == ["timeout"]

    def test_multiple_hooks(self):
        mgr = HookManager()
        results = []

        @mgr.register(HookPoint.ON_TOOL_RESULT)
        def hook1(ctx: HookContext):
            results.append("h1")

        @mgr.register(HookPoint.ON_TOOL_RESULT)
        def hook2(ctx: HookContext):
            results.append("h2")

        mgr.trigger_sync(HookContext(point=HookPoint.ON_TOOL_RESULT))
        assert results == ["h1", "h2"]

    def test_hook_failure_does_not_stop_others(self):
        mgr = HookManager()
        results = []

        @mgr.register(HookPoint.ON_AGENT_START)
        def bad_hook(ctx: HookContext):
            raise ValueError("boom")

        @mgr.register(HookPoint.ON_AGENT_START)
        def good_hook(ctx: HookContext):
            results.append("ok")

        mgr.trigger_sync(HookContext(point=HookPoint.ON_AGENT_START))
        assert results == ["ok"]

    def test_remove_hook(self):
        mgr = HookManager()
        calls = []

        def hook(ctx: HookContext):
            calls.append(1)

        mgr.add_hook(HookPoint.ON_AGENT_END, hook)
        mgr.trigger_sync(HookContext(point=HookPoint.ON_AGENT_END))
        assert len(calls) == 1

        mgr.remove_hook(HookPoint.ON_AGENT_END, hook)
        mgr.trigger_sync(HookContext(point=HookPoint.ON_AGENT_END))
        assert len(calls) == 1

    def test_clear(self):
        mgr = HookManager()
        mgr.add_hook(HookPoint.ON_AGENT_START, lambda ctx: None)
        mgr.add_hook(HookPoint.ON_AGENT_END, lambda ctx: None)
        mgr.clear()
        assert mgr.get_hooks(HookPoint.ON_AGENT_START) == []
        assert mgr.get_hooks(HookPoint.ON_AGENT_END) == []

    def test_get_hooks(self):
        mgr = HookManager()
        fn1 = lambda ctx: None
        fn2 = lambda ctx: None
        mgr.add_hook(HookPoint.ON_TOOL_CALL, fn1)
        mgr.add_hook(HookPoint.ON_TOOL_CALL, fn2)
        hooks = mgr.get_hooks(HookPoint.ON_TOOL_CALL)
        assert len(hooks) == 2

    @pytest.mark.anyio
    async def test_trigger_skips_sync_for_async_hook(self):
        mgr = HookManager()
        results = []

        @mgr.register(HookPoint.ON_MEMORY_WRITE)
        async def async_hook(ctx: HookContext):
            results.append("async")

        # trigger_sync 应跳过异步 Hook
        mgr.trigger_sync(HookContext(point=HookPoint.ON_MEMORY_WRITE))
        assert results == []

        # trigger 应执行异步 Hook
        await mgr.trigger(HookContext(point=HookPoint.ON_MEMORY_WRITE))
        assert results == ["async"]
