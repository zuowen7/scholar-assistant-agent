"""ArgGraphStore — 多图 JSON 持久化存储。"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from src.argument.models_v2 import (
    ALLOWED_EDGES,
    ArgEdge,
    ArgGraph,
    ArgIssue,
    ArgNode,
    SpanMapping,
)

logger = logging.getLogger(__name__)


class ArgGraphStore:
    """多图存储：内存 dict + 每图独立 JSON 文件。

    持久化路径: {runtime_dir}/argument_graphs/{gid}.json
    """

    def __init__(self, runtime_dir: str | Path = "data") -> None:
        self._graphs_dir = Path(runtime_dir) / "argument_graphs"
        self._graphs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, ArgGraph] = {}
        self._lock = threading.RLock()
        self._load_all()

    # ── 内部 IO ───────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for json_file in self._graphs_dir.glob("*.json"):
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                g = ArgGraph.model_validate(raw)
                self._cache[g.id] = g
            except Exception as e:
                logger.warning("跳过损坏的图文件 %s: %s", json_file.name, e)

    def _flush(self, gid: str) -> None:
        g = self._cache.get(gid)
        if g is None:
            return
        g.updated_at = time.time()
        path = self._graphs_dir / f"{gid}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(g.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(path))

    # ── 图 CRUD ───────────────────────────────────────────────────────────────

    def create(self, title: str = "Untitled Argument Map", source_doc: str | None = None) -> ArgGraph:
        with self._lock:
            g = ArgGraph(title=title, source_doc=source_doc)
            self._cache[g.id] = g
            self._flush(g.id)
            return g

    def get(self, gid: str) -> ArgGraph | None:
        return self._cache.get(gid)

    def get_by_source_doc(self, source_doc: str) -> ArgGraph | None:
        """按 source_doc（文件路径）查找论证图，返回最近更新的一个。

        先尝试字符串精确匹配，再尝试路径 resolve 后比较（吸收 / vs \\、
        相对/绝对路径差异）。多个匹配时取 updated_at 最大者。
        """
        if not source_doc:
            return None
        target = None
        try:
            target = Path(source_doc).resolve()
        except Exception as e:
            logger.debug("path resolve failed for graph lookup: %s", e)
            target = None
        matches: list[ArgGraph] = []
        for g in self._cache.values():
            if not g.source_doc:
                continue
            if g.source_doc == source_doc:
                matches.append(g)
                continue
            if target is not None:
                try:
                    if Path(g.source_doc).resolve() == target:
                        matches.append(g)
                except Exception as e:
                    logger.debug("graph source_doc path comparison failed: %s", e)
        if not matches:
            return None
        return max(matches, key=lambda g: g.updated_at)

    def list_graphs(self) -> list[dict]:
        return [
            {
                "id": g.id,
                "title": g.title,
                "node_count": len(g.nodes),
                "updated_at": g.updated_at,
                "source_doc": g.source_doc,
            }
            for g in self._cache.values()
        ]

    def delete(self, gid: str) -> None:
        with self._lock:
            self._cache.pop(gid, None)
            path = self._graphs_dir / f"{gid}.json"
            if path.exists():
                path.unlink()

    # ── 节点 CRUD ─────────────────────────────────────────────────────────────

    def upsert_node(self, gid: str, node: ArgNode) -> ArgNode:
        with self._lock:
            g = self._cache[gid]
            existing = next((n for n in g.nodes if n.id == node.id), None)
            if existing is None:
                g.nodes.append(node)
            else:
                idx = g.nodes.index(existing)
                g.nodes[idx] = node
            self._flush(gid)
            return node

    def delete_node(self, gid: str, nid: str) -> None:
        with self._lock:
            g = self._cache[gid]
            node = next((n for n in g.nodes if n.id == nid), None)
            if node is None:
                raise KeyError(nid)
            g.nodes = [n for n in g.nodes if n.id != nid]
            # cascade: remove incident edges
            g.edges = [e for e in g.edges if e.source_id != nid and e.target_id != nid]
            # cascade: remove spans and issues linked to this node
            g.spans = [s for s in g.spans if s.node_id != nid]
            g.issues = [i for i in g.issues if i.node_id != nid]
            self._flush(gid)

    # ── 边 CRUD + 校验 ────────────────────────────────────────────────────────

    def _node_type(self, g: ArgGraph, nid: str) -> str | None:
        n = next((x for x in g.nodes if x.id == nid), None)
        return n.node_type if n else None

    def upsert_edge(self, gid: str, edge: ArgEdge) -> ArgEdge:
        with self._lock:
            g = self._cache[gid]

            if edge.source_id == edge.target_id:
                raise ValueError("self_loop: source and target must differ")

            src_type = self._node_type(g, edge.source_id)
            tgt_type = self._node_type(g, edge.target_id)
            allowed = ALLOWED_EDGES.get(edge.relation_type, set())
            if (src_type, tgt_type) not in allowed:
                raise ValueError(
                    f"invalid_edge: ({src_type}, {tgt_type}) not allowed for '{edge.relation_type}'"
                )

            # duplicate check (same source/target/type, different id)
            dup = next(
                (
                    e for e in g.edges
                    if e.source_id == edge.source_id
                    and e.target_id == edge.target_id
                    and e.relation_type == edge.relation_type
                    and e.id != edge.id
                ),
                None,
            )
            if dup:
                raise ValueError("duplicate: edge with same source/target/relation already exists")

            existing = next((e for e in g.edges if e.id == edge.id), None)
            if existing is None:
                g.edges.append(edge)
            else:
                idx = g.edges.index(existing)
                g.edges[idx] = edge
            self._flush(gid)
            return edge

    def delete_edge(self, gid: str, eid: str) -> None:
        with self._lock:
            g = self._cache[gid]
            g.edges = [e for e in g.edges if e.id != eid]
            self._flush(gid)

    # ── Span CRUD ─────────────────────────────────────────────────────────────

    def add_span(self, gid: str, span: SpanMapping) -> SpanMapping:
        with self._lock:
            g = self._cache[gid]
            g.spans.append(span)
            self._flush(gid)
            return span

    def delete_span(self, gid: str, sid: str) -> None:
        with self._lock:
            g = self._cache[gid]
            g.spans = [s for s in g.spans if s.id != sid]
            self._flush(gid)

    # ── 批量写入（AI 提取用） ─────────────────────────────────────────────────

    def replace_graph(
        self,
        gid: str,
        nodes: list[ArgNode],
        edges: list[ArgEdge],
        spans: list[SpanMapping],
    ) -> ArgGraph:
        with self._lock:
            g = self._cache[gid]
            g.nodes = nodes
            g.edges = edges
            g.spans = spans
            self._flush(gid)
            return g

    # ── 问题（critique 用） ───────────────────────────────────────────────────

    def set_issues(self, gid: str, issues: list[ArgIssue]) -> None:
        with self._lock:
            g = self._cache[gid]
            # Clear existing issue_ids from all nodes
            for node in g.nodes:
                node.issue_ids = []
            g.issues = issues
            # Re-link issue_ids to nodes
            for issue in issues:
                if issue.node_id:
                    node = next((n for n in g.nodes if n.id == issue.node_id), None)
                    if node and issue.id not in node.issue_ids:
                        node.issue_ids.append(issue.id)
            self._flush(gid)
