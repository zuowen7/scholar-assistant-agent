"""学术工具 — 翻译、导出、arXiv、RAG 检索。

参考 claw-code: retrieve_context_tool (RAG), dispatch_tool (file ops).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
from contextlib import suppress
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from src.agent_v2.runtime.file_mutations import atomic_write_bytes, atomic_write_text
from src.agent_v2.tools.registry import ToolRegistry, ToolResult

_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+[^)]*)?\)")
_LATEX_IMAGE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*])?\{([^}]+)}")
_LATEX_BIB_RE = re.compile(r"\\bibliography\{([^}]+)}|\\addbibresource\{([^}]+)}")
_YAML_BIB_RE = re.compile(r"(?im)^\s*bibliography\s*:\s*[\"']?([^\"'\r\n]+\.bib)[\"']?\s*$")
_YAML_TEMPLATE_RE = re.compile(r"(?im)^\s*template\s*:\s*[\"']?([^\"'\r\n#]+?)[\"']?\s*(?:#.*)?$")
_LATEX_CITE_RE = re.compile(r"\\cite\w*\{([^}]+)}")
_PANDOC_CITE_RE = re.compile(r"(?<![\w.])@([A-Za-z0-9_:.+\-/]+)")
_BIB_KEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.IGNORECASE)
_WEB_FETCH_MAX_BYTES = 2 * 1024 * 1024


def _local_resource_path(source: Path, raw_path: str) -> Path | None:
    cleaned = raw_path.strip().strip("\"'")
    if not cleaned or cleaned.startswith(("#", "data:")):
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme or parsed.netloc:
        return None
    return (source.parent / parsed.path).resolve()


def _resource_is_in_workspace(resource: Path, workspace_root: Path) -> bool:
    try:
        resource.relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def _preflight_document_resources(
    source: Path,
    content: str,
    workspace_root: Path,
) -> list[str]:
    """Return deterministic missing-resource diagnostics before export."""

    issues: list[str] = []
    image_refs = [match.group(1) for match in _MARKDOWN_IMAGE_RE.finditer(content)]
    image_refs.extend(match.group(1) for match in _LATEX_IMAGE_RE.finditer(content))
    for raw_path in image_refs:
        resource = _local_resource_path(source, raw_path)
        if resource is not None and not _resource_is_in_workspace(resource, workspace_root):
            issues.append(f"image escapes workspace: {raw_path}")
        elif resource is not None and not resource.is_file():
            issues.append(f"missing image: {raw_path}")

    template_refs = [match.group(1).strip() for match in _YAML_TEMPLATE_RE.finditer(content)]
    for raw_path in template_refs:
        resource = _local_resource_path(source, raw_path)
        if resource is not None and not _resource_is_in_workspace(resource, workspace_root):
            issues.append(f"template escapes workspace: {raw_path}")
        elif resource is not None and not resource.is_file():
            issues.append(f"missing template: {raw_path}")

    bib_refs: list[str] = []
    for match in _LATEX_BIB_RE.finditer(content):
        raw_group = match.group(1) or match.group(2) or ""
        for item in raw_group.split(","):
            value = item.strip()
            if value and not value.lower().endswith(".bib"):
                value += ".bib"
            if value:
                bib_refs.append(value)
    bib_refs.extend(match.group(1).strip() for match in _YAML_BIB_RE.finditer(content))

    bib_paths: list[Path] = []
    for raw_path in bib_refs:
        resource = _local_resource_path(source, raw_path)
        if resource is None:
            continue
        if not _resource_is_in_workspace(resource, workspace_root):
            issues.append(f"bibliography escapes workspace: {raw_path}")
        elif not resource.is_file():
            issues.append(f"missing bibliography: {raw_path}")
        else:
            bib_paths.append(resource)

    cited_keys: set[str] = set()
    for match in _LATEX_CITE_RE.finditer(content):
        cited_keys.update(key.strip() for key in match.group(1).split(",") if key.strip())
    cited_keys.update(_PANDOC_CITE_RE.findall(content))
    if cited_keys:
        if not bib_paths:
            if not bib_refs:
                issues.append("citations found but no bibliography resource is declared")
        else:
            known_keys: set[str] = set()
            for path in bib_paths:
                try:
                    known_keys.update(_BIB_KEY_RE.findall(path.read_text(encoding="utf-8")))
                except OSError as exc:
                    issues.append(f"cannot read bibliography {path.name}: {exc}")
            for key in sorted(cited_keys - known_keys):
                issues.append(f"missing bibliography key: {key}")
    return issues


def _validate_public_http_url(
    url: str,
    *,
    resolved_ips: list[str] | None,
) -> tuple[bool, str]:
    """Reject URLs that can address local, private, or otherwise non-public hosts."""
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        return False, f"invalid URL: {exc}"
    if parsed.scheme not in {"http", "https"}:
        return False, "URL scheme must be http or https"
    if not parsed.hostname:
        return False, "URL hostname is required"
    if parsed.username or parsed.password:
        return False, "URL credentials are not allowed"
    try:
        port = parsed.port
    except ValueError as exc:
        return False, f"invalid URL port: {exc}"
    expected_port = 443 if parsed.scheme == "https" else 80
    if port is not None and port != expected_port:
        return False, f"URL port {port} is not allowed for {parsed.scheme}"
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False, "localhost targets are not allowed"

    addresses = list(resolved_ips or [])
    with suppress(ValueError):
        addresses.append(str(ipaddress.ip_address(hostname)))
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False, f"invalid resolved IP address: {address}"
        if not ip.is_global:
            return False, f"non-public network target is not allowed: {ip}"
    return True, ""


async def _resolve_public_http_target(url: str) -> tuple[bool, str, str | None]:
    allowed, reason = _validate_public_http_url(url, resolved_ips=None)
    if not allowed:
        return allowed, reason, None
    hostname = urlsplit(url).hostname
    if hostname is None:
        return False, "URL hostname is required", None
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        return False, f"hostname resolution failed: {exc}", None
    addresses = sorted(
        {str(info[4][0]) for info in infos},
        key=lambda value: (
            ipaddress.ip_address(value).version,
            int(ipaddress.ip_address(value)),
        ),
    )
    if not addresses:
        return False, "hostname did not resolve to an address", None
    allowed, reason = _validate_public_http_url(url, resolved_ips=addresses)
    return allowed, reason, addresses[0] if allowed else None


async def _resolve_public_http_url(url: str) -> tuple[bool, str]:
    """Compatibility wrapper used by validation tests and callers."""
    allowed, reason, _address = await _resolve_public_http_target(url)
    return allowed, reason


def _pinned_http_request_parts(url: str, address: str) -> tuple[str, str, str]:
    """Build an IP-pinned URL while preserving the HTTP and TLS host identity."""
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("URL hostname is required")
    pinned_host = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
    pinned_url = urlunsplit((parsed.scheme, pinned_host, parsed.path or "/", parsed.query, ""))
    return pinned_url, parsed.netloc, hostname


async def _fetch_pinned_public_url(url: str) -> tuple[int, dict[str, str], str] | ToolResult:
    """Fetch one URL by connecting only to a DNS address validated as public."""
    allowed, reason, address = await _resolve_public_http_target(url)
    if not allowed or address is None:
        return ToolResult(f"Fetch blocked: {reason}", is_error=True)

    import httpx

    pinned_url, host_header, sni_hostname = _pinned_http_request_parts(url, address)
    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        request = client.build_request(
            "GET",
            pinned_url,
            headers={
                "Host": host_header,
                "User-Agent": "ScholarAssistant/0.4",
            },
        )
        request.extensions["sni_hostname"] = sni_hostname
        response = await client.send(request, stream=True)
        try:
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > _WEB_FETCH_MAX_BYTES:
                        return ToolResult(
                            "Fetch blocked: response body is too large", is_error=True
                        )
                except ValueError:
                    pass

            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > _WEB_FETCH_MAX_BYTES:
                    return ToolResult("Fetch blocked: response body is too large", is_error=True)
                chunks.append(chunk)
            text = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            return response.status_code, dict(response.headers), text
        finally:
            await response.aclose()


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
                preflight_issues = _preflight_document_resources(
                    full,
                    markdown,
                    registry._workspace_root or full.parent,
                )
                allow_missing = bool(args.get("allow_missing_resources", False))
                if preflight_issues and not allow_missing:
                    details = "\n".join(f"- {issue}" for issue in preflight_issues)
                    return ToolResult(
                        f"error: document resource preflight failed:\n{details}",
                        is_error=True,
                    )
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
                    await asyncio.to_thread(atomic_write_bytes, out_path, resp.content)
                    message = f"Export successful: {out_path}"
                    if preflight_issues:
                        message += "\nwarning: missing resources were explicitly allowed"
                    return ToolResult(message)
                data = resp.json()
                if normalized in ("word", "docx"):
                    generated_path = data.get("path")
                    if not generated_path or not Path(generated_path).is_file():
                        return ToolResult(
                            "error: Word export did not produce a file", is_error=True
                        )
                    out_path = full.with_suffix(".docx")
                    generated_bytes = await asyncio.to_thread(Path(generated_path).read_bytes)
                    await asyncio.to_thread(atomic_write_bytes, out_path, generated_bytes)
                else:
                    tex = data.get("tex")
                    if not isinstance(tex, str) or not tex:
                        return ToolResult("error: LaTeX export returned no content", is_error=True)
                    out_path = full.with_suffix(".tex")
                    await asyncio.to_thread(atomic_write_text, out_path, tex)
                message = f"Export successful: {out_path}"
                if preflight_issues:
                    message += "\nwarning: missing resources were explicitly allowed"
                return ToolResult(message)
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

            url = "http://export.arxiv.org/api/query"
            params = {
                "search_query": f"all:{query}",
                "max_results": str(max_results),
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
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
        effects={"external_side_effect", "cost"},
        approval_scope="exact-input",
        network_scope={"local-translation-api"},
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
                "allow_missing_resources": {
                    "type": "boolean",
                    "default": False,
                    "description": "Explicitly allow export despite missing local resources",
                },
            },
            "required": ["file_path"],
        },
        export_document,
        permission="workspace-write",
        effects={"filesystem_write", "network"},
        approval_scope="path",
        network_scope={"local-export-api"},
        rollback_capability="journaled",
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
        effects={"network"},
        approval_scope="domain",
        network_scope={"export.arxiv.org"},
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
        effects={"network"},
        approval_scope="domain",
        network_scope={"html.duckduckgo.com"},
    )

    # ---- web_fetch (参考 claw-code WebFetch) ----
    async def web_fetch(args: dict) -> ToolResult:
        """抓取网页内容。"""
        url = str(args.get("url", ""))
        if not url:
            return ToolResult("error: url is required", is_error=True)
        try:
            current_url = url
            response: tuple[int, dict[str, str], str] | None = None
            for _hop in range(6):
                fetched = await _fetch_pinned_public_url(current_url)
                if isinstance(fetched, ToolResult):
                    return fetched
                response = fetched
                status_code, headers, _text = response
                if status_code not in {301, 302, 303, 307, 308}:
                    break
                location = headers.get("location", "")
                if not location:
                    return ToolResult("Fetch redirect missing Location header", is_error=True)
                current_url = urljoin(current_url, location)
            else:
                return ToolResult("Fetch blocked: too many redirects", is_error=True)
            if response is None:
                return ToolResult("Fetch failed: no response", is_error=True)
            status_code, _headers, text = response
            if status_code != 200:
                return ToolResult(f"Fetch returned {status_code}", is_error=True)

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
        effects={"network"},
        approval_scope="domain",
        network_scope={"user-approved-domain"},
    )
