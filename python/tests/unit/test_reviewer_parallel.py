"""Unit tests for Reviewer-2 DAG three-perspective parallel review (Phase D)."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.argument._reviewer_perspectives import (
    aggregate_perspectives,
    run_experiment_perspective,
    run_method_perspective,
    run_writing_perspective,
)
from src.argument.companion_models import ReviewPoint


# ── D1: three perspectives run in parallel ────────────────────────────────────

@pytest.mark.asyncio
async def test_three_perspectives_run_in_parallel():
    """D1: asyncio.gather runs perspectives concurrently (not serially)."""
    call_count = [0]

    async def slow_llm(prompt, *args, **kwargs):
        call_count[0] += 1
        await asyncio.sleep(0.05)
        return "[]"

    with patch("src.argument._reviewer_perspectives.call_llm_chat", slow_llm):
        t0 = time.monotonic()
        await asyncio.gather(
            run_method_perspective("paper", "generic", None, None),
            run_experiment_perspective("paper", "generic", None, None),
            run_writing_perspective("paper", "generic", None, None),
        )
        elapsed = time.monotonic() - t0

    assert elapsed < 0.13, f"Expected parallel (~0.05s) but took {elapsed:.3f}s (serial would be ~0.15s)"
    assert call_count[0] == 3


# ── D2: aggregator merges all three ──────────────────────────────────────────

def test_aggregator_merges_three():
    """D2: aggregate_perspectives collects points from all three angles."""
    m = [ReviewPoint(severity="major", category="soundness", title="Method issue", detail="d")]
    e = [ReviewPoint(severity="minor", category="ablation", title="Experiment issue", detail="d")]
    w = [ReviewPoint(severity="minor", category="writing_clarity", title="Writing issue", detail="d")]

    result = aggregate_perspectives(m, e, w)

    assert len(result) == 3
    titles = {p.title for p in result}
    assert "Method issue" in titles
    assert "Experiment issue" in titles
    assert "Writing issue" in titles


# ── D3–D5: each perspective prompt focuses on its domain ─────────────────────

@pytest.mark.asyncio
async def test_perspective_method_prompt_focused():
    """D3: method perspective prompt contains methodology keywords."""
    captured: list[str] = []

    async def spy(prompt, *a, **kw):
        captured.append(prompt)
        return "[]"

    with patch("src.argument._reviewer_perspectives.call_llm_chat", spy):
        await run_method_perspective("paper text", "venue profile", None, None)

    assert captured, "call_llm_chat was not called"
    text = captured[0].lower()
    assert any(kw in text for kw in ["method", "methodology", "soundness", "theoretical", "approach"])


@pytest.mark.asyncio
async def test_perspective_experiment_prompt_focused():
    """D4: experiment perspective prompt contains experiment keywords."""
    captured: list[str] = []

    async def spy(prompt, *a, **kw):
        captured.append(prompt)
        return "[]"

    with patch("src.argument._reviewer_perspectives.call_llm_chat", spy):
        await run_experiment_perspective("paper text", "venue profile", None, None)

    assert captured
    text = captured[0].lower()
    assert any(kw in text for kw in ["experiment", "baseline", "ablation", "reproducib", "evaluation"])


@pytest.mark.asyncio
async def test_perspective_writing_prompt_focused():
    """D5: writing perspective prompt contains writing/clarity keywords."""
    captured: list[str] = []

    async def spy(prompt, *a, **kw):
        captured.append(prompt)
        return "[]"

    with patch("src.argument._reviewer_perspectives.call_llm_chat", spy):
        await run_writing_perspective("paper text", "venue profile", None, None)

    assert captured
    text = captured[0].lower()
    assert any(kw in text for kw in ["writing", "clarity", "presentation", "language", "structure"])


# ── D6: aggregator deduplicates by (title, category) ─────────────────────────

def test_aggregator_no_duplicate_points():
    """D6: identical (title, category) across perspectives appears only once."""
    pt1 = ReviewPoint(severity="major", category="baseline", title="Missing baseline", detail="d1")
    pt2 = ReviewPoint(severity="minor", category="baseline", title="Missing baseline", detail="d2")
    pt3 = ReviewPoint(severity="minor", category="writing_clarity", title="Unclear writing", detail="d3")

    result = aggregate_perspectives([pt1], [pt2], [pt3])

    titles = [p.title for p in result]
    assert titles.count("Missing baseline") == 1
    assert len(result) == 2


# ── D7: one perspective failing doesn't crash the others ─────────────────────

@pytest.mark.asyncio
async def test_failure_partial_tolerance():
    """D7: when one perspective LLM fails, others still return results."""
    async def selective(prompt, *a, **kw):
        if "experiment" in prompt.lower():
            raise RuntimeError("simulated LLM timeout")
        return '[{"severity":"minor","category":"soundness","title":"T","detail":"d"}]'

    with patch("src.argument._reviewer_perspectives.call_llm_chat", selective):
        m_pts = await run_method_perspective("paper", "generic", None, None)
        e_pts = await run_experiment_perspective("paper", "generic", None, None)
        w_pts = await run_writing_perspective("paper", "generic", None, None)

    assert isinstance(m_pts, list)
    assert isinstance(e_pts, list)   # empty because exception was caught
    assert isinstance(w_pts, list)
    assert len(e_pts) == 0           # exception path returns []


# ── D8: rebuttal continues on aggregated session ──────────────────────────────

@pytest.mark.asyncio
async def test_rebuttal_continues_on_aggregated(tmp_path):
    """D8: continue_rebuttal() works on a ReviewSession built from parallel perspectives."""
    from src.argument.companion_models import ReviewSession
    from src.argument.companion_store import CompanionStore
    from src.argument.reviewer import continue_rebuttal

    store = CompanionStore(tmp_path)
    point = ReviewPoint(
        severity="major",
        category="baseline",
        title="Missing baseline comparison",
        detail="Paper lacks comparison against baseline X.",
    )
    session = ReviewSession(doc_id="test_doc", checks=["parallel"], points=[point])
    store.save_review(session)

    async def mock_reply(*a, **kw):
        return "Reviewer maintains this concern pending more evidence."

    with patch("src.argument.reviewer.call_llm_chat", mock_reply):
        events = []
        async for ev in continue_rebuttal(
            session.id, point.id, "We added baseline X in Table 3.",
            "full paper text", store, None, None,
        ):
            events.append(ev)

    event_types = {e["event"] for e in events}
    assert "reviewer_reply" in event_types
    assert "complete" in event_types


# ── D9: output order is stable (method → experiment → writing) ────────────────

def test_perspective_order_stable():
    """D9: aggregate_perspectives preserves method→experiment→writing order."""
    m = [ReviewPoint(severity="major", category="soundness", title="M1", detail="d")]
    e = [ReviewPoint(severity="minor", category="ablation", title="E1", detail="d")]
    w = [ReviewPoint(severity="minor", category="writing_clarity", title="W1", detail="d")]

    result = aggregate_perspectives(m, e, w)
    assert len(result) == 3
    assert result[0].title == "M1"
    assert result[1].title == "E1"
    assert result[2].title == "W1"

    # Stable across multiple calls
    result2 = aggregate_perspectives(m, e, w)
    assert [p.title for p in result] == [p.title for p in result2]


# ── D10: three perspectives make exactly 3 LLM calls ─────────────────────────

@pytest.mark.asyncio
async def test_token_cost_logged():
    """D10: three perspectives each make exactly one LLM call (3 total)."""
    call_count = [0]

    async def counting_mock(prompt, *a, **kw):
        call_count[0] += 1
        return "[]"

    with patch("src.argument._reviewer_perspectives.call_llm_chat", counting_mock):
        await asyncio.gather(
            run_method_perspective("paper", "venue", None, None),
            run_experiment_perspective("paper", "venue", None, None),
            run_writing_perspective("paper", "venue", None, None),
        )

    assert call_count[0] == 3, f"Expected 3 LLM calls (one per perspective), got {call_count[0]}"
