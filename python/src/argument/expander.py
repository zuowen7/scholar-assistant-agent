"""Argument Mapping — AI Expand（LLM 生成子节点）

复用 cloud_client / ollama_client 的 chat 能力，
通过 prompt 引导模型输出 JSON 格式的子节点列表。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.argument.models import NodeStatus, _now_iso
from src.argument.store import ArgumentStore

logger = logging.getLogger(__name__)

_EXPAND_PROMPT = """你是一位学术论文结构化助手。请为以下学术主题生成 {max_children} 个子课题/子方向作为思维导图的子节点。

父节点主题: {topic}
父节点内容: {content}
领域标签: {domain_tags}
方向: {direction}

要求:
1. 每个子节点必须有一个简短的 topic（中文名称）
2. 每个子节点附带 1-3 个 domain_tags
3. 严格输出 JSON 数组格式，不要输出任何其他内容
4. 格式: [{{"topic": "...", "domain_tags": ["...", "..."]}}]"""

_REFINE_PROMPT = """你是一位学术论文结构化助手。请深化以下节点的内容，生成 2-3 个更具体的子方向。

节点主题: {topic}
节点内容: {content}
领域标签: {domain_tags}

要求:
1. 每个子节点必须有一个简短的 topic
2. 每个子节点附带 1-3 个 domain_tags
3. 严格输出 JSON 数组格式，不要输出任何其他内容
4. 格式: [{{"topic": "...", "domain_tags": ["...", "..."]}}]"""


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 输出中提取 JSON 数组。"""
    # 尝试直接解析
    text = text.strip()
    if text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 提取 ```json ... ``` 块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 暴力提取第一个 [...] 块
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return []


class ArgumentExpander:
    """AI Expand — 调用 LLM 为节点生成子节点。"""

    def __init__(self, store: ArgumentStore) -> None:
        self._store = store

    async def expand(
        self,
        node_id: str,
        max_children: int = 4,
        direction: str = "expand",
        cloud_client: Any = None,
        ollama_client: Any = None,
    ) -> dict[str, Any]:
        """Expand a node by calling LLM to generate child topics.

        Args:
            node_id: 要展开的节点 ID。
            max_children: 最大子节点数。
            direction: "expand"（向下展开）或 "refine"（深化当前节点）。
            cloud_client: CloudClient 实例（优先使用）。
            ollama_client: OllamaClient 实例（fallback）。

        Returns:
            dict with parent_id, children list, and expanded_node info.
        """
        node = self._store.get_node(node_id)
        if not node:
            return {"error": "Node not found", "children": []}

        # Build prompt
        if direction == "refine":
            prompt = _REFINE_PROMPT.format(
                topic=node.topic,
                content=node.content or "(无详细内容)",
                domain_tags=", ".join(node.domain_tags) or "未指定",
            )
        else:
            prompt = _EXPAND_PROMPT.format(
                max_children=max_children,
                topic=node.topic,
                content=node.content or "(无详细内容)",
                domain_tags=", ".join(node.domain_tags) or "未指定",
                direction=direction,
            )

        # Call LLM
        raw_text = await self._call_llm(prompt, cloud_client, ollama_client)

        if raw_text:
            items = _extract_json_array(raw_text)
            if not items:
                logger.warning("LLM 输出无法解析为 JSON 数组: %s", raw_text[:200])
        else:
            # Fallback tier 3: template-based generation (no LLM)
            items = self._template_expand(node.topic, node.domain_tags, max_children)

        if not items:
            return {"parent_id": node_id, "children": [], "expanded_node": None}

        # Create child nodes
        created: list[dict] = []
        base_y = node.position.get("y", 0) + 200
        spacing = 250

        for i, item in enumerate(items[:max_children]):
            if not isinstance(item, dict):
                continue
            topic = item.get("topic", f"子方向 {i + 1}")
            tags = item.get("domain_tags", [])

            child = self._store.upsert_node(
                parent_id=node_id,
                topic=topic,
                domain_tags=tags,
                position={
                    "x": node.position.get("x", 0) + (i - len(items) / 2) * spacing,
                    "y": base_y,
                },
            )
            created.append({
                "id": child.id,
                "topic": child.topic,
                "domain_tags": child.domain_tags,
                "depth": child.depth,
                "position": child.position,
            })

        # Update parent status
        self._store.update_node_fields(node_id, status=NodeStatus.expanded)

        return {
            "parent_id": node_id,
            "children": created,
            "expanded_node": {
                "id": node_id,
                "status": "expanded",
                "updated_at": self._store.get_node(node_id).updated_at if self._store.get_node(node_id) else _now_iso(),
            },
        }

    async def _call_llm(self, prompt: str, cloud_client: Any = None, ollama_client: Any = None) -> str:
        from src.argument.llm_client import call_llm_chat
        return await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=2048, temperature=0.7)

    def _template_expand(self, topic: str, domain_tags: list[str], max_children: int) -> list[dict]:
        """第三层降级：基于主题和领域标签的模板生成（不调用 LLM）。"""
        _DOMAIN_TEMPLATES: dict[str, list[str]] = {
            "control_theory": ["系统建模与分析", "控制器设计", "稳定性证明", "仿真验证", "对比实验"],
            "machine_learning": ["数据集与预处理", "模型架构", "训练策略", "评估指标", "基线对比"],
            "nlp": ["数据集构建", "模型设计", "训练细节", "评估方法", "案例分析"],
        }

        candidates: list[str] = []
        for tag in domain_tags:
            if tag in _DOMAIN_TEMPLATES:
                candidates.extend(_DOMAIN_TEMPLATES[tag])

        if not candidates:
            candidates = [f"{topic} — 子方向 {i + 1}" for i in range(max_children)]

        items = []
        for c in candidates[:max_children]:
            items.append({"topic": c, "domain_tags": domain_tags[:2]})
        return items
