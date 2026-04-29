"""Agent 特殊元素处理 — 图片、表格、公式、引用

本模块让 Agent 能够理解和处理 Markdown 中的特殊元素：
- 图片: 识别图片引用，理解图片内容
- 表格: 解析 Markdown 表格，生成/修改表格
- 公式: 解析 LaTeX 公式，生成/修改公式
- 引用: 识别文献引用，处理参考文献

这些工具将注册到 Agent 的 ToolRegistry 中。

Internal structure (split since v0.3):
- _elements_types.py   — regex patterns, ElementInfo data class
- _elements_parser.py  — MarkdownElements parser class
- _elements_tools.py   — standalone tool functions (table, formula, citation, analysis)
- _elements_vision.py  — Vision API integration (image/chart analysis)
"""

from __future__ import annotations

# Re-export everything for backward compatibility.
from src.agent._elements_parser import MarkdownElements
from src.agent._elements_tools import (
    analyze_markdown_elements,
    extract_image_for_analysis,
    format_latex_formula,
    generate_table_markdown,
    generate_table_suggestion,
    get_citation_context,
    parse_table_structure,
)
from src.agent._elements_types import ElementInfo
from src.agent._elements_vision import analyze_chart_image, analyze_image_with_vision

__all__ = [
    "ElementInfo",
    "MarkdownElements",
    "analyze_chart_image",
    "analyze_image_with_vision",
    "analyze_markdown_elements",
    "build_special_elements_tools",
    "extract_image_for_analysis",
    "format_latex_formula",
    "generate_table_markdown",
    "generate_table_suggestion",
    "get_citation_context",
    "parse_table_structure",
]


def build_special_elements_tools() -> list:
    """构建特殊元素相关的工具定义。

    Returns:
        ToolDefinition 列表。
    """
    from src.agent.tools import ToolDefinition, _extract_schema_from_function

    tools = []

    tools.append(ToolDefinition(
        name="analyze_markdown_elements",
        description="分析 Markdown 文本中的特殊元素（图片、表格、公式、引用），返回文档结构摘要。",
        parameters=_extract_schema_from_function(analyze_markdown_elements),
        fn=analyze_markdown_elements,
    ))

    tools.append(ToolDefinition(
        name="extract_image_for_analysis",
        description="提取图片的 base64 编码和元数据，为 Vision API 分析做准备。只支持本地图片文件。",
        parameters=_extract_schema_from_function(extract_image_for_analysis),
        fn=extract_image_for_analysis,
    ))

    tools.append(ToolDefinition(
        name="parse_table_structure",
        description="解析 Markdown 表格为结构化数据，方便修改表格内容。",
        parameters=_extract_schema_from_function(parse_table_structure),
        fn=parse_table_structure,
    ))

    tools.append(ToolDefinition(
        name="generate_table_markdown",
        description="从结构化数据生成 Markdown 表格文本。用于修改或创建表格。",
        parameters=_extract_schema_from_function(generate_table_markdown),
        fn=generate_table_markdown,
    ))

    tools.append(ToolDefinition(
        name="format_latex_formula",
        description="格式化 LaTeX 数学公式，添加 $ 或 $$ 包裹。",
        parameters=_extract_schema_from_function(format_latex_formula),
        fn=format_latex_formula,
    ))

    tools.append(ToolDefinition(
        name="get_citation_context",
        description="获取文献引用在文档中的前后上下文，帮助理解引用用途。",
        parameters=_extract_schema_from_function(get_citation_context),
        fn=get_citation_context,
    ))

    tools.append(ToolDefinition(
        name="analyze_image_with_vision",
        description="使用 Vision API 分析图片内容（需要云端 API Key）。识别图片中的文字、图表数据、关键发现等。",
        parameters=_extract_schema_from_function(analyze_image_with_vision),
        fn=analyze_image_with_vision,
    ))

    tools.append(ToolDefinition(
        name="analyze_chart_image",
        description="使用 Vision API 分析图表图片（柱状图、折线图、饼图等），提取数据趋势和关键发现。",
        parameters=_extract_schema_from_function(analyze_chart_image),
        fn=analyze_chart_image,
    ))

    return tools
