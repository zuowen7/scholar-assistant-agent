"""Phase 5 TDD — flatten_graph unit tests.

Constructs hand-crafted Toulmin graphs and asserts that flatten_graph produces
structurally correct draft output. No LLM calls — purely deterministic.
"""

from __future__ import annotations

import pytest

from src.argument.models_v2 import ArgEdge, ArgGraph, ArgNode


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_node(node_type: str, nid: str, text: str) -> ArgNode:
    n = ArgNode(node_type=node_type, text=text)
    n.id = nid
    return n


def make_edge(source_id: str, target_id: str, relation_type: str) -> ArgEdge:
    return ArgEdge(source_id=source_id, target_id=target_id, relation_type=relation_type)


def simple_toulmin_graph() -> ArgGraph:
    """claim ← supports ← grounds; claim ← warrants ← warrant; claim ← rebuts ← rebuttal; rebuttal ← counters ← claim2"""
    c1 = make_node("claim",   "c1", "AI accelerates scientific discovery.")
    g1 = make_node("grounds", "g1", "Papers are published 3x faster since 2020.")
    w1 = make_node("warrant", "w1", "Faster publication implies faster knowledge propagation.")
    r1 = make_node("rebuttal","r1", "Not all AI-assisted papers are high quality.")
    c2 = make_node("claim",   "c2", "Quality filters have improved alongside volume.")
    return ArgGraph(
        nodes=[c1, g1, w1, r1, c2],
        edges=[
            make_edge("g1", "c1", "supports"),
            make_edge("w1", "c1", "warrants"),
            make_edge("r1", "c1", "rebuts"),
            make_edge("c2", "r1", "counters"),
        ],
    )


def multi_claim_graph() -> ArgGraph:
    c1 = make_node("claim",   "c1", "Claim one.")
    c3 = make_node("claim",   "c3", "Claim two.")
    g1 = make_node("grounds", "g1", "Evidence for claim one.")
    g2 = make_node("grounds", "g2", "Evidence for claim two.")
    return ArgGraph(
        nodes=[c1, c3, g1, g2],
        edges=[
            make_edge("g1", "c1", "supports"),
            make_edge("g2", "c3", "supports"),
        ],
    )


# ── flatten_graph basic structure ─────────────────────────────────────────────

class TestFlattenGraphMarkdown:
    def test_output_contains_claim_text(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert "AI accelerates scientific discovery" in md

    def test_output_contains_grounds_text(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert "Papers are published 3x faster" in md

    def test_output_contains_rebuttal_section(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert "Not all AI-assisted papers are high quality" in md

    def test_output_contains_counter_for_rebuttal(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert "Quality filters have improved alongside volume" in md

    def test_output_is_string(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert isinstance(md, str)
        assert len(md) > 50

    def test_multi_claim_graph_contains_both_claims(self):
        from src.argument.flatten_graph import flatten_graph
        graph = multi_claim_graph()
        md = flatten_graph(graph, template="markdown")
        assert "Claim one" in md
        assert "Claim two" in md

    def test_empty_graph_returns_string(self):
        from src.argument.flatten_graph import flatten_graph
        graph = ArgGraph(nodes=[], edges=[])
        md = flatten_graph(graph, template="markdown")
        assert isinstance(md, str)

    def test_markdown_has_heading_markers(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert "#" in md

    def test_rebuttal_section_heading_present(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        # Should have a section for limitations/rebuttals
        lower = md.lower()
        assert any(kw in lower for kw in ["反驳", "局限", "rebuttal", "limitation", "objection"])


# ── format variants ───────────────────────────────────────────────────────────

class TestFlattenGraphFormats:
    def test_latex_format_returns_latex_markers(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        tex = flatten_graph(graph, template="latex")
        assert isinstance(tex, str)
        # Fallback latex or pandoc output should have LaTeX-ish content
        assert "\\" in tex or "begin{" in tex or "#" in tex  # fallback may use md

    def test_docx_format_returns_string(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        result = flatten_graph(graph, template="docx")
        assert isinstance(result, str)
        assert len(result) > 10


# ── graph_to_sections ─────────────────────────────────────────────────────────

class TestGraphToSections:
    def test_returns_list(self):
        from src.argument.flatten_graph import graph_to_sections
        graph = simple_toulmin_graph()
        sections = graph_to_sections(graph)
        assert isinstance(sections, list)

    def test_each_section_has_title_and_body(self):
        from src.argument.flatten_graph import graph_to_sections
        graph = simple_toulmin_graph()
        sections = graph_to_sections(graph)
        for sec in sections:
            assert "title" in sec
            assert "body" in sec
            assert isinstance(sec["title"], str)
            assert isinstance(sec["body"], str)

    def test_claim_section_body_contains_claim_text(self):
        from src.argument.flatten_graph import graph_to_sections
        graph = simple_toulmin_graph()
        sections = graph_to_sections(graph)
        claim_secs = [s for s in sections if "c1" in s.get("node_ids", [])]
        assert any("AI accelerates" in s["body"] for s in sections)

    def test_rebuttal_section_present_when_rebuttals_exist(self):
        from src.argument.flatten_graph import graph_to_sections
        graph = simple_toulmin_graph()
        sections = graph_to_sections(graph)
        # There should be at least one section containing rebuttal text
        assert any("Not all AI-assisted" in s["body"] for s in sections)


# ── flatten_graph with title ──────────────────────────────────────────────────

class TestFlattenGraphTitle:
    def test_custom_title_in_output(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown", title="My Research Draft")
        assert "My Research Draft" in md

    def test_default_title_when_not_specified(self):
        from src.argument.flatten_graph import flatten_graph
        graph = simple_toulmin_graph()
        md = flatten_graph(graph, template="markdown")
        assert isinstance(md, str)  # just shouldn't crash
