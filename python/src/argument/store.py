"""Argument Mapping — 节点树 CRUD + JSON 持久化"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.argument.models import (
    ArgumentNode,
    ArgumentTree,
    LogicStatus,
    NodeStatus,
    _gen_id,
    _now_iso,
)

logger = logging.getLogger(__name__)


class ArgumentStore:
    """内存 + JSON 文件持久化的思维导图节点树存储。

    单树设计：当前仅支持一棵活跃的思维导图。
    持久化路径: {persist_dir}/argument_tree.json
    """

    def __init__(self, persist_dir: str | Path = "data") -> None:
        self._persist_path = Path(persist_dir) / "argument_tree.json"
        self._tree = ArgumentTree()
        self._load()

    @property
    def tree(self) -> ArgumentTree:
        return self._tree

    def _load(self) -> None:
        if self._persist_path.exists():
            try:
                raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
                # 反序列化 nodes 字典
                nodes = {}
                for nid, ndata in raw.get("nodes", {}).items():
                    nodes[nid] = ArgumentNode(**ndata)
                self._tree = ArgumentTree(
                    root_id=raw.get("root_id"),
                    nodes=nodes,
                    created_at=raw.get("created_at", _now_iso()),
                    updated_at=raw.get("updated_at", _now_iso()),
                )
                logger.info("已加载 Argument Tree: %d nodes", len(nodes))
            except Exception as e:
                logger.warning("加载 Argument Tree 失败，使用空树: %s", e)
                self._tree = ArgumentTree()

    def _save(self) -> None:
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "root_id": self._tree.root_id,
            "nodes": {nid: node.model_dump() for nid, node in self._tree.nodes.items()},
            "created_at": self._tree.created_at,
            "updated_at": self._tree.updated_at,
        }
        tmp = self._persist_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(self._persist_path))

    def _touch(self) -> None:
        self._tree.updated_at = _now_iso()
        self._save()

    # ── Tree ──────────────────────────────────────────────────────

    def get_tree(self) -> ArgumentTree:
        return self._tree

    def create_tree(self, topic: str, domain_tags: list[str] | None = None,
                    position: dict[str, float] | None = None) -> ArgumentNode:
        root = ArgumentNode(
            id="node_root",
            topic=topic,
            depth=0,
            domain_tags=domain_tags or [],
            position=position or {"x": 400.0, "y": 50.0},
            logic_status=LogicStatus.warning,
            rule_issues=["MISSING_CLASSIC_CHAIN"],
            status=NodeStatus.draft,
        )
        self._tree = ArgumentTree(
            root_id=root.id,
            nodes={root.id: root},
        )
        self._touch()
        return root

    # ── Node CRUD ─────────────────────────────────────────────────

    def get_node(self, node_id: str) -> ArgumentNode | None:
        return self._tree.nodes.get(node_id)

    def upsert_node(self, **kwargs: Any) -> ArgumentNode:
        """创建或更新节点。有 id 且存在则更新，否则创建。"""
        node_id = kwargs.get("id")

        if node_id and node_id in self._tree.nodes:
            # 更新
            node = self._tree.nodes[node_id]
            for key, val in kwargs.items():
                if val is not None and key != "id" and hasattr(node, key):
                    setattr(node, key, val)
            node.updated_at = _now_iso()
            self._touch()
            return node

        # 创建新节点
        parent_id = kwargs.get("parent_id")
        depth = 0
        if parent_id and parent_id in self._tree.nodes:
            depth = self._tree.nodes[parent_id].depth + 1

        new_node = ArgumentNode(
            id=node_id or _gen_id("node"),
            parent_id=parent_id,
            topic=kwargs.get("topic", ""),
            content=kwargs.get("content", ""),
            depth=depth,
            position=kwargs.get("position", {"x": 0.0, "y": 0.0}),
            domain_tags=kwargs.get("domain_tags", []),
            status=NodeStatus.draft,
            logic_status=LogicStatus.warning,
            rule_issues=[],
        )

        self._tree.nodes[new_node.id] = new_node

        # 更新父节点的 children
        if parent_id and parent_id in self._tree.nodes:
            parent = self._tree.nodes[parent_id]
            if new_node.id not in parent.children:
                parent.children.append(new_node.id)

        self._touch()
        return new_node

    def delete_node(self, node_id: str, cascade: bool = False) -> list[str]:
        """删除节点，返回被删除的节点 ID 列表。"""
        node = self._tree.nodes.get(node_id)
        if not node:
            return []

        deleted: list[str] = []

        if cascade:
            # 递归收集所有子孙节点
            stack = [node_id]
            while stack:
                nid = stack.pop()
                nd = self._tree.nodes.get(nid)
                if nd:
                    deleted.append(nid)
                    stack.extend(nd.children)
        else:
            deleted.append(node_id)
            # 非 cascade 模式：将被删节点的子节点重新挂到其父节点
            if node.parent_id and node.parent_id in self._tree.nodes:
                parent = self._tree.nodes[node.parent_id]
                for child_id in node.children:
                    child = self._tree.nodes.get(child_id)
                    if child:
                        child.parent_id = node.parent_id
                        parent.children.append(child_id)

        # 从父节点的 children 中移除被删节点
        if node.parent_id and node.parent_id in self._tree.nodes:
            parent = self._tree.nodes[node.parent_id]
            parent.children = [c for c in parent.children if c not in deleted]

        # 从树中移除
        for nid in deleted:
            self._tree.nodes.pop(nid, None)

        self._touch()
        return deleted

    # ── Reference binding ─────────────────────────────────────────

    def bind_reference(self, node_id: str, doc_id: str, citation_key: str,
                       binding_type: str, relevance_score: float) -> ArgumentNode | None:
        from src.argument.models import BindingType, Reference

        node = self._tree.nodes.get(node_id)
        if not node:
            return None

        ref = Reference(
            doc_id=doc_id,
            citation_key=citation_key,
            relevance_score=relevance_score,
            binding_type=BindingType(binding_type),
        )
        # 避免重复绑定
        if not any(r.doc_id == doc_id for r in node.references):
            node.references.append(ref)
            node.updated_at = _now_iso()
            self._touch()
        return node

    def unbind_reference(self, node_id: str, doc_id: str) -> bool:
        node = self._tree.nodes.get(node_id)
        if not node:
            return False
        before = len(node.references)
        node.references = [r for r in node.references if r.doc_id != doc_id]
        if len(node.references) < before:
            node.updated_at = _now_iso()
            self._touch()
            return True
        return False

    def get_subtree_ids(self, node_id: str) -> list[str]:
        """返回以 node_id 为根的子树中所有节点 ID（包含自身）。"""
        if node_id == "root":
            node_id = self._tree.root_id or ""
        result: list[str] = []
        stack = [node_id]
        while stack:
            nid = stack.pop()
            if nid in self._tree.nodes:
                result.append(nid)
                stack.extend(self._tree.nodes[nid].children)
        return result

    def update_node_fields(self, node_id: str, **fields: Any) -> ArgumentNode | None:
        node = self._tree.nodes.get(node_id)
        if not node:
            return None
        # Convert string values to enum types where needed
        if "logic_status" in fields and isinstance(fields["logic_status"], str):
            fields["logic_status"] = LogicStatus(fields["logic_status"])
        if "status" in fields and isinstance(fields["status"], str):
            fields["status"] = NodeStatus(fields["status"])
        for key, val in fields.items():
            if hasattr(node, key):
                setattr(node, key, val)
        node.updated_at = _now_iso()
        self._touch()
        return node
