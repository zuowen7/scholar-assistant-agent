"""Integration tests for Reviewer-2 DAG parallel perspectives (Phase D)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.argument.companion_models import ReviewPoint, ReviewSession
from src.argument.companion_store import CompanionStore


# ── E1: basic parallel review flow ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_review_parallel_basic(tmp_path: Path):
    """E1: run_review_parallel() yields review_point events and complete."""
    from src.argument.reviewer import run_review_parallel

    store = CompanionStore(tmp_path)

    async def mock_llm(prompt, *a, **kw):
        return '[{"severity":"major","category":"baseline","title":"Test issue","detail":"Details here"}]'

    with patch("src.argument._reviewer_perspectives.call_llm_chat", mock_llm):
        events = []
        async for ev in run_review_parallel(
            doc_id="doc_e1",
            text="Sample paper text for testing the parallel reviewer.",
            store=store,
            cloud_client=None,
            ollama_client=None,
        ):
            events.append(ev)

    event_types = [e["event"] for e in events]
    assert "complete" in event_types
    review_events = [e for e in events if e["event"] == "review_point"]
    assert len(review_events) >= 1


# ── E2: deduplication across perspectives ─────────────────────────────────────

@pytest.mark.asyncio
async def test_run_review_parallel_deduplicates(tmp_path: Path):
    """E2: identical (title, category) points across perspectives appear once."""
    from src.argument.reviewer import run_review_parallel

    store = CompanionStore(tmp_path)

    async def dup_mock(prompt, *a, **kw):
        # All three perspectives return same title+category
        return '[{"severity":"major","category":"baseline","title":"Same issue everywhere","detail":"d"}]'

    with patch("src.argument._reviewer_perspectives.call_llm_chat", dup_mock):
        events = []
        async for ev in run_review_parallel(
            doc_id="doc_e2",
            text="Paper text.",
            store=store,
        ):
            events.append(ev)

    review_events = [e for e in events if e["event"] == "review_point"]
    titles = [json.loads(e["data"])["title"] for e in review_events]
    assert titles.count("Same issue everywhere") == 1, (
        f"Expected 1 occurrence after dedup, got {titles.count('Same issue everywhere')}: {titles}"
    )


# ── E3: session persisted to store ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_review_parallel_persists(tmp_path: Path):
    """E3: run_review_parallel() saves a ReviewSession to CompanionStore."""
    from src.argument.reviewer import run_review_parallel

    store = CompanionStore(tmp_path)

    async def mock_llm(prompt, *a, **kw):
        return '[{"severity":"minor","category":"soundness","title":"Minor T","detail":"d"}]'

    with patch("src.argument._reviewer_perspectives.call_llm_chat", mock_llm):
        events = []
        async for ev in run_review_parallel(
            doc_id="doc_e3",
            text="Paper.",
            store=store,
            doc_title="Test Paper Title",
        ):
            events.append(ev)

    complete = next((e for e in events if e["event"] == "complete"), None)
    assert complete is not None
    session_id = json.loads(complete["data"])["session_id"]

    session = store.get_review(session_id)
    assert session is not None
    assert session.doc_id == "doc_e3"
    assert len(session.points) >= 1
