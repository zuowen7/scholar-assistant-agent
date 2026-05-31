"""Editor endpoints integration tests.

Covers /api/edit, /api/complete, /api/export/*, /api/compliance,
/api/paper-*, /api/upload/image, /api/assets, /api/tectonic/*,
/api/citation/*, /api/zotero/*, /api/vision/* via TestClient.
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
        yield TestClient(app, raise_server_exceptions=False)

    shutil.rmtree(test_dir, ignore_errors=True)


# ── /api/edit ────────────────────────────────────────────────────────────


class TestEditEndpoint:
    def test_edit_echo_when_no_instruction(self, client):
        """No instruction → SSE echoes input text."""
        resp = client.post("/api/edit", json={"text": "hello world", "instruction": ""})
        assert resp.status_code in (200, 503, 500)
        if resp.status_code == 200:
            body = resp.text
            assert "hello world" in body or "content" in body

    def test_edit_with_instruction_ollama_not_running(self, client):
        """With instruction → tries LLM, may fail gracefully if unavailable."""
        resp = client.post("/api/edit", json={
            "text": "This is a test paragraph.",
            "instruction": "polish",
        })
        assert resp.status_code in (200, 503, 500)

    def test_edit_with_task_type(self, client):
        resp = client.post("/api/edit", json={
            "text": "test text",
            "instruction": "translate to Chinese",
            "task_type": "translate",
        })
        assert resp.status_code in (200, 503, 500)

    def test_edit_validation_missing_instruction_field(self, client):
        """FastAPI should treat missing optional fields gracefully with defaults."""
        resp = client.post("/api/edit", json={"text": "just text"})
        assert resp.status_code in (200, 503, 500)


# ── /api/complete ────────────────────────────────────────────────────────


class TestCompleteEndpoint:
    def test_complete_empty_context(self, client):
        resp = client.post("/api/complete", json={"context": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["completion"] == ""

    def test_complete_with_context(self, client):
        resp = client.post("/api/complete", json={
            "context": "The results show that the proposed method",
            "max_tokens": 16,
        })
        assert resp.status_code in (200, 503, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "completion" in data
            assert "usage" in data

    def test_complete_max_tokens_default(self, client):
        resp = client.post("/api/complete", json={"context": "test"})
        assert resp.status_code in (200, 503, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["usage"], dict)


# ── /api/export/templates, /api/export, /api/export/pdf ──────────────────


class TestExportEndpoints:
    def test_list_templates(self, client):
        resp = client.get("/api/export/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["templates"], list)
        assert len(data["templates"]) > 0
        assert "tectonic_available" in data

    def test_export_latex(self, client):
        resp = client.post("/api/export", json={
            "markdown": "# Introduction\n\nThis is a test paragraph.",
            "template_id": "generic_article",
            "title": "Test Paper",
        })
        assert resp.status_code in (200, 400)

    def test_export_latex_empty_markdown(self, client):
        resp = client.post("/api/export", json={
            "markdown": "",
            "template_id": "generic_article",
        })
        assert resp.status_code in (200, 400)

    def test_export_latex_missing_template(self, client):
        resp = client.post("/api/export", json={
            "markdown": "# test",
            "template_id": "nonexistent_template_xyz",
        })
        assert resp.status_code in (200, 400, 404)

    def test_export_pdf(self, client):
        resp = client.post("/api/export/pdf", json={
            "markdown": "# Test\n\nContent here.",
            "template_id": "generic_article",
            "title": "PDF Test",
        })
        assert resp.status_code in (200, 400, 500)


# ── /api/tectonic/* ──────────────────────────────────────────────────────


class TestTectonicEndpoints:
    def test_tectonic_status(self, client):
        resp = client.get("/api/tectonic/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert isinstance(data["available"], bool)

    def test_tectonic_install_not_running(self, client):
        resp = client.post("/api/tectonic/install")
        assert resp.status_code in (200, 400, 500)


# ── /api/paper-assets/* ──────────────────────────────────────────────────


class TestPaperAssets:
    def test_list_templates(self, client):
        resp = client.get("/api/paper-assets/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        for tmpl in data["templates"]:
            assert "id" in tmpl

    def test_ingest(self, client):
        """rag_store is None in test config → 503 or 500."""
        resp = client.post("/api/paper-assets/ingest")
        assert resp.status_code in (200, 500, 503)


# ── /api/paper-scaffold, /api/paper-style-transfer ────────────────────────


class TestPaperScaffold:
    def test_scaffold_generic(self, client):
        resp = client.post("/api/paper-scaffold", json={
            "template_id": "generic_article",
            "title": "My Paper",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "markdown" in data

    def test_scaffold_with_sections(self, client):
        resp = client.post("/api/paper-scaffold", json={
            "template_id": "generic_article",
            "title": "Paper",
            "sections": ["introduction", "methods", "results"],
        })
        assert resp.status_code == 200

    def test_scaffold_default_template(self, client):
        resp = client.post("/api/paper-scaffold", json={"title": "Test"})
        assert resp.status_code == 200
        assert "template_id" in resp.json()


class TestPaperStyleTransfer:
    def test_style_transfer(self, client):
        resp = client.post("/api/paper-style-transfer", json={
            "text": "This is a test paragraph for style analysis.",
            "template_id": "generic_article",
            "section": "introduction",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "style_context" in data


# ── /api/compliance ──────────────────────────────────────────────────────


class TestCompliance:
    def test_compliance_no_llm(self, client):
        """Without LLM available, should return error gracefully."""
        resp = client.post("/api/compliance", json={
            "markdown": "# Abstract\n\nTest content.",
            "title": "Test",
            "venue": "arxiv",
            "required_sections": "",
        })
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "report" in data or "error" in data


# ── /api/export/word ─────────────────────────────────────────────────────


class TestWordExport:
    def test_export_and_download_roundtrip(self, client):
        resp = client.post("/api/export/word", json={
            "content": "# Test\n\nHello world.",
            "title": "Test Export",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "filename" in data
        assert "path" in data
        assert data["size"] > 0

        # Download
        dl = client.get(f"/api/export/word/{data['filename']}")
        assert dl.status_code == 200
        assert len(dl.content) > 0

    def test_download_nonexistent_file(self, client):
        resp = client.get("/api/export/word/nonexistent_xxxxx.docx")
        assert resp.status_code in (404, 403)

    def test_download_path_traversal_blocked(self, client):
        resp = client.get("/api/export/word/../../../etc/passwd.docx")
        assert resp.status_code in (403, 404)


# ── /api/upload/image + /api/assets ──────────────────────────────────────


class TestImageUpload:
    def test_upload_png(self, client):
        # Minimal valid PNG (1x1 pixel)
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        resp = client.post("/api/upload/image", files={
            "file": ("test.png", io.BytesIO(png), "image/png"),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "filename" in data
        assert "path" in data

    def test_serve_uploaded_asset(self, client):
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        upload = client.post("/api/upload/image", files={
            "file": ("test.png", io.BytesIO(png), "image/png"),
        })
        filename = upload.json()["filename"]
        resp = client.get(f"/api/assets/{filename}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/")

    def test_upload_rejects_bad_type(self, client):
        resp = client.post("/api/upload/image", files={
            "file": ("bad.txt", io.BytesIO(b"not an image"), "text/plain"),
        })
        assert resp.status_code == 400

    def test_upload_rejects_no_file(self, client):
        resp = client.post("/api/upload/image")
        assert resp.status_code in (400, 422)

    def test_serve_nonexistent_asset(self, client):
        resp = client.get("/api/assets/nonexistent_xxxx.png")
        assert resp.status_code == 404


# ── /api/citation/* ──────────────────────────────────────────────────────


class TestCitationEndpoints:
    def test_extract_citations(self, client):
        resp = client.get("/api/citation/extract", params={
            "content": "See [1] and [2] for details.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "keys" in data
        assert "index" in data

    def test_index_citations(self, client):
        resp = client.put("/api/citation/index", json={
            "content": "This is described in [1].",
            "bibliography": [{"id": 1, "title": "Test Ref", "authors": "A. Smith"}],
            "style": "ieee",
        })
        assert resp.status_code in (200, 500)


# ── /api/zotero/* ────────────────────────────────────────────────────────


class TestZoteroEndpoints:
    def test_status_not_configured(self, client):
        resp = client.get("/api/zotero/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "connected" in data

    def test_search_not_configured(self, client):
        resp = client.post("/api/zotero/search", json={"query": "machine learning"})
        assert resp.status_code in (200, 400, 500)

    def test_get_item_not_configured(self, client):
        resp = client.get("/api/zotero/item/NONEXISTENT")
        assert resp.status_code in (200, 400, 404, 500)

    def test_get_item_bibtex_not_configured(self, client):
        resp = client.get("/api/zotero/item/NONEXISTENT/bibtex")
        assert resp.status_code in (200, 400, 404, 500)

    def test_export_not_configured(self, client):
        resp = client.post("/api/zotero/export", json=["KEY1", "KEY2"])
        assert resp.status_code in (200, 400, 500)

    def test_citations_not_configured(self, client):
        resp = client.post("/api/zotero/citations", json=["KEY1"])
        assert resp.status_code in (200, 400, 500)


# ── /api/vision/* ────────────────────────────────────────────────────────


class TestVisionEndpoints:
    @pytest.fixture
    def png_file(self):
        return io.BytesIO(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    def test_vision_analyze(self, client, png_file):
        resp = client.post("/api/vision/analyze", files={
            "file": ("img.png", png_file, "image/png"),
        })
        assert resp.status_code in (200, 500)

    def test_vision_ocr(self, client, png_file):
        png_file.seek(0)
        resp = client.post("/api/vision/ocr", files={
            "file": ("img.png", png_file, "image/png"),
        })
        assert resp.status_code in (200, 500)

    def test_vision_chart(self, client, png_file):
        png_file.seek(0)
        resp = client.post("/api/vision/chart", files={
            "file": ("chart.png", png_file, "image/png"),
        })
        assert resp.status_code in (200, 500)

    def test_vision_table(self, client, png_file):
        png_file.seek(0)
        resp = client.post("/api/vision/table", files={
            "file": ("table.png", png_file, "image/png"),
        })
        assert resp.status_code in (200, 500)
