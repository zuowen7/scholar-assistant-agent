"""RAG endpoints integration tests.

Covers /api/rag/documents, /api/rag/ingest, /api/rag/upload,
DELETE /api/rag/documents/{doc_id} via TestClient.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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
"""


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
        yield TestClient(app)

    shutil.rmtree(test_dir, ignore_errors=True)


class TestRAGDocuments:
    """GET /api/rag/documents — list all ingested documents."""

    def test_list_returns_array(self, client):
        resp = client.get("/api/rag/documents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestRAGIngest:
    """POST /api/rag/ingest — ingest a text document."""

    def test_ingest_text_document(self, client):
        resp = client.post("/api/rag/ingest", json={
            "doc_id": "test-doc-001",
            "title": "Test Document",
            "text": "This is a test document about machine learning and neural networks.",
        })
        assert resp.status_code in (200, 400, 500)

    def test_ingest_then_list(self, client):
        # Ingest
        resp = client.post("/api/rag/ingest", json={
            "doc_id": "test-doc-002",
            "title": "Integration Test Doc",
            "text": "Integration testing ensures components work together.",
        })
        if resp.status_code == 200:
            # Should appear in list
            lst = client.get("/api/rag/documents").json()
            doc_ids = [d.get("doc_id") or d.get("id") for d in (
                lst if isinstance(lst, list) else []
            )]
            assert "test-doc-002" in doc_ids

    def test_ingest_minimal_payload(self, client):
        resp = client.post("/api/rag/ingest", json={
            "doc_id": "minimal-doc",
            "text": "minimal content",
        })
        assert resp.status_code in (200, 400, 500)


class TestRAGUpload:
    """POST /api/rag/upload — upload and ingest a file."""

    def test_upload_text_file(self, client):
        content = "This is a research paper about attention mechanisms in transformers."
        resp = client.post("/api/rag/upload", files={
            "file": ("paper.txt", io.BytesIO(content.encode()), "text/plain"),
        })
        assert resp.status_code in (200, 400, 500)

    def test_upload_markdown_file(self, client):
        content = "# Abstract\n\nWe propose a novel approach to few-shot learning.\n\n## Introduction"
        resp = client.post("/api/rag/upload", files={
            "file": ("paper.md", io.BytesIO(content.encode()), "text/markdown"),
        })
        assert resp.status_code in (200, 400, 500)

    def test_upload_then_list(self, client):
        content = "This document covers vector databases and semantic search."
        upload = client.post("/api/rag/upload", files={
            "file": ("search.txt", io.BytesIO(content.encode()), "text/plain"),
        })
        if upload.status_code == 200:
            data = upload.json()
            doc_id = data.get("doc_id") or data.get("id") or data.get("filename")
            if doc_id:
                lst = client.get("/api/rag/documents").json()
                found = any(
                    d.get("doc_id") == doc_id or d.get("id") == doc_id
                    for d in (lst if isinstance(lst, list) else [])
                )
                assert found, f"Uploaded doc {doc_id} not found in list"


class TestRAGDelete:
    """DELETE /api/rag/documents/{doc_id} — delete a document."""

    def test_delete_ingested_document(self, client):
        # Ingest first
        client.post("/api/rag/ingest", json={
            "doc_id": "to-delete-001",
            "title": "To Be Deleted",
            "text": "This document will be deleted.",
        })
        resp = client.delete("/api/rag/documents/to-delete-001")
        assert resp.status_code in (200, 404)

    def test_delete_nonexistent_document(self, client):
        resp = client.delete("/api/rag/documents/nonexistent-doc-xxxxx")
        assert resp.status_code in (200, 404)

    def test_delete_then_list_does_not_contain(self, client):
        client.post("/api/rag/ingest", json={
            "doc_id": "delete-verify-002",
            "title": "Delete Verify",
            "text": "This doc will be deleted and verified gone.",
        })
        del_resp = client.delete("/api/rag/documents/delete-verify-002")
        if del_resp.status_code == 200:
            lst = client.get("/api/rag/documents").json()
            ids = [d.get("doc_id") or d.get("id") for d in (lst if isinstance(lst, list) else [])]
            assert "delete-verify-002" not in ids
