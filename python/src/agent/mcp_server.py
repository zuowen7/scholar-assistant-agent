"""MCP Server — 将翻译管道和 Agent 工具暴露为 Model Context Protocol 端点。

本模块让 Claude/Cursor 等 MCP 客户端可以直接调用 Scholar Assistant 的核心能力:
- 翻译文本 (translate_text)
- 解析文档 (parse_document)
- 文档检索 (search_documents)
- arXiv 搜索 (crawl_arxiv)
- 参考文献格式化 (format_bibliography)

使用 stdio 传输（stdin/stdout），与 Claude Code / Cursor 等 IDE 无缝集成。
运行方式: python -m src.agent.mcp_server

接入指引（Claude Desktop / Cursor / Continue 配置）见 docs/mcp/README.md。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Refuse to run with the Windows Store Python
_windows_store_python = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "python.exe")
if sys.executable.lower() == _windows_store_python.lower():
    _conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if not _conda_prefix:
        print("错误: 请使用 Conda Python 运行 MCP 服务器（非 Windows Store Python）", file=sys.stderr)
        sys.exit(1)

from src.features import mcp as _MCP_AVAILABLE

if _MCP_AVAILABLE:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolResult,
        TextContent,
        Tool,
        ListToolsResult,
    )

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


def _build_ollama_client():
    """Create an OllamaClient from the MCP server's env configuration."""
    from src.translator.ollama_client import OllamaClient
    return OllamaClient(base_url=_ollama_base_url, model=_model)


def _build_cloud_client():
    """Create a CloudClient from the MCP server's env configuration."""
    from src.translator.cloud_client import CloudClient
    return CloudClient(
        base_url=_cloud_base_url,
        api_key=_cloud_api_key,
        model=_cloud_model or _model,
    )


def _build_translate_client():
    """Return the active translation client (Cloud if configured, else Ollama)."""
    if _cloud_api_key and _cloud_base_url:
        return _build_cloud_client()
    return _build_ollama_client()


# -- Special-element helpers (thin wrappers over src.agent.special_elements) --

def _call_special_element(fn, *args, **kwargs) -> str:
    """Call a special_elements function and format result as JSON when possible."""
    import json as _json
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, (dict, list)):
            return _json.dumps(result, ensure_ascii=False, indent=2)
        return str(result)
    except Exception as e:
        return f"执行失败: {e}"


# Replaced legacy standalone _xxx functions — the MCP server now delegates to
# tools.registry.ToolRegistry for core tools, and to src.agent.special_elements
# for markdown/table/citation/vision tools.  This eliminates the 16-function
# code duplication documented in internal review.


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

    # Build clients and tool registry (shared with AgentLoop, SecurityGate etc.)
    _init_special_handlers()
    tool_registry = _build_mcp_tool_registry()

    # Additional special-element tools not in the default registry
    _SPECIAL_TOOLS: list[Tool] = [
        Tool(name="analyze_markdown_elements",
             description="分析 Markdown 文本中的特殊元素（图片、表格、公式、引用），返回文档结构摘要。",
             inputSchema={"type": "object", "properties": {"text": {"type": "string", "description": "Markdown 格式的文本内容"}}, "required": ["text"]}),
        Tool(name="parse_table_structure",
             description="解析 Markdown 表格为结构化数据。",
             inputSchema={"type": "object", "properties": {"table_markdown": {"type": "string", "description": "Markdown 格式的表格文本"}}, "required": ["table_markdown"]}),
        Tool(name="generate_table_markdown",
             description="从结构化数据生成 Markdown 表格。",
             inputSchema={"type": "object", "properties": {"headers": {"type": "array", "items": {"type": "string"}, "description": "表头列表"}, "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}, "description": "数据行列表"}}, "required": ["headers", "rows"]}),
        Tool(name="format_latex_formula",
             description="格式化 LaTeX 数学公式，添加 $ 或 $$ 包裹。",
             inputSchema={"type": "object", "properties": {"formula": {"type": "string", "description": "LaTeX 公式内容"}, "display": {"type": "boolean", "description": "是否为块级公式", "default": False}}, "required": ["formula"]}),
        Tool(name="get_citation_context",
             description="获取文献引用在文档中的前后上下文。",
             inputSchema={"type": "object", "properties": {"text": {"type": "string", "description": "完整文档文本"}, "citation_key": {"type": "string", "description": "文献引用 key（如 smith2020）"}}, "required": ["text", "citation_key"]}),
        Tool(name="analyze_image_with_vision",
             description="使用 Vision API 分析图片内容（需要云端 API Key）。",
             inputSchema={"type": "object", "properties": {"image_path": {"type": "string", "description": "图片文件的绝对路径"}}, "required": ["image_path"]}),
        Tool(name="analyze_chart_image",
             description="使用 Vision API 分析图表图片，提取数据趋势和关键发现。",
             inputSchema={"type": "object", "properties": {"image_path": {"type": "string", "description": "图表图片文件的绝对路径"}}, "required": ["image_path"]}),
    ]

    # Flatten tool list: registry tools + special-element tools
    mcp_tools = _tools_to_mcp(tool_registry.list_tools()) + _SPECIAL_TOOLS

    # Create MCP server
    server = Server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        instructions="研墨 — 学术翻译与研究辅助 MCP 服务器",
    )

    @server.list_tools()
    async def list_tools() -> ListToolsResult:
        """返回所有可用工具。"""
        return ListToolsResult(tools=mcp_tools)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Execute a tool call. Core tools delegate to ToolRegistry; special-element
        tools call src.agent.special_elements directly."""
        logger.info("MCP 工具调用: %s", name)

        # Try registry first
        td = tool_registry.get(name)
        if td is not None:
            try:
                result = await asyncio.to_thread(td.fn, **arguments)
                text = str(result) if result is not None else ""
            except Exception as e:
                logger.exception("Registry tool %s failed", name)
                return CallToolResult(
                    content=[TextContent(type="text", text=f"工具执行错误 ({name}): {e}")],
                    isError=True,
                )
        else:
            # Try special-element tools
            handler = _SPECIAL_HANDLERS.get(name)
            if handler is None:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"未知工具: {name}")],
                    isError=True,
                )
            text = _call_special_element(handler)

        if len(text) > _TOOL_RESULT_MAX_LEN:
            text = text[:_TOOL_RESULT_MAX_LEN] + "\n...[结果已截断]"
        return CallToolResult(content=[TextContent(type="text", text=text)])

    # 启动 stdio 服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def _build_mcp_tool_registry() -> "ToolRegistry":
    """Build a ToolRegistry wired to the MCP server's env-configured clients."""
    from src.agent.tools.registry import create_default_registry

    cloud_client = _build_cloud_client() if (_cloud_api_key and _cloud_base_url) else None
    ollama_client = _build_ollama_client() if not cloud_client else None

    registry = create_default_registry(
        ollama_client=ollama_client,
        cloud_client=cloud_client,
        rag_store=None,
        ollama_base_url=_ollama_base_url,
        model=_model,
        cloud_base_url=_cloud_base_url,
        cloud_api_key=_cloud_api_key,
        cloud_model=_cloud_model,
        workspace_root=os.getcwd(),
    )
    return registry


def _tools_to_mcp(tool_defs: list) -> list[Tool]:
    """Convert ToolRegistry tool definitions to MCP Tool schemas."""
    result: list[Tool] = []
    for td in tool_defs:
        result.append(Tool(
            name=td.name,
            description=td.description,
            inputSchema=td.parameters or {"type": "object", "properties": {}},
        ))
    return result


# Special-element tools: these are thin wrappers over src.agent.special_elements
# and do not live in the default ToolRegistry (designed for in-app use only).
_SPECIAL_HANDLERS: dict[str, Any] = {}


def _init_special_handlers() -> None:
    """Populate _SPECIAL_HANDLERS with lazy imports to avoid import side effects
    when this module is not run as __main__."""
    if _SPECIAL_HANDLERS:
        return
    from src.agent.special_elements import (
        analyze_markdown_elements,
        parse_table_structure,
        generate_table_markdown,
        format_latex_formula,
        get_citation_context,
        analyze_image_with_vision,
        analyze_chart_image,
    )
    _SPECIAL_HANDLERS["analyze_markdown_elements"] = analyze_markdown_elements
    _SPECIAL_HANDLERS["parse_table_structure"] = parse_table_structure
    _SPECIAL_HANDLERS["generate_table_markdown"] = generate_table_markdown
    _SPECIAL_HANDLERS["format_latex_formula"] = format_latex_formula
    _SPECIAL_HANDLERS["get_citation_context"] = get_citation_context
    _SPECIAL_HANDLERS["analyze_image_with_vision"] = analyze_image_with_vision
    _SPECIAL_HANDLERS["analyze_chart_image"] = analyze_chart_image


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("MCP 服务器已关闭")
        sys.exit(0)