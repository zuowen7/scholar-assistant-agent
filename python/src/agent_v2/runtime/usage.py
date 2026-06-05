"""UsageTracker + ModelPricing — token/cost 追踪。

参考 claw-code:
  - runtime/usage.rs: UsageTracker, ModelPricing, format_usd
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.agent_v2.types import TokenUsage

# USD per 1M tokens (2024-2025 pricing)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input_price_per_1M, output_price_per_1M)
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen3:8b": (0, 0),  # local — free
}


def pricing_for_model(model: str) -> tuple[float, float]:
    """Get (input_price, output_price) per 1M tokens for a model."""
    for key, prices in _MODEL_PRICING.items():
        if key in model.lower():
            return prices
    return (1.00, 4.00)  # unknown model default


def format_usd(amount: float) -> str:
    if amount < 0.01:
        return f"${amount:.4f}"
    if amount < 1.0:
        return f"${amount:.3f}"
    return f"${amount:.2f}"


@dataclass
class UsageTracker:
    """Per-session usage tracker. 参考 claw-code UsageTracker。"""

    model: str = ""
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_creation: int = 0
    call_count: int = 0

    def record(self, usage: TokenUsage) -> None:
        self.total_input += usage.input_tokens
        self.total_output += usage.output_tokens
        self.total_cache_read += usage.cache_read_tokens
        self.total_cache_creation += usage.cache_creation_tokens
        self.call_count += 1

    def total_tokens(self) -> int:
        return self.total_input + self.total_output

    def estimated_cost(self) -> float:
        inp_price, out_price = pricing_for_model(self.model)
        cost = (self.total_input / 1_000_000) * inp_price
        cost += (self.total_output / 1_000_000) * out_price
        return cost

    def summary(self) -> str:
        cost = self.estimated_cost()
        return (
            f"Tokens: {self.total_input:,} in + {self.total_output:,} out = {self.total_tokens():,} total\n"
            f"Calls: {self.call_count} | Cost: ~{format_usd(cost)}"
        )

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "total_input": self.total_input,
            "total_output": self.total_output,
            "total_tokens": self.total_tokens(),
            "call_count": self.call_count,
            "estimated_cost_usd": round(self.estimated_cost(), 6),
            "estimated_cost_display": format_usd(self.estimated_cost()),
        }
