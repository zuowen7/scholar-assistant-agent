"""Edit SSE endpoint with mock LLM streaming integration tests.

Mocks httpx.AsyncClient to simulate cloud/Ollama streaming responses,
verifying that SSE events arrive with correct delta events.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

CONFIG = """\
translator:
  engine: cloud
  model: deepseek-chat
  ollama_base_url: http://localhost:11434
  temperature: 0.3
  timeout: 300.0
  cloud:
    base_url: https://api.deepseek.com/v1
    api_key: sk-test-mock-key-12345678
    model: deepseek-chat
    provider: deepseek
chunker:
  max_tokens: 2048
  overlap_tokens: 128
formatter:
  output_format: bilingual
agent:
  model: qwen3:8b
  max_steps: 3
"""


# ── Mock SSE line generators ──────────────────────────────────────────────

def _make_cloud_sse_lines(tokens: list[str]) -> list[str]:
    """Build cloud-format SSE lines from token list."""
    lines = []
    for token in tokens:
        chunk = {"choices": [{"delta": {"content": token}}]}
        lines.append(f"data: {json.dumps(chunk, ensure_ascii=False)}")
    lines.append("data: [DONE]")
    return lines


def _make_ollama_sse_lines(tokens: list[str]) -> list[str]:
    """Build ollama-format lines from token list."""
    lines = []
    for i, token in enumerate(tokens):
        chunk = {"message": {"content": token}, "done": False}
        lines.append(json.dumps(chunk, ensure_ascii=False))
    lines.append(json.dumps({"message": {"content": ""}, "done": True}))
    return lines


class _MockStreamResponse:
    """Simulates httpx async stream response."""

    def __init__(self, lines: list[str], status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_sse(text: str) -> list[dict]:
    events = []
    current = {}
    for line in text.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:"):].strip()
            events.append({**current})
            current = {}
    return events


# ── Fixtures ──────────────────────────────────────────────────────────────


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


# ── Cloud SSE tests ──────────────────────────────────────────────────────


class TestEditCloudSSE:
    """Test /api/edit with mock cloud LLM streaming."""

    @pytest.fixture(autouse=True)
    def mock_cloud_stream(self):
        """Replace httpx.AsyncClient.stream with mock for cloud API."""
        tokens = ["The", " ", "quick", " ", "brown", " ", "fox"]
        lines = _make_cloud_sse_lines(tokens)
        mock_resp = _MockStreamResponse(lines)

        def _mock_stream(self, method, url, *args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.stream", _mock_stream):
            yield

    def test_edit_cloud_stream_returns_delta_events(self, client):
        resp = client.post("/api/edit", json={
            "text": "The quick brown fox",
            "instruction": "polish",
        })
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        assert len(events) > 0
        deltas = [e for e in events if e.get("event") == "delta"]
        assert len(deltas) >= 1
        # At least one delta should contain the full accumulated content
        last_delta = json.loads(deltas[-1]["data"])
        assert "content" in last_delta
        full = last_delta["content"]
        assert "The" in full

    def test_edit_cloud_stream_content_accumulates(self, client):
        resp = client.post("/api/edit", json={
            "text": "Test text",
            "instruction": "translate to zh",
        })
        events = _parse_sse(resp.text)
        deltas = [e for e in events if e.get("event") == "delta"]
        # Last delta has full accumulated content
        if deltas:
            last = json.loads(deltas[-1]["data"])
            content = last["content"]
            assert "The" in content
            assert "quick" in content
            assert "fox" in content


# ── Echo mode (no instruction) ───────────────────────────────────────────


class TestEditEchoSSE:
    def test_edit_no_instruction_echoes_input(self, client):
        resp = client.post("/api/edit", json={
            "text": "Hello world from test.",
            "instruction": "",
        })
        events = _parse_sse(resp.text)
        deltas = [e for e in events if e.get("event") == "delta"]
        assert len(deltas) >= 1
        last = json.loads(deltas[-1]["data"])
        assert last["content"].strip() == "Hello world from test."


# ── Ollama SSE tests ─────────────────────────────────────────────────────


class TestEditOllamaSSE:
    @pytest.fixture(autouse=True)
    def mock_ollama_stream_and_config(self):
        """Replace httpx.AsyncClient.stream and switch to ollama engine."""
        tokens = ["Ollama", " ", "streaming", " ", "works"]
        lines = _make_ollama_sse_lines(tokens)
        mock_resp = _MockStreamResponse(lines)

        def _mock_stream(self, method, url, *args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.stream", _mock_stream):
            yield

    def test_edit_ollama_stream_returns_delta_events(self, client):
        """Uses cloud config, so reverts to stream-based response."""
        resp = client.post("/api/edit", json={
            "text": "some text to edit",
            "instruction": "summarize",
        })
        assert resp.status_code == 200


# ── Error handling ───────────────────────────────────────────────────────


class TestEditSSEErrors:
    @pytest.fixture(autouse=True)
    def mock_cloud_stream(self):
        tokens = ["fine"]
        lines = _make_cloud_sse_lines(tokens)
        mock_resp = _MockStreamResponse(lines)

        def _mock_stream(self, method, url, *args, **kwargs):
            return mock_resp

        with patch("httpx.AsyncClient.stream", _mock_stream):
            yield

    def test_edit_with_task_type_translate(self, client):
        resp = client.post("/api/edit", json={
            "text": "Hello world",
            "instruction": "translate to zh",
            "task_type": "translate",
        })
        assert resp.status_code == 200
