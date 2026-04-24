"""Agent 特殊元素处理 — 图片、表格、公式、引用

本模块让 Agent 能够理解和处理 Markdown 中的特殊元素：
- 图片: 识别图片引用，理解图片内容
- 表格: 解析 Markdown 表格，生成/修改表格
- 公式: 解析 LaTeX 公式，生成/修改公式
- 引用: 识别文献引用，处理参考文献

这些工具将注册到 Agent 的 ToolRegistry 中。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# 特殊元素正则表达式
# 图片: ![alt](url) — alt 可以包含 ( ) 但不能包含未转义的 ]
IMAGE_PATTERN = re.compile(r"!\[([^\]]*(?:[^\]]|$))?\]\(([^)]+)\)")
# 备选图片格式（简化）: ![alt](url "title")
IMAGE_PATTERN_FALLBACK = re.compile(r"!\[([^\]]*)\]\([^\s)]+\)")

TABLE_PATTERN = re.compile(r"\|(.+)\|[\r\n]+(?:\|[-: ]+\|[\r\n]+)?(?:\|(.+)\|[\r\n]+)*")
INLINE_MATH_PATTERN = re.compile(r"\$([^$\n]+)\$")
DISPLAY_MATH_PATTERN = re.compile(r"\$\$([\s\S]+?)\$\$")
# 引用: 支持 [@key] 和 [@key, p.123] 和 [@key1; @key2]
CITATION_PATTERN = re.compile(r"\[@(\w+)(?:,\s*[^]]+)?\]")
CITATION_GROUP_PATTERN = re.compile(r"\[@([\w]+(?:[\s;]*@[\w]+)*)(?:,\s*[^]]+)?\]")


class ElementInfo:
    """特殊元素信息"""

    def __init__(
        self,
        element_type: str,
        raw: str,
        index: int,
        content: str = "",
        metadata: dict | None = None,
    ):
        self.type = element_type
        self.raw = raw
        self.index = index
        self.content = content
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "index": self.index,
            "content": self.content,
            "metadata": self.metadata,
        }


class MarkdownElements:
    """Markdown 特殊元素解析器"""

    def __init__(self):
        self.elements: list[ElementInfo] = []

    def parse(self, text: str) -> list[ElementInfo]:
        """解析 Markdown 文本中的所有特殊元素"""
        self.elements = []

        # 图片（使用多个模式尝试匹配）
        for match in IMAGE_PATTERN.finditer(text):
            alt = match.group(1) or ""
            if alt:  # 只添加有效的图片
                self.elements.append(ElementInfo(
                    element_type="image",
                    raw=match.group(0),
                    index=match.start(),
                    content=match.group(2),
                    metadata={"alt": alt},
                ))

        # 如果标准模式没匹配到图片，尝试备选模式
        existing_image_indices = {e.index for e in self.elements}
        for match in IMAGE_PATTERN_FALLBACK.finditer(text):
            if match.start() not in existing_image_indices:
                self.elements.append(ElementInfo(
                    element_type="image",
                    raw=match.group(0),
                    index=match.start(),
                    content=match.group(2) if len(match.groups()) > 1 else match.group(1),
                    metadata={"alt": match.group(1) if len(match.groups()) > 1 else ""},
                ))

        # 行内公式
        for match in INLINE_MATH_PATTERN.finditer(text):
            self.elements.append(ElementInfo(
                element_type="inline_math",
                raw=match.group(0),
                index=match.start(),
                content=match.group(1),
            ))

        # 块级公式
        for match in DISPLAY_MATH_PATTERN.finditer(text):
            self.elements.append(ElementInfo(
                element_type="display_math",
                raw=match.group(0),
                index=match.start(),
                content=match.group(1),
            ))

        # 表格
        for match in TABLE_PATTERN.finditer(text):
            self.elements.append(ElementInfo(
                element_type="table",
                raw=match.group(0),
                index=match.start(),
                content=match.group(0),
                metadata=self._parse_table_metadata(match.group(0)),
            ))

        # 文献引用
        for match in CITATION_PATTERN.finditer(text):
            self.elements.append(ElementInfo(
                element_type="citation",
                raw=match.group(0),
                index=match.start(),
                content=match.group(1),
            ))

        # 处理分号分隔的多引用 [@key1; @key2]
        # 这种格式不会被上面的模式匹配，需要单独处理
        existing_citation_raws = {e.raw for e in self.elements}
        for match in CITATION_GROUP_PATTERN.finditer(text):
            raw = match.group(0)
            if raw not in existing_citation_raws:
                # 提取分号分隔的多个 key
                all_keys_text = match.group(1)
                # 分割并清理每个 key
                keys = [k.strip() for k in all_keys_text.split(";")]
                for key in keys:
                    if key.startswith("@"):
                        key = key[1:]
                    if key and key not in existing_citation_raws:
                        self.elements.append(ElementInfo(
                            element_type="citation",
                            raw=f"[@{key}]",
                            index=match.start(),
                            content=key,
                        ))
                        existing_citation_raws.add(f"[@{key}]")

        # 按位置排序
        self.elements.sort(key=lambda e: e.index)
        return self.elements

    def _parse_table_metadata(self, table_text: str) -> dict:
        """解析表格元数据"""
        lines = table_text.strip().split("\n")
        if not lines:
            return {"rows": 0, "cols": 0}

        # 计算列数（第一行）
        header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
        col_count = len(header_cells)

        # 计算行数（排除分隔符）
        data_rows = sum(1 for line in lines if line.strip() and not re.match(r"^\|[-: ]+\|$", line.strip()))

        return {
            "rows": data_rows,
            "cols": col_count,
            "headers": header_cells,
        }

    def get_by_type(self, element_type: str) -> list[ElementInfo]:
        """按类型筛选元素"""
        return [e for e in self.elements if e.type == element_type]

    def get_summary(self) -> str:
        """生成元素摘要"""
        if not self.elements:
            return "未发现特殊元素（图片、表格、公式、引用）"

        lines = ["文档包含以下特殊元素:"]
        by_type: dict[str, list[ElementInfo]] = {}
        for e in self.elements:
            by_type.setdefault(e.type, []).append(e)

        for etype, items in by_type.items():
            type_names = {
                "image": "图片",
                "inline_math": "行内公式",
                "display_math": "块级公式",
                "table": "表格",
                "citation": "引用",
            }
            lines.append(f"- {type_names.get(etype, etype)}: {len(items)} 个")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent 工具函数
# ---------------------------------------------------------------------------


def analyze_markdown_elements(text: str) -> dict:
    """分析 Markdown 文本中的特殊元素。

    识别并返回文档中的图片、表格、公式、引用等特殊元素，
    帮助 Agent 理解文档结构。

    Args:
        text: Markdown 格式的文本内容。

    Returns:
        包含元素分析的字典:
        {
            "summary": "文档包含...",
            "elements": [
                {"type": "image", "index": 100, "content": "path/to/image.png", "metadata": {...}},
                ...
            ]
        }
    """
    parser = MarkdownElements()
    elements = parser.parse(text)

    return {
        "summary": parser.get_summary(),
        "elements": [e.to_dict() for e in elements],
        "count": len(elements),
    }


def extract_image_for_analysis(image_path: str) -> dict:
    """提取图片并准备分析。

    获取图片的 base64 编码和元数据，供 Vision API 分析。

    Args:
        image_path: 图片路径或 URL。

    Returns:
        {
            "ready": true/false,
            "base64": "...",
            "format": "png/jpg/gif/...",
            "error": "错误信息（如果有）"
        }
    """
    path = Path(image_path)

    # 处理 URL（相对路径或 http）
    if not path.exists():
        if image_path.startswith(("http://", "https://")):
            return {
                "ready": False,
                "error": "暂不支持远程图片 URL，请提供本地文件路径",
            }
        return {
            "ready": False,
            "error": f"图片文件不存在: {image_path}",
        }

    # 检查格式
    ext = path.suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return {
            "ready": False,
            "error": f"不支持的图片格式: {ext}",
        }

    # 读取并编码
    try:
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")

        return {
            "ready": True,
            "base64": b64,
            "format": ext[1:],  # 去掉点
            "size_bytes": len(data),
        }
    except Exception as e:
        return {
            "ready": False,
            "error": f"读取图片失败: {e}",
        }


def parse_table_structure(table_markdown: str) -> dict:
    """解析 Markdown 表格结构。

    将 Markdown 表格转换为结构化数据，方便修改。

    Args:
        table_markdown: Markdown 格式的表格文本。

    Returns:
        {
            "headers": ["列1", "列2", ...],
            "rows": [["行1内容", ...], ...],
            "col_count": 3,
            "row_count": 5
        }
    """
    lines = table_markdown.strip().split("\n")
    if not lines:
        return {"headers": [], "rows": [], "col_count": 0, "row_count": 0}

    result = {"headers": [], "rows": [], "col_count": 0, "row_count": 0}

    # 解析表头
    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    result["headers"] = header_cells
    result["col_count"] = len(header_cells)

    # 解析数据行
    for line in lines[1:]:
        stripped = line.strip()
        # 分隔符行: | --- | --- | 或 |:---|:---| 等
        if not stripped or re.match(r"^\|[-: |]+\|$", stripped):
            continue  # 跳过分隔符
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if cells:
            result["rows"].append(cells)
            result["row_count"] += 1

    return result


def generate_table_markdown(headers: list[str], rows: list[list[str]]) -> str:
    """生成 Markdown 表格。

    从结构化数据生成 Markdown 表格文本。

    Args:
        headers: 表头列表。
        rows: 数据行列表。

    Returns:
        Markdown 格式的表格文本。
    """
    if not headers:
        return ""

    lines = []

    # 表头
    lines.append("| " + " | ".join(headers) + " |")

    # 分隔符
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines.append(sep)

    # 数据行
    for row in rows:
        cells = row[:len(headers)]  # 截断超长行
        while len(cells) < len(headers):
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def format_latex_formula(formula: str, display: bool = False) -> str:
    """格式化 LaTeX 公式。

    清理和标准化 LaTeX 公式格式。

    Args:
        formula: LaTeX 公式内容。
        display: 是否为块级公式。

    Returns:
        格式化后的公式。
    """
    formula = formula.strip()

    # 移除已有的 $ 包裹
    formula = formula.strip("$")

    # 块级公式用 $$ 包裹
    if display:
        return f"$$\n{formula}\n$$"

    # 行内公式用 $ 包裹
    return f"${formula}$"


def generate_table_suggestion(
    headers: list[str],
    rows: list[list[str]],
    instruction: str,
) -> str:
    """根据用户的修改指令生成表格建议。

    使用 LLM 理解用户的表格修改需求，生成新的表格内容。
    此函数生成提示信息，实际修改由 Agent 调用 generate_table_markdown 完成。

    Args:
        headers: 当前表格的表头。
        rows: 当前表格的数据行。
        instruction: 用户的修改指令。

    Returns:
        包含修改建议的提示信息。
    """
    table_info = f"""当前表格:
- 表头: {headers}
- 数据行数: {len(rows)}
- 数据: {rows[:3]}"""  # 只展示前3行

    return f"""{table_info}

用户修改指令: {instruction}

请根据上述指令，生成新的表格内容。返回格式:
1. 新的表头（如果有变化）
2. 新的数据行

示例响应:
```
新的表头: [列1, 列2, 列3]
新的数据:
[行1数据]
[行2数据]
...
```"""


def get_citation_context(text: str, citation_key: str) -> str:
    """获取引用在文档中的上下文。

    查找特定引用的前后文，帮助理解引用用途。

    Args:
        text: 完整文档文本。
        citation_key: 文献引用 key（如 "smith2020"）。

    Returns:
        包含引用的上下文段落。
    """
    pattern = rf"\[@{re.escape(citation_key)}(?:,\s*[^]]+)?\]"
    match = re.search(pattern, text)

    if not match:
        return f"未在文档中找到引用 [@{citation_key}]"

    start = max(0, match.start() - 200)
    end = min(len(text), match.end() + 200)

    context = text[start:end]
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."

    return context


def build_special_elements_tools() -> list:
    """构建特殊元素相关的工具定义。

    Returns:
        ToolDefinition 列表。
    """
    from src.agent.tools import ToolDefinition, _extract_schema_from_function

    tools = []

    # analyze_markdown_elements
    tools.append(ToolDefinition(
        name="analyze_markdown_elements",
        description="分析 Markdown 文本中的特殊元素（图片、表格、公式、引用），返回文档结构摘要。",
        parameters=_extract_schema_from_function(analyze_markdown_elements),
        fn=analyze_markdown_elements,
    ))

    # extract_image_for_analysis
    tools.append(ToolDefinition(
        name="extract_image_for_analysis",
        description="提取图片的 base64 编码和元数据，为 Vision API 分析做准备。只支持本地图片文件。",
        parameters=_extract_schema_from_function(extract_image_for_analysis),
        fn=extract_image_for_analysis,
    ))

    # parse_table_structure
    tools.append(ToolDefinition(
        name="parse_table_structure",
        description="解析 Markdown 表格为结构化数据，方便修改表格内容。",
        parameters=_extract_schema_from_function(parse_table_structure),
        fn=parse_table_structure,
    ))

    # generate_table_markdown
    tools.append(ToolDefinition(
        name="generate_table_markdown",
        description="从结构化数据生成 Markdown 表格文本。用于修改或创建表格。",
        parameters=_extract_schema_from_function(generate_table_markdown),
        fn=generate_table_markdown,
    ))

    # format_latex_formula
    tools.append(ToolDefinition(
        name="format_latex_formula",
        description="格式化 LaTeX 数学公式，添加 $ 或 $$ 包裹。",
        parameters=_extract_schema_from_function(format_latex_formula),
        fn=format_latex_formula,
    ))

    # get_citation_context
    tools.append(ToolDefinition(
        name="get_citation_context",
        description="获取文献引用在文档中的前后上下文，帮助理解引用用途。",
        parameters=_extract_schema_from_function(get_citation_context),
        fn=get_citation_context,
    ))

    # analyze_image_with_vision
    tools.append(ToolDefinition(
        name="analyze_image_with_vision",
        description="使用 Vision API 分析图片内容（需要云端 API Key）。识别图片中的文字、图表数据、关键发现等。",
        parameters=_extract_schema_from_function(analyze_image_with_vision),
        fn=analyze_image_with_vision,
    ))

    # analyze_chart_image
    tools.append(ToolDefinition(
        name="analyze_chart_image",
        description="使用 Vision API 分析图表图片（柱状图、折线图、饼图等），提取数据趋势和关键发现。",
        parameters=_extract_schema_from_function(analyze_chart_image),
        fn=analyze_chart_image,
    ))

    return tools


# ---------------------------------------------------------------------------
# Vision 集成 — Agent 理解图片内容
# ---------------------------------------------------------------------------


def _get_vision_client():
    """获取 Vision 客户端实例"""
    try:
        from src.mcp.vision_client import VisionClient
        return VisionClient()
    except ImportError:
        return None


async def _analyze_image_async(image_path: str, analysis_type: str = "general") -> dict:
    """异步分析图片"""
    client = _get_vision_client()
    if client is None:
        return {
            "success": False,
            "error": "Vision 客户端不可用，请确保已安装必要的依赖",
        }

    try:
        result = await client.analyze_image(image_path, analysis_type=analysis_type)
        return {
            "success": True,
            "analysis_type": analysis_type,
            "text": result.text,
            "chart_type": result.chart_type,
            "chart_description": result.chart_description,
            "table_data": result.table_data,
            "key_findings": result.key_findings,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def analyze_image_with_vision(image_path: str) -> str:
    """使用 Vision API 分析图片内容。

    识别图片中的文字、图表数据、关键发现等，帮助 Agent 理解图片。
    需要配置云端 API Key。

    Args:
        image_path: 图片文件的绝对路径（不支持远程 URL）。

    Returns:
        图片分析结果，包含识别的文字、图表类型、关键发现等。
    """
    result = asyncio.run(_analyze_image_async(image_path, "general"))

    if not result.get("success"):
        return f"图片分析失败: {result.get('error', '未知错误')}"

    lines = ["【图片分析结果】"]
    if result.get("text"):
        lines.append(f"\n识别的文字内容:\n{result['text']}")
    if result.get("chart_type"):
        lines.append(f"\n图表类型: {result['chart_type']}")
        if result.get("chart_description"):
            lines.append(f"图表描述: {result['chart_description']}")
    if result.get("key_findings"):
        lines.append("\n关键发现:")
        for finding in result["key_findings"][:5]:  # 最多5条
            lines.append(f"- {finding}")

    return "\n".join(lines)


def analyze_chart_image(image_path: str) -> str:
    """使用 Vision API 分析图表图片。

    专门分析柱状图、折线图、饼图等数据图表，提取数据趋势和关键发现。
    需要配置云端 API Key。

    Args:
        image_path: 图表图片文件的绝对路径。

    Returns:
        图表分析结果，包含图表类型、数据趋势、关键数值等。
    """
    result = asyncio.run(_analyze_image_async(image_path, "chart"))

    if not result.get("success"):
        return f"图表分析失败: {result.get('error', '未知错误')}"

    lines = ["【图表分析结果】"]

    chart_type = result.get("chart_type", "未知")
    type_names = {
        "bar": "柱状图",
        "line": "折线图",
        "pie": "饼图",
        "scatter": "散点图",
        "table": "表格",
        "flowchart": "流程图",
    }
    lines.append(f"\n图表类型: {type_names.get(chart_type, chart_type)}")

    if result.get("chart_description"):
        lines.append(f"\n详细描述:\n{result['chart_description']}")

    if result.get("table_data"):
        lines.append("\n提取的表格数据:")
        for row in result["table_data"][:10]:  # 最多10行
            lines.append(" | ".join(str(c) for c in row))

    if result.get("key_findings"):
        lines.append("\n关键发现:")
        for finding in result["key_findings"][:5]:
            lines.append(f"- {finding}")

    return "\n".join(lines)
