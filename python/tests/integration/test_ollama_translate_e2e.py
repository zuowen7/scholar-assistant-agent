"""Real Ollama translation pipeline E2E tests.

Tests the full 5-step SSE pipeline (parse → clean → chunk → translate → format)
using the local Ollama qwen3:8b model. NOT mocking any translation layer.

Marked with pytest.mark.ollama — skipped when Ollama is not reachable.
"""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── Ollama availability check ────────────────────────────────────────────


def _ollama_reachable() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        return any("qwen" in m for m in models)
    except Exception:
        return False


OLLAMA_AVAILABLE = _ollama_reachable()
needs_ollama = pytest.mark.skipif(
    not OLLAMA_AVAILABLE,
    reason="Ollama with qwen model not reachable at localhost:11434",
)


# ── Rate-limit bypass ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_rate_limit():
    import api_factory as _mod
    with _mod._rl_lock:
        _mod._rl_windows.clear()
    yield
    with _mod._rl_lock:
        _mod._rl_windows.clear()


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from api_factory import create_app

    tmp = tmp_path_factory.mktemp("ollama_e2e")
    config_dir = tmp / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "translator:\n  engine: ollama\n  model: qwen3:8b\n"
        "  ollama_base_url: http://localhost:11434\n  temperature: 0.3\n"
        "  timeout: 180.0\nchunker:\n  max_tokens: 800\n  overlap_tokens: 128\n"
        "formatter:\n  output_format: bilingual\n",
        encoding="utf-8",
    )

    with (
        patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"),
        patch("api_factory.RUNTIME_DIR", tmp),
        patch("api_factory.BASE_DIR", tmp),
    ):
        app = create_app()
        yield TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────


def _upload(client, text: str = "Hello world. Test content.") -> str:
    resp = client.post(
        "/api/translate",
        files={"file": ("test.txt", io.BytesIO(text.encode()), "text/plain")},
    )
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    return resp.json()["task_id"]


def _consume(client, task_id: str, timeout: int = 180) -> tuple[bytes, int]:
    """Stream a task and return (body_bytes, status_code)."""
    resp = client.get(f"/api/translate/{task_id}/stream", timeout=timeout)
    return resp.content, resp.status_code


def _parse_sse_events(body: bytes) -> list[dict]:
    events: list[dict] = []
    current: dict = {}
    for line in body.decode("utf-8").splitlines():
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            current["data"] = line[5:].strip()
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


# ── Tests ────────────────────────────────────────────────────────────────


@needs_ollama
class TestOllamaTranslationPipeline:
    """Real Ollama pipeline — no mock at translate layer."""

    def test_full_pipeline_completes(self, client):
        """Upload a short English text → stream → verify translate.complete."""
        text = (
            "Machine learning is a subset of artificial intelligence. "
            "It enables computers to learn from data without being explicitly programmed."
        )
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200, f"Stream returned {status}"
        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]
        assert "translate.complete" in event_types, (
            f"No translate.complete event. Events: {event_types}"
        )

    def test_pipeline_produces_translation(self, client):
        """Verify actual translated content contains Chinese characters."""
        text = "Artificial intelligence has transformed many industries."
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        block_events = [e for e in events if e.get("event") == "translate.block_translated"]

        assert block_events, "No block_translated events received"
        all_translated = ""
        for e in block_events:
            data = json.loads(e["data"])
            all_translated += data.get("translated", "")

        assert all_translated.strip(), "Translated text is empty"
        # Should contain Chinese characters
        contains_chinese = any("一" <= ch <= "鿿" for ch in all_translated)
        assert contains_chinese, (
            f"Translation does not contain Chinese characters: {all_translated[:200]}"
        )

    def test_pipeline_all_five_steps_present(self, client):
        """All 5 pipeline steps emit events: progress, parsed, cleaned, chunked, complete."""
        text = "Deep learning uses neural networks with many layers."
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]

        required = [
            "translate.progress",
            "translate.parsed",
            "translate.cleaned",
            "translate.chunked",
        ]
        for r in required:
            assert r in event_types, (
                f"Missing required step '{r}' in events: {event_types}"
            )
        assert "translate.complete" in event_types

    def test_short_sentence_translation(self, client):
        """Single short sentence should translate cleanly."""
        text = "The cat sat on the mat."
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        block_events = [e for e in events if e.get("event") == "translate.block_translated"]
        assert len(block_events) >= 1

        data = json.loads(block_events[0]["data"])
        assert data.get("status") == "ok", f"Block status not ok: {data.get('status')}"
        assert data.get("original", "").strip()

    def test_multi_sentence_paragraph(self, client):
        """Multiple sentences should be translated together."""
        text = (
            "Reinforcement learning is a powerful paradigm. "
            "It has been applied to robotics, gaming, and autonomous driving. "
            "The key idea is learning through trial and error."
        )
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        block_events = [e for e in events if e.get("event") == "translate.block_translated"]

        assert len(block_events) >= 1, "Expected at least one block_translated event"

        # All blocks should have ok status (no fallbacks for standard English)
        fallback_count = 0
        for e in block_events:
            data = json.loads(e["data"])
            if data.get("status") != "ok":
                fallback_count += 1

        # Allow a small number of fallbacks, but not all
        assert fallback_count < len(block_events), (
            f"All {len(block_events)} blocks fell back — translation failed"
        )

    def test_rag_ingested_after_translation(self, client):
        """Translation result should be auto-ingested into RAG."""
        text = "Natural language processing enables computers to understand human language."
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        complete_events = [e for e in events if e.get("event") == "translate.complete"]
        assert complete_events

        data = json.loads(complete_events[0]["data"])
        assert data.get("rag_ingested") is True

    def test_download_after_real_translation(self, client):
        """After real translation completes, download should return the file."""
        text = "Download this translated content after pipeline finishes."
        task_id = _upload(client, text)
        body, status = _consume(client, task_id, timeout=180)

        assert status == 200
        events = _parse_sse_events(body)
        complete = [e for e in events if e.get("event") == "translate.complete"]
        assert complete, "Translation did not complete"

        # Now try to download
        dl = client.get(f"/api/download/{task_id}")
        assert dl.status_code == 200, f"Download failed: {dl.status_code} {dl.text}"
        content = dl.text
        assert len(content) > 0, "Downloaded file is empty"
        assert "text/markdown" in dl.headers.get("content-type", "")
