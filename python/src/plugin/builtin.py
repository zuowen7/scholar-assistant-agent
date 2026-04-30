"""Built-in Plugin — 注册 Scholar Assistant 内置工具为插件。

本模块将现有 Agent 工具（translate_text, parse_document, search_documents 等）
声明为 PluginServer，供 PluginRegistry 统一管理。

每个工具的 handler 直接复用 api_factory.py 中对应端点的逻辑，
通过 FastAPI 路由注入后，Agent 和 MCP 客户端都能调用。

工具列表（MCP 协议兼容格式）：
https://modelcontextprotocol.io/specification/tools
"""

from __future__ import annotations

import logging
from typing import Any

from src.plugin.registry import PluginServer, PluginRegistry, ToolSpec

logger = logging.getLogger(__name__)


# ── 工具 Handler（复用 api_factory.py 逻辑）────────────────────────────

def _tool_translate_text(text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
    """翻译文本。"""
    from src.translator.ollama_client import OllamaClient
    from src.translator.cloud_client import CloudClient
    from src.translator.context import extract_document_context

    # 尝试读取全局配置（延迟导入避免循环）
    try:
        from api_factory import _load_config
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        use_cloud = trans_cfg.get("engine", "ollama") == "cloud"
        if use_cloud and cloud_cfg.get("api_key"):
            client = CloudClient(
                base_url=cloud_cfg.get("base_url", "https://api.openai.com/v1"),
                api_key=cloud_cfg.get("api_key", ""),
                model=cloud_cfg.get("model", "gpt-4o"),
            )
        else:
            client = OllamaClient(
                base_url=trans_cfg.get("ollama_base_url", "http://localhost:11434"),
                model=trans_cfg.get("model", "qwen3:8b"),
                temperature=trans_cfg.get("temperature", 0.3),
                num_predict=trans_cfg.get("num_predict", 16384),
                system_prompt=trans_cfg.get("system_prompt", ""),
                timeout=trans_cfg.get("timeout", 300.0),
            )
    except Exception:
        # Fallback: 使用默认配置
        client = OllamaClient()

    try:
        result = client.translate(text)
        return result.translated if hasattr(result, "translated") else str(result)
    finally:
        if hasattr(client, "close"):
            client.close()


def _tool_parse_document(file_path: str) -> str:
    """解析文档，提取纯文本。"""
    from src.parser import extract_document
    MAX_LEN = 4000
    try:
        doc = extract_document(file_path)
        text = doc.full_text
        if len(text) > MAX_LEN:
            text = text[:MAX_LEN] + "\n...[内容已截断]"
        return text
    except Exception as e:
        return f"文档解析失败: {e}"


def _tool_search_documents(query: str, top_k: int = 5, rag_store: Any = None) -> str:
    """在知识库中检索相关文档片段。"""
    if rag_store is None:
        return "知识库未初始化（RAG store 不可用）"
    try:
        results = rag_store.retrieve_context(query, top_k=top_k)
        if not results:
            return "未找到相关文档内容。"
        parts = []
        for i, r in enumerate(results):
            dist = r.get("distance", 0)
            parts.append(f"[片段 {i + 1}] (相似度: {1 - dist:.2f})\n{r['text']}")
        return "\n\n---\n\n".join(parts)
    except Exception as e:
        return f"文档检索失败: {e}"


def _tool_crawl_arxiv(query: str, max_results: int = 5) -> str:
    """搜索 arXiv 学术论文。"""
    import httpx
    import time
    import xml.etree.ElementTree as ET

    try:
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        with httpx.Client(timeout=30.0) as client:
            for attempt in range(3):
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            else:
                resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return "未找到相关论文。"

        results = []
        for entry in entries:
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            published = entry.find("atom:published", ns)
            authors = entry.findall("atom:author/atom:name", ns)

            title_text = title.text.strip().replace("\n", " ") if title is not None else "无标题"
            summary_text = summary.text.strip().replace("\n", " ")[:300] if summary is not None else ""
            pub_date = published.text[:10] if published is not None else "未知日期"
            author_names = ", ".join(a.text for a in authors[:3] if a.text)
            if len(authors) > 3:
                author_names += " et al."

            results.append(
                f"标题: {title_text}\n"
                f"作者: {author_names}\n"
                f"日期: {pub_date}\n"
                f"摘要: {summary_text}"
            )
        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"arXiv 搜索失败: {e}"


def _tool_polish_text(text: str, style: str = "academic") -> str:
    """润色学术文本。"""
    style_hints = {
        "academic": "使用严谨的学术语言，确保逻辑清晰、用词精准",
        "formal": "使用正式的书面语，避免口语化表达",
        "concise": "精简冗余表达，保留核心信息，使文字更加凝练",
    }
    hint = style_hints.get(style, style_hints["academic"])
    prompt = f"请润色以下文本。要求：{hint}。只输出润色后的文本，不要解释。\n\n{text}"
    return _call_llm_simple(prompt)


def _tool_summarize_text(text: str, max_sentences: int = 5) -> str:
    """生成文本摘要。"""
    prompt = f"请用中文为以下文本生成摘要，不超过 {max_sentences} 个句子。提取核心论点和关键信息。\n\n{text}"
    return _call_llm_simple(prompt)


def _tool_generate_outline(topic: str, sections: int = 5) -> str:
    """生成论文大纲。"""
    prompt = (
        f"请为主题「{topic}」生成一个学术论文大纲，包含 {sections} 个主要章节。"
        "每个章节下给出 2-3 个子节。使用 Markdown 格式输出。"
    )
    return _call_llm_simple(prompt)


def _tool_expand_section(section: str, context: str = "") -> str:
    """扩写段落。"""
    ctx_part = f"\n\n参考上下文:\n{context}" if context else ""
    prompt = (
        f"请将以下段落扩写为 200-400 字的完整论述，补充细节、论据和例子。"
        "保持学术风格，逻辑连贯。只输出扩写后的文本。\n\n"
        f"原文: {section}{ctx_part}"
    )
    return _call_llm_simple(prompt)


def _tool_format_bibliography(bibtex_entry: str, style: str = "ieee", target_lang: str = "zh") -> str:
    """格式化参考文献。"""
    prompt = f"""请将以下 BibTeX 条目格式化为 {style.upper()} 引用格式的文本。
只输出格式化后的参考文献，不要任何解释。目标语言：{"中文" if target_lang == "zh" else "英文"}。
BibTeX 条目：{bibtex_entry}"""
    return _call_llm_simple(prompt)


def _tool_analyze_markdown_elements(text: str) -> str:
    """分析 Markdown 文本中的特殊元素。"""
    from src.agent.special_elements import analyze_markdown_elements
    import json
    result = analyze_markdown_elements(text)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _tool_parse_table_structure(table_markdown: str) -> str:
    """解析 Markdown 表格结构。"""
    from src.agent.special_elements import parse_table_structure
    import json
    result = parse_table_structure(table_markdown)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _tool_generate_table_markdown(headers: list, rows: list) -> str:
    """从结构化数据生成 Markdown 表格。"""
    from src.agent.special_elements import generate_table_markdown
    return generate_table_markdown(headers, rows)


def _tool_format_latex_formula(formula: str, display: bool = False) -> str:
    """格式化 LaTeX 公式。"""
    from src.agent.special_elements import format_latex_formula
    return format_latex_formula(formula, display=display)


def _tool_get_citation_context(text: str, citation_key: str) -> str:
    """获取文献引用的上下文。"""
    from src.agent.special_elements import get_citation_context
    return get_citation_context(text, citation_key)


def _tool_analyze_image_with_vision(image_path: str) -> str:
    """使用 Vision API 分析图片内容。"""
    from src.agent.special_elements import analyze_image_with_vision
    return analyze_image_with_vision(image_path)


def _tool_analyze_chart_image(image_path: str) -> str:
    """使用 Vision API 分析图表图片。"""
    from src.agent.special_elements import analyze_chart_image
    return analyze_chart_image(image_path)


def _call_llm_simple(prompt: str) -> str:
    """同步调用 LLM（极简版，用于辅助工具）。"""
    import httpx
    import re

    try:
        from api_factory import _load_config
        config = _load_config()
        trans_cfg = config.get("translator", {})
        cloud_cfg = trans_cfg.get("cloud", {})
        use_cloud = trans_cfg.get("engine", "ollama") == "cloud"
    except Exception:
        use_cloud = False
        cloud_cfg = {}

    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            if use_cloud and cloud_cfg.get("api_key"):
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {cloud_cfg.get('api_key', '')}"}
                resp = client.post(
                    f"{cloud_cfg.get('base_url', 'https://api.openai.com/v1')}/chat/completions",
                    json={
                        "model": cloud_cfg.get("model", "gpt-4o"),
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2048,
                        "stream": False,
                    },
                    headers=headers,
                )
            else:
                resp = client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "qwen3:8b",
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 2048},
                    },
                )
            resp.raise_for_status()
            data = resp.json()
            if "choices" in data:
                content = data["choices"][0]["message"]["content"]
            else:
                content = data.get("message", {}).get("content", "")
            content = re.sub(r"<think.*?>.*?</think.*?>", "", content, flags=re.DOTALL).strip()
            return content if content else "（LLM 返回为空）"
    except Exception as e:
        return f"LLM 调用失败: {e}"


# ── 插件定义 ─────────────────────────────────────────────────────────

def create_builtin_server() -> PluginServer:
    """创建内置 Scholar Assistant 插件（所有内置工具的集合）。

    这个服务器对标 mcp_server.py 的 MCP_TOOLS 列表，
    区别在于：这里的工具可以同时注册到 FastAPI 路由。
    """
    server = PluginServer(
        name="yanmo",
        version="0.3.1",
        description="研墨 学术翻译与研究辅助工具集",
        instructions="提供翻译、文档解析、文献检索、论文润色等功能。使用时需提供文件路径（绝对路径）。",
        tools=[
            ToolSpec(
                name="translate_text",
                description="翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "待翻译的文本内容"},
                        "source_lang": {"type": "string", "description": "源语言代码，默认 en", "default": "en"},
                        "target_lang": {"type": "string", "description": "目标语言代码，默认 zh", "default": "zh"},
                    },
                    "required": ["text"],
                },
                handler=_make_handler("text", _tool_translate_text, ["text", "source_lang", "target_lang"]),
            ),
            ToolSpec(
                name="parse_document",
                description="解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文档文件的绝对路径"},
                    },
                    "required": ["file_path"],
                },
                handler=_make_handler("file_path", _tool_parse_document, ["file_path"]),
            ),
            ToolSpec(
                name="search_documents",
                description="在已入库的文档中检索与查询相关的段落。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "查询文本（中英文均可）"},
                        "top_k": {"type": "integer", "description": "返回的最大结果数量，默认 5", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=_make_handler("query", _tool_search_documents, ["query", "top_k"]),
            ),
            ToolSpec(
                name="crawl_arxiv",
                description="搜索 arXiv 学术论文，返回标题、作者和摘要。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词（英文）"},
                        "max_results": {"type": "integer", "description": "最大返回结果数，默认 5", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=_make_handler("query", _tool_crawl_arxiv, ["query", "max_results"]),
            ),
            ToolSpec(
                name="polish_text",
                description="润色学术文本，改善表达和语法。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "待润色的文本内容"},
                        "style": {"type": "string", "description": "润色风格：academic/formal/concise，默认 academic", "default": "academic"},
                    },
                    "required": ["text"],
                },
                handler=_make_handler("text", _tool_polish_text, ["text", "style"]),
            ),
            ToolSpec(
                name="summarize_text",
                description="生成文本的精简摘要。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "待摘要的文本内容"},
                        "max_sentences": {"type": "integer", "description": "摘要的最大句子数，默认 5", "default": 5},
                    },
                    "required": ["text"],
                },
                handler=_make_handler("text", _tool_summarize_text, ["text", "max_sentences"]),
            ),
            ToolSpec(
                name="generate_outline",
                description="生成学术论文或报告的结构化大纲。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "论文或报告的主题"},
                        "sections": {"type": "integer", "description": "大纲的章节数量，默认 5", "default": 5},
                    },
                    "required": ["topic"],
                },
                handler=_make_handler("topic", _tool_generate_outline, ["topic", "sections"]),
            ),
            ToolSpec(
                name="expand_section",
                description="扩写论文段落，补充细节和论据。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "section": {"type": "string", "description": "待扩写的段落内容"},
                        "context": {"type": "string", "description": "上下文信息（可选）", "default": ""},
                    },
                    "required": ["section"],
                },
                handler=_make_handler("section", _tool_expand_section, ["section", "context"]),
            ),
            ToolSpec(
                name="format_bibliography",
                description="将 BibTeX 条目格式化为指定引用格式（IEEE/APA/GB/T 7714/MLA）。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "bibtex_entry": {"type": "string", "description": "BibTeX 格式的参考文献条目"},
                        "style": {"type": "string", "description": "引用格式：ieee/apa/gbt7714/mla", "default": "ieee"},
                        "target_lang": {"type": "string", "description": "目标语言：zh/en", "default": "zh"},
                    },
                    "required": ["bibtex_entry"],
                },
                handler=_make_handler("bibtex_entry", _tool_format_bibliography, ["bibtex_entry", "style", "target_lang"]),
            ),
            # ── 特殊元素处理工具 ──────────────────────────────────
            ToolSpec(
                name="analyze_markdown_elements",
                description="分析 Markdown 文本中的特殊元素（图片、表格、公式、引用），返回文档结构摘要。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Markdown 格式的文本内容"},
                    },
                    "required": ["text"],
                },
                handler=_make_handler("text", _tool_analyze_markdown_elements, ["text"]),
            ),
            ToolSpec(
                name="parse_table_structure",
                description="解析 Markdown 表格为结构化数据，方便修改表格内容。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "table_markdown": {"type": "string", "description": "Markdown 格式的表格文本"},
                    },
                    "required": ["table_markdown"],
                },
                handler=_make_handler("table_markdown", _tool_parse_table_structure, ["table_markdown"]),
            ),
            ToolSpec(
                name="generate_table_markdown",
                description="从结构化数据生成 Markdown 表格文本。用于修改或创建表格。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "表头列表",
                        },
                        "rows": {
                            "type": "array",
                            "items": {"type": "array", "items": {"type": "string"}},
                            "description": "数据行列表",
                        },
                    },
                    "required": ["headers", "rows"],
                },
                handler=_make_handler("headers", _tool_generate_table_markdown, ["headers", "rows"]),
            ),
            ToolSpec(
                name="format_latex_formula",
                description="格式化 LaTeX 数学公式，添加 $ 或 $$ 包裹。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "formula": {"type": "string", "description": "LaTeX 公式内容"},
                        "display": {
                            "type": "boolean",
                            "description": "是否为块级公式，默认 false（行内公式）",
                            "default": False,
                        },
                    },
                    "required": ["formula"],
                },
                handler=_make_handler("formula", _tool_format_latex_formula, ["formula", "display"]),
            ),
            ToolSpec(
                name="get_citation_context",
                description="获取文献引用在文档中的前后上下文，帮助理解引用用途。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "完整文档文本"},
                        "citation_key": {"type": "string", "description": "文献引用 key（如 smith2020）"},
                    },
                    "required": ["text", "citation_key"],
                },
                handler=_make_handler("text", _tool_get_citation_context, ["text", "citation_key"]),
            ),
            ToolSpec(
                name="analyze_image_with_vision",
                description="使用 Vision API 分析图片内容（需要云端 API Key）。识别图片中的文字、图表数据、关键发现等。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图片文件的绝对路径（不支持远程 URL）"},
                    },
                    "required": ["image_path"],
                },
                handler=_make_handler("image_path", _tool_analyze_image_with_vision, ["image_path"]),
            ),
            ToolSpec(
                name="analyze_chart_image",
                description="使用 Vision API 分析图表图片（柱状图、折线图、饼图等），提取数据趋势和关键发现。",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "图表图片文件的绝对路径"},
                    },
                    "required": ["image_path"],
                },
                handler=_make_handler("image_path", _tool_analyze_chart_image, ["image_path"]),
            ),
        ],
    )
    return server


def _make_handler(
    query_param: str,
    tool_fn: callable,
    param_names: list[str],
):
    """为工具函数生成 FastAPI handler。

    使用 Body(...) 提取任意 JSON body，无需动态 Pydantic model。
    返回 {"result": ...} 格式供 Agent 解析。
    """
    import asyncio

    async def handler(body: dict):
        filtered = {k: v for k, v in body.items() if k in param_names}
        result = await asyncio.to_thread(tool_fn, **filtered)
        return {"result": result}

    return handler


# ── 注册入口 ─────────────────────────────────────────────────────────

def register_builtin(registry: PluginRegistry) -> None:
    """将内置插件注册到全局注册表。"""
    server = create_builtin_server()
    registry.register(server)
    logger.info("内置插件已注册: %s (%d tools)", server.name, len(server.tools))
