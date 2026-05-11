"""Phase 1 TDD — Toulmin 论证图 v2 数据模型测试。

在实现 python/src/argument/models.py 重写之前，本文件中的测试应当失败。
实现完成后，所有测试必须通过。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _import_models():
    """延迟导入，使测试文件即便实现未就绪也能被收集。"""
    from src.argument.models_v2 import (
        NodeType, RelationType,
        SpanMapping, ArgIssue, ArgNode, ArgEdge, ArgGraph,
        ALLOWED_EDGES,
    )
    return NodeType, RelationType, SpanMapping, ArgIssue, ArgNode, ArgEdge, ArgGraph, ALLOWED_EDGES


# ── NodeType / RelationType 枚举校验 ────────────────────────────────────────

class TestNodeType:
    def test_valid_values(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        for nt in ("claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"):
            node = ArgNode(node_type=nt, text="test")
            assert node.node_type == nt

    def test_invalid_node_type_raises(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            ArgNode(node_type="invalid_type", text="test")


class TestRelationType:
    def test_valid_values(self):
        _, _, _, _, _, ArgEdge, _, _ = _import_models()
        for rt in ("supports", "warrants", "backs", "qualifies", "rebuts", "counters"):
            edge = ArgEdge(source_id="a", target_id="b", relation_type=rt)
            assert edge.relation_type == rt

    def test_invalid_relation_type_raises(self):
        _, _, _, _, _, ArgEdge, _, _ = _import_models()
        with pytest.raises(ValidationError):
            ArgEdge(source_id="a", target_id="b", relation_type="hates")


# ── SpanMapping ──────────────────────────────────────────────────────────────

class TestSpanMapping:
    def test_minimal_required_fields(self):
        _, _, SpanMapping, _, _, _, _, _ = _import_models()
        span = SpanMapping(node_id="n1", source_type="block", quote="some text")
        assert span.node_id == "n1"
        assert span.quote == "some text"
        assert span.char_start is None
        assert span.char_end is None
        assert span.side == "trans"

    def test_auto_id_generated(self):
        _, _, SpanMapping, _, _, _, _, _ = _import_models()
        s1 = SpanMapping(node_id="n1", source_type="block", quote="x")
        s2 = SpanMapping(node_id="n1", source_type="block", quote="y")
        assert s1.id != s2.id
        assert s1.id.startswith("sp_")

    def test_invalid_source_type_raises(self):
        _, _, SpanMapping, _, _, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            SpanMapping(node_id="n1", source_type="unknown", quote="x")

    def test_invalid_side_raises(self):
        _, _, SpanMapping, _, _, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            SpanMapping(node_id="n1", source_type="block", quote="x", side="both")

    def test_missing_quote_raises(self):
        _, _, SpanMapping, _, _, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            SpanMapping(node_id="n1", source_type="block")


# ── ArgIssue ─────────────────────────────────────────────────────────────────

class TestArgIssue:
    def test_valid_severity_and_category(self):
        _, _, _, ArgIssue, _, _, _, _ = _import_models()
        issue = ArgIssue(severity="warning", category="missing_grounds", message="no grounds")
        assert issue.severity == "warning"
        assert issue.category == "missing_grounds"
        assert issue.id.startswith("is_")

    def test_invalid_severity_raises(self):
        _, _, _, ArgIssue, _, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            ArgIssue(severity="fatal", category="missing_grounds", message="x")

    def test_invalid_category_raises(self):
        _, _, _, ArgIssue, _, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            ArgIssue(severity="warning", category="bad_category", message="x")

    def test_all_valid_categories(self):
        _, _, _, ArgIssue, _, _, _, _ = _import_models()
        cats = [
            "missing_grounds", "missing_warrant", "missing_backing",
            "unaddressed_rebuttal", "fallacy", "weak_link", "orphan",
            "unsupported_qualifier", "other",
        ]
        for cat in cats:
            issue = ArgIssue(severity="info", category=cat, message="x")
            assert issue.category == cat


# ── ArgNode ──────────────────────────────────────────────────────────────────

class TestArgNode:
    def test_default_created_by_is_user(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        node = ArgNode(node_type="claim", text="This is a claim")
        assert node.created_by == "user"

    def test_auto_id_starts_with_n(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        node = ArgNode(node_type="claim", text="x")
        assert node.id.startswith("n_")

    def test_span_ids_default_empty(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        node = ArgNode(node_type="grounds", text="evidence")
        assert node.span_ids == []
        assert node.issue_ids == []

    def test_qualifier_can_have_confidence(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        node = ArgNode(node_type="qualifier", text="probably", confidence=0.75)
        assert node.confidence == 0.75

    def test_ai_created_by(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        node = ArgNode(node_type="claim", text="AI claim", created_by="ai")
        assert node.created_by == "ai"

    def test_invalid_created_by_raises(self):
        _, _, _, _, ArgNode, _, _, _ = _import_models()
        with pytest.raises(ValidationError):
            ArgNode(node_type="claim", text="x", created_by="robot")


# ── ArgEdge ──────────────────────────────────────────────────────────────────

class TestArgEdge:
    def test_auto_id_starts_with_e(self):
        _, _, _, _, _, ArgEdge, _, _ = _import_models()
        edge = ArgEdge(source_id="n1", target_id="n2", relation_type="supports")
        assert edge.id.startswith("e_")

    def test_all_fields_stored(self):
        _, _, _, _, _, ArgEdge, _, _ = _import_models()
        edge = ArgEdge(source_id="a", target_id="b", relation_type="rebuts", label="attacks claim")
        assert edge.source_id == "a"
        assert edge.target_id == "b"
        assert edge.relation_type == "rebuts"
        assert edge.label == "attacks claim"


# ── ArgGraph ─────────────────────────────────────────────────────────────────

class TestArgGraph:
    def test_empty_graph_defaults(self):
        _, _, _, _, _, _, ArgGraph, _ = _import_models()
        g = ArgGraph(title="Test Graph")
        assert g.title == "Test Graph"
        assert g.nodes == []
        assert g.edges == []
        assert g.spans == []
        assert g.issues == []
        assert g.source_doc is None
        assert g.id.startswith("g_")

    def test_auto_timestamps(self):
        _, _, _, _, _, _, ArgGraph, _ = _import_models()
        g = ArgGraph(title="x")
        assert g.created_at > 0
        assert g.updated_at > 0

    def test_can_hold_nodes_and_edges(self):
        _, _, _, _, ArgNode, ArgEdge, ArgGraph, _ = _import_models()
        n1 = ArgNode(node_type="claim", text="claim")
        n2 = ArgNode(node_type="grounds", text="evidence")
        e = ArgEdge(source_id=n2.id, target_id=n1.id, relation_type="supports")
        g = ArgGraph(title="x", nodes=[n1, n2], edges=[e])
        assert len(g.nodes) == 2
        assert len(g.edges) == 1


# ── ALLOWED_EDGES constraint dict ────────────────────────────────────────────

class TestAllowedEdges:
    def test_supports_only_grounds_to_claim(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("grounds", "claim") in ALLOWED_EDGES["supports"]
        assert ("claim", "claim") not in ALLOWED_EDGES["supports"]

    def test_warrants_only_warrant_to_claim(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("warrant", "claim") in ALLOWED_EDGES["warrants"]

    def test_backs_only_backing_to_warrant(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("backing", "warrant") in ALLOWED_EDGES["backs"]

    def test_qualifies_only_qualifier_to_claim(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("qualifier", "claim") in ALLOWED_EDGES["qualifies"]

    def test_rebuts_only_rebuttal_to_claim(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("rebuttal", "claim") in ALLOWED_EDGES["rebuts"]

    def test_counters_allows_two_source_types(self):
        *_, ALLOWED_EDGES = _import_models()
        assert ("claim", "rebuttal") in ALLOWED_EDGES["counters"]
        assert ("grounds", "rebuttal") in ALLOWED_EDGES["counters"]

    def test_all_six_relation_types_present(self):
        *_, ALLOWED_EDGES = _import_models()
        assert set(ALLOWED_EDGES.keys()) == {
            "supports", "warrants", "backs", "qualifies", "rebuts", "counters"
        }
