"""结构性论证图审查 + LLM 谬误检测。"""

from __future__ import annotations

import logging
from typing import Any

from .models_v2 import ArgGraph, ArgIssue
from src.utils.json_extract import extract_json_array

logger = logging.getLogger(__name__)


def structural_critique(graph: ArgGraph) -> list[ArgIssue]:
    """纯规则检查，不调 LLM。按图中关系边检测常见结构性缺陷。"""
    if not graph.nodes:
        return []

    issues: list[ArgIssue] = []

    # Index which nodes are connected (for orphan detection)
    connected: set[str] = set()
    # Incoming relation sets
    supports_targets: set[str] = set()
    warrants_targets: set[str] = set()
    backs_targets: set[str] = set()
    counters_targets: set[str] = set()   # rebuttal node_ids that are countered
    qualifier_sources: set[str] = set()  # qualifier node_ids with outgoing qualifies edge

    for e in graph.edges:
        connected.add(e.source_id)
        connected.add(e.target_id)
        rt = e.relation_type
        if rt == "supports":
            supports_targets.add(e.target_id)
        elif rt == "warrants":
            warrants_targets.add(e.target_id)
        elif rt == "backs":
            backs_targets.add(e.target_id)
        elif rt == "counters":
            counters_targets.add(e.target_id)
        elif rt == "qualifies":
            qualifier_sources.add(e.source_id)

    # Collect rebuttal node_ids (those that have a `rebuts` incoming edge relationship)
    # A rebuttal node is identified by its node_type == 'rebuttal'
    rebuttal_ids = {n.id for n in graph.nodes if n.node_type == "rebuttal"}

    multi_node = len(graph.nodes) > 1

    for n in graph.nodes:
        nid = n.id
        short = n.text[:30]

        if n.node_type == "claim":
            if nid not in supports_targets:
                issues.append(ArgIssue(
                    node_id=nid,
                    severity="warning",
                    category="missing_grounds",
                    message=f"主张「{short}」缺少依据（grounds）支撑",
                    suggestion='添加一个【依据】节点，并连接 supports 关系',
                ))
            if nid not in warrants_targets:
                issues.append(ArgIssue(
                    node_id=nid,
                    severity="info",
                    category="missing_warrant",
                    message=f"主张「{short}」缺少论证保证（warrant）",
                    suggestion='添加【论证保证】节点说明依据为何能支持此主张',
                ))

        elif n.node_type == "warrant":
            if nid not in backs_targets:
                issues.append(ArgIssue(
                    node_id=nid,
                    severity="info",
                    category="missing_backing",
                    message=f"论证保证「{short}」缺少支撑（backing）",
                    suggestion='添加【支撑】节点为此论证保证提供来源或权威依据',
                ))

        elif n.node_type == "rebuttal":
            if nid not in counters_targets:
                issues.append(ArgIssue(
                    node_id=nid,
                    severity="warning",
                    category="unaddressed_rebuttal",
                    message=f"反驳「{short}」没有被回应",
                    suggestion="添加回应（counters 关系）来说明为何此反驳不影响主张",
                ))

        elif n.node_type == "qualifier":
            if nid not in qualifier_sources:
                issues.append(ArgIssue(
                    node_id=nid,
                    severity="info",
                    category="unsupported_qualifier",
                    message=f"限定词「{short}」未连接到任何主张",
                    suggestion="将限定词连接到对应的主张节点（qualifies 关系）",
                ))

        # Orphan: no edges at all (only meaningful in a multi-node graph)
        if multi_node and nid not in connected:
            issues.append(ArgIssue(
                node_id=nid,
                severity="warning",
                category="orphan",
                message=f"节点「{short}」孤立（无任何关系边）",
                suggestion="将此节点与其他节点连接",
            ))

    return issues


async def llm_critique(
    graph: ArgGraph,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ArgIssue]:
    """LLM 谬误/弱链检测，失败时静默返回空列表。"""
    from .llm_client import call_llm_chat

    if not graph.nodes:
        return []

    nodes_text = "\n".join(
        f"[{n.node_type.upper()}] ({n.id}) {n.text}" for n in graph.nodes
    )
    edges_text = "\n".join(
        f"{e.source_id} --{e.relation_type}--> {e.target_id}" for e in graph.edges
    ) or "(无关系边)"

    prompt = (
        "请分析以下 Toulmin 论证图，找出逻辑谬误、弱链接和问题。\n\n"
        f"节点：\n{nodes_text}\n\n"
        f"关系：\n{edges_text}\n\n"
        "请输出 JSON 数组（若无问题则输出 []），每项格式：\n"
        '{"node_id": "<id 或 null>", "severity": "info|warning|error", '
        '"category": "fallacy|weak_link|other", '
        '"message": "<问题描述>", "suggestion": "<改进建议>"}\n\n'
        "只输出 JSON 数组，不要其他文字。"
    )

    try:
        raw = await call_llm_chat(
            prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.3
        )
        if not raw.strip():
            return []
        items = extract_json_array(raw)
        if items is None:
            return []
        node_ids = {n.id for n in graph.nodes}
        result: list[ArgIssue] = []
        for item in items:
            nid = item.get("node_id")
            if nid and nid not in node_ids:
                nid = None
            result.append(ArgIssue(
                node_id=nid,
                severity=item.get("severity", "info"),
                category=item.get("category", "other"),
                message=str(item.get("message", "")),
                suggestion=item.get("suggestion"),
            ))
        return result
    except Exception as exc:
        logger.debug("LLM critique failed: %s", exc)
        return []


async def critique_graph(
    graph: ArgGraph,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ArgIssue]:
    """结构性检查 + LLM 谬误检测，合并去重结果。"""
    structural = structural_critique(graph)
    llm_issues = await llm_critique(graph, cloud_client, ollama_client)
    return structural + llm_issues
