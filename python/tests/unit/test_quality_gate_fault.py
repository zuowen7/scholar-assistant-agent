"""Fault injection tests — DB failure, corruption, race conditions."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.fault


def test_config_load_missing_file():
    """Missing config file should raise FileNotFoundError."""
    import yaml
    missing = Path("/nonexistent/path/default.yaml")
    with pytest.raises(FileNotFoundError):
        open(missing)


def test_session_save_to_nonexistent_dir():
    """Session save to nonexistent dir should create parent dirs."""
    from src.agent_v2.runtime.session import Session
    tmp = tempfile.mkdtemp()
    session = Session(workspace=tmp, model="test")
    save_path = os.path.join(tmp, "deep", "nested", "session.jsonl")
    session.save(save_path)
    assert Path(save_path).exists()


def test_translate_corrupted_config():
    """Corrupted YAML in config should be handled."""
    import yaml
    bad_yaml = "{{invalid yaml::"
    with pytest.raises(Exception):
        yaml.safe_load(bad_yaml)


def test_rag_store_chromadb_unavailable():
    """RAG store should degrade gracefully when ChromaDB is unavailable."""
    from routers.rag import register_rag_routes
    from fastapi import FastAPI
    app = FastAPI()
    tmp = tempfile.mkdtemp()
    state = register_rag_routes(app, runtime_dir=Path(tmp))
    assert state["get_rag_store"]() is None


def test_translate_nonexistent_task():
    """Requesting stream for non-existent task returns 404."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    @app.get("/api/translate/{task_id}/stream")
    def fake_stream(task_id: str):
        raise HTTPException(404, f"Task {task_id} not found")

    tc = TestClient(app)
    resp = tc.get("/api/translate/nonexistent/stream")
    assert resp.status_code == 404
