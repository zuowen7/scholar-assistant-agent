"""Phase 3 TDD — reviewer unit tests (ledger_cross_check, coherence_check,
related_work_check, _load_venue_profile, run_review).

LLM 调用全部 mock，不发真实网络请求。
"""

from __future__ import annotations

import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

import pytest

from src.argument.companion_models import (
    Anchor, Ledger, Promise, ReviewSession, ReviewPoint,
)
from src.argument.anchor import make_anchor_from_quote


# ── helpers ───────────────────────────────────────────────────────────────────

SAMPLE_TEXT = """\
# Abstract

We propose method M that achieves state-of-the-art performance on benchmark B.
Our main contributions are: (1) contribution A; (2) contribution B at scale N=1e6.

# Introduction

The problem of X is important. Existing methods fail because of Z.
We address this by introducing W.

## Related Work

Smith (2022) proposed A. Jones (2023) extended it. However, none handled Y efficiently.

# Methodology

We use technique T with parameter P.

# Experiments

We evaluate on B. Results show 30% improvement. We compare against baseline C.

# Conclusion

We have shown that M works well on B. Future work includes scaling to larger datasets.
"""

def make_promise(status: str, note: str | None = None, kind: str = "contribution") -> Promise:
    anchor = make_anchor_from_quote("doc1", SAMPLE_TEXT, "contribution A")
    return Promise(
        text=f"Promise with status {status}",
        kind=kind,
        source_anchor_id=anchor.id,
        status=status,
        severity="error" if status in ("unpaid", "mismatch") else "warning",
        note=note,
    )

def make_ledger(promises: list[Promise]) -> Ledger:
    anchors = []
    for p in promises:
        a = make_anchor_from_quote("doc1", SAMPLE_TEXT, "contribution A")
        a = a.model_copy(update={"id": p.source_anchor_id})
        anchors.append(a)
    return Ledger(
        doc_id="doc1",
        doc_title="Test Paper",
        promises=promises,
        anchors=anchors,
    )


# ── ledger_cross_check ────────────────────────────────────────────────────────

class TestLedgerCrossCheck:
    def test_unpaid_produces_claim_overreach_point(self):
        from src.argument.reviewer import ledger_cross_check
        p = make_promise("unpaid")
        ledger = make_ledger([p])
        points = ledger_cross_check(ledger)
        assert len(points) == 1
        pt = points[0]
        assert pt.category == "claim_overreach"
        assert pt.severity == "major"
        assert pt.source == "ledger_check"
        assert pt.anchor_id == p.source_anchor_id

    def test_mismatch_produces_point_with_note_in_detail(self):
        from src.argument.reviewer import ledger_cross_check
        p = make_promise("mismatch", note="Found N=1e5, expected N=1e6")
        ledger = make_ledger([p])
        points = ledger_cross_check(ledger)
        assert len(points) == 1
        pt = points[0]
        assert pt.category == "claim_overreach"
        assert "N=1e5" in pt.detail or "mismatch" in pt.detail.lower() or "N=1e5" in pt.detail

    def test_paid_promise_produces_no_point(self):
        from src.argument.reviewer import ledger_cross_check
        p = make_promise("paid")
        ledger = make_ledger([p])
        points = ledger_cross_check(ledger)
        assert points == []

    def test_partial_promise_produces_no_point(self):
        from src.argument.reviewer import ledger_cross_check
        p = make_promise("partial")
        ledger = make_ledger([p])
        points = ledger_cross_check(ledger)
        assert points == []

    def test_none_ledger_returns_empty(self):
        from src.argument.reviewer import ledger_cross_check
        points = ledger_cross_check(None)
        assert points == []

    def test_multiple_problematic_promises(self):
        from src.argument.reviewer import ledger_cross_check
        promises = [
            make_promise("unpaid"),
            make_promise("mismatch", note="wrong scale"),
            make_promise("paid"),
        ]
        ledger = make_ledger(promises)
        points = ledger_cross_check(ledger)
        assert len(points) == 2


# ── coherence_check ───────────────────────────────────────────────────────────

class TestCoherenceCheck:
    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_deterministic_only(self):
        from src.argument.reviewer import coherence_check
        ledger = make_ledger([make_promise("paid")])
        points = await coherence_check(ledger, SAMPLE_TEXT)
        # Should return without error; may have 0-N deterministic points
        assert isinstance(points, list)

    @pytest.mark.asyncio
    async def test_inconsistency_point_from_llm(self):
        from src.argument.reviewer import coherence_check
        inconsistency_json = json.dumps([{
            "category": "inconsistency",
            "severity": "major",
            "title": "Conclusion contradicts abstract",
            "detail": "Abstract claims A but conclusion discusses B",
            "verbatim_quote": "We have shown that M works well",
        }])

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=inconsistency_json)):
            ledger = make_ledger([make_promise("paid")])
            points = await coherence_check(ledger, SAMPLE_TEXT)
        inconsistency_pts = [p for p in points if p.category == "inconsistency"]
        assert len(inconsistency_pts) >= 1
        assert inconsistency_pts[0].source == "coherence_check"

    @pytest.mark.asyncio
    async def test_gap_mismatch_point_from_llm(self):
        from src.argument.reviewer import coherence_check
        gap_json = json.dumps([{
            "category": "gap_mismatch",
            "severity": "major",
            "title": "Gap not addressed",
            "detail": "Intro claims gap Z but experiments don't address it",
            "verbatim_quote": "Existing methods fail because of Z",
        }])

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=gap_json)):
            ledger = make_ledger([make_promise("unpaid", kind="gap_statement")])
            points = await coherence_check(ledger, SAMPLE_TEXT)
        gap_pts = [p for p in points if p.category == "gap_mismatch"]
        assert len(gap_pts) >= 1

    @pytest.mark.asyncio
    async def test_llm_bad_json_returns_deterministic_only(self):
        from src.argument.reviewer import coherence_check
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="this is not json {{{")):
            ledger = make_ledger([make_promise("paid")])
            points = await coherence_check(ledger, SAMPLE_TEXT)
        # Should not crash; may return deterministic points only
        assert isinstance(points, list)


# ── related_work_check ────────────────────────────────────────────────────────

class TestRelatedWorkCheck:
    @pytest.mark.asyncio
    async def test_no_contrast_marker_produces_weak_positioning(self):
        from src.argument.reviewer import related_work_check
        text_no_contrast = """\
# Abstract

We propose method M.

## Related Work

Smith (2022) proposed A. Jones (2023) extended it. Liu (2021) used technique T.
Prior methods focused on B. Earlier work studied C.
"""
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="[]")):
            points = await related_work_check(text_no_contrast)
        wp_pts = [p for p in points if p.category == "weak_positioning"]
        assert len(wp_pts) >= 1
        assert all(p.source == "rw_check" for p in wp_pts)

    @pytest.mark.asyncio
    async def test_no_related_work_section_produces_info_point(self):
        from src.argument.reviewer import related_work_check
        text_no_rw = """\
# Abstract

We propose method M.

# Introduction

Previous work lacks X.

# Experiments

Results show improvement.
"""
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="[]")):
            points = await related_work_check(text_no_rw)
        # Either missing_related_work or weak_positioning info point
        relevant = [p for p in points if p.category in ("weak_positioning", "missing_related_work")]
        assert len(relevant) >= 1

    @pytest.mark.asyncio
    async def test_llm_returns_weak_positioning_point(self):
        from src.argument.reviewer import related_work_check
        rw_json = json.dumps([{
            "category": "weak_positioning",
            "severity": "major",
            "title": "False comparison claimed",
            "detail": "The paper claims it outperforms X but X does not address this task",
            "verbatim_quote": "none handled Y efficiently",
        }])
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=rw_json)):
            points = await related_work_check(SAMPLE_TEXT)
        llm_pts = [p for p in points if p.source == "rw_check" and p.title]
        assert len(llm_pts) >= 1

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_deterministic_only(self):
        from src.argument.reviewer import related_work_check
        # No cloud/ollama client → call_llm_chat returns ""
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="")):
            points = await related_work_check(SAMPLE_TEXT)
        assert isinstance(points, list)


# ── _load_venue_profile ───────────────────────────────────────────────────────

class TestLoadVenueProfile:
    def test_known_venue_neurips(self):
        from src.argument.reviewer import _load_venue_profile
        profile = _load_venue_profile("NeurIPS")
        assert profile  # non-empty
        assert isinstance(profile, str)

    def test_known_venue_chi(self):
        from src.argument.reviewer import _load_venue_profile
        profile = _load_venue_profile("CHI")
        assert profile

    def test_unknown_venue_returns_generic_plus_name(self):
        from src.argument.reviewer import _load_venue_profile
        profile = _load_venue_profile("MYCONF2099")
        assert profile
        assert "MYCONF2099" in profile or len(profile) > 50  # generic text included

    def test_none_venue_returns_generic(self):
        from src.argument.reviewer import _load_venue_profile
        profile = _load_venue_profile(None)
        assert profile
        assert isinstance(profile, str)


# ── run_review ────────────────────────────────────────────────────────────────

class TestRunReview:
    def _collect(self, coro) -> list[dict]:
        """Run async generator and collect all events."""
        async def _run():
            events = []
            async for ev in coro:
                events.append(ev)
            return events
        return asyncio.get_event_loop().run_until_complete(_run())

    def _make_store(self, tmp_path: Path):
        from src.argument.companion_store import CompanionStore
        return CompanionStore(runtime_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_yields_complete_event_with_session_id(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)
        llm_json = json.dumps([{
            "severity": "major",
            "category": "baseline",
            "title": "Weak baselines",
            "detail": "The baselines chosen are not competitive",
            "verbatim_quote": "compare against baseline C",
        }])

        events = []
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=llm_json)):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue="NeurIPS", persona="reviewer2", ledger=None, store=store,
            ):
                events.append(ev)

        event_types = [e["event"] for e in events]
        assert "complete" in event_types
        complete_data = json.loads(events[-1]["data"])
        assert "session_id" in complete_data
        assert complete_data["session_id"]  # non-empty

    @pytest.mark.asyncio
    async def test_focus_mode_only_yields_scoped_points(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)
        scoped_json = json.dumps([{
            "severity": "major",
            "category": "soundness",
            "title": "Claim unsupported",
            "detail": "This sentence makes an unsupported claim",
            "verbatim_quote": "30% improvement",
        }])

        events = []
        focus = {"quote": "30% improvement", "char_start": 100, "char_end": 115}
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=scoped_json)):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue=None, persona="reviewer2", ledger=None, store=store,
                focus=focus,
            ):
                events.append(ev)

        point_events = [e for e in events if e["event"] == "review_point"]
        for ev in point_events:
            data = json.loads(ev["data"])
            assert data["source"] == "scoped"

    @pytest.mark.asyncio
    async def test_checks_ledger_only(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)
        ledger = make_ledger([make_promise("unpaid")])

        events = []
        async for ev in run_review(
            doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
            venue=None, persona="reviewer2", ledger=ledger, store=store,
            checks=["ledger"],
        ):
            events.append(ev)

        point_events = [e for e in events if e["event"] == "review_point"]
        assert len(point_events) >= 1
        for ev in point_events:
            data = json.loads(ev["data"])
            assert data["source"] == "ledger_check"

    @pytest.mark.asyncio
    async def test_session_id_given_appends_to_existing(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)

        # Create an existing session
        existing_session = ReviewSession(
            doc_id="doc1",
            points=[],
            anchors=[],
        )
        store.save_review(existing_session)

        llm_json = json.dumps([{
            "severity": "minor",
            "category": "writing_clarity",
            "title": "Unclear prose",
            "detail": "Section 2 is unclear",
            "verbatim_quote": "technique T with parameter P",
        }])

        events = []
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=llm_json)):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue=None, persona="reviewer2", ledger=None, store=store,
                session_id=existing_session.id,
            ):
                events.append(ev)

        # Session should still be the existing one
        complete_data = json.loads(events[-1]["data"])
        assert complete_data["session_id"] == existing_session.id
        updated = store.get_review(existing_session.id)
        assert len(updated.points) >= 1

    @pytest.mark.asyncio
    async def test_llm_parse_failure_discards_bad_items(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)

        # Malformed: missing required fields
        bad_json = json.dumps([
            {"severity": "major"},  # missing title/detail/category/verbatim_quote
            {
                "severity": "major",
                "category": "baseline",
                "title": "Good point",
                "detail": "Well-formed item",
                "verbatim_quote": "30% improvement",
            },
        ])

        events = []
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=bad_json)):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue=None, persona="reviewer2", ledger=None, store=store,
            ):
                events.append(ev)

        # Should not crash, complete event present
        event_types = [e["event"] for e in events]
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_by_category_count_in_complete(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)
        llm_json = json.dumps([
            {"severity": "major", "category": "baseline", "title": "T1",
             "detail": "D1", "verbatim_quote": "30% improvement"},
            {"severity": "minor", "category": "writing_clarity", "title": "T2",
             "detail": "D2", "verbatim_quote": "technique T"},
        ])

        events = []
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=llm_json)):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue="NeurIPS", persona="reviewer2", ledger=None, store=store,
            ):
                events.append(ev)

        complete_data = json.loads(events[-1]["data"])
        assert "by_category" in complete_data
        assert isinstance(complete_data["by_category"], dict)

    @pytest.mark.asyncio
    async def test_llm_totally_unavailable_no_error_event(self, tmp_path):
        from src.argument.reviewer import run_review
        store = self._make_store(tmp_path)

        events = []
        with patch("src.argument.reviewer.call_llm_chat", new=AsyncMock(return_value="")):
            async for ev in run_review(
                doc_id="doc1", doc_title="Paper", text=SAMPLE_TEXT,
                venue=None, persona="reviewer2", ledger=None, store=store,
            ):
                events.append(ev)

        event_types = [e["event"] for e in events]
        assert "error" not in event_types
        assert "complete" in event_types


# ── continue_rebuttal ─────────────────────────────────────────────────────────

class TestContinueRebuttal:
    def _make_session_with_point(self, tmp_path: Path):
        from src.argument.companion_store import CompanionStore
        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(
            severity="major", category="baseline",
            title="Missing baselines", detail="No comparison to prior work.",
            anchor_id=None, status="open", source="llm",
        )
        session = ReviewSession(doc_id="doc1", points=[rp])
        store.save_review(session)
        return store, session, rp

    @pytest.mark.asyncio
    async def test_appends_author_and_reviewer_turns(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="Your rebuttal is insufficient.")):
            events = []
            async for ev in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="We added baselines X and Y.",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                events.append(ev)

        event_types = [e["event"] for e in events]
        assert "reviewer_reply" in event_types
        assert "status" in event_types
        assert "complete" in event_types

        # Thread should have both author and reviewer turns
        updated = store.get_review(session.id)
        updated_point = next(p for p in updated.points if p.id == rp.id)
        roles = [t.role for t in updated_point.thread]
        assert "author" in roles
        assert "reviewer" in roles

    @pytest.mark.asyncio
    async def test_author_turn_appears_before_reviewer_turn(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="Still not convinced.")):
            async for ev in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="We addressed this.",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                pass

        updated = store.get_review(session.id)
        point = next(p for p in updated.points if p.id == rp.id)
        assert point.thread[0].role == "author"
        assert point.thread[1].role == "reviewer"

    @pytest.mark.asyncio
    async def test_surrender_signal_changes_status_to_rebutted(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        surrender_reply = "这点可以认为已 rebutted — 你补的实验确实证明了这点。"
        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value=surrender_reply)):
            events = []
            async for ev in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="We added baselines.",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                events.append(ev)

        # status event should say rebutted
        status_events = [e for e in events if e["event"] == "status"]
        assert len(status_events) == 1
        import json
        assert json.loads(status_events[0]["data"])["status"] == "rebutted"

        # point in store should be updated
        updated = store.get_review(session.id)
        point = next(p for p in updated.points if p.id == rp.id)
        assert point.status == "rebutted"

    @pytest.mark.asyncio
    async def test_no_surrender_keeps_status_open(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="I am still not satisfied.")):
            events = []
            async for ev in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="We tried.",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                events.append(ev)

        import json
        status_events = [e for e in events if e["event"] == "status"]
        assert json.loads(status_events[0]["data"])["status"] == "open"

        updated = store.get_review(session.id)
        point = next(p for p in updated.points if p.id == rp.id)
        assert point.status == "open"

    @pytest.mark.asyncio
    async def test_session_persisted_with_thread(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(return_value="Your response is noted.")):
            async for _ in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="Our clarification.",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                pass

        # Reload from disk to verify persistence
        store2 = type(store)(runtime_dir=tmp_path)
        reloaded = store2.get_review(session.id)
        assert reloaded is not None
        point = next(p for p in reloaded.points if p.id == rp.id)
        assert len(point.thread) == 2

    @pytest.mark.asyncio
    async def test_session_not_found_yields_error(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store = type(self._make_session_with_point(tmp_path)[0])(runtime_dir=tmp_path)

        events = []
        async for ev in continue_rebuttal(
            session_id="nonexistent_session_xyz",
            point_id="any_point",
            author_message="msg",
            doc_text="text",
            store=store,
        ):
            events.append(ev)

        assert any(e["event"] == "error" for e in events)

    @pytest.mark.asyncio
    async def test_llm_unavailable_still_completes(self, tmp_path):
        from src.argument.reviewer import continue_rebuttal
        store, session, rp = self._make_session_with_point(tmp_path)

        with patch("src.argument.reviewer.call_llm_chat",
                   new=AsyncMock(side_effect=Exception("LLM down"))):
            events = []
            async for ev in continue_rebuttal(
                session_id=session.id,
                point_id=rp.id,
                author_message="msg",
                doc_text=SAMPLE_TEXT,
                store=store,
            ):
                events.append(ev)

        event_types = [e["event"] for e in events]
        assert "complete" in event_types
        assert "reviewer_reply" in event_types
