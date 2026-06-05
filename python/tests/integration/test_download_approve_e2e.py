"""Download happy-path and approve flow integration tests.

Tests /api/download/{task_id} (400 + 200) and /api/agent/v2/approve
by injecting state into the closure variables of the route handlers.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CONFIG = """\
translator:
  engine: ollama
  model: qwen3:8b
  ollama_base_url: http://localhost:11434
  temperature: 0.3
  timeout: 300.0
chunker:
  max_tokens: 2048
  overlap_tokens: 128
formatter:
  output_format: bilingual
agent:
  model: qwen3:8b
  max_steps: 3
translate:
  max_tasks: 10
  max_upload_mb: 50
  max_pdf_pages: 50
features:
  argument_map_v2: true
  argument_companion: true
"""


# ── Closure helpers ──────────────────────────────────────────────────────


def _get_closure_var_by_name(handler: Any, name: str) -> Any:
    """Retrieve a closure variable from a function by its free-variable name."""
    if not hasattr(handler, "__closure__") or not handler.__closure__:
        return None
    freevars = handler.__code__.co_freevars
    if name not in freevars:
        # Try unwrapping
        if hasattr(handler, "__wrapped__"):
            return _get_closure_var_by_name(handler.__wrapped__, name)
        return None
    idx = freevars.index(name)
    return handler.__closure__[idx].cell_contents


def _find_route_endpoint(app, path: str, method: str = "GET"):
    """Find a FastAPI route endpoint by path and method."""
    from fastapi.routing import APIRoute
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    return None


def _inject_task(tasks_dict: dict, task_id: str, output_path: str) -> None:
    tasks_dict[task_id] = {
        "status": "done",
        "input_path": "/tmp/fake_input.txt",
        "output_path": output_path,
        "content": "Translated text.",
        "error": None,
        "filename": "test.txt",
        "blocks": None,
        "layout_doc": None,
        "block_translations": [],
        "chunks": [],
    }


def _inject_session(session_pool: dict, sid: str, approve_returns: bool = True) -> Any:
    """Create and inject a mock AgentSession into the pool."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.session_id = sid
    mock.approve = AsyncMock(return_value=approve_returns)
    mock.abort = AsyncMock()
    mock.journal = None
    mock.state = MagicMock(status="running")
    mock.task_queue = None
    mock.context = []
    mock.metadata = {"workspace_root": "/tmp/test_workspace"}
    session_pool[sid] = mock
    return mock


# ── App fixture ──────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api_factory import create_app

    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "default.yaml").write_text(CONFIG, encoding="utf-8")

    with (
        patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"),
        patch("api_factory.RUNTIME_DIR", Path(test_dir)),
        patch("api_factory.BASE_DIR", Path(test_dir)),
    ):
        app = create_app()
        yield TestClient(app, raise_server_exceptions=False)

    shutil.rmtree(test_dir, ignore_errors=True)


# ── Download endpoint ────────────────────────────────────────────────────


class TestDownloadTask:
    """GET /api/download/{task_id} — task state transitions."""

    def test_download_pending_task_returns_400(self, client):
        """Newly created task has status=pending → download must return 400."""
        resp = client.post("/api/translate", files={
            "file": ("test.txt", b"This is a test document for download testing.", "text/plain"),
        })
        if resp.status_code == 409:
            pytest.skip("Another task already active, skip")
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        task_id = resp.json()["task_id"]

        dl = client.get(f"/api/download/{task_id}")
        assert dl.status_code == 400, f"Expected 400 (not done), got {dl.status_code}: {dl.text}"
        assert "尚未完成" in dl.json()["detail"] or "尚未完成" in dl.text

    def test_download_done_task_returns_file(self, client, app_with_tasks):
        """Completed task with output file → download returns FileResponse."""
        task_id, client = app_with_tasks
        dl = client.get(f"/api/download/{task_id}")
        assert dl.status_code == 200
        assert "text/markdown" in dl.headers.get("content-type", "")
        assert b"translated content" in dl.content

    def test_download_task_not_found(self, client):
        resp = client.get("/api/download/task-not-exists-999")
        assert resp.status_code == 404


# ── Fixture for download happy path ──────────────────────────────────────


@pytest.fixture
def app_with_tasks(client):
    """Inject a completed task with a real output file into the app."""
    from fastapi.testclient import TestClient
    from api_factory import create_app

    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "default.yaml").write_text(CONFIG, encoding="utf-8")

    with (
        patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"),
        patch("api_factory.RUNTIME_DIR", Path(test_dir)),
        patch("api_factory.BASE_DIR", Path(test_dir)),
    ):
        app = create_app()
        tc = TestClient(app, raise_server_exceptions=False)

        # Create output file
        output_dir = Path(test_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        task_id = "happy_dl_001"
        out_file = output_dir / f"{task_id}_translated.md"
        out_file.write_text("# Test\n\nThis is translated content.", encoding="utf-8")

        # Inject into tasks dict
        ep = _find_route_endpoint(app, "/api/download/{task_id}", "GET")
        tasks = _get_closure_var_by_name(ep, "tasks")
        assert tasks is not None, "Could not find tasks dict in download handler closure"
        _inject_task(tasks, task_id, str(out_file))

        try:
            yield task_id, tc
        finally:
            pass

        shutil.rmtree(test_dir, ignore_errors=True)


# ── Approve endpoint ─────────────────────────────────────────────────────


class TestApproveEndpoint:
    """POST /api/agent/v2/approve/{session_id}/{event_id}."""

    def test_approve_nonexistent_session_404(self, client):
        resp = client.post("/api/agent/v2/approve/fake-session/evt_001", json={
            "decision": "allow_once",
        })
        assert resp.status_code in (403, 404)

    def test_approve_happy_path(self, client, agent_app_with_session):
        session_id, event_id, tc = agent_app_with_session
        resp = tc.post(
            f"/api/agent/v2/approve/{session_id}/{event_id}",
            json={"decision": "allow_once"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_approve_reject_decision(self, client, agent_app_with_session):
        session_id, event_id, tc = agent_app_with_session
        resp = tc.post(
            f"/api/agent/v2/approve/{session_id}/{event_id}",
            json={"decision": "deny"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ── Fixture for approve happy path ───────────────────────────────────────


@pytest.fixture
def agent_app_with_session():
    """Create an app with a mock session injected, returning session_id and event_id."""
    from fastapi.testclient import TestClient
    from api_factory import create_app

    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "default.yaml").write_text(CONFIG, encoding="utf-8")

    with (
        patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"),
        patch("api_factory.RUNTIME_DIR", Path(test_dir)),
        patch("api_factory.BASE_DIR", Path(test_dir)),
    ):
        app = create_app()
        tc = TestClient(app, raise_server_exceptions=False)

        # Inject mock session into _SESSION_POOL via module-level import
        import src.agent_v2.router as agent_router
        session_pool = agent_router._SESSION_POOL

        session_id = "test_session_approve_001"
        event_id = "evt_workspace_escape_001"
        _inject_session(session_pool, session_id)

        yield session_id, event_id, tc

    shutil.rmtree(test_dir, ignore_errors=True)
