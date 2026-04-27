"""MCP Server — 将翻译管道和 Agent 工具暴露为 Model Context Protocol 端点。

本模块让 Claude/Cursor 等 MCP 客户端可以直接调用 Scholar Assistant 的核心能力:
- 翻译文本 (translate_text)
- 解析文档 (parse_document)
- 文档检索 (search_documents)
- arXiv 搜索 (crawl_arxiv)
- 文本润色 (polish_text)
- 文本摘要 (summarize_text)
- 大纲生成 (generate_outline)
- 段落扩写 (expand_section)

使用 stdio 传输（stdin/stdout），与 Claude Code / Cursor 等 IDE 无缝集成。
运行方式: python -m src.agent.mcp_server

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
MCP 协议暴露与工具调度机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

# Refuse to run with the Windows Store Python
_windows_store_python = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "python.exe")
if sys.executable.lower() == _windows_store_python.lower():
    _conda_python = os.path.join(os.environ.get("CONDA_PREFIX", "D:\\env\\anaconda"), "python.exe")
    if os.path.exists(_conda_python):
        print(f"错误: 请使用 Anaconda Python 运行此模块: {_conda_python}", file=sys.stderr)
        sys.exit(1)

# Runtime check for MCP availability
_mcp_runtime_available = False
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolResult,
        TextContent,
        Tool,
        ListToolsResult,
    )
    _mcp_runtime_available = True
except ImportError:
    pass

_MCP_AVAILABLE = _mcp_runtime_available

logger = logging.getLogger(__name__)

# 工具执行结果最大字符数
_TOOL_RESULT_MAX_LEN = 4000

# MCP 服务器名称
SERVER_NAME = "scholar-assistant"
SERVER_VERSION = "0.3.1"

# 全局配置
_ollama_base_url = "http://localhost:11434"
_model = "qwen3:8b"
_cloud_base_url = ""
_cloud_api_key = ""
_cloud_model = ""


def _build_llm() -> "LLMClient":
    from src.agent.llm_client import LLMClient
    return LLMClient(
        ollama_base_url=_ollama_base_url,
        model=_model,
        cloud_base_url=_cloud_base_url,
        cloud_api_key=_cloud_api_key,
        cloud_model=_cloud_model,
        temperature=0.3,
        num_predict=2048,
    )


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _translate_text(text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
    """翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。"""
    from src.translator.ollama_client import OllamaClient
    from src.translator.cloud_client import CloudClient
    if _cloud_api_key and _cloud_base_url:
        client = CloudClient(
            base_url=_cloud_base_url,
            api_key=_cloud_api_key,
            model=_cloud_model or _model,
        )
    else:
        client = OllamaClient(
            base_url=_ollama_base_url,
            model=_model,
        )
    try:
        result = client.translate(text)
        return result.translated if hasattr(result, "translated") else str(result)
    finally:
        if hasattr(client, "close"):
            client.close()


def _parse_document(file_path: str) -> str:
    """解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。"""
    from src.parser import extract_document
    try:
        doc = extract_document(file_path)
        text = doc.full_text
        if len(text) > _TOOL_RESULT_MAX_LEN:
            text = text[:_TOOL_RESULT_MAX_LEN] + "\n...[内容已截断]"
        return text
    except Exception as e:
        return f"文档解析失败: {e}"


def _search_documents(query: str, top_k: int = 5) -> str:
    """在已入库的文档中检索与查询相关的段落。"""
    try:
        from src.agent.rag import RAGStore
        rag_store = RAGStore()
        results = rag_store.retrieve_context(query, top_k=top_k)
        if not results:
            return "未找到相关文档内容。请先使用 parse_document 解析文档并入库。"
        parts: list[str] = []
        for i, r in enumerate(results):
            parts.append(f"[片段 {i + 1}] (相似度: {1 - r.get('distance', 0):.2f})\n{r['text']}")
        return "\n\n---\n\n".join(parts)
    except Exception as e:
        return f"文档检索失败: {e}"


def _crawl_arxiv(query: str, max_results: int = 5) -> str:
    """搜索 arXiv 学术论文，返回标题、作者和摘要。"""
    import httpx
    try:
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = None
        with httpx.Client(timeout=30.0) as client:
            for attempt in range(3):
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            else:
                if resp is not None:
                    resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return "未找到相关论文。"

        results: list[str] = []
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


def _call_llm(prompt: str) -> str:
    """同步调用 LLM。"""
    return _build_llm().call_simple_sync(prompt)


def _polish_text(text: str, style: str = "academic") -> str:
    """润色学术文本，改善表达和语法。"""
    style_hints = {
        "academic": "使用严谨的学术语言，确保逻辑清晰、用词精准",
        "formal": "使用正式的书面语，避免口语化表达",
        "concise": "精简冗余表达，保留核心信息，使文字更加凝练",
    }
    hint = style_hints.get(style, style_hints["academic"])
    prompt = f"请润色以下文本。要求：{hint}。只输出润色后的文本，不要解释。\n\n{text}"
    return _call_llm(prompt)


def _summarize_text(text: str, max_sentences: int = 5) -> str:
    """生成文本的精简摘要。"""
    prompt = f"请用中文为以下文本生成摘要，不超过 {max_sentences} 个句子。提取核心论点和关键信息。\n\n{text}"
    return _call_llm(prompt)


def _generate_outline(topic: str, sections: int = 5) -> str:
    """生成学术论文或报告的结构化大纲。"""
    prompt = (
        f"请为主题「{topic}」生成一个学术论文大纲，包含 {sections} 个主要章节。"
        "每个章节下给出 2-3 个子节。使用 Markdown 格式输出。"
    )
    return _call_llm(prompt)


def _expand_section(section: str, context: str = "") -> str:
    """扩写论文段落，补充细节和论据。"""
    ctx_part = f"\n\n参考上下文:\n{context}" if context else ""
    prompt = (
        f"请将以下段落扩写为 200-400 字的完整论述，补充细节、论据和例子。"
        "保持学术风格，逻辑连贯。只输出扩写后的文本。\n\n"
        f"原文: {section}{ctx_part}"
    )
    return _call_llm(prompt)


def _format_bibliography(bibtex_entry: str, style: str = "ieee", target_lang: str = "zh") -> str:
    """将 BibTeX 条目格式化为指定引用格式。"""
    styles = ["ieee", "apa", "gbt7714", "mla"]
    if style not in styles:
        return f"不支持的引用格式: {style}。支持的格式: {', '.join(styles)}"
    prompt = f"""请将以下 BibTeX 条目格式化为 {style.upper()} 引用格式的文本。

要求：
1. 只输出格式化后的参考文献，不要任何解释或说明
2. 严格按照 {style.upper()} 格式规范
3. 目标语言：{"中文" if target_lang == "zh" else "英文"}
4. 译名使用学界公认译法

BibTeX 条目：
{bibtex_entry}

格式化后的引用："""
    return _call_llm(prompt)


# ---------------------------------------------------------------------------
# 特殊元素处理函数
# ---------------------------------------------------------------------------

def _analyze_markdown_elements(text: str) -> str:
    """分析 Markdown 文本中的特殊元素。"""
    from src.agent.special_elements import analyze_markdown_elements as analyze
    import json
    result = analyze(text)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _parse_table_structure(table_markdown: str) -> str:
    """解析 Markdown 表格结构。"""
    from src.agent.special_elements import parse_table_structure as parse_tbl
    import json
    result = parse_tbl(table_markdown)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _generate_table_markdown_handler(headers: list, rows: list) -> str:
    """从结构化数据生成 Markdown 表格。"""
    from src.agent.special_elements import generate_table_markdown as gen_tbl
    return gen_tbl(headers, rows)


def _format_latex_formula_handler(formula: str, display: bool = False) -> str:
    """格式化 LaTeX 公式。"""
    from src.agent.special_elements import format_latex_formula as fmt
    return fmt(formula, display=display)


def _get_citation_context_handler(text: str, citation_key: str) -> str:
    """获取文献引用的上下文。"""
    from src.agent.special_elements import get_citation_context as get_ctx
    return get_ctx(text, citation_key)


def _analyze_image_with_vision_handler(image_path: str) -> str:
    """使用 Vision API 分析图片内容。"""
    from src.agent.special_elements import analyze_image_with_vision as analyze_img
    return analyze_img(image_path)


def _analyze_chart_image_handler(image_path: str) -> str:
    """使用 Vision API 分析图表图片。"""
    from src.agent.special_elements import analyze_chart_image as analyze_ch
    return analyze_ch(image_path)


# ---------------------------------------------------------------------------
# MCP 工具定义
# ---------------------------------------------------------------------------

MCP_TOOLS: list[Tool] = [
    Tool(
        name="translate_text",
        description="翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待翻译的文本内容"},
                "source_lang": {"type": "string", "description": "源语言代码，默认 en（英文）", "default": "en"},
                "target_lang": {"type": "string", "description": "目标语言代码，默认 zh（中文）", "default": "zh"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="parse_document",
        description="解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文档文件的绝对路径"},
            },
            "required": ["file_path"],
        },
    ),
    Tool(
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
    ),
    Tool(
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
    ),
    Tool(
        name="polish_text",
        description="润色学术文本，改善表达和语法。",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待润色的文本内容"},
                "style": {"type": "string", "description": "润色风格，可选 academic/formal/concise，默认 academic", "default": "academic"},
            },
            "required": ["text"],
        },
    ),
    Tool(
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
    ),
    Tool(
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
    ),
    Tool(
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
    ),
    Tool(
        name="format_bibliography",
        description="将 BibTeX 条目格式化为指定引用格式（IEEE/APA/GB/T 7714/MLA）。",
        inputSchema={
            "type": "object",
            "properties": {
                "bibtex_entry": {"type": "string", "description": "BibTeX 格式的参考文献条目"},
                "style": {
                    "type": "string",
                    "description": "引用格式：ieee / apa / gbt7714 / mla",
                    "default": "ieee",
                },
                "target_lang": {
                    "type": "string",
                    "description": "目标语言：zh（中文）/ en（英文）",
                    "default": "zh",
                },
            },
            "required": ["bibtex_entry"],
        },
    ),
    # === 特殊元素处理工具 ===
    Tool(
        name="analyze_markdown_elements",
        description="分析 Markdown 文本中的特殊元素（图片、表格、公式、引用），返回文档结构摘要。",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Markdown 格式的文本内容"},
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="parse_table_structure",
        description="解析 Markdown 表格为结构化数据，方便修改表格内容。",
        inputSchema={
            "type": "object",
            "properties": {
                "table_markdown": {"type": "string", "description": "Markdown 格式的表格文本"},
            },
            "required": ["table_markdown"],
        },
    ),
    Tool(
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
    ),
    Tool(
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
    ),
    Tool(
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
    ),
    Tool(
        name="analyze_image_with_vision",
        description="使用 Vision API 分析图片内容（需要云端 API Key）。识别图片中的文字、图表数据、关键发现等。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "图片文件的绝对路径（不支持远程 URL）"},
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="analyze_chart_image",
        description="使用 Vision API 分析图表图片（柱状图、折线图、饼图等），提取数据趋势和关键发现。",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "图表图片文件的绝对路径"},
            },
            "required": ["image_path"],
        },
    ),
]


# ---------------------------------------------------------------------------
# MCP 服务器入口
# ---------------------------------------------------------------------------

async def main():
    """启动 MCP stdio 服务器。"""
    if not _MCP_AVAILABLE:
        print("错误: mcp 包未安装。请运行: pip install mcp", file=sys.stderr)
        sys.exit(1)

    # 从环境变量读取配置
    global _ollama_base_url, _model, _cloud_base_url, _cloud_api_key, _cloud_model
    _ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    _model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    _cloud_base_url = os.environ.get("CLOUD_BASE_URL", "")
    _cloud_api_key = os.environ.get("CLOUD_API_KEY", "")
    _cloud_model = os.environ.get("CLOUD_MODEL", "")

    logger.info("启动 Scholar Assistant MCP Server v%s", SERVER_VERSION)
    logger.info("Ollama: %s / %s", _ollama_base_url, _model)
    if _cloud_api_key:
        logger.info("Cloud API: %s / %s", _cloud_base_url, _cloud_model)

    # 创建 MCP 服务器
    server = Server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions="Scholar Assistant — 学术翻译与研究辅助 MCP 服务器",
    )

    @server.list_tools()
    async def list_tools() -> ListToolsResult:
        """返回所有可用工具。"""
        return ListToolsResult(tools=MCP_TOOLS)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        """执行工具调用。"""
        logger.info("MCP 工具调用: %s", name)

        handlers: dict[str, Any] = {
            "translate_text": lambda args: _translate_text(
                text=args["text"],
                source_lang=args.get("source_lang", "en"),
                target_lang=args.get("target_lang", "zh"),
            ),
            "parse_document": lambda args: _parse_document(file_path=args["file_path"]),
            "search_documents": lambda args: _search_documents(
                query=args["query"],
                top_k=args.get("top_k", 5),
            ),
            "crawl_arxiv": lambda args: _crawl_arxiv(
                query=args["query"],
                max_results=args.get("max_results", 5),
            ),
            "polish_text": lambda args: _polish_text(
                text=args["text"],
                style=args.get("style", "academic"),
            ),
            "summarize_text": lambda args: _summarize_text(
                text=args["text"],
                max_sentences=args.get("max_sentences", 5),
            ),
            "generate_outline": lambda args: _generate_outline(
                topic=args["topic"],
                sections=args.get("sections", 5),
            ),
            "expand_section": lambda args: _expand_section(
                section=args["section"],
                context=args.get("context", ""),
            ),
            "format_bibliography": lambda args: _format_bibliography(
                bibtex_entry=args["bibtex_entry"],
                style=args.get("style", "ieee"),
                target_lang=args.get("target_lang", "zh"),
            ),
            # === 特殊元素处理工具 ===
            "analyze_markdown_elements": lambda args: _analyze_markdown_elements(args["text"]),
            "parse_table_structure": lambda args: _parse_table_structure(args["table_markdown"]),
            "generate_table_markdown": lambda args: _generate_table_markdown_handler(
                headers=args["headers"],
                rows=args["rows"],
            ),
            "format_latex_formula": lambda args: _format_latex_formula_handler(
                formula=args["formula"],
                display=args.get("display", False),
            ),
            "get_citation_context": lambda args: _get_citation_context_handler(
                text=args["text"],
                citation_key=args["citation_key"],
            ),
            "analyze_image_with_vision": lambda args: _analyze_image_with_vision_handler(
                image_path=args["image_path"],
            ),
            "analyze_chart_image": lambda args: _analyze_chart_image_handler(
                image_path=args["image_path"],
            ),
        }

        handler = handlers.get(name)
        if handler is None:
            return CallToolResult(
                content=[TextContent(type="text", text=f"未知工具: {name}")],
                isError=True,
            )

        try:
            result = await asyncio.to_thread(handler, arguments)
            text = str(result) if result is not None else ""
            if len(text) > _TOOL_RESULT_MAX_LEN:
                text = text[:_TOOL_RESULT_MAX_LEN] + "\n...[结果已截断]"
            return CallToolResult(content=[TextContent(type="text", text=text)])
        except Exception as e:
            logger.exception("工具 %s 执行失败", name)
            return CallToolResult(
                content=[TextContent(type="text", text=f"工具执行错误 ({name}): {e}")],
                isError=True,
            )

    # 启动 stdio 服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP 服务器已关闭")
        sys.exit(0)