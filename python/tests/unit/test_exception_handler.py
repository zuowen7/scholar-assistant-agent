"""异常处理体系单元测试"""

import pytest

from src.translator.exception_handler import (
    classify_error,
    ErrorCategory,
    get_fallback_strategy,
    format_error_for_user,
    build_fallback_result,
)


class TestClassifyError:
    def test_fatal_oom(self):
        assert classify_error(ConnectionError("out of memory")) == ErrorCategory.FATAL
        assert classify_error("GPU out of memory") == ErrorCategory.FATAL
        assert classify_error(RuntimeError("OOM during inference")) == ErrorCategory.FATAL

    def test_transient_timeout(self):
        assert classify_error(ConnectionError("connection timed out")) == ErrorCategory.TRANSIENT
        assert classify_error("connection refused") == ErrorCategory.TRANSIENT
        assert classify_error("Load model timeout") == ErrorCategory.TRANSIENT

    def test_transient_rate_limit(self):
        assert classify_error("HTTP 429 rate limit") == ErrorCategory.TRANSIENT
        assert classify_error("503 service unavailable") == ErrorCategory.TRANSIENT

    def test_transient_gpu(self):
        assert classify_error("GPU memory allocation failed") == ErrorCategory.TRANSIENT

    def test_permanent_bad_request(self):
        assert classify_error("HTTP 400 bad request") == ErrorCategory.PERMANENT
        assert classify_error("invalid request format") == ErrorCategory.PERMANENT
        assert classify_error("model not found") == ErrorCategory.PERMANENT

    def test_permanent_unsupported(self):
        assert classify_error("format unsupported") == ErrorCategory.PERMANENT

    def test_default_transient(self):
        assert classify_error("some unknown error") == ErrorCategory.TRANSIENT

    def test_exception_object(self):
        err = ConnectionError("connection reset by peer")
        assert classify_error(err) == ErrorCategory.TRANSIENT

    def test_string_error(self):
        assert classify_error("context length exceeded") == ErrorCategory.TRANSIENT


class TestGetFallbackStrategy:
    def test_fatal_aborts(self):
        strategy = get_fallback_strategy(
            "out of memory",
            chunk_index=5,
            total_chunks=10,
            has_cloud_fallback=True,
        )
        assert strategy["action"] == "abort"
        assert strategy["recoverable"] is False

    def test_transient_retries(self):
        strategy = get_fallback_strategy(
            "connection timeout",
            chunk_index=0,
            total_chunks=10,
            has_cloud_fallback=False,
        )
        assert strategy["action"] == "retry"
        assert strategy["delay"] == 3.0
        assert strategy["recoverable"] is True

    def test_ollama_with_cloud_fallback(self):
        strategy = get_fallback_strategy(
            "Ollama GPU error",
            chunk_index=3,
            total_chunks=10,
            has_cloud_fallback=True,
        )
        assert strategy["action"] == "retry_cloud"
        assert strategy["recoverable"] is True

    def test_last_chunk_skips(self):
        strategy = get_fallback_strategy(
            "connection reset",
            chunk_index=9,
            total_chunks=10,
            has_cloud_fallback=False,
        )
        assert strategy["action"] == "skip"
        assert strategy["recoverable"] is True

    def test_permanent_skips(self):
        strategy = get_fallback_strategy(
            "invalid request",
            chunk_index=2,
            total_chunks=10,
            has_cloud_fallback=True,
        )
        assert strategy["action"] == "skip"
        assert strategy["recoverable"] is True


class TestFormatErrorForUser:
    def test_fatal_error(self):
        msg = format_error_for_user("out of memory", ErrorCategory.FATAL)
        assert len(msg) > 0  # non-empty

    def test_permanent_empty(self):
        msg = format_error_for_user("content is empty", ErrorCategory.PERMANENT)
        assert len(msg) > 0

    def test_permanent_format(self):
        msg = format_error_for_user("unsupported format", ErrorCategory.PERMANENT)
        assert len(msg) > 0

    def test_transient_timeout(self):
        msg = format_error_for_user("connection timed out", ErrorCategory.TRANSIENT)
        assert len(msg) > 0

    def test_transient_connection(self):
        msg = format_error_for_user("connection refused", ErrorCategory.TRANSIENT)
        assert len(msg) > 0

    def test_transient_gpu(self):
        msg = format_error_for_user("GPU memory error", ErrorCategory.TRANSIENT)
        assert len(msg) > 0

    def test_transient_rate_limit(self):
        msg = format_error_for_user("rate limit exceeded", ErrorCategory.TRANSIENT)
        assert len(msg) > 0


class TestBuildFallbackResult:
    def test_returns_original_as_translated(self):
        result = build_fallback_result("Hello world", "connection timeout", 3)
        assert result["original"] == "Hello world"
        assert result["translated"] == "Hello world"

    def test_has_fallback_flag(self):
        result = build_fallback_result("test", "error", 0)
        assert result["fallback"] is True

    def test_includes_chunk_index(self):
        result = build_fallback_result("test", "error", 5)
        assert result["chunk_index"] == 5

    def test_includes_error_message(self):
        result = build_fallback_result("test", "specific error message", 0)
        assert result["error"] == "specific error message"

    def test_empty_text(self):
        result = build_fallback_result("", "empty content", 0)
        assert result["original"] == ""
        assert result["translated"] == ""