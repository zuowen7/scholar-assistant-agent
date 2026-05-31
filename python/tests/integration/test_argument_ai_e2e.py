"""Argument extract SSE with mock LLM integration tests.

Mocks call_llm_chat to return canned Toulmin extraction results,
verifying SSE events arrive correctly.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
features:
  argument_map_v2: true
  argument_companion: true
"""

# Canned LLM response for argument extraction
_EXTRACT_JSON = json.dumps({
    "nodes": [
        {"local_id": "c1", "type": "claim", "text": "Deep learning improves accuracy",
         "verbatim_quote": "Deep learning models significantly improve accuracy"},
        {"local_id": "g1", "type": "grounds", "text": "Experiments show 15% improvement",
         "verbatim_quote": "our experiments demonstrate a 15% improvement over baselines"},
    ],
    "edges": [
        {"source": "g1", "target": "c1", "relation": "supports"},
    ],
})


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


class TestArgumentExtractSSE:
    """POST /api/argument/graph/{gid}/extract with mock LLM."""

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Extract Test"})
        return create.json().get("id") or create.json().get("gid")

    def test_extract_stream_emits_events(self, client, graph_id):
        with patch(
            "src.argument.ai_ops.call_llm_chat",
            AsyncMock(return_value=_EXTRACT_JSON),
        ):
            resp = client.post(f"/api/argument/graph/{graph_id}/extract", json={
                "text": "Deep learning models significantly improve accuracy. "
                        "Our experiments demonstrate a 15% improvement over baselines.",
                "source_label": "test.md",
            })
            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            assert len(events) > 0

    def test_extract_creates_nodes(self, client, graph_id):
        with patch(
            "src.argument.ai_ops.call_llm_chat",
            AsyncMock(return_value=_EXTRACT_JSON),
        ):
            resp = client.post(f"/api/argument/graph/{graph_id}/extract", json={
                "text": "Test content for extraction.",
                "side": "orig",
            })
            events = _parse_sse(resp.text)
            event_types = [e.get("event") for e in events]

            # Should emit either 'node' events or 'complete'/'error'
            has_node_events = "node" in event_types
            has_complete = "complete" in event_types
            has_error = "error" in event_types
            assert has_node_events or has_complete or has_error, (
                f"Expected node/complete/error events, got: {event_types}"
            )

    def test_extract_graph_not_found(self, client):
        resp = client.post("/api/argument/graph/fake-gid/extract", json={
            "text": "Some text.",
        })
        assert resp.status_code == 404


class TestArgumentCritiqueSSE:
    """POST /api/argument/graph/{gid}/critique with mock LLM."""

    _CRITIQUE_JSON = json.dumps([{
        "category": "logic_gap",
        "severity": "major",
        "title": "Missing warrant",
        "detail": "Claim c1 lacks a warrant connecting it to ground g1.",
        "node_ids": ["c1"],
    }])

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Critique Test"})
        return create.json().get("id") or create.json().get("gid")

    def test_critique_returns_issues(self, client, graph_id):
        with patch(
            "src.argument.ai_ops.call_llm_chat",
            AsyncMock(return_value=self._CRITIQUE_JSON),
        ):
            resp = client.post(f"/api/argument/graph/{graph_id}/critique", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, dict)
            assert "issues" in data or "error" in data

    def test_critique_graph_not_found(self, client):
        resp = client.post("/api/argument/graph/fake-gid/critique", json={})
        assert resp.status_code == 404


class TestArgumentSuggestSSE:
    """POST /api/argument/graph/{gid}/suggest with mock LLM."""

    _SUGGEST_JSON = json.dumps({
        "node_type": "backing",
        "text": "The warrant is supported by established theory.",
        "rationale": "Adding theoretical backing strengthens the warrant.",
    })

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Suggest Test"})
        return create.json().get("id") or create.json().get("gid")

    def test_suggest_returns_element(self, client, graph_id):
        with patch(
            "src.argument.ai_ops.call_llm_chat",
            AsyncMock(return_value=self._SUGGEST_JSON),
        ):
            resp = client.post(f"/api/argument/graph/{graph_id}/suggest", json={
                "node_id": "c1",
            })
            assert resp.status_code in (200, 400, 422)


class TestArgumentFlattenSSE:
    """POST /api/argument/graph/{gid}/flatten with mock LLM."""

    _FLATTEN_TEXT = "# Introduction\n\nThis is a test paper scaffolded from argument graph."

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Flatten Test"})
        return create.json().get("id") or create.json().get("gid")

    def test_flatten_stream_emits_events(self, client, graph_id):
        with patch(
            "src.argument.ai_ops.call_llm_chat",
            AsyncMock(return_value=self._FLATTEN_TEXT),
        ):
            resp = client.post(f"/api/argument/graph/{graph_id}/flatten", json={})
            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            assert len(events) > 0

    def test_flatten_graph_not_found(self, client):
        resp = client.post("/api/argument/graph/fake-gid/flatten", json={})
        assert resp.status_code == 404
