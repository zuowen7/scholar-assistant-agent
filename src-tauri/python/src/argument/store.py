"""JSON-backed Argument Map store."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_node_id() -> str:
    return f"node_{uuid.uuid4().hex[:4]}"


class ArgumentStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, tree: dict[str, Any]) -> dict[str, Any]:
        tree["updated_at"] = utc_now()
        self.path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        return tree

    def create_tree(self, topic: str, domain_tags: list[str] | None = None, position: dict[str, float] | None = None) -> dict[str, Any]:
        now = utc_now()
        root = self._make_node(
            node_id="node_root",
            parent_id=None,
            topic=topic.strip() or "Untitled Argument",
            content="",
            depth=0,
            position=position or {"x": 400, "y": 50},
            domain_tags=domain_tags or [],
            now=now,
        )
        root["logic_status"] = "warning"
        root["rule_issues"] = ["MISSING_CLASSIC_CHAIN"]
        tree = {"root_id": "node_root", "nodes": {"node_root": root}, "created_at": now, "updated_at": now}
        return self.save(tree)

    def upsert_node(
        self,
        tree: dict[str, Any],
        topic: str,
        parent_id: str | None = None,
        content: str = "",
        domain_tags: list[str] | None = None,
        position: dict[str, float] | None = None,
        node_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        nodes = tree["nodes"]
        now = utc_now()
        if node_id and node_id in nodes:
            node = nodes[node_id]
            node.update({
                "topic": topic.strip() or node.get("topic", "Untitled"),
                "content": content,
                "domain_tags": domain_tags or [],
                "position": position or node.get("position", {"x": 400, "y": 200}),
                "updated_at": now,
            })
            self.save(tree)
            return node, False

        if parent_id and parent_id not in nodes:
            raise ValueError("Invalid parent_id")
        parent = nodes.get(parent_id) if parent_id else None
        nid = node_id or new_node_id()
        depth = (parent.get("depth", 0) + 1) if parent else 0
        node = self._make_node(nid, parent_id, topic, content, depth, position, domain_tags or [], now)
        nodes[nid] = node
        if parent:
            parent.setdefault("children", [])
            if nid not in parent["children"]:
                parent["children"].append(nid)
            parent["updated_at"] = now
        self.save(tree)
        return node, True

    def delete_node(self, tree: dict[str, Any], node_id: str, cascade: bool = False) -> list[str]:
        nodes = tree["nodes"]
        if node_id not in nodes:
            raise KeyError(node_id)
        if node_id == tree.get("root_id"):
            raise ValueError("Cannot delete root node")
        children = list(nodes[node_id].get("children", []))
        if children and not cascade:
            raise ValueError("Node has children; use cascade=true")
        deleted: list[str] = []

        def remove(nid: str) -> None:
            for child in list(nodes.get(nid, {}).get("children", [])):
                remove(child)
            parent_id = nodes.get(nid, {}).get("parent_id")
            if parent_id in nodes:
                nodes[parent_id]["children"] = [cid for cid in nodes[parent_id].get("children", []) if cid != nid]
            if nid in nodes:
                del nodes[nid]
                deleted.append(nid)

        remove(node_id)
        self.save(tree)
        return deleted

    def bind_reference(self, tree: dict[str, Any], node_id: str, ref: dict[str, Any]) -> dict[str, Any]:
        node = tree["nodes"][node_id]
        refs = [r for r in node.get("references", []) if r.get("doc_id") != ref["doc_id"]]
        refs.append(ref)
        node["references"] = refs
        node["updated_at"] = utc_now()
        self.save(tree)
        return ref

    def unbind_reference(self, tree: dict[str, Any], node_id: str, doc_id: str) -> None:
        node = tree["nodes"][node_id]
        node["references"] = [r for r in node.get("references", []) if r.get("doc_id") != doc_id]
        node["updated_at"] = utc_now()
        self.save(tree)

    @staticmethod
    def _make_node(
        node_id: str,
        parent_id: str | None,
        topic: str,
        content: str,
        depth: int,
        position: dict[str, float] | None,
        domain_tags: list[str],
        now: str,
    ) -> dict[str, Any]:
        return {
            "id": node_id,
            "parent_id": parent_id,
            "topic": topic.strip() or "Untitled",
            "content": content,
            "depth": depth,
            "position": position or {"x": 400, "y": 200 + depth * 120},
            "domain_tags": domain_tags,
            "references": [],
            "logic_status": "draft",
            "rule_issues": [],
            "agent_feedback": None,
            "status": "draft",
            "children": [],
            "created_at": now,
            "updated_at": now,
        }
