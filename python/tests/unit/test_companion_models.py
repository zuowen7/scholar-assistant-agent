"""Phase 1 TDD — companion_models.py Pydantic 模型契约测试。

Tests: Anchor, Promise, Ledger, ReviewPoint, RebuttalTurn, ReviewSession
"""

from __future__ import annotations

import pytest
import time


# ── helpers ───────────────────────────────────────────────────────────────────


def _models():
    from src.argument.companion_models import (
        Anchor,
        Promise,
        Ledger,
        ReviewPoint,
        RebuttalTurn,
        ReviewSession,
        NodeKind,
        PromiseStatus,
        PointSeverity,
        PointCategory,
        PointStatus,
        PointSource,
    )
    return (
        Anchor, Promise, Ledger, ReviewPoint, RebuttalTurn, ReviewSession,
        NodeKind, PromiseStatus, PointSeverity, PointCategory, PointStatus, PointSource,
    )


# ── Promise ───────────────────────────────────────────────────────────────────


class TestPromise:
    def test_id_prefix(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.id.startswith("p_")

    def test_default_status_unknown(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.status == "unknown"

    def test_default_severity_info(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.severity == "info"

    def test_default_created_by_ai(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.created_by == "ai"

    def test_user_overridden_false_by_default(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.user_overridden is False

    def test_discharge_anchor_ids_empty_list(self):
        _, Promise, *_ = _models()
        p = Promise(text="We show X.", kind="contribution", source_anchor_id="a_001")
        assert p.discharge_anchor_ids == []

    def test_all_valid_kinds(self):
        _, Promise, *_ = _models()
        for kind in ("contribution", "claim", "hypothesis", "gap_statement", "scope"):
            p = Promise(text="text", kind=kind, source_anchor_id="a_001")
            assert p.kind == kind

    def test_invalid_kind_raises(self):
        _, Promise, *_ = _models()
        with pytest.raises(Exception):
            Promise(text="text", kind="invalid_kind", source_anchor_id="a_001")

    def test_all_valid_statuses(self):
        _, Promise, *_ = _models()
        for s in ("paid", "partial", "unpaid", "mismatch", "unknown"):
            p = Promise(text="t", kind="contribution", source_anchor_id="a_001", status=s)
            assert p.status == s

    def test_invalid_status_raises(self):
        _, Promise, *_ = _models()
        with pytest.raises(Exception):
            Promise(text="t", kind="contribution", source_anchor_id="a_001", status="broken")

    def test_note_optional(self):
        _, Promise, *_ = _models()
        p = Promise(text="t", kind="contribution", source_anchor_id="a_001")
        assert p.note is None


# ── Ledger ────────────────────────────────────────────────────────────────────


class TestLedger:
    def test_id_prefix(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_abc")
        assert ledger.id.startswith("L_")

    def test_promises_empty_by_default(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_abc")
        assert ledger.promises == []

    def test_anchors_empty_by_default(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_abc")
        assert ledger.anchors == []

    def test_doc_hash_optional(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_abc")
        assert ledger.doc_hash is None

    def test_last_built_at_is_float(self):
        _, _, Ledger, *_ = _models()
        before = time.time()
        ledger = Ledger(doc_id="doc_abc")
        after = time.time()
        assert before <= ledger.last_built_at <= after

    def test_doc_title_empty_string_default(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_abc")
        assert ledger.doc_title == ""

    def test_serialise_roundtrip(self):
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="d1", doc_title="My Paper")
        data = ledger.model_dump()
        Ledger2 = Ledger.__class__
        restored = Ledger.model_validate(data)
        assert restored.doc_id == "d1"
        assert restored.doc_title == "My Paper"


# ── RebuttalTurn ──────────────────────────────────────────────────────────────


class TestRebuttalTurn:
    def test_id_prefix(self):
        *_, RebuttalTurn, _, = _models()[:6]
        _, _, _, _, RebuttalTurn, _ = _models()[:6]
        rt = RebuttalTurn(role="author", text="My rebuttal here.")
        assert rt.id.startswith("rt_")

    def test_role_values(self):
        _, _, _, _, RebuttalTurn, _ = _models()[:6]
        for role in ("author", "reviewer"):
            rt = RebuttalTurn(role=role, text="text")
            assert rt.role == role

    def test_invalid_role_raises(self):
        _, _, _, _, RebuttalTurn, _ = _models()[:6]
        with pytest.raises(Exception):
            RebuttalTurn(role="editor", text="text")

    def test_created_at_is_float(self):
        _, _, _, _, RebuttalTurn, _ = _models()[:6]
        before = time.time()
        rt = RebuttalTurn(role="author", text="t")
        after = time.time()
        assert before <= rt.created_at <= after


# ── ReviewPoint ───────────────────────────────────────────────────────────────


class TestReviewPoint:
    def test_id_prefix(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(
            severity="major",
            category="baseline",
            title="Missing baselines",
            detail="The paper does not compare to X.",
        )
        assert rp.id.startswith("rp_")

    def test_default_status_open(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(severity="minor", category="writing_clarity",
                         title="t", detail="d")
        assert rp.status == "open"

    def test_default_source_llm(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(severity="minor", category="novelty", title="t", detail="d")
        assert rp.source == "llm"

    def test_default_thread_empty(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(severity="minor", category="novelty", title="t", detail="d")
        assert rp.thread == []

    def test_anchor_id_optional(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(severity="minor", category="novelty", title="t", detail="d")
        assert rp.anchor_id is None

    def test_reviewer_label_optional(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        rp = ReviewPoint(severity="minor", category="novelty", title="t", detail="d")
        assert rp.reviewer_label is None

    def test_valid_severity_values(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        for sev in ("minor", "major", "fatal"):
            rp = ReviewPoint(severity=sev, category="other", title="t", detail="d")
            assert rp.severity == sev

    def test_invalid_severity_raises(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        with pytest.raises(Exception):
            ReviewPoint(severity="critical", category="other", title="t", detail="d")

    def test_new_categories_present(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        for cat in ("inconsistency", "gap_mismatch", "weak_positioning", "term_drift"):
            rp = ReviewPoint(severity="minor", category=cat, title="t", detail="d")
            assert rp.category == cat

    def test_all_source_values(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        for src in ("llm", "ledger_check", "coherence_check", "rw_check", "scoped", "imported"):
            rp = ReviewPoint(severity="minor", category="other", title="t", detail="d", source=src)
            assert rp.source == src

    def test_valid_statuses(self):
        _, _, _, ReviewPoint, *_ = _models()[:6]
        for st in ("open", "rebutted", "accepted", "dismissed"):
            rp = ReviewPoint(severity="minor", category="other", title="t", detail="d", status=st)
            assert rp.status == st


# ── ReviewSession ─────────────────────────────────────────────────────────────


class TestReviewSession:
    def test_id_prefix(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.id.startswith("R_")

    def test_default_persona_reviewer2(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.persona == "reviewer2"

    def test_all_personas(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        for p in ("reviewer2", "ac", "domain_expert", "friendly", "real"):
            s = ReviewSession(doc_id="d1", persona=p)
            assert s.persona == p

    def test_invalid_persona_raises(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        with pytest.raises(Exception):
            ReviewSession(doc_id="d1", persona="chatgpt")

    def test_checks_default_llm(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.checks == ["llm"]

    def test_points_empty_by_default(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.points == []

    def test_anchors_empty_by_default(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.anchors == []

    def test_venue_optional(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.venue is None

    def test_doc_hash_optional(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        s = ReviewSession(doc_id="d1")
        assert s.doc_hash is None

    def test_created_at_is_float(self):
        _, _, _, _, _, ReviewSession = _models()[:6]
        before = time.time()
        s = ReviewSession(doc_id="d1")
        after = time.time()
        assert before <= s.created_at <= after

    def test_serialise_roundtrip(self):
        _, _, _, ReviewPoint, _, ReviewSession = _models()[:6]
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Missing baselines", detail="No comparison to X.")
        s = ReviewSession(doc_id="d1", venue="NeurIPS", points=[rp])
        data = s.model_dump()
        s2 = ReviewSession.model_validate(data)
        assert s2.doc_id == "d1"
        assert s2.venue == "NeurIPS"
        assert len(s2.points) == 1
        assert s2.points[0].category == "baseline"
