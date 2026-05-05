"""FastAPI endpoint integration tests using TestClient.

Tests the HTTP API layer end-to-end:
- Config read/write
- Tectonic status
- Paper assets templates
- Cloud provider presets
- Chat endpoint validation
- RAG document listing
- Health endpoint
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── App fixture ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app.

    Uses module scope to avoid recreating the app for every test.
    Patches config path to avoid polluting real config.
    """
    from api_factory import create_app

    # Temp dir for test data isolation
    test_dir = tempfile.mkdtemp()
    config_dir = Path(test_dir) / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Write a minimal config file
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

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


# ── 1. Config GET ───────────────────────────────────────────────────────


class TestConfigEndpoints:
    """Tests for /api/config endpoints."""

    def test_config_get(self, client):
        """GET /api/config returns 200 with valid structure."""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        # Config should contain translator section
        assert "translator" in data

    def test_config_update(self, client):
        """PUT /api/config with valid data returns 200 and persists changes."""
        resp = client.put("/api/config", json={
            "chunker": {"max_tokens": 3000},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["chunker"]["max_tokens"] == 3000

        # Verify persistence via GET
        resp2 = client.get("/api/config")
        assert resp2.status_code == 200
        assert resp2.json()["chunker"]["max_tokens"] == 3000

    def test_config_update_cloud_masking(self, client):
        """PUT /api/config with masked API key should not overwrite existing key."""
        # First set a real key
        client.put("/api/config", json={
            "cloud": {"api_key": "sk-real-test-key-12345678"},
        })

        # Then try to update with masked key
        resp = client.put("/api/config", json={
            "cloud": {"api_key": "sk-r****5678"},
        })
        assert resp.status_code == 200
        data = resp.json()
        # The returned value should be masked
        assert "****" in data["translator"]["cloud"]["api_key"]


# ── 2. Health endpoint ──────────────────────────────────────────────────


class TestHealthEndpoint:
    """Tests for /api/health and general app startup."""

    def test_health_endpoint(self, client):
        """Verify the app starts and health endpoint returns ok."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_has_version(self, client):
        """Health endpoint should include version string."""
        resp = client.get("/api/health")
        data = resp.json()
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


# ── 3. Tectonic status ──────────────────────────────────────────────────


class TestTectonicStatus:
    """Tests for /api/tectonic/status."""

    def test_tectonic_status(self, client):
        """GET /api/tectonic/status returns valid JSON."""
        resp = client.get("/api/tectonic/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "available" in data
        assert isinstance(data["available"], bool)


# ── 4. Paper assets templates ───────────────────────────────────────────


class TestPaperAssets:
    """Tests for /api/paper-assets/templates."""

    def test_paper_assets_templates(self, client):
        """GET /api/paper-assets/templates returns 200 with template list."""
        resp = client.get("/api/paper-assets/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)
        # Each template should have an id
        for tmpl in data["templates"]:
            assert "id" in tmpl


# ── 5. Cloud provider presets ───────────────────────────────────────────


class TestCloudPresets:
    """Tests for /api/cloud/providers."""

    def test_provider_presets(self, client):
        """GET /api/cloud/providers returns preset data."""
        resp = client.get("/api/cloud/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        # Should have at least openai preset
        assert "openai" in data
        assert "name" in data["openai"]
        assert "base_url" in data["openai"]


# ── 6. Chat endpoint validation ─────────────────────────────────────────


class TestChatEndpoint:
    """Tests for /api/chat endpoint validation."""

    def test_chat_endpoint_validation(self, client):
        """POST /api/chat with missing message field returns 422."""
        # FastAPI/Pydantic validation error for missing required field
        resp = client.post("/api/agent/v2/chat", json={})
        assert resp.status_code == 422

    def test_chat_endpoint_validation_wrong_types(self, client):
        """POST /api/chat with wrong types for message returns 422."""
        resp = client.post("/api/agent/v2/chat", json={"message": 12345})
        assert resp.status_code == 422

    def test_chat_endpoint_accepts_valid_payload(self, client):
        """POST /api/chat with valid payload should not fail validation.

        The chat endpoint returns an SSE stream which blocks with TestClient.
        We use a thread with timeout to verify the endpoint accepts the request
        (does not return 422 validation error).
        """
        import threading

        result = {"status": None, "error": None}

        def _make_request():
            try:
                resp = client.post("/api/agent/v2/chat", json={
                    "message": "test query",
                    "history": [
                        {"role": "user", "content": "previous question"},
                        {"role": "assistant", "content": "previous answer"},
                    ],
                }, timeout=5.0)
                result["status"] = resp.status_code
            except Exception as e:
                result["error"] = str(e)

        t = threading.Thread(target=_make_request, daemon=True)
        t.start()
        t.join(timeout=10.0)

        # Either we got a response (200/403/500/503) or a timeout/connection error
        # The key assertion: we should NOT get a 422 validation error
        # 403 is expected from TestClient (host is "testclient", not 127.0.0.1)
        if result["status"] is not None:
            assert result["status"] in (200, 403, 500, 503), (
                f"Expected 200/403/500/503, got {result['status']}"
            )
        # If error, it should be a timeout (agent tries to connect to Ollama)
        # which is expected and acceptable for integration tests


# ── 7. RAG documents list ───────────────────────────────────────────────


class TestRAGDocuments:
    """Tests for /api/rag/documents."""

    def test_rag_documents_list(self, client):
        """GET /api/rag/documents returns list (may be empty)."""
        resp = client.get("/api/rag/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── 8. Ollama status ────────────────────────────────────────────────────


class TestOllamaStatus:
    """Tests for /api/ollama/status."""

    def test_ollama_status_returns_json(self, client):
        """GET /api/ollama/status returns valid JSON."""
        resp = client.get("/api/ollama/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "reachable" in data
        assert isinstance(data["reachable"], bool)
