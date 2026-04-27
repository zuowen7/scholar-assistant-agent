"""Mind map persistence + AI analysis/expansion endpoints."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MindMapAnalyzeRequest(BaseModel):
    root_id: str
    nodes: dict[str, Any]
    links: list[dict[str, Any]] = []


class MindMapExpandRequest(BaseModel):
    node_text: str
    context: str = ""
    max_children: int = 4


def register_mindmap(
    app: FastAPI,
    *,
    runtime_dir: Path,
    load_config=None,
    build_cloud_client=None,
) -> None:
    mindmap_path = runtime_dir / "mindmap.json"

    def _get_cloud_client():
        if not load_config or not build_cloud_client:
            return None
        config = load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        if not cloud_cfg.get("api_key"):
            return None
        return build_cloud_client(trans_cfg, cloud_cfg)

    async def _llm_call(system_prompt: str, user_prompt: str) -> str | None:
        import asyncio
        client = _get_cloud_client()
        if not client:
            return None
        try:
            original_sp = client.system_prompt
            client.system_prompt = system_prompt
            client._chunk_index = 0
            client._prev_translation = ""
            result = await asyncio.to_thread(client.translate, user_prompt)
            client.system_prompt = original_sp
            return result.translated if result else None
        except Exception as exc:
            logger.warning("Mind map LLM call failed: %s", exc)
            return None

    # ── Persistence ────────────────────────────────────────────────

    @app.post("/api/mindmap/save")
    async def save_mindmap(data: dict) -> dict:
        mindmap_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mindmap_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"ok": True}

    @app.get("/api/mindmap/load")
    async def load_mindmap() -> JSONResponse:
        if not mindmap_path.exists():
            raise HTTPException(status_code=404, detail="没有已保存的思维导图")
        try:
            with open(mindmap_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("读取思维导图失败: %s", exc)
            raise HTTPException(status_code=500, detail=f"读取思维导图失败: {exc}")
        return JSONResponse(data)

    @app.delete("/api/mindmap")
    async def clear_mindmap() -> dict:
        if mindmap_path.exists():
            mindmap_path.unlink()
        return {"ok": True}

    # ── AI Analysis ────────────────────────────────────────────────

    @app.post("/api/mindmap/analyze")
    async def analyze_mindmap(req: MindMapAnalyzeRequest) -> dict:
        nodes = req.nodes
        root_id = req.root_id
        links = req.links

        # Build text outline for LLM context
        outline_lines: list[str] = []
        visited: set[str] = set()

        def walk(nid: str, depth: int) -> None:
            if nid in visited:
                return
            visited.add(nid)
            node = nodes.get(nid)
            if not node:
                return
            indent = "  " * depth
            text = node.get("text", "")
            children = node.get("children", [])
            outline_lines.append(f"{indent}- {text} (children: {len(children)})")
            for cid in children:
                walk(cid, depth + 1)

        walk(root_id, 0)
        # Catch orphaned nodes
        for nid, node in nodes.items():
            if nid not in visited:
                outline_lines.append(f"- [ORPHAN] {node.get('text', '')}")

        if links:
            outline_lines.append("\nAssociation links:")
            for link in links:
                from_text = nodes.get(link.get("from", ""), {}).get("text", "?")
                to_text = nodes.get(link.get("to", ""), {}).get("text", "?")
                outline_lines.append(f"  {from_text} <-> {to_text}")

        outline = "\n".join(outline_lines)

        system_prompt = (
            "你是一位学术论文逻辑审查助手。用户会给你一个思维导图的大纲结构，"
            "你需要分析其中的逻辑缺陷和改进建议。\n\n"
            "请返回 JSON 数组，每个元素包含：\n"
            '- "severity": "info" | "warning" | "critical"\n'
            '- "type": "isolated" | "duplicate" | "logic_gap" | "shallow_branch" | "weak_link" | "missing_support"\n'
            '- "title": 简短标题\n'
            '- "message": 具体说明和建议\n'
            '- "node_texts": 涉及的节点文字数组（用于前端定位节点）\n\n'
            "关注：逻辑跳跃、论据不足、分支过浅、重复概念、孤立节点、关联线解释不足。"
            "最多返回 8 条。只返回 JSON 数组，不要其他文字。"
        )

        llm_raw = await _llm_call(system_prompt, outline)

        issues: list[dict[str, Any]] = []

        if llm_raw:
            try:
                # Strip markdown code fences if present
                cleaned = llm_raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for i, item in enumerate(parsed[:12]):
                        issues.append({
                            "id": f"issue-{i + 1}",
                            "type": item.get("type", "logic_gap"),
                            "severity": item.get("severity", "info"),
                            "title": str(item.get("title", "")),
                            "message": str(item.get("message", "")),
                            "node_texts": item.get("node_texts", []),
                        })
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Failed to parse LLM analysis response, returning structural analysis")

        # If LLM didn't return usable results, fall back to structural analysis
        if not issues:
            issues = _structural_analysis(nodes, root_id, links)

        return {"issues": issues, "source": "llm" if llm_raw else "structural"}

    # ── AI Expansion ───────────────────────────────────────────────

    @app.post("/api/mindmap/expand")
    async def expand_mindmap_node(req: MindMapExpandRequest) -> dict:
        system_prompt = (
            "你是一位学术论文写作助手。用户正在构建思维导图，"
            "需要你为指定节点生成子主题建议。\n\n"
            "请返回 JSON 数组，每个元素是一个子主题对象：\n"
            '- "text": 子主题标题（简洁，10字以内）\n'
            '- "rationale": 简短说明为什么需要这个子主题\n\n'
            f"生成 {req.max_children} 个子主题。只返回 JSON 数组，不要其他文字。"
        )

        user_prompt = f"当前节点：{req.node_text}"
        if req.context:
            user_prompt += f"\n上下文：\n{req.context}"

        llm_raw = await _llm_call(system_prompt, user_prompt)

        children: list[dict[str, str]] = []

        if llm_raw:
            try:
                cleaned = llm_raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()

                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for item in parsed[:req.max_children]:
                        children.append({
                            "text": str(item.get("text", "新节点")),
                            "rationale": str(item.get("rationale", "")),
                        })
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Failed to parse LLM expand response, using fallback")

        # Fallback if LLM unavailable
        if not children:
            children = _fallback_expand(req.node_text, req.max_children)

        return {"children": children}


def _structural_analysis(
    nodes: dict[str, Any],
    root_id: str,
    links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Lightweight structural checks when LLM is unavailable."""
    issues: list[dict[str, Any]] = []
    idx = 0

    GENERIC = {"中心主题", "新节点", "未命名节点"}

    root = nodes.get(root_id)
    if root and not root.get("children"):
        issues.append({
            "id": f"issue-{idx}",
            "type": "shallow_branch",
            "severity": "warning",
            "title": "主链还没有展开",
            "message": "中心主题下面还没有分支，建议先拆出研究问题、方法、论据或结论。",
            "node_texts": [root.get("text", "")],
        })
        idx += 1

    # Build text-to-ids map for duplicate detection
    text_to_ids: dict[str, list[str]] = {}
    for nid, node in nodes.items():
        t = node.get("text", "").strip().lower()
        if t and t not in GENERIC:
            text_to_ids.setdefault(t, []).append(nid)

    for text, ids in text_to_ids.items():
        if len(ids) > 1:
            issues.append({
                "id": f"issue-{idx}",
                "type": "duplicate",
                "severity": "warning",
                "title": "存在相似表达",
                "message": f"有 {len(ids)} 个节点使用了相近表述「{text}」，建议合并或区分论点侧重点。",
                "node_texts": [nodes[nid].get("text", "") for nid in ids],
            })
            idx += 1

    for nid, node in nodes.items():
        parent_id = node.get("parentId")
        if nid != root_id and parent_id and parent_id not in nodes:
            issues.append({
                "id": f"issue-{idx}",
                "type": "isolated",
                "severity": "critical",
                "title": "发现孤立节点",
                "message": "这个节点没有有效父节点，建议把它接回主链或删除。",
                "node_texts": [node.get("text", "")],
            })
            idx += 1
            continue

        children = node.get("children", [])
        if nid != root_id and not children:
            text = node.get("text", "").strip()
            if not text or len(text) < 6 or text in GENERIC:
                issues.append({
                    "id": f"issue-{idx}",
                    "type": "missing_support",
                    "severity": "info",
                    "title": "建议补充支撑信息",
                    "message": "节点内容较短，建议补充前置条件、证据来源或预期结论。",
                    "node_texts": [text],
                })
                idx += 1

    return issues[:12]


def _fallback_expand(topic: str, max_children: int) -> list[dict[str, str]]:
    """Hardcoded expansion suggestions when LLM is unavailable."""
    topic_l = topic.lower()
    if any(k in topic_l for k in ("control", "stability", "校正", "控制", "稳定")):
        templates = [
            ("系统建模", "建立数学模型描述被控对象"),
            ("稳定性分析", "分析系统在扰动下的稳定性条件"),
            ("控制器设计", "设计满足性能指标的校正装置"),
            ("仿真验证", "通过仿真验证设计效果"),
        ]
    else:
        templates = [
            ("问题定义", "明确研究问题的范围和边界"),
            ("方法设计", "选择或设计合适的研究方法"),
            ("实验验证", "设计实验验证方法的有效性"),
            ("结论与展望", "总结发现并指出未来方向"),
        ]
    return [{"text": t, "rationale": r} for t, r in templates[:max(1, max_children)]]
