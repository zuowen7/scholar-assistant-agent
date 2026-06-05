"""Special element tool functions — table, formula, citation, analysis helpers."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from src.agent_v2._elements_parser import MarkdownElements


def analyze_markdown_elements(text: str) -> dict:
    """分析 Markdown 文本中的特殊元素。

    识别并返回文档中的图片、表格、公式、引用等特殊元素。

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
        {"ready": true/false, "base64": "...", "format": "png/jpg/...", "error": "..."}
    """
    path = Path(image_path)

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

    ext = path.suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return {
            "ready": False,
            "error": f"不支持的图片格式: {ext}",
        }

    try:
        with open(path, "rb") as f:
            data = f.read()
            b64 = base64.b64encode(data).decode("utf-8")

        return {
            "ready": True,
            "base64": b64,
            "format": ext[1:],
            "size_bytes": len(data),
        }
    except Exception as e:
        return {
            "ready": False,
            "error": f"读取图片失败: {e}",
        }


def parse_table_structure(table_markdown: str) -> dict:
    """解析 Markdown 表格结构。

    Args:
        table_markdown: Markdown 格式的表格文本。

    Returns:
        {"headers": [...], "rows": [...], "col_count": N, "row_count": M}
    """
    lines = table_markdown.strip().split("\n")
    if not lines:
        return {"headers": [], "rows": [], "col_count": 0, "row_count": 0}

    result: dict = {"headers": [], "rows": [], "col_count": 0, "row_count": 0}

    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    result["headers"] = header_cells
    result["col_count"] = len(header_cells)

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or re.match(r"^\|[-: |]+\|$", stripped):
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if cells:
            result["rows"].append(cells)
            result["row_count"] += 1

    return result


def generate_table_markdown(headers: list[str], rows: list[list[str]]) -> str:
    """生成 Markdown 表格。

    Args:
        headers: 表头列表。
        rows: 数据行列表。

    Returns:
        Markdown 格式的表格文本。
    """
    if not headers:
        return ""

    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    lines.append(sep)

    for row in rows:
        cells = row[:len(headers)]
        while len(cells) < len(headers):
            cells.append("")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def format_latex_formula(formula: str, display: bool = False) -> str:
    """格式化 LaTeX 公式。

    Args:
        formula: LaTeX 公式内容。
        display: 是否为块级公式。

    Returns:
        格式化后的公式。
    """
    formula = formula.strip()
    formula = formula.strip("$")

    if display:
        return f"$$\n{formula}\n$$"

    return f"${formula}$"


def generate_table_suggestion(
    headers: list[str],
    rows: list[list[str]],
    instruction: str,
) -> str:
    """根据用户的修改指令生成表格建议。

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
- 数据: {rows[:3]}"""

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
