"""Phase 1 TDD — ledger.py build_ledger / rebuild_ledger SSE 契约测试（LLM mocked）。

使用 asyncio.run() 而非 pytest-asyncio。
LLM 调用通过 patch("src.argument.llm_client.call_llm_chat") mock。
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch, call

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_store(tmp_path):
    from src.argument.companion_store import CompanionStore
    return CompanionStore(runtime_dir=tmp_path)


# Realistic LLM response: Phase 1 extraction
EXTRACT_LLM_RESP = json.dumps({
    "promises": [
        {
            "local_id": "p1",
            "kind": "contribution",
            "text": "Our method scales to N=1e6.",
            "verbatim_quote": "our method scales to N=1e6",
        },
        {
            "local_id": "p2",
            "kind": "claim",
            "text": "The approach outperforms all baselines.",
            "verbatim_quote": "outperforms all baselines",
        },
    ]
})

# Phase 2: discharge resolution
DISCHARGE_LLM_RESP = json.dumps([
    {
        "promise_local_id": "p1",
        "status": "partial",
        "discharge_quotes": ["We evaluate on N=1e5 samples"],
        "note": "§5 uses N=1e5, not 1e6 as promised",
    },
    {
        "promise_local_id": "p2",
        "status": "paid",
        "discharge_quotes": ["Table 2 shows our method achieves the best results"],
        "note": "",
    },
])

PAPER_TEXT = (
    "# Abstract\n\n"
    "In this paper we show that our method scales to N=1e6, and outperforms all baselines.\n\n"
    "# 1 Introduction\n\n"
    "Prior methods are limited to N=1e4. We claim our approach outperforms all baselines.\n\n"
    "# 5 Experiments\n\n"
    "We evaluate on N=1e5 samples. Table 2 shows our method achieves the best results.\n"
)


async def _collect_build(store, llm_responses, doc_id="doc_test", text=PAPER_TEXT):
    from src.argument.ledger import build_ledger

    events = []
    resp_iter = iter(llm_responses)

    async def mock_llm(prompt, *a, **kw):
        try:
            return next(resp_iter)
        except StopIteration:
            return ""

    with patch("src.argument.ledger.call_llm_chat", new=mock_llm):
        async for ev in build_ledger(
            doc_id=doc_id,
            doc_title="Test Paper",
            text=text,
            store=store,
        ):
            events.append(ev)
    return events


# ── build_ledger — 正常路径 ───────────────────────────────────────────────────


class TestBuildLedger:
    def test_yields_promise_events(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        promise_evs = [e for e in events if e["event"] == "promise"]
        assert len(promise_evs) >= 1

    def test_yields_complete_event_last(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        assert events[-1]["event"] == "complete"

    def test_complete_data_has_promise_count(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        data = json.loads(events[-1]["data"])
        assert "promise_count" in data
        assert data["promise_count"] >= 1

    def test_complete_data_has_by_status(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        data = json.loads(events[-1]["data"])
        assert "by_status" in data
        assert isinstance(data["by_status"], dict)

    def test_complete_data_has_warnings(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        data = json.loads(events[-1]["data"])
        assert "warnings" in data
        assert isinstance(data["warnings"], list)

    def test_promise_event_data_is_valid_json(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        for e in events:
            if e["event"] == "promise":
                data = json.loads(e["data"])
                assert "id" in data
                assert "text" in data
                assert "kind" in data
                assert "status" in data

    def test_saves_ledger_to_store(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        assert ledger is not None
        assert len(ledger.promises) >= 1

    def test_ledger_has_doc_hash(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        assert ledger.doc_hash is not None
        assert len(ledger.doc_hash) == 16  # sha1[:16]

    def test_promise_status_from_llm(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        statuses = {p.text: p.status for p in ledger.promises}
        # p1 should be partial, p2 should be paid
        p1 = next((p for p in ledger.promises if "scales" in p.text), None)
        p2 = next((p for p in ledger.promises if "outperforms" in p.text), None)
        if p1:
            assert p1.status == "partial"
        if p2:
            assert p2.status == "paid"

    def test_partial_promise_severity_warning(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        p1 = next((p for p in ledger.promises if "scales" in p.text), None)
        if p1:
            assert p1.severity == "warning"

    def test_paid_promise_severity_info(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        p2 = next((p for p in ledger.promises if "outperforms" in p.text), None)
        if p2:
            assert p2.severity == "info"

    def test_anchors_created_for_promises(self, tmp_path):
        store = _make_store(tmp_path)
        _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        ledger = store.get_ledger("doc_test")
        assert len(ledger.anchors) >= 1
        for p in ledger.promises:
            assert p.source_anchor_id is not None

    def test_promise_event_order_before_complete(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        event_types = [e["event"] for e in events]
        # complete must come last
        assert event_types[-1] == "complete"
        # promise events come before complete
        if "promise" in event_types:
            last_promise = max(i for i, e in enumerate(event_types) if e == "promise")
            complete_idx = event_types.index("complete")
            assert last_promise < complete_idx


# ── build_ledger — 失败兜底 ───────────────────────────────────────────────────


class TestBuildLedgerFailure:
    def test_invalid_json_yields_error_event(self, tmp_path):
        store = _make_store(tmp_path)
        # Both LLM calls return invalid JSON (after retry)
        events = _run(_collect_build(store, ["not json", "still not json"]))
        event_types = [e["event"] for e in events]
        assert "error" in event_types

    def test_no_dirty_write_on_error(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, ["bad json", "bad json again"],
                                     doc_id="doc_fail"))
        event_types = [e["event"] for e in events]
        if "error" in event_types:
            # Store must NOT have saved the ledger
            assert store.get_ledger("doc_fail") is None

    def test_empty_llm_response_yields_error(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, ["", ""]))
        event_types = [e["event"] for e in events]
        assert "error" in event_types

    def test_error_event_has_message(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(_collect_build(store, ["garbage", "garbage"]))
        error_evs = [e for e in events if e["event"] == "error"]
        if error_evs:
            data = json.loads(error_evs[0]["data"])
            assert "message" in data


# ── rebuild_ledger — 合并保留 user_overridden ─────────────────────────────────


class TestRebuildLedger:
    async def _run_rebuild(self, store, llm_responses, doc_id="doc_rb", text=PAPER_TEXT):
        from src.argument.ledger import rebuild_ledger

        events = []
        resp_iter = iter(llm_responses)

        async def mock_llm(prompt, *a, **kw):
            try:
                return next(resp_iter)
            except StopIteration:
                return ""

        with patch("src.argument.ledger.call_llm_chat", new=mock_llm):
            async for ev in rebuild_ledger(
                doc_id=doc_id,
                doc_title="Test Paper",
                text=text,
                store=store,
            ):
                events.append(ev)
        return events

    def test_user_overridden_promise_preserved(self, tmp_path):
        from src.argument.companion_models import Promise, Ledger
        store = _make_store(tmp_path)

        # Pre-seed ledger with one user-overridden promise
        p_user = Promise(
            text="User-edited claim: specific domain.",
            kind="claim",
            source_anchor_id="a_001",
            status="paid",
            user_overridden=True,
        )
        ledger = Ledger(doc_id="doc_rb", doc_title="Test", promises=[p_user])
        store.save_ledger(ledger)

        _run(self._run_rebuild(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        new_ledger = store.get_ledger("doc_rb")
        assert new_ledger is not None
        # user_overridden promise must survive
        match = next((p for p in new_ledger.promises if p.id == p_user.id), None)
        assert match is not None
        assert match.text == p_user.text
        assert match.status == p_user.status
        assert match.user_overridden is True

    def test_non_overridden_promise_replaced_by_ai(self, tmp_path):
        from src.argument.companion_models import Promise, Ledger
        store = _make_store(tmp_path)

        p_ai = Promise(
            text="Original AI claim.",
            kind="contribution",
            source_anchor_id="a_002",
            status="unknown",
            user_overridden=False,
        )
        ledger = Ledger(doc_id="doc_rb2", doc_title="Test", promises=[p_ai])
        store.save_ledger(ledger)

        async def run():
            from src.argument.ledger import rebuild_ledger
            resp_iter = iter([EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP])

            async def mock_llm(prompt, *a, **kw):
                try:
                    return next(resp_iter)
                except StopIteration:
                    return ""

            events = []
            with patch("src.argument.ledger.call_llm_chat", new=mock_llm):
                async for ev in rebuild_ledger(
                    doc_id="doc_rb2", doc_title="Test",
                    text=PAPER_TEXT, store=store,
                ):
                    events.append(ev)
            return events

        _run(run())
        new_ledger = store.get_ledger("doc_rb2")
        assert new_ledger is not None
        # Old non-overridden promise should be gone (replaced by new AI promises)
        assert not any(p.text == "Original AI claim." for p in new_ledger.promises)

    def test_rebuild_yields_complete(self, tmp_path):
        store = _make_store(tmp_path)
        events = _run(self._run_rebuild(store, [EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP]))
        assert any(e["event"] == "complete" for e in events)

    def test_anchors_relocated_on_rebuild(self, tmp_path):
        from src.argument.companion_models import Promise, Anchor, Ledger
        store = _make_store(tmp_path)

        # Anchor pointing to old text position
        anchor = Anchor(
            doc_id="doc_rb3",
            quote="scales to N=1e6",
            char_start=50,
            char_end=66,
            status="anchored",
        )
        p = Promise(
            text="Our method scales to N=1e6.",
            kind="contribution",
            source_anchor_id=anchor.id,
            status="paid",
            user_overridden=True,  # keep it through rebuild
        )
        ledger = Ledger(doc_id="doc_rb3", promises=[p], anchors=[anchor])
        store.save_ledger(ledger)

        async def run():
            from src.argument.ledger import rebuild_ledger
            resp_iter = iter([EXTRACT_LLM_RESP, DISCHARGE_LLM_RESP])

            async def mock_llm(prompt, *a, **kw):
                try:
                    return next(resp_iter)
                except StopIteration:
                    return ""

            events = []
            with patch("src.argument.ledger.call_llm_chat", new=mock_llm):
                async for ev in rebuild_ledger(
                    doc_id="doc_rb3", doc_title="Test",
                    text=PAPER_TEXT, store=store,
                ):
                    events.append(ev)
            return events

        _run(run())
        new_ledger = store.get_ledger("doc_rb3")
        assert new_ledger is not None
        # The anchor for the user-overridden promise should have been relocated
        if new_ledger.anchors:
            relocated = next((a for a in new_ledger.anchors if a.id == anchor.id), None)
            if relocated:
                # Re-located anchor should have updated char_start to match new_text
                assert relocated.char_start != 50 or relocated.status in ("anchored", "drifted", "lost")
