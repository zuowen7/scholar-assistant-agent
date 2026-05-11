"""Phase 4 TDD — AI ops unit tests (LLM mocked).

Tests extract_argument (SSE streaming) and suggest_element (no store write).
Uses asyncio.run() instead of pytest-asyncio to avoid extra dependency.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.argument.models_v2 import ArgGraph, ArgNode
from src.argument.graph_store import ArgGraphStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_LLM_JSON = json.dumps({
    "nodes": [
        {"local_id": "c1", "type": "claim", "text": "AI accelerates science.", "verbatim_quote": "AI accelerates"},
        {"local_id": "g1", "type": "grounds", "text": "Papers published 3x faster.", "verbatim_quote": "Papers published"},
    ],
    "edges": [
        {"source": "g1", "target": "c1", "relation": "supports"},
    ],
})

SUGGEST_LLM_JSON = json.dumps({
    "candidates": [
        {"local_id": "g1", "type": "grounds", "text": "Empirical studies support this."},
        {"local_id": "w1", "type": "warrant", "text": "Evidence from peer review."},
    ],
    "suggested_edges": [
        {"source": "g1", "target": "CLAIM_ID", "relation": "supports"},
    ],
})

SOURCE_TEXT = "AI accelerates science in many ways. Papers published 3x faster since 2020."


@pytest.fixture
def store(tmp_path):
    return ArgGraphStore(runtime_dir=tmp_path)


@pytest.fixture
def graph_id(store):
    g = store.create(title="Test Graph")
    return g.id


def _run(coro):
    """Helper: run an async coroutine synchronously."""
    return asyncio.run(coro)


async def _collect_extract(graph_id, store, llm_json):
    """Consume the async generator from extract_argument."""
    from src.argument.ai_ops import extract_argument
    events = []
    async for ev in extract_argument(
        gid=graph_id, text=SOURCE_TEXT,
        source_label="test", side="trans", store=store,
    ):
        events.append(ev)
    return events


# ── extract_argument ───────────────────────────────────────────────────────────

class TestExtractArgument:
    def test_emits_node_events(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            events = _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        assert any(e["event"] == "node" for e in events)

    def test_emits_edge_events(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            events = _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        assert any(e["event"] == "edge" for e in events)

    def test_emits_complete_event_last(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            events = _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        assert events[-1]["event"] == "complete"

    def test_writes_nodes_to_store(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        g = store.get(graph_id)
        assert len(g.nodes) == 2

    def test_writes_edges_to_store(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        g = store.get(graph_id)
        assert len(g.edges) == 1

    def test_creates_spans_for_quotes(self, store, graph_id):
        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = VALID_LLM_JSON
            _run(_collect_extract(graph_id, store, VALID_LLM_JSON))
        g = store.get(graph_id)
        assert len(g.spans) == 2  # one per node with verbatim_quote

    def test_invalid_json_emits_error_not_complete(self, store, graph_id):
        async def _run_bad():
            from src.argument.ai_ops import extract_argument
            events = []
            async for ev in extract_argument(
                gid=graph_id, text=SOURCE_TEXT,
                source_label="test", side="trans", store=store,
            ):
                events.append(ev)
            return events

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = "not json at all #!@"
            events = _run(_run_bad())

        assert any(e["event"] == "error" for e in events)
        assert not any(e["event"] == "complete" for e in events)

    def test_invalid_json_does_not_write_dirty_data(self, store, graph_id):
        async def _run_bad():
            from src.argument.ai_ops import extract_argument
            async for _ in extract_argument(
                gid=graph_id, text=SOURCE_TEXT,
                source_label="test", side="trans", store=store,
            ):
                pass

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = "not json at all"
            _run(_run_bad())

        g = store.get(graph_id)
        assert len(g.nodes) == 0  # no dirty data

    def test_illegal_edge_skipped_with_warning(self, store, graph_id):
        """claim->claim via supports is illegal — edge dropped, warning emitted."""
        bad_json = json.dumps({
            "nodes": [
                {"local_id": "c1", "type": "claim", "text": "Claim 1.", "verbatim_quote": "AI accelerates"},
                {"local_id": "c2", "type": "claim", "text": "Claim 2.", "verbatim_quote": "Papers published"},
            ],
            "edges": [
                {"source": "c1", "target": "c2", "relation": "supports"},
            ],
        })

        async def _run_bad():
            from src.argument.ai_ops import extract_argument
            events = []
            async for ev in extract_argument(
                gid=graph_id, text=SOURCE_TEXT,
                source_label="test", side="trans", store=store,
            ):
                events.append(ev)
            return events

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = bad_json
            events = _run(_run_bad())

        g = store.get(graph_id)
        assert len(g.edges) == 0
        complete_ev = next(e for e in events if e["event"] == "complete")
        data = json.loads(complete_ev["data"])
        assert len(data.get("warnings", [])) > 0


# ── suggest_element ────────────────────────────────────────────────────────────

class TestSuggestElement:
    def test_returns_candidates(self, store, graph_id):
        claim = store.upsert_node(graph_id, ArgNode(node_type="claim", text="My claim."))

        async def _run_suggest():
            from src.argument.ai_ops import suggest_element
            return await suggest_element(graph_id=graph_id, node_id=claim.id, store=store)

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = SUGGEST_LLM_JSON
            result = _run(_run_suggest())

        assert "candidates" in result
        assert len(result["candidates"]) > 0

    def test_does_not_save_candidates_to_store(self, store, graph_id):
        claim = store.upsert_node(graph_id, ArgNode(node_type="claim", text="My claim."))

        async def _run_suggest():
            from src.argument.ai_ops import suggest_element
            await suggest_element(graph_id=graph_id, node_id=claim.id, store=store)

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.return_value = SUGGEST_LLM_JSON
            _run(_run_suggest())

        g = store.get(graph_id)
        assert len(g.nodes) == 1  # only original claim

    def test_unknown_node_returns_empty(self, store, graph_id):
        async def _run_suggest():
            from src.argument.ai_ops import suggest_element
            return await suggest_element(graph_id=graph_id, node_id="n_nonexistent", store=store)

        result = _run(_run_suggest())
        assert result["candidates"] == []

    def test_llm_error_returns_empty_candidates(self, store, graph_id):
        claim = store.upsert_node(graph_id, ArgNode(node_type="claim", text="My claim."))

        async def _run_suggest():
            from src.argument.ai_ops import suggest_element
            return await suggest_element(graph_id=graph_id, node_id=claim.id, store=store)

        with patch("src.argument.ai_ops.call_llm_chat", new_callable=AsyncMock) as m:
            m.side_effect = RuntimeError("LLM unavailable")
            result = _run(_run_suggest())

        assert result["candidates"] == []
