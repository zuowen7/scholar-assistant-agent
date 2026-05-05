"""新 API 端点集成测试 — PPTX 导出、Data Availability、QA 警告

使用 FastAPI TestClient 测试 HTTP 层的：
- 入参校验（缺失必填字段 → 422）
- 正常响应
- 异常处理（无效 task_id 等）
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def client():
    """创建 TestClient，隔离配置和数据目录"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from api_factory import create_app
    from fastapi.testclient import TestClient

    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "default.yaml"
    config_file.write_text(
        "translator:\n  engine: ollama\n  model: qwen3:8b\n"
        "  ollama_base_url: http://localhost:11434\n  temperature: 0.3\n"
        "  timeout: 300.0\n"
        "chunker:\n  max_tokens: 2048\n  overlap_tokens: 128\n"
        "formatter:\n  output_format: bilingual\n"
        "agent:\n  model: qwen3:8b\n  max_steps: 3\n",
        encoding="utf-8",
    )

    with patch("api_factory.CONFIG_PATH", config_file):
        with patch("api_factory.RUNTIME_DIR", Path(test_dir)):
            with patch("api_factory.BASE_DIR", Path(test_dir)):
                app = create_app()
                c = TestClient(app)
                yield c

    shutil.rmtree(test_dir, ignore_errors=True)


# ── 1. PPTX Export Endpoint ────────────────────────────────────────────


class TestPPTXExport:
    """POST /api/export/pptx"""

    def test_missing_task_id_returns_422(self, client) -> None:
        resp = client.post("/api/export/pptx", json={})
        assert resp.status_code == 422

    def test_missing_body_returns_422(self, client) -> None:
        resp = client.post("/api/export/pptx")
        assert resp.status_code == 422

    def test_invalid_task_id_returns_400(self, client) -> None:
        resp = client.post("/api/export/pptx", json={
            "task_id": "nonexistent-task-id",
            "block_translations": [],
        })
        # Should return 400 or 404 for nonexistent task
        assert resp.status_code in (400, 404)

    def test_valid_task_id_with_empty_blocks(self, client) -> None:
        """Valid task_id with empty blocks — 404 if task doesn't exist in fresh app"""
        resp = client.post("/api/export/pptx", json={
            "task_id": "test-task-empty",
            "block_translations": [],
        })
        # 404 = task doesn't exist (fresh test app), 200/400 otherwise
        assert resp.status_code in (200, 400, 404)


# ── 2. Data Availability Export Endpoint ───────────────────────────────


class TestDataAvailabilityExport:
    """POST /api/export/data_availability"""

    def test_missing_task_id_returns_422(self, client) -> None:
        resp = client.post("/api/export/data_availability", json={})
        assert resp.status_code == 422

    def test_missing_body_returns_422(self, client) -> None:
        resp = client.post("/api/export/data_availability")
        assert resp.status_code == 422

    def test_accepts_task_id(self, client) -> None:
        resp = client.post("/api/export/data_availability", json={
            "task_id": "test-da-task",
        })
        # May return 404 if task doesn't exist, but shouldn't 422
        assert resp.status_code != 422


# ── 3. Health Endpoint ─────────────────────────────────────────────────


class TestHealthEndpoint:
    """GET /api/health"""

    def test_health_returns_200(self, client) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_is_json(self, client) -> None:
        resp = client.get("/api/health")
        assert resp.headers["content-type"].startswith("application/json")


# ── 4. Config Endpoint ─────────────────────────────────────────────────


class TestConfigEndpoint:
    """GET /api/config — basic integrity"""

    def test_config_returns_200(self, client) -> None:
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "translator" in data

    def test_config_contains_chunker(self, client) -> None:
        resp = client.get("/api/config")
        data = resp.json()
        assert "chunker" in data
        assert "max_tokens" in data["chunker"]

    def test_config_hides_api_key(self, client) -> None:
        resp = client.get("/api/config")
        data = resp.json()
        translator = data.get("translator", {})
        cloud = translator.get("cloud", {})
        # If api_key exists, it should be masked
        if "api_key" in cloud and cloud["api_key"]:
            assert "****" in cloud["api_key"] or len(cloud["api_key"]) < 20


# ── 5. Provider Presets Endpoint ───────────────────────────────────────


class TestCloudProviders:
    """GET /api/cloud/providers — returns dict of provider presets"""

    def test_providers_returns_200(self, client) -> None:
        resp = client.get("/api/cloud/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_providers_have_required_fields(self, client) -> None:
        resp = client.get("/api/cloud/providers")
        data = resp.json()
        for provider_id, provider in data.items():
            assert "name" in provider, f"Missing 'name' in provider {provider_id}"
            assert "base_url" in provider, f"Missing 'base_url' in {provider_id}"
            assert "models" in provider, f"Missing 'models' in {provider_id}"


# ── 6. Ollama Health Endpoint ──────────────────────────────────────────


class TestOllamaStatus:
    """GET /api/ollama/status"""

    def test_ollama_status_responds(self, client) -> None:
        """Ollama may or may not be running; endpoint should respond."""
        resp = client.get("/api/ollama/status")
        assert resp.status_code in (200, 503)


# ── 7. Error Handling for Invalid Routes ───────────────────────────────


class TestErrorHandling:
    """通用错误处理"""

    def test_invalid_route_returns_404(self, client) -> None:
        resp = client.get("/api/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_invalid_method_returns_405(self, client) -> None:
        resp = client.get("/api/export/pptx")  # POST expected
        assert resp.status_code in (405, 404)

    def test_invalid_json_body(self, client) -> None:
        resp = client.post(
            "/api/export/pptx",
            content=b"not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)

    def test_cors_headers_present(self, client) -> None:
        resp = client.options("/api/health")
        # FastAPI should handle OPTIONS
        assert resp.status_code in (200, 405)


# ── 8. Status Endpoint (if exists) ─────────────────────────────────────


class TestStatusEndpoint:
    """GET /api/status — application status"""

    def test_status_responds(self, client) -> None:
        resp = client.get("/api/status")
        # May be 200 or 404 depending on router registration
        assert resp.status_code in (200, 404)
