"""学术工具 — 翻译、导出、arXiv 搜索。

直接注册到 ToolRegistry，不需单独启动 MCP 进程。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from src.agent_v2.tools.registry import ToolRegistry, ToolResult


def register_academic_tools(registry: ToolRegistry) -> None:
    """注册学术领域工具到 ToolRegistry。"""

    # ---- translate_document ----
    async def translate_document(args: dict) -> ToolResult:
        """翻译文档。调用现有的翻译管道。"""
        file_path = str(args.get("file_path", ""))
        source_lang = str(args.get("source_lang", "en"))
        target_lang = str(args.get("target_lang", "zh-CN"))
        engine = str(args.get("engine", "cloud"))

        if not file_path:
            return ToolResult("error: file_path is required", is_error=True)

        ws = registry._workspace_root
        full = Path(file_path) if Path(file_path).is_absolute() else (ws / file_path) if ws else Path(file_path)
        if not full.is_file():
            return ToolResult(f"error: file not found: {file_path}", is_error=True)

        # Use the existing translation pipeline via HTTP call to local API
        try:
            import httpx
            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=300.0) as client:
                # Step 1: Parse
                resp = await client.post(f"{api_base}/api/translate/parse", json={
                    "file_path": str(full),
                    "source_lang": source_lang,
                    "target_lang": target_lang,
                    "engine": engine,
                })
                if resp.status_code != 200:
                    return ToolResult(f"error: translation API returned {resp.status_code}", is_error=True)
                data = resp.json()
                task_id = data.get("task_id", "")
                if not task_id:
                    return ToolResult(f"Translation queued for {file_path} ({source_lang} → {target_lang})")
                return ToolResult(f"Translation started: {file_path} ({source_lang} → {target_lang}), task_id={task_id}")
        except Exception as e:
            return ToolResult(f"error connecting to translation API: {e}. Is the API running on port 18088?", is_error=True)

    # ---- export_document ----
    async def export_document(args: dict) -> ToolResult:
        """导出文档为 LaTeX/Word/PDF。"""
        file_path = str(args.get("file_path", ""))
        fmt = str(args.get("format", "latex"))

        if not file_path:
            return ToolResult("error: file_path is required", is_error=True)

        ws = registry._workspace_root
        full = Path(file_path) if Path(file_path).is_absolute() else (ws / file_path) if ws else Path(file_path)
        if not full.is_file():
            return ToolResult(f"error: file not found: {file_path}", is_error=True)

        try:
            import httpx
            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{api_base}/api/editor/export", json={
                    "file_path": str(full),
                    "format": fmt,
                })
                if resp.status_code != 200:
                    return ToolResult(f"error: export API returned {resp.status_code}", is_error=True)
                data = resp.json()
                out_path = data.get("output_path", f"{file_path}.{fmt}")
                return ToolResult(f"Export successful: {out_path}")
        except Exception as e:
            return ToolResult(f"error connecting to export API: {e}", is_error=True)

    # ---- arxiv_search ----
    async def arxiv_search(args: dict) -> ToolResult:
        """搜索 arXiv 论文。"""
        query = str(args.get("query", ""))
        max_results = int(args.get("max_results", 5))

        if not query:
            return ToolResult("error: query is required", is_error=True)

        try:
            import httpx
            url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ToolResult(f"arXiv API returned {resp.status_code}", is_error=True)
                text = resp.text[:4000]
                return ToolResult(text)
        except Exception as e:
            return ToolResult(f"arXiv search failed: {e}", is_error=True)

    # Register tools
    registry.register("translate_document", "Translate a PDF or Markdown document", {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "source_lang": {"type": "string", "default": "en"},
            "target_lang": {"type": "string", "default": "zh-CN"},
            "engine": {"type": "string", "default": "cloud"},
        },
        "required": ["file_path"],
    }, translate_document, permission="read-only")

    registry.register("export_document", "Export document to LaTeX, Word, or PDF", {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "format": {"type": "string", "default": "latex", "description": "latex, docx, or pdf"},
        },
        "required": ["file_path"],
    }, export_document, permission="workspace-write")

    registry.register("arxiv_search", "Search arXiv for papers", {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }, arxiv_search, permission="read-only")
