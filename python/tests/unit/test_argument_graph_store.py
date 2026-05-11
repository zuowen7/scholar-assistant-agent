"""Phase 1 TDD — ArgGraphStore 持久化与 CRUD 测试。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path


def _make_store(tmp_path: Path):
    from src.argument.graph_store import ArgGraphStore
    return ArgGraphStore(runtime_dir=tmp_path)


def _models():
    from src.argument.models_v2 import ArgNode, ArgEdge, SpanMapping, ArgIssue
    return ArgNode, ArgEdge, SpanMapping, ArgIssue


# ── 图 CRUD ──────────────────────────────────────────────────────────────────

class TestGraphCrud:
    def test_create_and_get(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("Test Graph")
        assert g.title == "Test Graph"
        assert g.id.startswith("g_")
        retrieved = store.get(g.id)
        assert retrieved is not None
        assert retrieved.id == g.id

    def test_list_graphs(self, tmp_path):
        store = _make_store(tmp_path)
        g1 = store.create("Graph A")
        g2 = store.create("Graph B")
        lst = store.list_graphs()
        ids = [item["id"] for item in lst]
        assert g1.id in ids
        assert g2.id in ids

    def test_list_includes_metadata(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("Meta Graph")
        lst = store.list_graphs()
        item = next(x for x in lst if x["id"] == g.id)
        assert "title" in item
        assert "node_count" in item
        assert "updated_at" in item

    def test_delete_graph(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("To Delete")
        store.delete(g.id)
        assert store.get(g.id) is None

    def test_get_nonexistent_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get("g_nonexistent") is None

    def test_delete_nonexistent_no_error(self, tmp_path):
        store = _make_store(tmp_path)
        store.delete("g_nonexistent")  # should not raise

    def test_create_with_source_doc(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("Sourced Graph", source_doc="paper.pdf")
        assert store.get(g.id).source_doc == "paper.pdf"


# ── 节点 CRUD ────────────────────────────────────────────────────────────────

class TestNodeCrud:
    def test_upsert_node_creates_new(self, tmp_path):
        ArgNode, _, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="claim", text="My claim")
        result = store.upsert_node(g.id, node)
        graph = store.get(g.id)
        assert any(n.id == result.id for n in graph.nodes)

    def test_upsert_node_updates_existing(self, tmp_path):
        ArgNode, _, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="claim", text="Original")
        store.upsert_node(g.id, node)
        node.text = "Updated"
        store.upsert_node(g.id, node)
        graph = store.get(g.id)
        stored = next(n for n in graph.nodes if n.id == node.id)
        assert stored.text == "Updated"
        assert len([n for n in graph.nodes if n.id == node.id]) == 1

    def test_delete_node_removes_it(self, tmp_path):
        ArgNode, _, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="grounds", text="Evidence")
        store.upsert_node(g.id, node)
        store.delete_node(g.id, node.id)
        graph = store.get(g.id)
        assert not any(n.id == node.id for n in graph.nodes)

    def test_delete_node_cascades_incident_edges(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        claim = ArgNode(node_type="claim", text="C")
        grounds = ArgNode(node_type="grounds", text="G")
        store.upsert_node(g.id, claim)
        store.upsert_node(g.id, grounds)
        edge = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        store.upsert_edge(g.id, edge)
        store.delete_node(g.id, grounds.id)
        graph = store.get(g.id)
        assert not any(e.id == edge.id for e in graph.edges)

    def test_delete_node_cascades_spans(self, tmp_path):
        ArgNode, _, SpanMapping, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="claim", text="C")
        store.upsert_node(g.id, node)
        span = SpanMapping(node_id=node.id, source_type="block", quote="some text")
        store.add_span(g.id, span)
        store.delete_node(g.id, node.id)
        graph = store.get(g.id)
        assert not any(s.id == span.id for s in graph.spans)


# ── 边 CRUD + 校验 ───────────────────────────────────────────────────────────

class TestEdgeCrud:
    def test_upsert_valid_edge(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        claim = ArgNode(node_type="claim", text="C")
        grounds = ArgNode(node_type="grounds", text="Ev")
        store.upsert_node(g.id, claim)
        store.upsert_node(g.id, grounds)
        edge = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        result = store.upsert_edge(g.id, edge)
        graph = store.get(g.id)
        assert any(e.id == result.id for e in graph.edges)

    def test_upsert_invalid_type_combo_raises(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        c1 = ArgNode(node_type="claim", text="C1")
        c2 = ArgNode(node_type="claim", text="C2")
        store.upsert_node(g.id, c1)
        store.upsert_node(g.id, c2)
        # claim -> claim with "supports" is not allowed
        edge = ArgEdge(source_id=c1.id, target_id=c2.id, relation_type="supports")
        with pytest.raises(ValueError, match="invalid_edge"):
            store.upsert_edge(g.id, edge)

    def test_self_loop_raises(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="claim", text="C")
        store.upsert_node(g.id, node)
        edge = ArgEdge(source_id=node.id, target_id=node.id, relation_type="supports")
        with pytest.raises(ValueError, match="self.loop"):
            store.upsert_edge(g.id, edge)

    def test_duplicate_edge_raises(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        claim = ArgNode(node_type="claim", text="C")
        grounds = ArgNode(node_type="grounds", text="Ev")
        store.upsert_node(g.id, claim)
        store.upsert_node(g.id, grounds)
        edge = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        store.upsert_edge(g.id, edge)
        edge2 = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        with pytest.raises(ValueError, match="duplicate"):
            store.upsert_edge(g.id, edge2)

    def test_delete_edge(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        claim = ArgNode(node_type="claim", text="C")
        grounds = ArgNode(node_type="grounds", text="Ev")
        store.upsert_node(g.id, claim)
        store.upsert_node(g.id, grounds)
        edge = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        store.upsert_edge(g.id, edge)
        store.delete_edge(g.id, edge.id)
        graph = store.get(g.id)
        assert not any(e.id == edge.id for e in graph.edges)

    def test_all_valid_relation_combos(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        combos = [
            ("grounds", "claim", "supports"),
            ("warrant", "claim", "warrants"),
            ("backing", "warrant", "backs"),
            ("qualifier", "claim", "qualifies"),
            ("rebuttal", "claim", "rebuts"),
            ("claim", "rebuttal", "counters"),
            ("grounds", "rebuttal", "counters"),
        ]
        created_nodes: dict[str, ArgNode] = {}
        for src_type, tgt_type, rel in combos:
            src_key = f"{src_type}_{rel}"
            tgt_key = f"{tgt_type}_{rel}"
            if src_key not in created_nodes:
                n = ArgNode(node_type=src_type, text=src_type)
                store.upsert_node(g.id, n)
                created_nodes[src_key] = n
            if tgt_key not in created_nodes:
                n = ArgNode(node_type=tgt_type, text=tgt_type)
                store.upsert_node(g.id, n)
                created_nodes[tgt_key] = n
            edge = ArgEdge(
                source_id=created_nodes[src_key].id,
                target_id=created_nodes[tgt_key].id,
                relation_type=rel,
            )
            result = store.upsert_edge(g.id, edge)
            assert result.id.startswith("e_")


# ── Span CRUD ────────────────────────────────────────────────────────────────

class TestSpanCrud:
    def test_add_and_retrieve_span(self, tmp_path):
        ArgNode, _, SpanMapping, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="claim", text="C")
        store.upsert_node(g.id, node)
        span = SpanMapping(node_id=node.id, source_type="block", quote="relevant text")
        store.add_span(g.id, span)
        graph = store.get(g.id)
        assert any(s.id == span.id for s in graph.spans)

    def test_delete_span(self, tmp_path):
        ArgNode, _, SpanMapping, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("G")
        node = ArgNode(node_type="grounds", text="G")
        store.upsert_node(g.id, node)
        span = SpanMapping(node_id=node.id, source_type="selection", quote="selected text")
        store.add_span(g.id, span)
        store.delete_span(g.id, span.id)
        graph = store.get(g.id)
        assert not any(s.id == span.id for s in graph.spans)


# ── JSON 持久化 round-trip ────────────────────────────────────────────────────

class TestPersistence:
    def test_graph_survives_reload(self, tmp_path):
        ArgNode, ArgEdge, SpanMapping, _ = _models()
        from src.argument.graph_store import ArgGraphStore

        store = ArgGraphStore(runtime_dir=tmp_path)
        g = store.create("Persistent Graph")
        node = ArgNode(node_type="claim", text="Durable claim")
        store.upsert_node(g.id, node)

        # Reload from disk
        store2 = ArgGraphStore(runtime_dir=tmp_path)
        g2 = store2.get(g.id)
        assert g2 is not None
        assert g2.title == "Persistent Graph"
        assert any(n.text == "Durable claim" for n in g2.nodes)

    def test_json_file_created_on_graph_creation(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("File Test")
        graphs_dir = tmp_path / "argument_graphs"
        assert graphs_dir.exists()
        json_file = graphs_dir / f"{g.id}.json"
        assert json_file.exists()

    def test_json_file_deleted_on_graph_deletion(self, tmp_path):
        store = _make_store(tmp_path)
        g = store.create("Del Test")
        json_file = tmp_path / "argument_graphs" / f"{g.id}.json"
        assert json_file.exists()
        store.delete(g.id)
        assert not json_file.exists()

    def test_edges_and_spans_survive_reload(self, tmp_path):
        ArgNode, ArgEdge, SpanMapping, _ = _models()
        from src.argument.graph_store import ArgGraphStore

        store = ArgGraphStore(runtime_dir=tmp_path)
        g = store.create("Full Graph")
        claim = ArgNode(node_type="claim", text="C")
        grounds = ArgNode(node_type="grounds", text="E")
        store.upsert_node(g.id, claim)
        store.upsert_node(g.id, grounds)
        edge = ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports")
        store.upsert_edge(g.id, edge)
        span = SpanMapping(node_id=claim.id, source_type="block", quote="claim text")
        store.add_span(g.id, span)

        store2 = ArgGraphStore(runtime_dir=tmp_path)
        g2 = store2.get(g.id)
        assert any(e.relation_type == "supports" for e in g2.edges)
        assert any(s.quote == "claim text" for s in g2.spans)


# ── replace_graph ─────────────────────────────────────────────────────────────

class TestReplaceGraph:
    def test_replace_graph_bulk_write(self, tmp_path):
        ArgNode, ArgEdge, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("Replace Test")

        nodes = [
            ArgNode(node_type="claim", text="Claim 1"),
            ArgNode(node_type="grounds", text="Evidence 1"),
        ]
        edges = [
            ArgEdge(source_id=nodes[1].id, target_id=nodes[0].id, relation_type="supports"),
        ]
        store.replace_graph(g.id, nodes=nodes, edges=edges, spans=[])
        graph = store.get(g.id)
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

    def test_replace_graph_overwrites_existing(self, tmp_path):
        ArgNode, _, _, _ = _models()
        store = _make_store(tmp_path)
        g = store.create("Overwrite Test")
        old_node = ArgNode(node_type="claim", text="Old")
        store.upsert_node(g.id, old_node)

        new_nodes = [ArgNode(node_type="grounds", text="New")]
        store.replace_graph(g.id, nodes=new_nodes, edges=[], spans=[])
        graph = store.get(g.id)
        assert len(graph.nodes) == 1
        assert graph.nodes[0].text == "New"


# ── set_issues ────────────────────────────────────────────────────────────────

class TestSetIssues:
    def test_set_issues_replaces_all(self, tmp_path):
        ArgNode, _, _, ArgIssue = _models()
        store = _make_store(tmp_path)
        g = store.create("Issue Test")
        node = ArgNode(node_type="claim", text="C")
        store.upsert_node(g.id, node)

        issues = [
            ArgIssue(node_id=node.id, severity="warning",
                     category="missing_grounds", message="no grounds"),
        ]
        store.set_issues(g.id, issues)
        graph = store.get(g.id)
        assert len(graph.issues) == 1
        assert graph.issues[0].category == "missing_grounds"

    def test_set_issues_updates_node_issue_ids(self, tmp_path):
        ArgNode, _, _, ArgIssue = _models()
        store = _make_store(tmp_path)
        g = store.create("Issue Link Test")
        node = ArgNode(node_type="claim", text="C")
        store.upsert_node(g.id, node)

        issue = ArgIssue(node_id=node.id, severity="error",
                         category="orphan", message="orphan node")
        store.set_issues(g.id, [issue])
        graph = store.get(g.id)
        stored_node = next(n for n in graph.nodes if n.id == node.id)
        assert issue.id in stored_node.issue_ids
