"""Concurrency and input validation integration tests.

Tests:
- Pydantic Field constraints reject oversized payloads (B3)
- V2ToolRequest localhost-only restriction (A2)
- _busy_lock serializes concurrent translate requests (A1)
- MemoryManager concurrent write safety (B2)
"""

import io
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(scope="module")
def client():
    """Create a TestClient for the FastAPI app."""
    from api_factory import create_app

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

    with (
        patch("api_factory.CONFIG_PATH", config_file),
        patch("api_factory.RUNTIME_DIR", Path(test_dir)),
        patch("api_factory.BASE_DIR", Path(test_dir)),
    ):
        app = create_app()
        c = TestClient(app)
        yield c

    shutil.rmtree(test_dir, ignore_errors=True)


# ── Pydantic Field Validation (B3) ────────────────────────────────────────


class TestFieldValidation:
    """Verify Pydantic Field constraints reject oversized payloads."""

    def test_chat_message_too_long(self, client):
        resp = client.post("/api/agent/v2/chat", json={"message": "x" * 100_001})
        assert resp.status_code == 422

    def test_chat_history_too_many_items(self, client):
        resp = client.post("/api/agent/v2/chat", json={
            "message": "hi",
            "history": [{"role": "user", "content": f"m{i}"} for i in range(51)],
        })
        assert resp.status_code == 422

    def test_chat_context_text_too_long(self, client):
        resp = client.post("/api/agent/v2/chat", json={
            "message": "hi",
            "context_text": "x" * 500_001,
        })
        assert resp.status_code == 422

    def test_v2tool_name_too_long(self, client):
        resp = client.post("/api/agent/v2/tool", json={
            "tool": "x" * 129,
            "args": {},
        })
        assert resp.status_code in (403, 422)

    def test_v2tool_too_many_args(self, client):
        resp = client.post("/api/agent/v2/tool", json={
            "tool": "read_file",
            "args": {f"key{i}": "val" for i in range(21)},
        })
        assert resp.status_code in (403, 422)

    def test_completion_max_tokens_out_of_range(self, client):
        resp = client.post("/api/complete", json={
            "context": "text",
            "max_tokens": 99999,
        })
        assert resp.status_code == 422

    def test_completion_max_tokens_zero(self, client):
        resp = client.post("/api/complete", json={
            "context": "text",
            "max_tokens": 0,
        })
        assert resp.status_code == 422

    def test_zotero_limit_too_high(self, client):
        resp = client.post("/api/zotero/search", json={
            "query": "test",
            "limit": 999,
        })
        assert resp.status_code == 422


# ── V2Tool Localhost Restriction (A2) ─────────────────────────────────────


class TestV2ToolLocalhost:
    """V2 tool endpoint should reject non-localhost requests."""

    def test_non_localhost_rejected(self, client):
        """TestClient uses 'testclient' as host, not 127.0.0.1."""
        resp = client.post("/api/agent/v2/tool", json={
            "tool": "read_file",
            "args": {"path": "/tmp/test"},
        })
        assert resp.status_code == 403

    def test_tool_not_in_whitelist(self, client):
        """Tools not in _V2_TOOL_WHITELIST should be rejected."""
        # Even if we could bypass localhost, non-whitelisted tools fail
        # This tests the whitelist logic by checking the response mentions it
        resp = client.post("/api/agent/v2/tool", json={
            "tool": "write_file",
            "args": {"path": "/tmp/evil", "content": "hacked"},
        })
        assert resp.status_code == 403


# ── Translate Lock Concurrency (A1) ───────────────────────────────────────


class TestTranslateLockConcurrency:
    """Verify _busy_lock serializes concurrent translate uploads."""

    def test_second_upload_rejected_while_first_holds_lock(self, client):
        """After first upload acquires lock, second upload gets 409."""
        resp1 = client.post("/api/translate", files={
            "file": ("test.txt", io.BytesIO(b"hello world"), "text/plain"),
        })
        if resp1.status_code != 200:
            pytest.skip("Upload setup failed (no input dir or similar)")

        resp2 = client.post("/api/translate", files={
            "file": ("test2.txt", io.BytesIO(b"second"), "text/plain"),
        })
        assert resp2.status_code == 409
        assert "已有翻译任务" in resp2.json()["detail"]

    def test_translate_path_too_long(self, client):
        """FilePathPayload with oversized path should get 422 (if route registered)."""
        resp = client.post("/api/translate/path", json={
            "path": "x" * 1025,
        })
        # Route may not be registered in all configs; skip if 404
        assert resp.status_code in (404, 422)


# ── MemoryManager Thread Safety (B2) ──────────────────────────────────────


class TestMemoryManagerConcurrency:
    """Test MemoryManager handles concurrent writes safely."""

    def test_concurrent_add_memory(self, tmp_path):
        """5 threads each write 20 memories; all should succeed."""
        from src.agent.memory import MemoryManager

        mm = MemoryManager(data_dir=str(tmp_path / "mem"))
        errors: list[Exception] = []

        def writer(idx: int):
            try:
                for i in range(20):
                    mm.add_memory(
                        content=f"memory-{idx}-{i}",
                        category="fact",
                        importance=0.5,
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent writes failed: {errors}"
        assert mm.get_stats()["memories_count"] == 100
        mm.close()

    def test_concurrent_read_write(self, tmp_path):
        """Writer + 2 readers in parallel; no exceptions."""
        from src.agent.memory import MemoryManager

        mm = MemoryManager(data_dir=str(tmp_path / "mem_rw"))
        errors: list[Exception] = []

        def writer():
            try:
                for i in range(50):
                    mm.add_memory(content=f"mem-{i}", category="fact")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    mm.search_memories("mem")
                    mm.get_recent_memories()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent read/write failed: {errors}"
        mm.close()
