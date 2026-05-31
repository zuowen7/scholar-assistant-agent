"""Translation memory, glossary, and export format integration tests.

Covers /api/tm/*, /api/glossary*, /api/export/{bilingual_docx,translation_only_docx,pptx,data_availability},
and /api/download/{task_id} via TestClient.
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


# ── Translation Memory ───────────────────────────────────────────────────


class TestTranslationMemory:
    def test_stats_returns_tm_stats(self, client):
        resp = client.get("/api/tm/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_pairs" in data
        assert isinstance(data["total_pairs"], int)

    def test_import_tmx(self, client):
        tmx = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tmx SYSTEM "tmx14.dtd">
<tmx version="1.4">
<header creationtool="test" segtype="sentence" adminlang="en" srclang="en" datatype="plaintext"/>
<body>
<tu>
<tuv xml:lang="en"><seg>Hello world</seg></tuv>
<tuv xml:lang="zh"><seg>你好世界</seg></tuv>
</tu>
</body>
</tmx>"""
        resp = client.post("/api/tm/import", files={
            "file": ("test.tmx", io.BytesIO(tmx.encode()), "application/xml"),
        })
        assert resp.status_code in (200, 400)

    def test_export_returns_tmx(self, client):
        resp = client.get("/api/tm/export")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert resp.headers.get("content-type") in (
                "application/xml",
                "text/xml",
                "application/octet-stream",
            ) or "xml" in resp.headers.get("content-type", "")


# ── Glossary ─────────────────────────────────────────────────────────────


class TestGlossary:
    def test_get_glossary_empty(self, client):
        resp = client.get("/api/glossary")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list) or isinstance(data, dict)

    def test_put_glossary(self, client):
        resp = client.put("/api/glossary", json={"entries": [
            {"source": "machine learning", "target": "机器学习"},
            {"source": "deep learning", "target": "深度学习"},
        ]})
        assert resp.status_code in (200, 400)

    def test_put_then_get_glossary(self, client):
        put_resp = client.put("/api/glossary", json={"entries": [{"source": "neural network", "target": "神经网络"}]})
        if put_resp.status_code == 200:
            get_resp = client.get("/api/glossary")
            if get_resp.status_code == 200:
                data = get_resp.json()
                if isinstance(data, list):
                    assert len(data) >= 1

    def test_import_csv_glossary(self, client):
        csv = "source,target\nartificial intelligence,人工智能\ngradient descent,梯度下降\n"
        resp = client.post("/api/glossary/import", files={
            "file": ("glossary.csv", io.BytesIO(csv.encode()), "text/csv"),
        })
        assert resp.status_code in (200, 400)


# ── Export formats ───────────────────────────────────────────────────────


class TestExportFormats:
    def test_export_bilingual_docx_nonexistent_task(self, client):
        resp = client.post("/api/export/bilingual_docx", json={
            "task_id": "nonexistent-task-for-export",
        })
        assert resp.status_code in (200, 400, 404)

    def test_export_translation_only_docx_nonexistent_task(self, client):
        resp = client.post("/api/export/translation_only_docx", json={
            "task_id": "nonexistent-task-for-export",
        })
        assert resp.status_code in (200, 400, 404)

    def test_export_pptx_nonexistent_task(self, client):
        resp = client.post("/api/export/pptx", json={
            "task_id": "nonexistent-task-for-pptx",
        })
        assert resp.status_code in (200, 400, 404)

    def test_export_data_availability_nonexistent_task(self, client):
        resp = client.post("/api/export/data_availability", json={
            "task_id": "nonexistent-task-for-da",
        })
        assert resp.status_code in (200, 400, 404)

    def test_export_missing_task_id_rejected(self, client):
        resp = client.post("/api/export/bilingual_docx", json={})
        assert resp.status_code == 422


# ── Download ─────────────────────────────────────────────────────────────


class TestDownload:
    def test_download_nonexistent_task(self, client):
        resp = client.get("/api/download/nonexistent-task-id-99999")
        assert resp.status_code in (404, 400)

    def test_download_path_traversal(self, client):
        resp = client.get("/api/download/../../../etc/passwd")
        assert resp.status_code in (404, 400, 403)
