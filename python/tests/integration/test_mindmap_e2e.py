"""Mind map CRUD + AI analysis/expansion integration tests.

Covers /api/mindmap/* endpoints via TestClient with no live Ollama/cloud LLM.
"""

from __future__ import annotations

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


SAMPLE_MAP = {
    "nodes": {
        "root": {"id": "root", "text": "Research Topic", "children": ["n1", "n2"]},
        "n1": {"id": "n1", "text": "Method", "children": []},
        "n2": {"id": "n2", "text": "Experiment", "children": []},
    },
    "links": [],
}


class TestMindMapPersistence:
    """save → load → delete round-trip."""

    def test_load_404_when_empty(self, client):
        resp = client.get("/api/mindmap/load")
        assert resp.status_code == 404

    def test_save_and_load_roundtrip(self, client):
        resp = client.post("/api/mindmap/save", json=SAMPLE_MAP)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = client.get("/api/mindmap/load")
        assert resp.status_code == 200
        data = resp.json()
        assert data["nodes"]["root"]["text"] == "Research Topic"
        assert len(data["nodes"]["n1"]["children"]) == 0

    def test_save_overwrites_previous(self, client):
        alt = {**SAMPLE_MAP, "nodes": {"x": {"id": "x", "text": "Solo", "children": []}}}
        client.post("/api/mindmap/save", json=alt)
        data = client.get("/api/mindmap/load").json()
        assert "x" in data["nodes"]
        assert "root" not in data["nodes"]

    def test_delete_clears(self, client):
        client.post("/api/mindmap/save", json=SAMPLE_MAP)
        resp = client.delete("/api/mindmap")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert client.get("/api/mindmap/load").status_code == 404

    def test_delete_idempotent(self, client):
        resp = client.delete("/api/mindmap")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestMindMapAnalyze:
    """POST /api/mindmap/analyze — falls back to structural analysis without LLM."""

    ANALYZE_PAYLOAD = {
        "root_id": "root",
        "nodes": {
            "root": {"id": "root", "text": "中心主题", "children": ["a"]},
            "a": {"id": "a", "text": "浅分支", "children": []},
        },
        "links": [],
    }

    def test_analyze_returns_issues_list(self, client):
        resp = client.post("/api/mindmap/analyze", json=self.ANALYZE_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("issues"), list)
        # Should have structural fallback since no cloud API key configured
        assert data.get("source") == "structural"

    def test_analyze_detects_duplicates(self, client):
        dup_payload = {
            "root_id": "r",
            "nodes": {
                "r": {"id": "r", "text": "root", "children": ["a", "b"]},
                "a": {"id": "a", "text": "相同表述", "children": []},
                "b": {"id": "b", "text": "相同表述", "children": []},
            },
            "links": [],
        }
        resp = client.post("/api/mindmap/analyze", json=dup_payload)
        assert resp.status_code == 200
        data = resp.json()
        types = [i["type"] for i in data["issues"]]
        assert "duplicate" in types

    def test_analyze_detects_shallow_root(self, client):
        shallow = {
            "root_id": "r",
            "nodes": {
                "r": {"id": "r", "text": "root", "children": []},
            },
            "links": [],
        }
        resp = client.post("/api/mindmap/analyze", json=shallow)
        assert resp.status_code == 200
        types = [i["type"] for i in resp.json()["issues"]]
        assert "shallow_branch" in types

    def test_analyze_detects_orphans(self, client):
        orphan = {
            "root_id": "r",
            "nodes": {
                "r": {"id": "r", "text": "root", "children": []},
                "o": {"id": "o", "text": "orphan", "children": [], "parentId": "missing"},
            },
            "links": [],
        }
        resp = client.post("/api/mindmap/analyze", json=orphan)
        assert resp.status_code == 200
        types = [i["type"] for i in resp.json()["issues"]]
        assert "isolated" in types

    def test_analyze_includes_issue_fields(self, client):
        resp = client.post("/api/mindmap/analyze", json=self.ANALYZE_PAYLOAD)
        issues = resp.json()["issues"]
        for issue in issues:
            assert "id" in issue
            assert "type" in issue
            assert "severity" in issue
            assert "title" in issue
            assert "message" in issue
            assert "node_texts" in issue


class TestMindMapExpand:
    """POST /api/mindmap/expand — falls back to hardcoded suggestions without LLM."""

    def test_expand_returns_children_list(self, client):
        resp = client.post("/api/mindmap/expand", json={
            "node_text": "研究方法",
            "max_children": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("children"), list)
        assert len(data["children"]) >= 1

    def test_expand_children_have_text_and_rationale(self, client):
        resp = client.post("/api/mindmap/expand", json={"node_text": "绪论"})
        for child in resp.json()["children"]:
            assert "text" in child
            assert "rationale" in child
            assert len(child["text"]) > 0

    def test_expand_max_children_respected(self, client):
        resp = client.post("/api/mindmap/expand", json={
            "node_text": "test",
            "max_children": 2,
        })
        assert len(resp.json()["children"]) <= 2

    def test_expand_control_topic(self, client):
        resp = client.post("/api/mindmap/expand", json={
            "node_text": "控制系统稳定性",
        })
        texts = [c["text"] for c in resp.json()["children"]]
        assert any("建模" in t or "稳定性" in t or "控制" in t for t in texts)

    def test_expand_with_context(self, client):
        resp = client.post("/api/mindmap/expand", json={
            "node_text": "实验设计",
            "context": "本文研究深度学习模型在医学影像分析中的应用",
            "max_children": 2,
        })
        assert resp.status_code == 200
        assert len(resp.json()["children"]) == 2
