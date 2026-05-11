"""Phase 1 TDD — CompanionStore CRUD + 持久化契约测试。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_store(tmp_path: Path):
    from src.argument.companion_store import CompanionStore
    return CompanionStore(runtime_dir=tmp_path)


def _models():
    from src.argument.companion_models import (
        Anchor, Promise, Ledger, ReviewPoint, RebuttalTurn, ReviewSession,
    )
    return Anchor, Promise, Ledger, ReviewPoint, RebuttalTurn, ReviewSession


def _make_promise(source_anchor_id="a_001"):
    _, Promise, *_ = _models()
    return Promise(text="We scale to N=1e6.", kind="contribution",
                   source_anchor_id=source_anchor_id)


def _make_ledger(doc_id="doc_abc"):
    _, _, Ledger, *_ = _models()
    return Ledger(doc_id=doc_id, doc_title="Test Paper")


def _make_review(doc_id="doc_abc", venue="NeurIPS"):
    _, _, _, _, _, ReviewSession = _models()
    return ReviewSession(doc_id=doc_id, venue=venue)


# ── 目录结构 ───────────────────────────────────────────────────────────────────


class TestDirectorySetup:
    def test_ledger_dir_created(self, tmp_path):
        store = _make_store(tmp_path)
        assert (tmp_path / "companion" / "ledgers").exists()

    def test_review_dir_created(self, tmp_path):
        store = _make_store(tmp_path)
        assert (tmp_path / "companion" / "reviews").exists()

    def test_loads_existing_ledgers_on_init(self, tmp_path):
        # Pre-seed a ledger JSON file, then re-init store
        store = _make_store(tmp_path)
        ledger = _make_ledger("pre_existing_doc")
        store.save_ledger(ledger)
        # New store instance should load it
        store2 = _make_store(tmp_path)
        assert store2.get_ledger("pre_existing_doc") is not None

    def test_loads_existing_reviews_on_init(self, tmp_path):
        store = _make_store(tmp_path)
        s = _make_review("doc_abc")
        store.save_review(s)
        store2 = _make_store(tmp_path)
        assert store2.get_review(s.id) is not None


# ── 账本 CRUD ─────────────────────────────────────────────────────────────────


class TestLedgerCrud:
    def test_save_and_get(self, tmp_path):
        store = _make_store(tmp_path)
        ledger = _make_ledger("doc_1")
        store.save_ledger(ledger)
        got = store.get_ledger("doc_1")
        assert got is not None
        assert got.doc_id == "doc_1"
        assert got.doc_title == "Test Paper"

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_ledger("no_such_doc") is None

    def test_list_ledgers_returns_summary(self, tmp_path):
        store = _make_store(tmp_path)
        ledger = _make_ledger("doc_x")
        store.save_ledger(ledger)
        lst = store.list_ledgers()
        assert len(lst) >= 1
        entry = next(e for e in lst if e["doc_id"] == "doc_x")
        assert "doc_title" in entry
        assert "promise_count" in entry
        assert "last_built_at" in entry

    def test_delete_ledger(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_ledger(_make_ledger("doc_del"))
        store.delete_ledger("doc_del")
        assert store.get_ledger("doc_del") is None

    def test_delete_nonexistent_noop(self, tmp_path):
        store = _make_store(tmp_path)
        store.delete_ledger("not_there")  # should not raise

    def test_save_overrides_previous(self, tmp_path):
        store = _make_store(tmp_path)
        _, _, Ledger, *_ = _models()
        ledger = Ledger(doc_id="doc_ov", doc_title="Version 1")
        store.save_ledger(ledger)
        ledger2 = Ledger(doc_id="doc_ov", doc_title="Version 2",
                         id=ledger.id)  # same doc_id, updated title
        store.save_ledger(ledger2)
        got = store.get_ledger("doc_ov")
        assert got.doc_title == "Version 2"


# ── 持久化文件名安全化 ────────────────────────────────────────────────────────


class TestDocIdSafeFilename:
    def test_special_chars_replaced(self, tmp_path):
        store = _make_store(tmp_path)
        doc_id = "some/path:with?special*chars"
        ledger = _make_ledger(doc_id)
        store.save_ledger(ledger)
        ledger_dir = tmp_path / "companion" / "ledgers"
        files = list(ledger_dir.glob("*.json"))
        assert len(files) == 1
        name = files[0].name
        # Must not contain problematic chars
        assert "/" not in name
        assert ":" not in name
        assert "?" not in name
        assert "*" not in name

    def test_safe_filename_matches_re_sub(self, tmp_path):
        store = _make_store(tmp_path)
        doc_id = "untitled-abc123.md"
        ledger = _make_ledger(doc_id)
        store.save_ledger(ledger)
        expected_stem = re.sub(r'[^\w.-]', '_', doc_id)
        ledger_dir = tmp_path / "companion" / "ledgers"
        files = list(ledger_dir.glob("*.json"))
        assert any(expected_stem in f.name for f in files)


# ── Promise CRUD ──────────────────────────────────────────────────────────────


class TestPromiseCrud:
    def test_upsert_adds_promise(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_ledger(_make_ledger("doc_p"))
        p = _make_promise()
        store.upsert_promise("doc_p", p)
        ledger = store.get_ledger("doc_p")
        ids = [x.id for x in ledger.promises]
        assert p.id in ids

    def test_upsert_updates_existing(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_ledger(_make_ledger("doc_p2"))
        p = _make_promise()
        store.upsert_promise("doc_p2", p)
        _, Promise, *_ = _models()
        p_updated = Promise(id=p.id, text="Updated text.", kind="claim",
                            source_anchor_id="a_002")
        store.upsert_promise("doc_p2", p_updated)
        ledger = store.get_ledger("doc_p2")
        match = next(x for x in ledger.promises if x.id == p.id)
        assert match.text == "Updated text."

    def test_upsert_nonexistent_ledger_raises_or_noop(self, tmp_path):
        store = _make_store(tmp_path)
        p = _make_promise()
        # Should either raise KeyError/ValueError or silently do nothing — not crash with AttributeError
        try:
            store.upsert_promise("nonexistent_doc", p)
        except (KeyError, ValueError):
            pass  # acceptable

    def test_delete_promise(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_ledger(_make_ledger("doc_dp"))
        p = _make_promise()
        store.upsert_promise("doc_dp", p)
        store.delete_promise("doc_dp", p.id)
        ledger = store.get_ledger("doc_dp")
        assert all(x.id != p.id for x in ledger.promises)


# ── Review CRUD ───────────────────────────────────────────────────────────────


class TestReviewCrud:
    def test_save_and_get(self, tmp_path):
        store = _make_store(tmp_path)
        s = _make_review("doc_r")
        store.save_review(s)
        got = store.get_review(s.id)
        assert got is not None
        assert got.doc_id == "doc_r"
        assert got.venue == "NeurIPS"

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_review("no_such_session") is None

    def test_list_reviews_for_doc(self, tmp_path):
        store = _make_store(tmp_path)
        s1 = _make_review("docA", "NeurIPS")
        s2 = _make_review("docA", "ICML")
        s3 = _make_review("docB", "CHI")
        store.save_review(s1)
        store.save_review(s2)
        store.save_review(s3)
        lst = store.list_reviews("docA")
        ids = [e["session_id"] for e in lst]
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id not in ids

    def test_list_reviews_includes_summary_fields(self, tmp_path):
        store = _make_store(tmp_path)
        s = _make_review("docZ")
        store.save_review(s)
        lst = store.list_reviews("docZ")
        assert len(lst) == 1
        entry = lst[0]
        for field in ("session_id", "venue", "persona", "created_at"):
            assert field in entry

    def test_delete_review(self, tmp_path):
        store = _make_store(tmp_path)
        s = _make_review("doc_del")
        store.save_review(s)
        store.delete_review(s.id)
        assert store.get_review(s.id) is None

    def test_multiple_reviews_per_doc(self, tmp_path):
        store = _make_store(tmp_path)
        s1 = _make_review("docM", "NeurIPS")
        s2 = _make_review("docM", "NeurIPS")
        store.save_review(s1)
        store.save_review(s2)
        assert store.get_review(s1.id) is not None
        assert store.get_review(s2.id) is not None
        lst = store.list_reviews("docM")
        assert len(lst) == 2


# ── update_point / append_turns ───────────────────────────────────────────────


class TestPointAndTurnUpdates:
    def _session_with_point(self, tmp_path):
        store = _make_store(tmp_path)
        _, _, _, ReviewPoint, _, ReviewSession = _models()
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Missing", detail="No baselines.")
        s = ReviewSession(doc_id="doc_t", points=[rp])
        store.save_review(s)
        return store, s, rp

    def test_update_point_status(self, tmp_path):
        store, s, rp = self._session_with_point(tmp_path)
        store.update_point(s.id, rp.id, "accepted")
        got = store.get_review(s.id)
        point = next(p for p in got.points if p.id == rp.id)
        assert point.status == "accepted"

    def test_update_invalid_point_noop_or_raises(self, tmp_path):
        store, s, _ = self._session_with_point(tmp_path)
        try:
            store.update_point(s.id, "nonexistent_point_id", "dismissed")
        except (KeyError, ValueError):
            pass  # acceptable

    def test_append_turns(self, tmp_path):
        store, s, rp = self._session_with_point(tmp_path)
        _, _, _, _, RebuttalTurn, _ = _models()
        turns = [
            RebuttalTurn(role="author", text="We added more baselines."),
            RebuttalTurn(role="reviewer", text="I remain unconvinced."),
        ]
        store.append_turns(s.id, rp.id, turns)
        got = store.get_review(s.id)
        point = next(p for p in got.points if p.id == rp.id)
        assert len(point.thread) == 2
        assert point.thread[0].role == "author"
        assert point.thread[1].role == "reviewer"

    def test_append_turns_accumulates(self, tmp_path):
        store, s, rp = self._session_with_point(tmp_path)
        _, _, _, _, RebuttalTurn, _ = _models()
        store.append_turns(s.id, rp.id, [RebuttalTurn(role="author", text="A")])
        store.append_turns(s.id, rp.id, [RebuttalTurn(role="reviewer", text="B")])
        got = store.get_review(s.id)
        point = next(p for p in got.points if p.id == rp.id)
        assert len(point.thread) == 2


# ── 原子性写入（atomic flush）─────────────────────────────────────────────────


class TestAtomicFlush:
    def test_json_file_valid_after_save_ledger(self, tmp_path):
        store = _make_store(tmp_path)
        ledger = _make_ledger("doc_flush")
        store.save_ledger(ledger)
        ledger_dir = tmp_path / "companion" / "ledgers"
        files = list(ledger_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["doc_id"] == "doc_flush"

    def test_json_file_valid_after_save_review(self, tmp_path):
        store = _make_store(tmp_path)
        s = _make_review("doc_fr")
        store.save_review(s)
        review_dir = tmp_path / "companion" / "reviews"
        files = list(review_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["doc_id"] == "doc_fr"
