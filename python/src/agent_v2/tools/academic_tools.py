"""学术工具 — 翻译、导出、arXiv、RAG 检索。

参考 claw-code: retrieve_context_tool (RAG), dispatch_tool (file ops).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from src.agent_v2.tools.registry import ToolRegistry, ToolResult


def register_academic_tools(registry: ToolRegistry) -> None:
    """注册学术领域工具到 ToolRegistry。"""

    # ---- translate_document ----
    async def translate_document(args: dict) -> ToolResult:
        """翻译文档。调用现有的翻译管道。"""
        file_path = str(args.get("file_path", ""))
        source_lang = str(args.get("source_lang", "en"))
        target_lang = str(args.get("target_lang", "zh-CN"))
        str(args.get("engine", "cloud"))

        if not file_path:
            return ToolResult("error: file_path is required", is_error=True)

        try:
            full = registry._resolve_path(file_path)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
        if not full.is_file():
            return ToolResult(f"error: file not found: {file_path}", is_error=True)

        # Use the existing translation pipeline via HTTP call to local API
        try:
            import httpx

            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(f"{api_base}/api/translate/path", json={"path": str(full)})
                if resp.status_code != 200:
                    return ToolResult(
                        f"error: translation API returned {resp.status_code}", is_error=True
                    )
                data = resp.json()
                task_id = data.get("task_id", "")
                if not task_id:
                    return ToolResult(
                        f"Translation queued for {file_path} ({source_lang} → {target_lang})"
                    )
                return ToolResult(
                    f"Translation started: {file_path} ({source_lang} → {target_lang}), task_id={task_id}"
                )
        except Exception as e:
            return ToolResult(
                f"error connecting to translation API: {e}. Is the API running on port 18088?",
                is_error=True,
            )

    # ---- export_document ----
    async def export_document(args: dict) -> ToolResult:
        """导出文档为 LaTeX/Word/PDF。"""
        file_path = str(args.get("file_path", ""))
        fmt = str(args.get("format", "latex"))

        if not file_path:
            return ToolResult("error: file_path is required", is_error=True)

        try:
            full = registry._resolve_path(file_path)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
        if not full.is_file():
            return ToolResult(f"error: file not found: {file_path}", is_error=True)

        try:
            import httpx

            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=120.0) as client:
                markdown = await asyncio.to_thread(full.read_text, encoding="utf-8")
                normalized = fmt.lower()
                if normalized in ("word", "docx"):
                    resp = await client.post(
                        f"{api_base}/api/export/word",
                        json={"content": markdown, "title": full.stem},
                    )
                elif normalized == "pdf":
                    resp = await client.post(
                        f"{api_base}/api/export/pdf",
                        json={"markdown": markdown, "title": full.stem},
                    )
                else:
                    resp = await client.post(
                        f"{api_base}/api/export",
                        json={"markdown": markdown, "title": full.stem},
                    )
                if resp.status_code != 200:
                    return ToolResult(
                        f"error: export API returned {resp.status_code}", is_error=True
                    )
                if normalized == "pdf":
                    out_path = full.with_suffix(".pdf")
                    await asyncio.to_thread(out_path.write_bytes, resp.content)
                    return ToolResult(f"Export successful: {out_path}")
                data = resp.json()
                if normalized in ("word", "docx"):
                    generated_path = data.get("path")
                    if not generated_path or not Path(generated_path).is_file():
                        return ToolResult(
                            "error: Word export did not produce a file", is_error=True
                        )
                    out_path = full.with_suffix(".docx")
                    await asyncio.to_thread(shutil.copy2, generated_path, out_path)
                else:
                    tex = data.get("tex")
                    if not isinstance(tex, str) or not tex:
                        return ToolResult("error: LaTeX export returned no content", is_error=True)
                    out_path = full.with_suffix(".tex")
                    await asyncio.to_thread(out_path.write_text, tex, encoding="utf-8")
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
    registry.register(
        "translate_document",
        "Translate a PDF or Markdown document",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the document"},
                "source_lang": {"type": "string", "default": "en"},
                "target_lang": {"type": "string", "default": "zh-CN"},
                "engine": {"type": "string", "default": "cloud"},
            },
            "required": ["file_path"],
        },
        translate_document,
        permission="read-only",
    )

    registry.register(
        "export_document",
        "Export document to LaTeX, Word, or PDF",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the document"},
                "format": {
                    "type": "string",
                    "default": "latex",
                    "description": "latex, docx, or pdf",
                },
            },
            "required": ["file_path"],
        },
        export_document,
        permission="workspace-write",
    )

    registry.register(
        "arxiv_search",
        "Search arXiv for papers",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        arxiv_search,
        permission="read-only",
    )

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
                resp = await client.post(
                    f"{api_base}/api/rag/query",
                    json={
                        "query": query,
                        "top_k": min(top_k, 10),
                    },
                )
                if resp.status_code == 404:
                    return ToolResult(
                        "RAG not configured. Ingest documents first via the Docs panel."
                    )
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
                    lines.append(f"[{i + 1}] {src}\n{snippet[:300]}")
                return ToolResult("\n\n".join(lines))
        except Exception as e:
            return ToolResult(f"RAG query failed: {e}", is_error=True)

    registry.register(
        "rag_search",
        (
            "Search the document library (RAG) for relevant papers, notes, and references. "
            "Use this when the user asks about topics that may be in their document collection."
        ),
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
            },
            "required": ["query"],
        },
        rag_search,
        permission="read-only",
    )

    # ---- Argument Companion / Reviewer read tools -----------------------
    # These tools expose the existing production stores through their public
    # API. They do not duplicate Reviewer-2, Claim Ledger, or Argument Map
    # logic; the Agent receives the same persisted data as the visible panels.

    async def read_argument_graph(args: dict) -> ToolResult:
        graph_id = str(args.get("graph_id", "")).strip()
        source_doc = str(args.get("source_doc", "")).strip()
        try:
            import httpx

            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=20.0) as client:
                if graph_id:
                    resp = await client.get(f"{api_base}/api/argument/graph/{graph_id}")
                    if resp.status_code == 404:
                        return ToolResult(f"Argument graph not found: {graph_id}", is_error=True)
                    resp.raise_for_status()
                    return ToolResult(json.dumps(resp.json(), ensure_ascii=False))

                resp = await client.get(f"{api_base}/api/argument/graphs")
                resp.raise_for_status()
                graphs = resp.json()
                if source_doc:
                    normalized = source_doc.replace("\\", "/").lower()
                    graphs = [
                        graph
                        for graph in graphs
                        if str(graph.get("source_doc", "")).replace("\\", "/").lower() == normalized
                    ]
                if not graphs:
                    return ToolResult("No argument graph found for the requested document.")
                return ToolResult(json.dumps(graphs, ensure_ascii=False))
        except Exception as e:
            return ToolResult(f"Argument graph lookup failed: {e}", is_error=True)

    registry.register(
        "read_argument_graph",
        (
            "Read the real Toulmin argument map. Provide graph_id for one full graph, "
            "or source_doc to find graphs linked to a manuscript."
        ),
        {
            "type": "object",
            "properties": {
                "graph_id": {"type": "string", "description": "Argument graph ID"},
                "source_doc": {"type": "string", "description": "Workspace document path"},
            },
        },
        read_argument_graph,
        permission="read-only",
    )

    async def read_argument_ledger(args: dict) -> ToolResult:
        doc_id = str(args.get("doc_id", "")).strip()
        if not doc_id:
            return ToolResult("error: doc_id is required", is_error=True)
        try:
            import httpx

            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=20.0) as client:
                # doc_id remains a query parameter because it may be a full path.
                resp = await client.get(
                    f"{api_base}/api/companion/ledger", params={"doc_id": doc_id}
                )
                if resp.status_code == 404:
                    return ToolResult(f"Claim Ledger not found for: {doc_id}", is_error=True)
                resp.raise_for_status()
                return ToolResult(json.dumps(resp.json(), ensure_ascii=False))
        except Exception as e:
            return ToolResult(f"Claim Ledger lookup failed: {e}", is_error=True)

    registry.register(
        "read_argument_ledger",
        (
            "Read the real Claim Ledger for a manuscript, including promises, "
            "source anchors, discharge anchors, and fulfillment status."
        ),
        {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "Document ID or full workspace file path",
                },
            },
            "required": ["doc_id"],
        },
        read_argument_ledger,
        permission="read-only",
    )

    async def read_reviewer_state(args: dict) -> ToolResult:
        session_id = str(args.get("session_id", "")).strip()
        doc_id = str(args.get("doc_id", "")).strip()
        if not session_id and not doc_id:
            return ToolResult("error: session_id or doc_id is required", is_error=True)
        try:
            import httpx

            api_base = os.environ.get("SCHOLAR_API_BASE", "http://localhost:18088")
            async with httpx.AsyncClient(timeout=20.0) as client:
                if session_id:
                    resp = await client.get(f"{api_base}/api/companion/review/{session_id}")
                else:
                    resp = await client.get(
                        f"{api_base}/api/companion/reviews", params={"doc_id": doc_id}
                    )
                if resp.status_code == 404:
                    return ToolResult("Reviewer-2 state not found.", is_error=True)
                resp.raise_for_status()
                return ToolResult(json.dumps(resp.json(), ensure_ascii=False))
        except Exception as e:
            return ToolResult(f"Reviewer-2 lookup failed: {e}", is_error=True)

    registry.register(
        "read_reviewer_state",
        (
            "Read persisted Reviewer-2 criticism, response status, rebuttal data, "
            "and anchored manuscript evidence."
        ),
        {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Reviewer session ID"},
                "doc_id": {
                    "type": "string",
                    "description": "Document ID or full workspace file path",
                },
            },
        },
        read_reviewer_state,
        permission="read-only",
    )

    # ---- web_search (参考 claw-code WebSearch) ----
    async def web_search(args: dict) -> ToolResult:
        """搜索网页。使用 DuckDuckGo HTML 搜索。"""
        query = str(args.get("query", ""))
        max_results = int(args.get("max_results", 5))

        if not query:
            return ToolResult("error: query is required", is_error=True)

        try:
            from urllib.parse import quote

            import httpx

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
                    cleaned = re.sub(r"<[^>]+>", "", s).strip()
                    if cleaned and len(cleaned) > 10:
                        results.append(cleaned[:300])
                if not results:
                    return ToolResult("No results found.")
                return ToolResult("\n\n".join(f"[{i + 1}] {r}" for i, r in enumerate(results)))
        except Exception as e:
            return ToolResult(f"Search failed: {e}", is_error=True)

    registry.register(
        "web_search",
        "Search the web for information",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        web_search,
        permission="read-only",
    )

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
            async with httpx.AsyncClient(
                timeout=15.0, headers=headers, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return ToolResult(f"Fetch returned {resp.status_code}", is_error=True)
                text = resp.text
                import re

                # Strip HTML tags for plain text
                cleaned = re.sub(
                    r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
                )
                cleaned = re.sub(
                    r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE
                )
                cleaned = re.sub(r"<[^>]+>", " ", cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if len(cleaned) > 5000:
                    cleaned = cleaned[:5000] + "... [truncated]"
                return ToolResult(cleaned or "(empty page)")
        except Exception as e:
            return ToolResult(f"Fetch failed: {e}", is_error=True)

    registry.register(
        "web_fetch",
        "Fetch and read the content of a web page",
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (must start with http:// or https://)",
                },
            },
            "required": ["url"],
        },
        web_fetch,
        permission="read-only",
    )
