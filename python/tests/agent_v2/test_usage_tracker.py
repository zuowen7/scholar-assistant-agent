"""UsageTracker 测试 — 边缘 + 精度 + 零值 + 大数。"""
from __future__ import annotations

import pytest

from src.agent_v2.runtime.usage import (
    UsageTracker,
    pricing_for_model,
    format_usd,
    _MODEL_PRICING,
)
from src.agent_v2.types import TokenUsage


class TestPricing:
    def test_known_models(self):
        """所有已知模型有定价"""
        for model in _MODEL_PRICING:
            inp, out = pricing_for_model(model)
            assert isinstance(inp, (int, float))
            assert isinstance(out, (int, float))

    def test_partial_match(self):
        """部分匹配查找定价"""
        inp, out = pricing_for_model("deepseek-chat-2025")
        assert inp == 0.27
        assert out == 1.10

    def test_unknown_model_default(self):
        inp, out = pricing_for_model("totally-unknown-model-xyz")
        assert inp == 1.00
        assert out == 4.00

    def test_local_model_free(self):
        inp, out = pricing_for_model("qwen3:8b")
        assert inp == 0
        assert out == 0


class TestFormatUsd:
    def test_tiny_amount(self):
        assert format_usd(0.0001) == "$0.0001"

    def test_small_amount(self):
        assert format_usd(0.05) == "$0.050"

    def test_medium_amount(self):
        assert format_usd(1.234) == "$1.23"

    def test_zero(self):
        assert format_usd(0) == "$0.0000"


class TestUsageTracker:
    def test_empty(self):
        t = UsageTracker(model="deepseek-chat")
        assert t.total_tokens() == 0
        assert t.estimated_cost() == 0.0
        assert t.call_count == 0

    def test_record_single(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=1000, output_tokens=500))
        assert t.total_input == 1000
        assert t.total_output == 500
        assert t.total_tokens() == 1500
        assert t.call_count == 1

    def test_record_multiple(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=100, output_tokens=50))
        t.record(TokenUsage(input_tokens=200, output_tokens=80))
        t.record(TokenUsage(input_tokens=300, output_tokens=120))
        assert t.total_input == 600
        assert t.total_output == 250
        assert t.total_tokens() == 850
        assert t.call_count == 3

    def test_zero_usage(self):
        t = UsageTracker()
        t.record(TokenUsage(input_tokens=0, output_tokens=0))
        assert t.total_tokens() == 0
        assert t.estimated_cost() == 0.0

    def test_cost_estimation_deepseek(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000))
        cost = t.estimated_cost()
        # 1M * $0.27/1M + 1M * $1.10/1M = $1.37
        assert abs(cost - 1.37) < 0.01

    def test_cost_estimation_free(self):
        t = UsageTracker(model="qwen3:8b")
        t.record(TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000))
        assert t.estimated_cost() == 0.0

    def test_cache_tokens_tracked(self):
        t = UsageTracker()
        t.record(TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=200, cache_creation_tokens=10))
        assert t.total_cache_read == 200
        assert t.total_cache_creation == 10
        # Cache tokens NOT counted in total
        assert t.total_tokens() == 150

    def test_summary_format(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=5000, output_tokens=2000))
        s = t.summary()
        assert "5,000" in s
        assert "2,000" in s
        assert "7,000" in s

    def test_to_dict(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=1000, output_tokens=500))
        d = t.to_dict()
        assert d["model"] == "deepseek-chat"
        assert d["total_input"] == 1000
        assert d["total_tokens"] == 1500
        assert d["call_count"] == 1
        assert "estimated_cost_usd" in d
        assert "estimated_cost_display" in d

    def test_large_numbers(self):
        """100M tokens — 不溢出"""
        t = UsageTracker(model="claude-opus-4-6")
        t.record(TokenUsage(input_tokens=50_000_000, output_tokens=50_000_000))
        cost = t.estimated_cost()
        assert cost > 0
        assert t.total_tokens() == 100_000_000

    def test_many_small_calls(self):
        """10000 次小调用 — 累积正确"""
        t = UsageTracker()
        for _ in range(10000):
            t.record(TokenUsage(input_tokens=10, output_tokens=5))
        assert t.total_input == 100_000
        assert t.total_output == 50_000
        assert t.call_count == 10000
