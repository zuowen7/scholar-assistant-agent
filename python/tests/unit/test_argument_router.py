"""Phase 1 TDD — argument v2 路由端点测试。

使用 FastAPI TestClient；feature flag 通过环境变量注入控制。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _build_app(tmp_path: Path, flag_enabled: bool = True) -> FastAPI:
    """构建带 v2 端点的 FastAPI 应用，注入临时目录作为 runtime_dir。"""
    from src.argument.graph_store import ArgGraphStore
    from routers.argument import register_argument_v2

    app = FastAPI()
    store = ArgGraphStore(runtime_dir=tmp_path)
    register_argument_v2(app, store=store, flag_enabled=flag_enabled)
    return app


@pytest.fixture
def client(tmp_path):
    app = _build_app(tmp_path, flag_enabled=True)
    return TestClient(app)


@pytest.fixture
def client_disabled(tmp_path):
    app = _build_app(tmp_path, flag_enabled=False)
    return TestClient(app)


# ── Feature flag 行为 ────────────────────────────────────────────────────────

class TestFeatureFlag:
    def test_v2_endpoints_return_404_when_flag_disabled(self, client_disabled):
        r = client_disabled.get("/api/argument/graphs")
        assert r.status_code == 404

    def test_v2_endpoints_available_when_flag_enabled(self, client):
        r = client.get("/api/argument/graphs")
        assert r.status_code == 200


# ── 图 CRUD 端点 ──────────────────────────────────────────────────────────────

class TestGraphEndpoints:
    def test_list_graphs_empty(self, client):
        r = client.get("/api/argument/graphs")
        assert r.status_code == 200
        assert r.json() == []

    def test_create_graph(self, client):
        r = client.post("/api/argument/graph", json={"title": "My Graph"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "My Graph"
        assert data["id"].startswith("g_")

    def test_create_graph_default_title(self, client):
        r = client.post("/api/argument/graph", json={})
        assert r.status_code == 200

    def test_get_graph(self, client):
        create_r = client.post("/api/argument/graph", json={"title": "Fetch Me"})
        gid = create_r.json()["id"]
        r = client.get(f"/api/argument/graph/{gid}")
        assert r.status_code == 200
        assert r.json()["id"] == gid

    def test_get_nonexistent_graph_404(self, client):
        r = client.get("/api/argument/graph/g_nonexistent")
        assert r.status_code == 404

    def test_delete_graph(self, client):
        create_r = client.post("/api/argument/graph", json={"title": "Delete Me"})
        gid = create_r.json()["id"]
        r = client.delete(f"/api/argument/graph/{gid}")
        assert r.status_code == 200
        assert client.get(f"/api/argument/graph/{gid}").status_code == 404

    def test_list_graphs_after_create(self, client):
        client.post("/api/argument/graph", json={"title": "A"})
        client.post("/api/argument/graph", json={"title": "B"})
        r = client.get("/api/argument/graphs")
        assert r.status_code == 200
        assert len(r.json()) == 2


# ── 节点端点 ──────────────────────────────────────────────────────────────────

class TestNodeEndpoints:
    def _graph(self, client) -> str:
        return client.post("/api/argument/graph", json={"title": "G"}).json()["id"]

    def test_upsert_node_creates(self, client):
        gid = self._graph(client)
        r = client.put(f"/api/argument/graph/{gid}/node",
                       json={"node_type": "claim", "text": "A claim"})
        assert r.status_code == 200
        data = r.json()
        assert data["node_type"] == "claim"
        assert data["id"].startswith("n_")

    def test_upsert_node_updates(self, client):
        gid = self._graph(client)
        create_r = client.put(f"/api/argument/graph/{gid}/node",
                              json={"node_type": "claim", "text": "Original"})
        nid = create_r.json()["id"]
        update_r = client.put(f"/api/argument/graph/{gid}/node",
                              json={"id": nid, "node_type": "claim", "text": "Updated"})
        assert update_r.status_code == 200
        assert update_r.json()["text"] == "Updated"
        graph_r = client.get(f"/api/argument/graph/{gid}")
        nodes = graph_r.json()["nodes"]
        assert len([n for n in nodes if n["id"] == nid]) == 1

    def test_upsert_node_invalid_type_422(self, client):
        gid = self._graph(client)
        r = client.put(f"/api/argument/graph/{gid}/node",
                       json={"node_type": "bad_type", "text": "x"})
        assert r.status_code == 422

    def test_delete_node(self, client):
        gid = self._graph(client)
        create_r = client.put(f"/api/argument/graph/{gid}/node",
                              json={"node_type": "grounds", "text": "Evidence"})
        nid = create_r.json()["id"]
        r = client.delete(f"/api/argument/graph/{gid}/node/{nid}")
        assert r.status_code == 200
        graph_r = client.get(f"/api/argument/graph/{gid}")
        assert not any(n["id"] == nid for n in graph_r.json()["nodes"])

    def test_delete_nonexistent_node_404(self, client):
        gid = self._graph(client)
        r = client.delete(f"/api/argument/graph/{gid}/node/n_ghost")
        assert r.status_code == 404


# ── 边端点 ────────────────────────────────────────────────────────────────────

class TestEdgeEndpoints:
    def _setup(self, client):
        gid = client.post("/api/argument/graph", json={"title": "G"}).json()["id"]
        claim = client.put(f"/api/argument/graph/{gid}/node",
                           json={"node_type": "claim", "text": "C"}).json()
        grounds = client.put(f"/api/argument/graph/{gid}/node",
                             json={"node_type": "grounds", "text": "E"}).json()
        return gid, claim["id"], grounds["id"]

    def test_upsert_valid_edge(self, client):
        gid, claim_id, grounds_id = self._setup(client)
        r = client.put(f"/api/argument/graph/{gid}/edge", json={
            "source_id": grounds_id,
            "target_id": claim_id,
            "relation_type": "supports",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["relation_type"] == "supports"
        assert data["id"].startswith("e_")

    def test_upsert_invalid_edge_combo_400(self, client):
        gid, claim_id, grounds_id = self._setup(client)
        # grounds -> grounds with "warrants" is invalid
        r = client.put(f"/api/argument/graph/{gid}/edge", json={
            "source_id": grounds_id,
            "target_id": grounds_id,
            "relation_type": "warrants",
        })
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_edge"

    def test_self_loop_edge_400(self, client):
        gid, claim_id, _ = self._setup(client)
        r = client.put(f"/api/argument/graph/{gid}/edge", json={
            "source_id": claim_id,
            "target_id": claim_id,
            "relation_type": "supports",
        })
        assert r.status_code == 400

    def test_duplicate_edge_400(self, client):
        gid, claim_id, grounds_id = self._setup(client)
        payload = {
            "source_id": grounds_id,
            "target_id": claim_id,
            "relation_type": "supports",
        }
        client.put(f"/api/argument/graph/{gid}/edge", json=payload)
        r = client.put(f"/api/argument/graph/{gid}/edge", json=payload)
        assert r.status_code == 400

    def test_delete_edge(self, client):
        gid, claim_id, grounds_id = self._setup(client)
        edge_r = client.put(f"/api/argument/graph/{gid}/edge", json={
            "source_id": grounds_id,
            "target_id": claim_id,
            "relation_type": "supports",
        })
        eid = edge_r.json()["id"]
        r = client.delete(f"/api/argument/graph/{gid}/edge/{eid}")
        assert r.status_code == 200
        graph_r = client.get(f"/api/argument/graph/{gid}")
        assert not any(e["id"] == eid for e in graph_r.json()["edges"])


# ── Span 端点 ─────────────────────────────────────────────────────────────────

class TestSpanEndpoints:
    def _graph_with_node(self, client):
        gid = client.post("/api/argument/graph", json={"title": "G"}).json()["id"]
        nid = client.put(f"/api/argument/graph/{gid}/node",
                         json={"node_type": "claim", "text": "C"}).json()["id"]
        return gid, nid

    def test_add_span(self, client):
        gid, nid = self._graph_with_node(client)
        r = client.put(f"/api/argument/graph/{gid}/span", json={
            "node_id": nid,
            "source_type": "block",
            "quote": "relevant passage",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["id"].startswith("sp_")
        assert data["quote"] == "relevant passage"

    def test_add_span_missing_quote_422(self, client):
        gid, nid = self._graph_with_node(client)
        r = client.put(f"/api/argument/graph/{gid}/span", json={
            "node_id": nid,
            "source_type": "block",
        })
        assert r.status_code == 422

    def test_delete_span(self, client):
        gid, nid = self._graph_with_node(client)
        span_r = client.put(f"/api/argument/graph/{gid}/span", json={
            "node_id": nid,
            "source_type": "selection",
            "quote": "text",
        })
        sid = span_r.json()["id"]
        r = client.delete(f"/api/argument/graph/{gid}/span/{sid}")
        assert r.status_code == 200
        graph_r = client.get(f"/api/argument/graph/{gid}")
        assert not any(s["id"] == sid for s in graph_r.json()["spans"])

    def test_add_span_with_char_offsets(self, client):
        gid, nid = self._graph_with_node(client)
        r = client.put(f"/api/argument/graph/{gid}/span", json={
            "node_id": nid,
            "source_type": "extracted",
            "quote": "exact text",
            "char_start": 10,
            "char_end": 20,
            "block_id": "blk_001",
            "side": "orig",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["char_start"] == 10
        assert data["char_end"] == 20
        assert data["side"] == "orig"
