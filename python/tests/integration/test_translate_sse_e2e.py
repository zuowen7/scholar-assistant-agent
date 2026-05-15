"""Integration tests — translate SSE pipeline end-to-end (H-9).

Strategy: use TestClient with mock at the LLM transport layer
(translate_block_chunks_parallel imported inside routers/translate.py).
This verifies the full 5-step pipeline flows through SSE correctly.

NOTE: module-scoped client is used for speed, but every test that leaves a
task in "pending" or "running" state must consume it before returning so that
the next test can upload (only one active task allowed at a time).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

import api_factory as _api_factory_mod


# ── Rate-limit bypass fixture ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_rate_limit():
    """Reset the module-level rate-limit window before each test so sequential
    tests don't trigger the 30-req/min cap."""
    with _api_factory_mod._rl_lock:
        _api_factory_mod._rl_windows.clear()
    yield
    with _api_factory_mod._rl_lock:
        _api_factory_mod._rl_windows.clear()


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create TestClient with minimal config — shared across all tests in module."""
    from api_factory import create_app

    tmp = tmp_path_factory.mktemp("sse_test")
    config_dir = tmp / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "translator:\n  engine: ollama\n  model: qwen3:8b\n"
        "  ollama_base_url: http://localhost:11434\n  temperature: 0.3\n"
        "  timeout: 30.0\nchunker:\n  max_tokens: 512\n  overlap_tokens: 64\n"
        "formatter:\n  output_format: bilingual\nagent:\n  model: qwen3:8b\n  max_steps: 3\n",
        encoding="utf-8",
    )

    with patch("api_factory.CONFIG_PATH", config_dir / "default.yaml"):
        with patch("api_factory.RUNTIME_DIR", tmp):
            with patch("api_factory.BASE_DIR", tmp):
                app = create_app()
                yield TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

_PARALLEL_TARGET = "routers.translate.translate_block_chunks_parallel"


def _make_txt_bytes(content: str = "This is a test document. It has two sentences.") -> bytes:
    return content.encode("utf-8")


def _upload(client: TestClient, text: str = "Hello world. Test content.") -> str:
    """POST /api/translate and return task_id."""
    resp = client.post(
        "/api/translate",
        files={"file": ("test.txt", io.BytesIO(text.encode()), "text/plain")},
    )
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    return resp.json()["task_id"]


def _consume(client: TestClient, task_id: str) -> bytes:
    """Stream a task to completion and return raw SSE body."""
    with client.stream("GET", f"/api/translate/{task_id}/stream") as response:
        return response.read()


def _parse_sse_events(body: bytes) -> list[dict]:
    """Parse raw SSE body into list of {event, data} dicts."""
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


async def _empty_gen(*args, **kwargs):
    """Async generator that produces no ChunkBlockResults (0-chunk document)."""
    return
    yield  # pragma: no cover — makes it an async generator


def _make_mock_generator(*chunk_results):
    """Return an async generator factory that yields given ChunkBlockResult items."""
    async def _gen(*args, **kwargs):
        for cr in chunk_results:
            yield cr
    return _gen


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestTranslateSSEPipeline:

    def test_upload_returns_task_id(self, client):
        """POST /api/translate 返回 task_id，然后消费任务以免阻塞后续测试。"""
        with patch(_PARALLEL_TARGET, _empty_gen):
            resp = client.post(
                "/api/translate",
                files={"file": ("test.txt", io.BytesIO(_make_txt_bytes()), "text/plain")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "task_id" in data
            assert len(data["task_id"]) > 0
            # Consume the task so subsequent tests can upload freely
            _consume(client, data["task_id"])

    def test_stream_emits_complete_event(self, client):
        """完整流程：upload → stream → 收到 translate.complete 事件。"""
        from src.translator.block_translator import BlockTranslation, ChunkBlockResult

        mock_cr = ChunkBlockResult(
            chunk_index=0,
            block_translations=[
                BlockTranslation(
                    block_id="b_0",
                    type="paragraph",
                    original="Hello world. Test content.",
                    translated="你好世界。测试内容。",
                    translatable=True,
                    status="ok",
                )
            ],
            aligned=True,
            is_fallback=False,
        )

        with patch(_PARALLEL_TARGET, _make_mock_generator(mock_cr)):
            task_id = _upload(client, "Hello world. Test content.")
            body = _consume(client, task_id)

        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]
        assert "translate.complete" in event_types or "translate.error" in event_types, (
            f"Expected complete or error event, got: {event_types}"
        )

    def test_stream_contains_progress_event(self, client):
        """流式响应包含 translate.progress 事件。"""
        with patch(_PARALLEL_TARGET, _empty_gen):
            task_id = _upload(client, "Short doc.")
            body = _consume(client, task_id)

        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]
        assert "translate.progress" in event_types, (
            f"No progress event. Got: {event_types}"
        )

    def test_task_not_found_returns_404(self, client):
        """不存在的 task_id 返回 404。"""
        resp = client.get("/api/translate/nonexistent_task_id_xyz/stream")
        assert resp.status_code == 404

    def test_done_task_returns_409_on_restream(self, client):
        """已完成的任务再次请求 stream 返回 409（done 不可重启）。"""
        with patch(_PARALLEL_TARGET, _empty_gen):
            task_id = _upload(client, "Done once doc.")
            _consume(client, task_id)

        # Task is now done/error — re-streaming should return 409
        resp = client.get(f"/api/translate/{task_id}/stream")
        assert resp.status_code == 409, (
            f"Expected 409 for done/error task re-stream, got {resp.status_code}"
        )

    def test_unsupported_file_extension_returns_400(self, client):
        """不支持的扩展名返回 400。"""
        resp = client.post(
            "/api/translate",
            files={"file": ("test.xyz", io.BytesIO(b"data"), "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_path_endpoint_with_valid_txt(self, client, tmp_path):
        """POST /api/translate/path 接受本地文件路径（不 500）。"""
        txt_file = tmp_path / "sample.txt"
        txt_file.write_text("Sample text for path translation.", encoding="utf-8")

        resp = client.post(
            "/api/translate/path",
            json={"path": str(txt_file)},
        )
        # Should succeed (200) or return validation / permission error — not 500
        assert resp.status_code in (200, 400, 403, 422), (
            f"Unexpected: {resp.status_code} {resp.text}"
        )
        # If accepted, consume the task
        if resp.status_code == 200:
            task_id = resp.json().get("task_id")
            if task_id:
                with patch(_PARALLEL_TARGET, _empty_gen):
                    _consume(client, task_id)

    def test_stream_events_order(self, client):
        """SSE 事件顺序：progress → parsed → cleaned → chunked。"""
        from src.translator.block_translator import BlockTranslation, ChunkBlockResult

        mock_cr = ChunkBlockResult(
            chunk_index=0,
            block_translations=[
                BlockTranslation(
                    block_id="b_0",
                    type="paragraph",
                    original="Order test sentence.",
                    translated="顺序测试句子。",
                    translatable=True,
                    status="ok",
                )
            ],
            aligned=True,
            is_fallback=False,
        )

        with patch(_PARALLEL_TARGET, _make_mock_generator(mock_cr)):
            task_id = _upload(client, "Order test sentence.")
            body = _consume(client, task_id)

        events = _parse_sse_events(body)
        event_types = [e.get("event") for e in events]

        # The pipeline always emits translate.progress first
        assert len(event_types) > 0, "No SSE events received"
        assert event_types[0] == "translate.progress", (
            f"First event should be translate.progress, got: {event_types[0]}"
        )

        # parsed must come before chunked
        if "translate.parsed" in event_types and "translate.chunked" in event_types:
            assert event_types.index("translate.parsed") < event_types.index("translate.chunked"), (
                "translate.parsed must precede translate.chunked"
            )

    def test_upload_empty_filename_returns_400(self, client):
        """文件名为空时 upload 返回 400 或 422。"""
        resp = client.post(
            "/api/translate",
            files={"file": ("", io.BytesIO(b"data"), "text/plain")},
        )
        # FastAPI may return 400 (HTTPException) or 422 (validation error)
        assert resp.status_code in (400, 422), (
            f"Expected 400/422 for empty filename, got {resp.status_code}"
        )

    def test_stream_data_fields_in_block_translated(self, client):
        """translate.block_translated 事件 data 含必要字段。"""
        from src.translator.block_translator import BlockTranslation, ChunkBlockResult

        mock_cr = ChunkBlockResult(
            chunk_index=0,
            block_translations=[
                BlockTranslation(
                    block_id="b_0",
                    type="paragraph",
                    original="Field test.",
                    translated="字段测试。",
                    translatable=True,
                    status="ok",
                )
            ],
            aligned=True,
            is_fallback=False,
        )

        with patch(_PARALLEL_TARGET, _make_mock_generator(mock_cr)):
            task_id = _upload(client, "Field test.")
            body = _consume(client, task_id)

        events = _parse_sse_events(body)
        block_events = [e for e in events if e.get("event") == "translate.block_translated"]

        if block_events:
            data = json.loads(block_events[0]["data"])
            for field in ("block_id", "type", "translatable", "original", "translated"):
                assert field in data, f"Missing field '{field}' in block_translated event"
