"""学术工具 — 翻译、导出、arXiv、RAG 检索。

参考 claw-code: retrieve_context_tool (RAG), dispatch_tool (file ops).
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

    # ---- rag_search — 参考 claw-code retrieve_context_tool ----
    async def rag_search(args: dict) -> ToolResult:
        """检索文档库，返回相关文档片段。参考 claw-code retrieve_context。"""
        query = str(args.get("query", ""))
        top_k = int(args.get("top_k", 5))

        if not query:
            return ToolResult("error: query is required", is_error=True)

        try:
            import httpx
            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{api_base}/api/rag/query", json={
                    "query": query,
                    "top_k": min(top_k, 10),
                })
                if resp.status_code == 404:
                    return ToolResult("RAG not configured. Ingest documents first via the Docs panel.")
                if resp.status_code != 200:
                    return ToolResult(f"RAG query returned {resp.status_code}", is_error=True)
                data = resp.json()
                hits = data.get("hits", data.get("results", []))
                if not hits:
                    return ToolResult("No relevant documents found.")
                lines = []
                for i, hit in enumerate(hits[:top_k]):
                    src = hit.get("source", hit.get("path", hit.get("doc_id", f"doc_{i}")))
                    snippet = hit.get("snippet", hit.get("text", hit.get("content", "")))
                    lines.append(f"[{i+1}] {src}\n{snippet[:300]}")
                return ToolResult("\n\n".join(lines))
        except Exception as e:
            return ToolResult(f"RAG query failed: {e}", is_error=True)

    registry.register("rag_search", (
        "Search the document library (RAG) for relevant papers, notes, and references. "
        "Use this when the user asks about topics that may be in their document collection."
    ), {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
        },
        "required": ["query"],
    }, rag_search, permission="read-only")

    # ---- web_search (参考 claw-code WebSearch) ----
    async def web_search(args: dict) -> ToolResult:
        """搜索网页。使用 DuckDuckGo HTML 搜索。"""
        query = str(args.get("query", ""))
        max_results = int(args.get("max_results", 5))

        if not query:
            return ToolResult("error: query is required", is_error=True)

        try:
            import httpx
            from urllib.parse import quote
            url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
            headers = {"User-Agent": "ScholarAssistant/0.4"}
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ToolResult(f"Search returned {resp.status_code}", is_error=True)
                text = resp.text
                # Simple extraction of result snippets
                import re
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)
                results = []
                for s in snippets[:max_results]:
                    cleaned = re.sub(r'<[^>]+>', '', s).strip()
                    if cleaned and len(cleaned) > 10:
                        results.append(cleaned[:300])
                if not results:
                    return ToolResult("No results found.")
                return ToolResult("\n\n".join(f"[{i+1}] {r}" for i, r in enumerate(results)))
        except Exception as e:
            return ToolResult(f"Search failed: {e}", is_error=True)

    registry.register("web_search", "Search the web for information", {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }, web_search, permission="read-only")

    # ---- web_fetch (参考 claw-code WebFetch) ----
    async def web_fetch(args: dict) -> ToolResult:
        """抓取网页内容。"""
        url = str(args.get("url", ""))
        if not url:
            return ToolResult("error: url is required", is_error=True)
        if not url.startswith(("http://", "https://")):
            return ToolResult("error: url must start with http:// or https://", is_error=True)
        try:
            import httpx
            headers = {"User-Agent": "ScholarAssistant/0.4"}
            async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ToolResult(f"Fetch returned {resp.status_code}", is_error=True)
                text = resp.text
                import re
                # Strip HTML tags for plain text
                cleaned = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
                cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                if len(cleaned) > 5000:
                    cleaned = cleaned[:5000] + "... [truncated]"
                return ToolResult(cleaned or "(empty page)")
        except Exception as e:
            return ToolResult(f"Fetch failed: {e}", is_error=True)

    registry.register("web_fetch", "Fetch and read the content of a web page", {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch (must start with http:// or https://)"},
        },
        "required": ["url"],
    }, web_fetch, permission="read-only")
