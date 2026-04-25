"""Small deterministic rule checker for argument maps."""

from __future__ import annotations

from typing import Any


CLASSIC_CHAIN = ("model", "analysis", "simulation", "experiment", "conclusion")
MARGIN_TERMS = ("margin", "phase margin", "gain margin", "stability margin")


def _node_text(node: dict[str, Any]) -> str:
    parts = [
        node.get("topic", ""),
        node.get("content", ""),
        " ".join(node.get("domain_tags") or []),
    ]
    return " ".join(str(p).lower() for p in parts if p)


def check_argument_tree(tree: dict[str, Any], node_id: str = "root", include_subtree: bool = True) -> dict[str, Any]:
    nodes = tree.get("nodes", {})
    root_id = tree.get("root_id")
    start_id = root_id if node_id in ("root", None, "") else node_id
    if start_id not in nodes:
        return {"reviewed_node_id": start_id, "reviewed_subtree": [], "overall_status": "error", "rule_results": []}

    reviewed: list[str] = []

    def walk(nid: str) -> None:
        if nid in reviewed or nid not in nodes:
            return
        reviewed.append(nid)
        if include_subtree:
            for child_id in nodes[nid].get("children", []):
                walk(child_id)

    walk(start_id)
    text = " ".join(_node_text(nodes[nid]) for nid in reviewed)
    issues: list[dict[str, Any]] = []

    missing = [term for term in CLASSIC_CHAIN if term not in text]
    if len(missing) >= 2:
        issues.append({
            "issue_code": "MISSING_CLASSIC_CHAIN",
            "severity": "warning",
            "node_ids": [start_id],
            "related_nodes": [],
            "description": "The argument chain is missing core modeling, analysis, validation, or conclusion steps.",
            "suggestion": "Add nodes that cover problem modeling, analysis, validation, and conclusion.",
            "template": None,
        })

    mentions_stability = any(word in text for word in ("stability", "stable", "control"))
    has_margin = any(term in text for term in MARGIN_TERMS)
    if mentions_stability and not has_margin:
        issues.append({
            "issue_code": "MISSING_MARGIN_ANALYSIS",
            "severity": "warning",
            "node_ids": [start_id],
            "related_nodes": [],
            "description": "Stability is mentioned but phase margin or gain margin analysis is not present.",
            "suggestion": "Add a phase margin / gain margin analysis node under the stability analysis branch.",
            "template": "Mentions {topic}, but no {required} node is present.",
        })

    for nid in reviewed:
        node = nodes[nid]
        if node.get("references") and not any(word in _node_text(node) for word in ("result", "conclusion", "shows", "indicates")):
            issues.append({
                "issue_code": "ORPHAN_REFERENCE",
                "severity": "warning",
                "node_ids": [nid],
                "related_nodes": [],
                "description": "A referenced node does not yet contain a downstream claim or conclusion.",
                "suggestion": "Add a short conclusion that explains how the bound reference supports this argument.",
                "template": None,
            })

    overall = "error" if any(i["severity"] == "error" for i in issues) else ("warning" if issues else "pass")
    return {
        "reviewed_node_id": start_id,
        "reviewed_subtree": reviewed,
        "overall_status": overall,
        "rule_results": issues,
    }
