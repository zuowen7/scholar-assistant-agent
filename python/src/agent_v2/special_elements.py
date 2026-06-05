"""Agent 特殊元素处理 — 图片、表格、公式、引用（V2 版本）。

从旧 src/agent/ 迁移，内部依赖改为 src/agent_v2/。
"""
from __future__ import annotations

from src.agent_v2._elements_parser import MarkdownElements
from src.agent_v2._elements_tools import (
    analyze_markdown_elements,
    extract_image_for_analysis,
    format_latex_formula,
    generate_table_markdown,
    generate_table_suggestion,
    get_citation_context,
    parse_table_structure,
)
from src.agent_v2._elements_vision import (
    analyze_chart_image,
    analyze_image_with_vision,
)
