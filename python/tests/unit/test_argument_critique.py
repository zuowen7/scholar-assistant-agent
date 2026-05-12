"""Phase 4 TDD — structural critique rules.

Tests structural_critique() with hand-crafted graphs.
No LLM calls — pure deterministic rule checks.
"""

from __future__ import annotations

import pytest

from src.argument.models_v2 import ArgEdge, ArgGraph, ArgNode


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_node(node_type: str, nid: str, text: str = "test") -> ArgNode:
    n = ArgNode(node_type=node_type, text=text)
    n.id = nid
    return n


def make_edge(source_id: str, target_id: str, relation_type: str) -> ArgEdge:
    return ArgEdge(source_id=source_id, target_id=target_id, relation_type=relation_type)


def make_graph(nodes: list[ArgNode], edges: list[ArgEdge] | None = None) -> ArgGraph:
    return ArgGraph(nodes=nodes, edges=edges or [])


# ── missing_grounds ────────────────────────────────────────────────────────────


class TestMissingGrounds:
    def test_claim_without_grounds_raises_warning(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        cats = [i.category for i in issues]
        assert "missing_grounds" in cats

    def test_missing_grounds_issue_severity_is_warning(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        mg = [i for i in issues if i.category == "missing_grounds"]
        assert mg[0].severity == "warning"

    def test_claim_with_grounds_no_missing_grounds(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        grounds = make_node("grounds", "g1")
        edge = make_edge("g1", "c1", "supports")
        issues = structural_critique(make_graph([claim, grounds], [edge]))
        cats = [i.category for i in issues]
        assert "missing_grounds" not in cats

    def test_missing_grounds_issue_references_claim_node_id(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        mg = [i for i in issues if i.category == "missing_grounds"]
        assert mg[0].node_id == "c1"


# ── missing_warrant ────────────────────────────────────────────────────────────


class TestMissingWarrant:
    def test_claim_without_warrant_raises_info(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        cats = [i.category for i in issues]
        assert "missing_warrant" in cats

    def test_missing_warrant_severity_is_info(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        mw = [i for i in issues if i.category == "missing_warrant"]
        assert mw[0].severity == "info"

    def test_claim_with_warrant_no_missing_warrant(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        warrant = make_node("warrant", "w1")
        edge = make_edge("w1", "c1", "warrants")
        issues = structural_critique(make_graph([claim, warrant], [edge]))
        cats = [i.category for i in issues]
        assert "missing_warrant" not in cats


# ── missing_backing ────────────────────────────────────────────────────────────


class TestMissingBacking:
    def test_warrant_without_backing_raises_issue(self):
        from src.argument.critique import structural_critique
        warrant = make_node("warrant", "w1")
        issues = structural_critique(make_graph([warrant]))
        cats = [i.category for i in issues]
        assert "missing_backing" in cats

    def test_missing_backing_severity_is_info(self):
        from src.argument.critique import structural_critique
        warrant = make_node("warrant", "w1")
        issues = structural_critique(make_graph([warrant]))
        mb = [i for i in issues if i.category == "missing_backing"]
        assert mb[0].severity == "info"

    def test_warrant_with_backing_no_issue(self):
        from src.argument.critique import structural_critique
        warrant = make_node("warrant", "w1")
        backing = make_node("backing", "b1")
        edge = make_edge("b1", "w1", "backs")
        issues = structural_critique(make_graph([warrant, backing], [edge]))
        cats = [i.category for i in issues]
        assert "missing_backing" not in cats


# ── unaddressed_rebuttal ───────────────────────────────────────────────────────


class TestUnaddressedRebuttal:
    def test_rebuttal_without_counter_raises_warning(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        rebuttal = make_node("rebuttal", "r1")
        edge = make_edge("r1", "c1", "rebuts")
        issues = structural_critique(make_graph([claim, rebuttal], [edge]))
        cats = [i.category for i in issues]
        assert "unaddressed_rebuttal" in cats

    def test_rebuttal_with_counter_no_issue(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        rebuttal = make_node("rebuttal", "r1")
        counter = make_node("claim", "c2")
        edge1 = make_edge("r1", "c1", "rebuts")
        edge2 = make_edge("c2", "r1", "counters")
        issues = structural_critique(make_graph([claim, rebuttal, counter], [edge1, edge2]))
        cats = [i.category for i in issues]
        assert "unaddressed_rebuttal" not in cats


# ── orphan ─────────────────────────────────────────────────────────────────────


class TestOrphan:
    def test_isolated_node_in_multi_node_graph_raises_orphan(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        grounds = make_node("grounds", "g1")
        orphan = make_node("backing", "b_orphan")
        edge = make_edge("g1", "c1", "supports")
        issues = structural_critique(make_graph([claim, grounds, orphan], [edge]))
        cats = [i.category for i in issues]
        assert "orphan" in cats

    def test_single_node_graph_no_orphan(self):
        from src.argument.critique import structural_critique
        node = make_node("claim", "c1")
        issues = structural_critique(make_graph([node]))
        cats = [i.category for i in issues]
        assert "orphan" not in cats

    def test_all_connected_nodes_no_orphan(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        grounds = make_node("grounds", "g1")
        edge = make_edge("g1", "c1", "supports")
        issues = structural_critique(make_graph([claim, grounds], [edge]))
        cats = [i.category for i in issues]
        assert "orphan" not in cats


# ── issue shape ────────────────────────────────────────────────────────────────


class TestIssueShape:
    def test_all_issues_have_required_fields(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        assert len(issues) > 0
        for issue in issues:
            assert issue.severity in ("info", "warning", "error")
            assert issue.category
            assert issue.message
            assert issue.id  # auto-generated

    def test_issue_node_id_references_real_node(self):
        from src.argument.critique import structural_critique
        claim = make_node("claim", "c1")
        issues = structural_critique(make_graph([claim]))
        for issue in issues:
            if issue.node_id:
                assert issue.node_id == "c1"

    def test_empty_graph_returns_no_issues(self):
        from src.argument.critique import structural_critique
        issues = structural_critique(make_graph([]))
        assert issues == []
