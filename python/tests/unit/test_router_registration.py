"""Unit tests for router registration — each router module registers routes into a FastAPI app."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Stubs ─────────────────────────────────────────────────────────────

def _stub_load_config():
    return {"translator": {}, "agent": {}}

def _stub_save_config(_cfg):
    pass

def _stub_build_cloud_client(**kw):
    return MagicMock()

def _stub_mask_api_key(_cfg):
    pass

def _stub_is_masked(_cfg):
    return False

def _stub_validate_file_path(_p):
    pass

RUNTIME_DIR = Path(__file__).parent.parent  # python/


# ── translate router ──────────────────────────────────────────────────

class TestRegisterTranslate:
    def test_routes_registered(self):
        """Happy path: register_translate adds expected endpoints."""
        from routers.translate import register_translate

        app = FastAPI()
        state = register_translate(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            save_config=_stub_save_config,
            build_cloud_client=_stub_build_cloud_client,
            mask_api_key=_stub_mask_api_key,
            is_masked=_stub_is_masked,
            validate_file_path=_stub_validate_file_path,
            runtime_dir=RUNTIME_DIR,
            rag_store_getter=lambda: None,
        )
        routes = [r.path for r in app.routes]
        assert "/api/translate" in routes
        assert "/api/translate/path" in routes
        assert "/api/translate/{task_id}/stream" in routes
        assert "/api/health" in routes
        assert "/api/config" in routes
        assert state is not None

    def test_state_keys(self):
        """After registration, state dict has expected keys."""
        from routers.translate import register_translate

        app = FastAPI()
        state = register_translate(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            save_config=_stub_save_config,
            build_cloud_client=_stub_build_cloud_client,
            mask_api_key=_stub_mask_api_key,
            is_masked=_stub_is_masked,
            validate_file_path=_stub_validate_file_path,
            runtime_dir=RUNTIME_DIR,
            rag_store_getter=lambda: None,
        )
        assert "tasks" in state
        assert "tm_store" in state
        assert "glossary_store" in state


# ── editor router ─────────────────────────────────────────────────────

class TestRegisterEditor:
    def test_routes_registered(self):
        """Happy path: register_editor adds expected endpoints."""
        from routers.editor import register_editor

        app = FastAPI()
        state = register_editor(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            runtime_dir=RUNTIME_DIR,
            data_root=RUNTIME_DIR / "data",
            rag_store_getter=lambda: None,
        )
        routes = [r.path for r in app.routes]
        assert "/api/edit" in routes
        assert "/api/complete" in routes
        assert "/api/export" in routes
        assert "/api/vision/analyze" in routes
        assert "/api/vision/ocr" in routes
        assert "/api/vision/chart" in routes
        assert "/api/vision/table" in routes
        assert state is not None


# ── mindmap router ────────────────────────────────────────────────────

class TestRegisterMindmap:
    def test_routes_registered(self):
        """Happy path: register_mindmap adds expected endpoints."""
        from routers.mindmap import register_mindmap

        app = FastAPI()
        state = register_mindmap(
            app,
            runtime_dir=RUNTIME_DIR,
            load_config=_stub_load_config,
            build_cloud_client=_stub_build_cloud_client,
        )
        routes = [r.path for r in app.routes]
        assert "/api/mindmap/save" in routes
        assert "/api/mindmap/load" in routes


# ── Error paths ───────────────────────────────────────────────────────

class TestRouterHealthEndpoint:
    """Verify /api/health returns ok when no tasks are running."""
    def test_health_ok(self):
        from routers.translate import register_translate

        app = FastAPI()
        register_translate(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            save_config=_stub_save_config,
            build_cloud_client=_stub_build_cloud_client,
            mask_api_key=_stub_mask_api_key,
            is_masked=_stub_is_masked,
            validate_file_path=_stub_validate_file_path,
            runtime_dir=RUNTIME_DIR,
            rag_store_getter=lambda: None,
        )
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestTranslateUploadValidation:
    """Verify /api/translate/upload rejects invalid payloads."""
    def test_no_file_400(self):
        from routers.translate import register_translate

        app = FastAPI()
        register_translate(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            save_config=_stub_save_config,
            build_cloud_client=_stub_build_cloud_client,
            mask_api_key=_stub_mask_api_key,
            is_masked=_stub_is_masked,
            validate_file_path=_stub_validate_file_path,
            runtime_dir=RUNTIME_DIR,
            rag_store_getter=lambda: None,
        )
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.post("/api/translate")
        assert resp.status_code in (400, 422)  # FastAPI validates missing file

    def test_stream_nonexistent_404(self):
        from routers.translate import register_translate

        app = FastAPI()
        register_translate(
            app,
            cloud_only=False,
            load_config=_stub_load_config,
            save_config=_stub_save_config,
            build_cloud_client=_stub_build_cloud_client,
            mask_api_key=_stub_mask_api_key,
            is_masked=_stub_is_masked,
            validate_file_path=_stub_validate_file_path,
            runtime_dir=RUNTIME_DIR,
            rag_store_getter=lambda: None,
        )
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/translate/nonexistent/stream")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]
