"""Tests for parallel_runner — concurrency, ordering, retry, and sequential equivalence."""

from __future__ import annotations

import asyncio
import time

import pytest

from src.translator.ollama_client import TranslationResult
from src.translator.parallel_runner import ChunkResult, translate_chunks_parallel


class _MockChunk:
    def __init__(self, text: str):
        self.text = text


class _MockClient:
    """Deterministic mock: each call sleeps *delay* seconds, returns prefixed text."""

    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.call_log: list[tuple[str, str]] = []

    def translate(self, text: str, prev_trans: str = "") -> TranslationResult:
        self.call_log.append((text, prev_trans))
        time.sleep(self.delay)
        return TranslationResult(
            original=text,
            translated=f"t_{text}",
            model="mock",
            completion_tokens=10,
        )


class _FlakyClient:
    """Fails on a specific call index (0-based), then succeeds on retry."""

    def __init__(self, fail_on: int, delay: float = 0.01):
        self.fail_on = fail_on
        self.delay = delay
        self.call_count = 0

    def translate(self, text: str, prev_trans: str = "") -> TranslationResult:
        self.call_count += 1
        time.sleep(self.delay)
        if self.call_count == self.fail_on + 1:
            raise RuntimeError("API error")
        return TranslationResult(
            original=text,
            translated=f"t_{text}",
            model="mock",
            completion_tokens=10,
        )


class _AlwaysFailClient:
    """Always fails — used to verify fallback behaviour."""

    def translate(self, text: str, prev_trans: str = "") -> TranslationResult:
        raise RuntimeError("permanent failure")


# ---------------------------------------------------------------------------
# 1. Order: parallel mode must yield chunk_done in index order
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_parallel_yields_in_index_order():
    client = _MockClient(delay=0.05)
    chunks = [_MockChunk(f"c{i}") for i in range(10)]

    indices = []
    async for cr in translate_chunks_parallel(client, chunks, max_concurrency=4):
        indices.append(cr.index)

    assert indices == list(range(10))


# ---------------------------------------------------------------------------
# 2. Speed: 10 chunks @ concurrency=4 with 100ms mock must complete < 350ms
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_parallel_faster_than_sequential():
    chunks = [_MockChunk(f"c{i}") for i in range(10)]

    # parallel
    client_par = _MockClient(delay=0.1)
    t0 = time.monotonic()
    results_par = []
    async for cr in translate_chunks_parallel(client_par, chunks, max_concurrency=4):
        results_par.append(cr)
    par_time = time.monotonic() - t0

    # All 10 present in order
    assert [cr.index for cr in results_par] == list(range(10))
    # Must finish well under sequential time (10 × 100ms = 1000ms)
    assert par_time < 0.350, f"Parallel took {par_time:.3f}s, expected < 0.35s"


# ---------------------------------------------------------------------------
# 3. Sequential (max_concurrency=1) chains prev_trans identically to old loop
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_sequential_prev_trans_chain():
    client = _MockClient(delay=0.01)
    chunks = [_MockChunk(f"c{i}") for i in range(4)]

    results = []
    async for cr in translate_chunks_parallel(client, chunks, max_concurrency=1):
        results.append(cr)

    assert len(results) == 4
    # Verify prev_trans chaining
    assert client.call_log[0] == ("c0", "")
    assert client.call_log[1] == ("c1", "t_c0")
    assert client.call_log[2] == ("c2", "t_c1")
    assert client.call_log[3] == ("c3", "t_c2")


# ---------------------------------------------------------------------------
# 4. Retry: single failure → retry succeeds → no fallback
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_retry_recovers():
    client = _FlakyClient(fail_on=2, delay=0.01)
    chunks = [_MockChunk(f"c{i}") for i in range(4)]

    results = []
    async for cr in translate_chunks_parallel(client, chunks, max_concurrency=1, retry_delay=0.01):
        results.append(cr)

    assert len(results) == 4
    assert results[2].error is None
    assert not results[2].is_fallback


# ---------------------------------------------------------------------------
# 5. Fallback: permanent failure → chunk_error + fallback
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_permanent_failure_fallback():
    client = _AlwaysFailClient()
    chunks = [_MockChunk(f"c{i}") for i in range(3)]

    results = []
    async for cr in translate_chunks_parallel(client, chunks, max_concurrency=1, retry_delay=0.01):
        results.append(cr)

    for cr in results:
        assert cr.error is not None
        assert cr.is_fallback
        assert cr.result.original == cr.result.translated


# ---------------------------------------------------------------------------
# 6. Empty input
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_empty_chunks():
    client = _MockClient()
    results = []
    async for cr in translate_chunks_parallel(client, [], max_concurrency=4):
        results.append(cr)
    assert results == []


# ---------------------------------------------------------------------------
# 7. Parallel does NOT chain prev_trans (each chunk gets "")
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_parallel_no_prev_trans():
    client = _MockClient(delay=0.01)
    chunks = [_MockChunk(f"c{i}") for i in range(4)]

    async for _ in translate_chunks_parallel(client, chunks, max_concurrency=4):
        pass

    for text, prev in client.call_log:
        assert prev == "", f"Expected empty prev_trans but got {prev!r} for {text!r}"
