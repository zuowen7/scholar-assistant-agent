"""PromptCache Event — track prompt cache hit/miss rates and token savings.

Port of claw-code PromptCacheEvent from conversation.rs.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CacheEvent:
    type: str  # "cache_hit" or "cache_miss"
    tokens: int = 0


@dataclass
class PromptCacheTracker:
    """Track prompt cache hits, misses, and token savings across a session."""

    cache_hits: int = 0
    cache_misses: int = 0
    tokens_saved: int = 0
    cache_writes: int = 0
    events: list[dict] = field(default_factory=list)

    def record_hit(self, tokens_saved: int = 0) -> None:
        self.cache_hits += 1
        self.tokens_saved += tokens_saved
        self.events.append({"type": "cache_hit", "tokens": tokens_saved})

    def record_miss(self, tokens_written: int = 0) -> None:
        self.cache_misses += 1
        self.cache_writes += tokens_written
        self.events.append({"type": "cache_miss", "tokens": tokens_written})

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def summary(self) -> dict:
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": round(self.hit_rate, 3),
            "tokens_saved": self.tokens_saved,
            "cache_writes": self.cache_writes,
        }
