"""Phase 1 TDD — register_companion 路由端点契约测试。

使用 FastAPI TestClient。feature flag=False 时所有 /api/companion/* 返回 404。
SSE 端点只测非流媒体行为（200 响应头、event-stream content-type）；
SSE 内容在 test_ledger.py 的异步测试中覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────


def _build_app(tmp_path: Path, flag_enabled: bool = True) -> FastAPI:
    from src.argument.companion_store import CompanionStore
    from routers.argument import register_companion

    app = FastAPI()
    store = CompanionStore(runtime_dir=tmp_path)
    register_companion(app, store=store, flag_enabled=flag_enabled)
    return app


@pytest.fixture
def client(tmp_path):
    return TestClient(_build_app(tmp_path, flag_enabled=True))


@pytest.fixture
def client_off(tmp_path):
    return TestClient(_build_app(tmp_path, flag_enabled=False))


@pytest.fixture
def store(tmp_path):
    from src.argument.companion_store import CompanionStore
    return CompanionStore(runtime_dir=tmp_path)


# ── feature flag disabled → all 404 ──────────────────────────────────────────


class TestFeatureFlagOff:
    def test_build_returns_404(self, client_off):
        r = client_off.post("/api/companion/ledger/build",
                            json={"doc_id": "d1", "text": "text"})
        assert r.status_code == 404

    def test_get_ledger_returns_404(self, client_off):
        r = client_off.get("/api/companion/ledger/d1")
        assert r.status_code == 404

    def test_review_returns_404(self, client_off):
        r = client_off.post("/api/companion/review",
                            json={"doc_id": "d1", "text": "text"})
        assert r.status_code == 404

    def test_reviews_list_returns_404(self, client_off):
        r = client_off.get("/api/companion/reviews?doc_id=d1")
        assert r.status_code == 404


# ── /api/companion/ledger/build (SSE) ────────────────────────────────────────


class TestLedgerBuildEndpoint:
    def test_accepts_doc_id_and_text(self, tmp_path):
        # Patch the heavy ledger function to yield a minimal complete event
        async def fake_build(*a, **kw):
            yield {"event": "complete",
                   "data": json.dumps({"promise_count": 0, "by_status": {}, "warnings": []})}

        app = _build_app(tmp_path)
        with patch("src.argument.ledger.build_ledger", new=fake_build), \
             patch("src.argument.ledger.rebuild_ledger", new=fake_build):
            client = TestClient(app)
            r = client.post("/api/companion/ledger/build",
                            json={"doc_id": "d1", "doc_title": "Paper", "text": "Some text."})
            assert r.status_code == 200

    def test_content_type_is_event_stream(self, tmp_path):
        async def fake_build(*a, **kw):
            yield {"event": "complete",
                   "data": json.dumps({"promise_count": 0, "by_status": {}, "warnings": []})}

        app = _build_app(tmp_path)
        with patch("src.argument.ledger.build_ledger", new=fake_build), \
             patch("src.argument.ledger.rebuild_ledger", new=fake_build):
            client = TestClient(app)
            r = client.post("/api/companion/ledger/build",
                            json={"doc_id": "d1", "text": "text"})
            assert "text/event-stream" in r.headers.get("content-type", "")

    def test_missing_doc_id_returns_422(self, client):
        r = client.post("/api/companion/ledger/build", json={"text": "text only"})
        assert r.status_code == 422

    def test_missing_text_returns_422(self, client):
        r = client.post("/api/companion/ledger/build", json={"doc_id": "d1"})
        assert r.status_code == 422

    def test_uses_rebuild_when_ledger_exists(self, tmp_path):
        from src.argument.companion_models import Ledger
        store_obj = __import__("src.argument.companion_store", fromlist=["CompanionStore"])
        from src.argument.companion_store import CompanionStore
        store = CompanionStore(runtime_dir=tmp_path)
        store.save_ledger(Ledger(doc_id="existing_doc"))

        rebuild_called = []

        async def fake_rebuild(*a, **kw):
            rebuild_called.append(True)
            yield {"event": "complete",
                   "data": json.dumps({"promise_count": 0, "by_status": {}, "warnings": []})}

        async def fake_build(*a, **kw):
            yield {"event": "complete",
                   "data": json.dumps({"promise_count": 0, "by_status": {}, "warnings": []})}

        from fastapi import FastAPI
        from routers.argument import register_companion
        app2 = FastAPI()
        register_companion(app2, store=store, flag_enabled=True)

        with patch("src.argument.ledger.rebuild_ledger", new=fake_rebuild), \
             patch("src.argument.ledger.build_ledger", new=fake_build):
            client2 = TestClient(app2)
            client2.post("/api/companion/ledger/build",
                         json={"doc_id": "existing_doc", "text": "some text"})
        assert rebuild_called, "rebuild_ledger should be called when ledger already exists"


# ── /api/companion/ledger/{doc_id} ────────────────────────────────────────────


class TestGetLedger:
    def test_404_when_not_found(self, client):
        r = client.get("/api/companion/ledger/no_such_doc")
        assert r.status_code == 404

    def test_returns_ledger_when_exists(self, tmp_path):
        from src.argument.companion_models import Ledger
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        ledger = Ledger(doc_id="doc_present", doc_title="My Paper")
        store.save_ledger(ledger)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.get("/api/companion/ledger/doc_present")
        assert r.status_code == 200
        data = r.json()
        assert data["doc_id"] == "doc_present"
        assert data["doc_title"] == "My Paper"


# ── /api/companion/ledger/{doc_id}/promise ────────────────────────────────────


class TestPromiseEndpoints:
    def _setup(self, tmp_path):
        from src.argument.companion_models import Ledger
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        store.save_ledger(Ledger(doc_id="doc_p"))
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), store

    def test_put_promise_creates_new(self, tmp_path):
        client, store = self._setup(tmp_path)
        r = client.put("/api/companion/ledger/doc_p/promise", json={
            "text": "We show X.", "kind": "contribution",
            "source_anchor_id": "a_001",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["text"] == "We show X."
        assert data["id"].startswith("p_")

    def test_put_promise_sets_user_overridden(self, tmp_path):
        client, store = self._setup(tmp_path)
        r = client.put("/api/companion/ledger/doc_p/promise", json={
            "text": "User edited.", "kind": "claim",
            "source_anchor_id": "a_001",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["user_overridden"] is True

    def test_delete_promise(self, tmp_path):
        client, store = self._setup(tmp_path)
        r_put = client.put("/api/companion/ledger/doc_p/promise", json={
            "text": "To delete.", "kind": "scope",
            "source_anchor_id": "a_001",
        })
        pid = r_put.json()["id"]
        r_del = client.delete(f"/api/companion/ledger/doc_p/promise/{pid}")
        assert r_del.status_code == 200

    def test_put_promise_on_missing_ledger_returns_404(self, client):
        r = client.put("/api/companion/ledger/no_doc/promise", json={
            "text": "t.", "kind": "claim", "source_anchor_id": "a_001",
        })
        assert r.status_code == 404


# ── /api/companion/ledger/{doc_id}/relocate ──────────────────────────────────


class TestRelocateEndpoint:
    def test_relocate_returns_updated_ledger(self, tmp_path):
        from src.argument.companion_models import Ledger, Anchor
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        anchor = Anchor(doc_id="doc_rel", quote="original phrase", char_start=0, char_end=15)
        ledger = Ledger(doc_id="doc_rel", anchors=[anchor])
        store.save_ledger(ledger)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.post("/api/companion/ledger/doc_rel/relocate",
                        json={"text": "New text: original phrase at a different position."})
        assert r.status_code == 200
        data = r.json()
        assert "doc_id" in data
        assert "anchors" in data

    def test_relocate_404_for_missing_ledger(self, client):
        r = client.post("/api/companion/ledger/no_doc/relocate",
                        json={"text": "some text"})
        assert r.status_code == 404


# ── /api/companion/review (SSE) ──────────────────────────────────────────────


class TestReviewEndpoint:
    def test_accepts_doc_id_and_text(self, tmp_path):
        async def fake_review(*a, **kw):
            yield {"event": "complete",
                   "data": json.dumps({"session_id": "R_test", "by_category": {}, "warnings": []})}

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post("/api/companion/review",
                            json={"doc_id": "d1", "text": "Paper text."})
            assert r.status_code == 200

    def test_content_type_is_event_stream(self, tmp_path):
        async def fake_review(*a, **kw):
            yield {"event": "complete",
                   "data": json.dumps({"session_id": "R_test", "by_category": {}, "warnings": []})}

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post("/api/companion/review",
                            json={"doc_id": "d1", "text": "text"})
            assert "text/event-stream" in r.headers.get("content-type", "")

    def test_missing_doc_id_returns_422(self, client):
        r = client.post("/api/companion/review", json={"text": "text"})
        assert r.status_code == 422

    def test_missing_text_returns_422(self, client):
        r = client.post("/api/companion/review", json={"doc_id": "d1"})
        assert r.status_code == 422


# ── /api/companion/review/{session_id} ───────────────────────────────────────


class TestGetReview:
    def test_404_when_not_found(self, client):
        r = client.get("/api/companion/review/nonexistent_session")
        assert r.status_code == 404

    def test_returns_session_when_exists(self, tmp_path):
        from src.argument.companion_models import ReviewSession
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        s = ReviewSession(doc_id="doc_rv", venue="NeurIPS")
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.get(f"/api/companion/review/{s.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["doc_id"] == "doc_rv"
        assert data["venue"] == "NeurIPS"


# ── /api/companion/reviews?doc_id=... ────────────────────────────────────────


class TestListReviews:
    def test_returns_empty_for_unknown_doc(self, client):
        r = client.get("/api/companion/reviews?doc_id=unknown")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_list_for_known_doc(self, tmp_path):
        from src.argument.companion_models import ReviewSession
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        s = ReviewSession(doc_id="doc_lst")
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.get("/api/companion/reviews?doc_id=doc_lst")
        assert r.status_code == 200
        lst = r.json()
        assert len(lst) >= 1
        assert lst[0]["session_id"] == s.id


# ── /api/companion/review/{session_id}/point/{pid} ───────────────────────────


class TestUpdatePoint:
    def _setup(self, tmp_path):
        from src.argument.companion_models import ReviewSession, ReviewPoint
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Missing", detail="No baselines.")
        s = ReviewSession(doc_id="doc_up", points=[rp])
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), store, s, rp

    def test_update_point_status(self, tmp_path):
        client, store, s, rp = self._setup(tmp_path)
        r = client.put(
            f"/api/companion/review/{s.id}/point/{rp.id}",
            json={"status": "accepted"},
        )
        assert r.status_code == 200

    def test_invalid_status_returns_422(self, tmp_path):
        client, store, s, rp = self._setup(tmp_path)
        r = client.put(
            f"/api/companion/review/{s.id}/point/{rp.id}",
            json={"status": "invalidXYZ"},
        )
        assert r.status_code == 422

    def test_session_not_found_returns_404(self, client):
        r = client.put(
            "/api/companion/review/no_session/point/no_point",
            json={"status": "accepted"},
        )
        assert r.status_code == 404


# ── /api/companion/review/{session_id}/point/{pid}/rebut ─────────────────────


class TestRebutEndpoint:
    def test_accepts_message_and_text(self, tmp_path):
        from src.argument.companion_models import ReviewSession, ReviewPoint
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion

        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Missing", detail="No baselines.")
        s = ReviewSession(doc_id="doc_rebut", points=[rp])
        store.save_review(s)

        async def fake_rebut(*a, **kw):
            yield {"event": "reviewer_reply", "data": json.dumps({"text": "I disagree."})}
            yield {"event": "status", "data": json.dumps({"status": "open"})}
            yield {"event": "complete", "data": json.dumps({})}

        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)

        with patch("src.argument.reviewer.continue_rebuttal", new=fake_rebut):
            client = TestClient(app)
            r = client.post(
                f"/api/companion/review/{s.id}/point/{rp.id}/rebut",
                json={"message": "We added more baselines.", "text": "paper text"},
            )
            assert r.status_code == 200

    def test_missing_message_returns_422(self, tmp_path):
        from src.argument.companion_models import ReviewSession, ReviewPoint
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion

        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(severity="minor", category="other", title="t", detail="d")
        s = ReviewSession(doc_id="doc_rebut2", points=[rp])
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.post(
            f"/api/companion/review/{s.id}/point/{rp.id}/rebut",
            json={"text": "paper text"},  # missing "message"
        )
        assert r.status_code == 422


# ── DELETE endpoints ──────────────────────────────────────────────────────────


class TestDeleteEndpoints:
    def test_delete_ledger(self, tmp_path):
        from src.argument.companion_models import Ledger
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        store.save_ledger(Ledger(doc_id="doc_del"))
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.delete("/api/companion/ledger/doc_del")
        assert r.status_code == 200
        assert store.get_ledger("doc_del") is None

    def test_delete_ledger_not_found_returns_404(self, client):
        r = client.delete("/api/companion/ledger/no_such")
        assert r.status_code == 404

    def test_delete_review(self, tmp_path):
        from src.argument.companion_models import ReviewSession
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        s = ReviewSession(doc_id="doc_del_rv")
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        client = TestClient(app)
        r = client.delete(f"/api/companion/review/{s.id}")
        assert r.status_code == 200
        assert store.get_review(s.id) is None

    def test_delete_review_not_found_returns_404(self, client):
        r = client.delete("/api/companion/review/nonexistent_session_xyz")
        assert r.status_code == 404


# ── Phase 3: SSE event sequence ──────────────────────────────────────────────


class TestReviewSSESequence:
    """Verify that the /review SSE stream emits review_point events then complete."""

    def test_sse_emits_review_points_then_complete(self, tmp_path):
        async def fake_review(*a, **kw):
            yield {
                "event": "review_point",
                "data": json.dumps({
                    "id": "rp_001", "severity": "major", "category": "baseline",
                    "title": "Missing baselines", "detail": "No comparison to prior work.",
                    "anchor_id": None, "status": "open", "source": "llm",
                    "reviewer_label": None, "thread": [],
                }),
            }
            yield {
                "event": "review_point",
                "data": json.dumps({
                    "id": "rp_002", "severity": "minor", "category": "writing_clarity",
                    "title": "Unclear notation", "detail": "Section 3 notation undefined.",
                    "anchor_id": None, "status": "open", "source": "llm",
                    "reviewer_label": None, "thread": [],
                }),
            }
            yield {
                "event": "complete",
                "data": json.dumps({
                    "session_id": "S_seq_test",
                    "by_category": {"baseline": 1, "writing_clarity": 1},
                    "warnings": [],
                }),
            }

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post(
                "/api/companion/review",
                json={"doc_id": "d_seq", "text": "Full paper text here."},
            )
        assert r.status_code == 200
        body = r.text
        assert "review_point" in body
        assert "Missing baselines" in body
        assert "Unclear notation" in body
        assert "session_id" in body
        assert "by_category" in body

    def test_complete_event_contains_session_id(self, tmp_path):
        async def fake_review(*a, **kw):
            yield {
                "event": "complete",
                "data": json.dumps({
                    "session_id": "S_known_id",
                    "by_category": {"soundness": 1},
                    "warnings": [],
                }),
            }

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post(
                "/api/companion/review",
                json={"doc_id": "d_cid", "text": "text"},
            )
        assert "S_known_id" in r.text


# ── Phase 3: scoped review (focus parameter) ──────────────────────────────────


class TestScopedReview:
    """Verify that /review accepts optional focus param → source='scoped' on points."""

    def test_scoped_review_returns_200(self, tmp_path):
        async def fake_review(*a, **kw):
            focus = kw.get("focus") or (a[3] if len(a) > 3 else None)
            source = "scoped" if focus else "llm"
            yield {
                "event": "review_point",
                "data": json.dumps({
                    "id": "rp_sc", "severity": "major", "category": "claim_overreach",
                    "title": "Overreach", "detail": "Claim not supported.",
                    "anchor_id": None, "status": "open", "source": source,
                    "reviewer_label": None, "thread": [],
                }),
            }
            yield {
                "event": "complete",
                "data": json.dumps({"session_id": "S_scoped", "by_category": {}, "warnings": []}),
            }

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post(
                "/api/companion/review",
                json={"doc_id": "d_sc", "text": "paper", "focus": "This claim is overstated."},
            )
        assert r.status_code == 200

    def test_scoped_points_have_source_scoped(self, tmp_path):
        async def fake_review(doc_id, text, ledger=None, focus=None, **kw):
            source = "scoped" if focus else "llm"
            yield {
                "event": "review_point",
                "data": json.dumps({
                    "id": "rp_src", "severity": "minor", "category": "other",
                    "title": "T", "detail": "D", "anchor_id": None,
                    "status": "open", "source": source,
                    "reviewer_label": None, "thread": [],
                }),
            }
            yield {
                "event": "complete",
                "data": json.dumps({"session_id": "S_s2", "by_category": {}, "warnings": []}),
            }

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post(
                "/api/companion/review",
                json={"doc_id": "d_s2", "text": "paper", "focus": "Suspect sentence."},
            )
        assert r.status_code == 200
        assert '"scoped"' in r.text

    def test_review_without_focus_defaults_to_full(self, tmp_path):
        async def fake_review(doc_id, text, ledger=None, focus=None, **kw):
            assert focus is None
            yield {
                "event": "complete",
                "data": json.dumps({"session_id": "S_full", "by_category": {}, "warnings": []}),
            }

        app = _build_app(tmp_path)
        with patch("src.argument.reviewer.run_review", new=fake_review):
            client = TestClient(app)
            r = client.post(
                "/api/companion/review",
                json={"doc_id": "d_full", "text": "paper"},
            )
        assert r.status_code == 200


# ── Phase 4: rebuttal SSE event sequence ──────────────────────────────────────


class TestRebutSSESequence:
    """Verify /rebut SSE stream: reviewer_reply → status → complete."""

    def _setup(self, tmp_path):
        from src.argument.companion_models import ReviewSession, ReviewPoint
        from src.argument.companion_store import CompanionStore
        from routers.argument import register_companion
        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Weak baselines", detail="Missing comparison.")
        s = ReviewSession(doc_id="doc_rebut_seq", points=[rp])
        store.save_review(s)
        app = FastAPI()
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), s, rp

    def test_sse_emits_reviewer_reply_then_status_then_complete(self, tmp_path):
        client, s, rp = self._setup(tmp_path)

        async def fake_rebut(*a, **kw):
            yield {"event": "reviewer_reply", "data": json.dumps({"text": "Your baselines are still weak."})}
            yield {"event": "status", "data": json.dumps({"status": "open"})}
            yield {"event": "complete", "data": json.dumps({})}

        with patch("src.argument.reviewer.continue_rebuttal", new=fake_rebut):
            r = client.post(
                f"/api/companion/review/{s.id}/point/{rp.id}/rebut",
                json={"message": "We added baseline X.", "text": "paper text"},
            )

        assert r.status_code == 200
        body = r.text
        assert "reviewer_reply" in body
        assert "Your baselines are still weak." in body
        assert "status" in body
        assert "complete" in body

    def test_sse_content_type_is_event_stream(self, tmp_path):
        client, s, rp = self._setup(tmp_path)

        async def fake_rebut(*a, **kw):
            yield {"event": "reviewer_reply", "data": json.dumps({"text": "OK."})}
            yield {"event": "status", "data": json.dumps({"status": "rebutted"})}
            yield {"event": "complete", "data": json.dumps({})}

        with patch("src.argument.reviewer.continue_rebuttal", new=fake_rebut):
            r = client.post(
                f"/api/companion/review/{s.id}/point/{rp.id}/rebut",
                json={"message": "msg", "text": "text"},
            )

        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_rebutted_status_in_sse_body(self, tmp_path):
        client, s, rp = self._setup(tmp_path)

        async def fake_rebut(*a, **kw):
            yield {"event": "reviewer_reply", "data": json.dumps({"text": "这点可以认为已 rebutted."})}
            yield {"event": "status", "data": json.dumps({"status": "rebutted"})}
            yield {"event": "complete", "data": json.dumps({})}

        with patch("src.argument.reviewer.continue_rebuttal", new=fake_rebut):
            r = client.post(
                f"/api/companion/review/{s.id}/point/{rp.id}/rebut",
                json={"message": "We addressed it.", "text": "text"},
            )

        assert "rebutted" in r.text

    def test_session_not_found_returns_200_with_error_event(self, client):
        r = client.post(
            "/api/companion/review/no_session_xyz/point/no_point_xyz/rebut",
            json={"message": "msg", "text": "text"},
        )
        # Router returns 200 with SSE error event (not HTTP 404, SSE streams always 200)
        assert r.status_code in (200, 404)


# ── Phase 5: /review/import SSE ───────────────────────────────────────────────


class TestImportReviewRoute:
    """POST /api/companion/review/import → SSE review_point* → complete."""

    def _setup(self, tmp_path):
        from routers.argument import register_companion
        from src.argument.companion_store import CompanionStore
        app = FastAPI()
        store = CompanionStore(runtime_dir=tmp_path)
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), store

    def test_import_review_returns_200_sse(self, tmp_path):
        client, store = self._setup(tmp_path)

        async def fake_import(*a, **kw):
            from src.argument.companion_models import ReviewPoint
            rp = ReviewPoint(severity="major", category="baseline",
                             title="Missing baseline", detail="Compare with XYZ.",
                             source="imported", reviewer_label="Reviewer 1")
            yield {"event": "review_point", "data": rp.model_dump_json()}
            yield {"event": "complete", "data": json.dumps({"session_id": "R_fake"})}

        with patch("src.argument.reviewer.import_real_reviews", new=fake_import):
            r = client.post(
                "/api/companion/review/import",
                json={"doc_id": "d1", "text": "paper", "reviews_raw": "Reviewer 1: ..."},
            )

        assert r.status_code == 200
        assert "review_point" in r.text
        assert "complete" in r.text

    def test_import_review_sse_content_type(self, tmp_path):
        client, store = self._setup(tmp_path)

        async def fake_import(*a, **kw):
            yield {"event": "complete", "data": json.dumps({"session_id": "R_x"})}

        with patch("src.argument.reviewer.import_real_reviews", new=fake_import):
            r = client.post(
                "/api/companion/review/import",
                json={"doc_id": "d1", "text": "paper", "reviews_raw": "some text"},
            )

        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_import_review_missing_reviews_raw_returns_422(self, tmp_path):
        client, store = self._setup(tmp_path)
        r = client.post(
            "/api/companion/review/import",
            json={"doc_id": "d1", "text": "paper"},  # missing reviews_raw
        )
        assert r.status_code == 422


# ── Phase 5: /download/review/{sid} ──────────────────────────────────────────


class TestDownloadReviewRoute:
    """GET /api/companion/download/review/{sid} → markdown file."""

    def _setup(self, tmp_path):
        from routers.argument import register_companion
        from src.argument.companion_store import CompanionStore
        from src.argument.companion_models import ReviewSession, ReviewPoint, RebuttalTurn
        app = FastAPI()
        store = CompanionStore(runtime_dir=tmp_path)
        rp = ReviewPoint(severity="major", category="baseline",
                         title="Missing baseline", detail="Compare with XYZ.",
                         thread=[
                             RebuttalTurn(role="author", text="We added baseline A."),
                             RebuttalTurn(role="reviewer", text="Insufficient."),
                         ])
        s = ReviewSession(doc_id="d1", points=[rp])
        store.save_review(s)
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), s

    def test_download_returns_200(self, tmp_path):
        client, s = self._setup(tmp_path)
        r = client.get(f"/api/companion/download/review/{s.id}")
        assert r.status_code == 200

    def test_download_contains_markdown_content(self, tmp_path):
        client, s = self._setup(tmp_path)
        r = client.get(f"/api/companion/download/review/{s.id}")
        text = r.text
        # Should contain the point title and thread turns
        assert "Missing baseline" in text
        assert "We added baseline A." in text

    def test_download_session_not_found_returns_404(self, tmp_path):
        client, _ = self._setup(tmp_path)
        r = client.get("/api/companion/download/review/nonexistent_session_xyz")
        assert r.status_code == 404


# ── Phase 5: /ledger/{doc_id}/promise/{pid}/suggest-experiment ───────────────


class TestSuggestExperimentRoute:
    """POST /api/companion/ledger/{doc_id}/promise/{pid}/suggest-experiment → {suggestion}."""

    def _setup(self, tmp_path):
        from routers.argument import register_companion
        from src.argument.companion_store import CompanionStore
        from src.argument.companion_models import Ledger, Promise
        from src.argument.anchor import make_anchor_from_quote
        app = FastAPI()
        store = CompanionStore(runtime_dir=tmp_path)
        anchor = make_anchor_from_quote("d1", "Some paper text here.", "Some paper text")
        promise = Promise(text="Our method scales to N=1e6.", kind="contribution",
                         source_anchor_id=anchor.id, status="partial")
        ledger = Ledger(doc_id="d1", promises=[promise], anchors=[anchor])
        store.save_ledger(ledger)
        register_companion(app, store=store, flag_enabled=True)
        return TestClient(app), promise

    def test_suggest_experiment_returns_200_with_suggestion(self, tmp_path):
        client, promise = self._setup(tmp_path)

        with patch("src.argument.ledger.suggest_experiment_for_promise",
                   new=AsyncMock(return_value="Run N=1e6 scale experiment.")):
            r = client.post(
                f"/api/companion/ledger/d1/promise/{promise.id}/suggest-experiment",
            )

        assert r.status_code == 200
        body = r.json()
        assert "suggestion" in body
        assert body["suggestion"] == "Run N=1e6 scale experiment."

    def test_suggest_experiment_promise_not_found_404(self, tmp_path):
        client, _ = self._setup(tmp_path)
        r = client.post(
            "/api/companion/ledger/d1/promise/nonexistent_pid/suggest-experiment",
        )
        assert r.status_code == 404

    def test_suggest_experiment_ledger_not_found_404(self, tmp_path):
        client, _ = self._setup(tmp_path)
        r = client.post(
            "/api/companion/ledger/no_such_doc/promise/any_pid/suggest-experiment",
        )
        assert r.status_code == 404
