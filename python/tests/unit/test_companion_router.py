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
