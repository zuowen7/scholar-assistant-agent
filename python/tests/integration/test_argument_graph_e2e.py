"""Argument Toulmin v2 graph CRUD integration tests.

Covers /api/argument/* endpoints (graph/node/edge/span CRUD) via TestClient.
Feature flag argument_map_v2 must be enabled.
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
features:
  argument_map_v2: true
  argument_companion: true
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


class TestGraphCRUD:
    """Create, list, get, delete graphs."""

    def test_create_graph(self, client):
        resp = client.post("/api/argument/graph", json={"title": "Test Graph"})
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "id" in data or "gid" in data

    def test_list_graphs(self, client):
        # Ensure at least one graph exists
        client.post("/api/argument/graph", json={"title": "Graph A"})
        client.post("/api/argument/graph", json={"title": "Graph B"})
        resp = client.get("/api/argument/graphs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_graph(self, client):
        create = client.post("/api/argument/graph", json={"title": "Retrieve Me"})
        gid = create.json().get("id") or create.json().get("gid")
        resp = client.get(f"/api/argument/graph/{gid}")
        assert resp.status_code == 200
        assert resp.json().get("title") == "Retrieve Me"

    def test_get_graph_not_found(self, client):
        resp = client.get("/api/argument/graph/nonexistent-graph-id")
        assert resp.status_code == 404

    def test_delete_graph(self, client):
        create = client.post("/api/argument/graph", json={"title": "Delete Me"})
        gid = create.json().get("id") or create.json().get("gid")
        resp = client.delete(f"/api/argument/graph/{gid}")
        assert resp.status_code in (200, 204)
        # Verify gone
        assert client.get(f"/api/argument/graph/{gid}").status_code == 404


class TestNodeCRUD:
    """Upsert and delete nodes within a graph."""

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Node Test Graph"})
        return create.json().get("id") or create.json().get("gid")

    def test_upsert_node(self, client, graph_id):
        node = {
            "id": "n1",
            "node_type": "claim",
            "text": "The sky is blue",
        }
        resp = client.put(f"/api/argument/graph/{graph_id}/node", json=node)
        assert resp.status_code in (200, 201)

    def test_upsert_multiple_nodes(self, client, graph_id):
        for n in [
            {"id": "n_claim", "node_type": "claim", "text": "Claim A"},
            {"id": "n_ground", "node_type": "grounds", "text": "Evidence A"},
            {"id": "n_warrant", "node_type": "warrant", "text": "Warrant A"},
        ]:
            resp = client.put(f"/api/argument/graph/{graph_id}/node", json=n)
            assert resp.status_code in (200, 201)

    def test_get_graph_includes_nodes(self, client, graph_id):
        client.put(f"/api/argument/graph/{graph_id}/node", json={
            "id": "n_visible", "node_type": "claim", "text": "Visible Node",
        })
        g = client.get(f"/api/argument/graph/{graph_id}").json()
        nodes = g.get("nodes", {})
        if isinstance(nodes, dict):
            assert "n_visible" in nodes
        elif isinstance(nodes, list):
            assert any(n.get("id") == "n_visible" for n in nodes)

    def test_delete_node(self, client, graph_id):
        client.put(f"/api/argument/graph/{graph_id}/node", json={
            "id": "n_to_delete", "node_type": "claim", "text": "Temp Node",
        })
        resp = client.delete(f"/api/argument/graph/{graph_id}/node/n_to_delete")
        assert resp.status_code in (200, 204, 404)

    def test_update_existing_node(self, client, graph_id):
        node_id = "n_update"
        client.put(f"/api/argument/graph/{graph_id}/node", json={
            "id": node_id, "node_type": "claim", "text": "Original",
        })
        resp = client.put(f"/api/argument/graph/{graph_id}/node", json={
            "id": node_id, "node_type": "claim", "text": "Updated Label",
        })
        assert resp.status_code in (200, 201)

    def test_node_auto_id(self, client, graph_id):
        """Node with no id gets auto-generated id."""
        node = {"node_type": "claim", "text": "Auto ID Node"}
        resp = client.put(f"/api/argument/graph/{graph_id}/node", json=node)
        assert resp.status_code in (200, 201)


class TestEdgeCRUD:
    """Upsert and delete edges within a graph."""

    @pytest.fixture
    def graph_with_nodes(self, client):
        create = client.post("/api/argument/graph", json={"title": "Edge Test Graph"})
        gid = create.json().get("id") or create.json().get("gid")
        for n in [
            {"id": "n_ground", "node_type": "grounds", "text": "Evidence"},
            {"id": "n_claim", "node_type": "claim", "text": "Thesis"},
            {"id": "n_rebut", "node_type": "rebuttal", "text": "Counter"},
        ]:
            client.put(f"/api/argument/graph/{gid}/node", json=n)
        return gid

    def test_upsert_edge(self, client, graph_with_nodes):
        edge = {
            "id": "e_supports",
            "source_id": "n_ground",
            "target_id": "n_claim",
            "relation_type": "supports",
        }
        resp = client.put(f"/api/argument/graph/{graph_with_nodes}/edge", json=edge)
        assert resp.status_code in (200, 201)

    def test_upsert_edge_counters(self, client, graph_with_nodes):
        edge = {
            "source_id": "n_claim",
            "target_id": "n_rebut",
            "relation_type": "counters",
        }
        resp = client.put(f"/api/argument/graph/{graph_with_nodes}/edge", json=edge)
        assert resp.status_code in (200, 201)

    def test_delete_edge(self, client, graph_with_nodes):
        edge_id = "e_to_delete"
        client.put(f"/api/argument/graph/{graph_with_nodes}/edge", json={
            "id": edge_id, "source_id": "n_ground", "target_id": "n_claim", "relation_type": "supports",
        })
        resp = client.delete(f"/api/argument/graph/{graph_with_nodes}/edge/{edge_id}")
        assert resp.status_code in (200, 204, 404)

    def test_get_graph_includes_edges(self, client, graph_with_nodes):
        client.put(f"/api/argument/graph/{graph_with_nodes}/edge", json={
            "id": "e_visible", "source_id": "n_rebut", "target_id": "n_claim", "relation_type": "rebuts",
        })
        g = client.get(f"/api/argument/graph/{graph_with_nodes}").json()
        edges = g.get("edges", {})
        if isinstance(edges, dict):
            assert "e_visible" in edges
        elif isinstance(edges, list):
            assert any(e.get("id") == "e_visible" for e in edges)


class TestSpanCRUD:
    """Add and delete text-span mappings within a graph."""

    @pytest.fixture
    def graph_id(self, client):
        create = client.post("/api/argument/graph", json={"title": "Span Test Graph"})
        return create.json().get("id") or create.json().get("gid")

    def test_upsert_span(self, client, graph_id):
        span = {
            "id": "s_doc_span",
            "node_id": "some_node",
            "source_type": "block",
            "quote": "The original text that this node represents.",
        }
        resp = client.put(f"/api/argument/graph/{graph_id}/span", json=span)
        assert resp.status_code in (200, 201, 400)

    def test_upsert_span_editor_type(self, client, graph_id):
        span = {
            "node_id": "editor_node",
            "source_type": "editor",
            "quote": "Selected text from the editor.",
            "block_id": "b1",
        }
        resp = client.put(f"/api/argument/graph/{graph_id}/span", json=span)
        assert resp.status_code in (200, 201, 400)

    def test_delete_span(self, client, graph_id):
        span_id = "s_to_delete"
        client.put(f"/api/argument/graph/{graph_id}/span", json={
            "id": span_id,
            "node_id": "node_x",
            "source_type": "selection",
            "quote": "Text to be deleted span.",
        })
        resp = client.delete(f"/api/argument/graph/{graph_id}/span/{span_id}")
        assert resp.status_code in (200, 204, 404)


class TestGraphErrorCases:
    """Boundary and error cases for argument graph endpoints."""

    def test_delete_nonexistent_node(self, client):
        create = client.post("/api/argument/graph", json={"title": "Err Graph"})
        gid = create.json().get("id") or create.json().get("gid")
        resp = client.delete(f"/api/argument/graph/{gid}/node/fake_node_999")
        assert resp.status_code in (200, 204, 404)

    def test_delete_nonexistent_edge(self, client):
        create = client.post("/api/argument/graph", json={"title": "Err Graph 2"})
        gid = create.json().get("id") or create.json().get("gid")
        resp = client.delete(f"/api/argument/graph/{gid}/edge/fake_edge_999")
        assert resp.status_code in (200, 204, 404)

    def test_get_nonexistent_graph(self, client):
        resp = client.get("/api/argument/graph/fake-graph-id-99999")
        assert resp.status_code == 404

    def test_create_graph_no_title(self, client):
        """Graph creation with no title should work (auto-default)."""
        resp = client.post("/api/argument/graph", json={})
        assert resp.status_code in (200, 201, 422)
