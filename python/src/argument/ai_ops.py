"""AI 辅助操作：提取论证图（SSE）、建议元素、批判审查。"""

import difflib
import json
import logging
import re

from src.utils.json_extract import extract_json_object
from typing import Any, AsyncIterator

from .graph_store import ArgGraphStore
from .llm_client import call_llm_chat
from .models_v2 import ALLOWED_EDGES, ArgEdge, ArgNode, SpanMapping

logger = logging.getLogger(__name__)


# ── Span quote locator ────────────────────────────────────────────────────────

def _locate_quote(text: str, quote: str) -> tuple[int | None, int | None]:
    """Locate quote in text. Returns (char_start, char_end) or (None, None)."""
    if not quote:
        return None, None

    # Exact match
    idx = text.find(quote)
    if idx >= 0:
        return idx, idx + len(quote)

    # Prefix match (first 20 chars)
    short = quote[:20]
    if len(short) >= 5:
        idx = text.find(short)
        if idx >= 0:
            return idx, min(idx + len(quote), len(text))

    # difflib fuzzy match
    q_len = max(len(quote), 1)
    best_ratio = 0.0
    best_start: int | None = None
    best_end: int | None = None
    step = max(1, q_len // 3)
    for i in range(0, max(1, len(text) - q_len + 1), step):
        window = text[i : i + q_len]
        ratio = difflib.SequenceMatcher(None, quote, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            best_end = i + q_len

    if best_ratio >= 0.6 and best_start is not None:
        return best_start, best_end
    return None, None


# ── extract_argument ──────────────────────────────────────────────────────────

async def extract_argument(
    gid: str,
    text: str,
    source_label: str | None,
    side: str,
    store: ArgGraphStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """从文本提取 Toulmin 论证图，流式产出 SSE 事件。

    事件序列: node* → span* → edge* → complete  (或 error)
    """
    prompt = (
        "你是学术论证分析专家。从以下文本提取 Toulmin 论证结构。\n\n"
        f"文本：\n{text[:4000]}\n\n"
        "请输出严格 JSON（不要任何其他文字）：\n"
        '{"nodes": [{"local_id": "c1", "type": "claim|grounds|warrant|backing|qualifier|rebuttal", '
        '"text": "节点内容（一句话）", "verbatim_quote": "原文精确子串（用于定位）"}], '
        '"edges": [{"source": "<local_id>", "target": "<local_id>", '
        '"relation": "supports|warrants|backs|qualifies|rebuts|counters"}]}\n\n'
        "要求：verbatim_quote 必须是输入文本的精确子串；每个 claim 至少尝试找 grounds；"
        "识别文中让步/例外作 rebuttal。"
    )

    raw = ""
    try:
        raw = await call_llm_chat(
            prompt, cloud_client, ollama_client, max_tokens=16384, temperature=0.3
        )
    except Exception as exc:
        yield {"event": "error", "data": json.dumps({"message": f"LLM 调用失败: {exc}"})}
        return

    # Parse — retry once with a stricter prompt on failure
    parsed: dict | None = None
    for attempt in range(2):
        parsed = extract_json_object(raw)
        if parsed is not None:
            break
        if attempt == 0:
            try:
                raw = await call_llm_chat(
                    f"请只输出有效的 JSON 对象，不要任何解释文字：\n{raw[:500]}",
                    cloud_client,
                    ollama_client,
                    max_tokens=16384,
                    temperature=0.1,
                )
            except Exception as e:
                logger.warning("LLM retry for Toulmin extraction failed: %s", e)
                break

    if not parsed:
        yield {"event": "error", "data": json.dumps({"message": "LLM 未返回有效 JSON，请重试"})}
        return

    # ── Build nodes ──────────────────────────────────────────────────────────

    local_to_id: dict[str, str] = {}
    new_nodes: list[ArgNode] = []
    new_edges: list[ArgEdge] = []
    new_spans: list[SpanMapping] = []
    warnings: list[str] = []

    valid_types = {"claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"}

    for n_data in parsed.get("nodes", []):
        local_id = str(n_data.get("local_id", ""))
        node_type = str(n_data.get("type", ""))
        node_text = str(n_data.get("text", "")).strip()
        verbatim = str(n_data.get("verbatim_quote", "")).strip()

        if node_type not in valid_types or not node_text:
            warnings.append(f"跳过无效节点 type={node_type!r}")
            continue

        node = ArgNode(node_type=node_type, text=node_text, created_by="ai")  # type: ignore[arg-type]
        new_nodes.append(node)
        if local_id:
            local_to_id[local_id] = node.id

        yield {"event": "node", "data": node.model_dump_json()}

        # Create span for verbatim_quote
        if verbatim:
            char_start, char_end = _locate_quote(text, verbatim)
            span = SpanMapping(
                node_id=node.id,
                source_type="extracted",
                side=side,  # type: ignore[arg-type]
                char_start=char_start,
                char_end=char_end,
                quote=verbatim,
                source_label=source_label,
            )
            new_spans.append(span)
            yield {"event": "span", "data": span.model_dump_json()}

    # ── Build edges ──────────────────────────────────────────────────────────

    node_map = {n.id: n for n in new_nodes}

    for e_data in parsed.get("edges", []):
        src_local = str(e_data.get("source", ""))
        tgt_local = str(e_data.get("target", ""))
        relation = str(e_data.get("relation", ""))

        src_id = local_to_id.get(src_local)
        tgt_id = local_to_id.get(tgt_local)

        if not src_id or not tgt_id:
            warnings.append(f"边 {src_local!r}→{tgt_local!r} 引用的节点未找到，已跳过")
            continue

        src_node = node_map.get(src_id)
        tgt_node = node_map.get(tgt_id)
        if not src_node or not tgt_node:
            continue

        allowed = ALLOWED_EDGES.get(relation, set())
        if (src_node.node_type, tgt_node.node_type) not in allowed:
            warnings.append(
                f"关系 {relation!r}: {src_node.node_type}→{tgt_node.node_type} 非法，已跳过"
            )
            continue

        edge = ArgEdge(
            source_id=src_id,
            target_id=tgt_id,
            relation_type=relation,  # type: ignore[arg-type]
            created_by="ai",
        )
        new_edges.append(edge)
        yield {"event": "edge", "data": edge.model_dump_json()}

    # ── Write atomically ─────────────────────────────────────────────────────

    store.replace_graph(gid, nodes=new_nodes, edges=new_edges, spans=new_spans)

    yield {
        "event": "complete",
        "data": json.dumps({
            "node_count": len(new_nodes),
            "edge_count": len(new_edges),
            "span_count": len(new_spans),
            "warnings": warnings,
        }),
    }


# ── suggest_element ───────────────────────────────────────────────────────────

async def suggest_element(
    graph_id: str,
    node_id: str,
    store: ArgGraphStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> dict:
    """为指定节点建议下一个 Toulmin 元素。不写入 store。"""
    graph = store.get(graph_id)
    if graph is None:
        return {"candidates": [], "suggested_edges": []}

    node = next((n for n in graph.nodes if n.id == node_id), None)
    if node is None:
        return {"candidates": [], "suggested_edges": []}

    prompt = (
        f"你是论证分析专家。对于以下 Toulmin 论证中的{node.node_type}节点：\n\n"
        f"节点内容：{node.text}\n\n"
        "请建议 2-3 个合适的下一级支撑元素，输出严格 JSON：\n"
        '{"candidates": [{"local_id": "g1", "type": "grounds|warrant|backing|qualifier|rebuttal", '
        '"text": "候选内容"}], '
        f'"suggested_edges": [{{"source": "<local_id>", "target": "{node_id}", '
        '"relation": "supports|warrants|backs|qualifies|rebuts|counters"}}]}\n\n'
        "只输出 JSON，不要其他文字。"
    )

    try:
        raw = await call_llm_chat(
            prompt, cloud_client, ollama_client, max_tokens=512, temperature=0.7
        )
        data = extract_json_object(raw)
        if not data:
            return {"candidates": [], "suggested_edges": []}
        candidates = [
            {
                "local_id": c.get("local_id", ""),
                "node_type": c.get("type", "grounds"),
                "text": str(c.get("text", "")),
                "created_by": "ai",
            }
            for c in data.get("candidates", [])
        ]
        return {
            "candidates": candidates,
            "suggested_edges": data.get("suggested_edges", []),
        }
    except Exception as exc:
        logger.debug("suggest_element failed: %s", exc)
        return {"candidates": [], "suggested_edges": []}
