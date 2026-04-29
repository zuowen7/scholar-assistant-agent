"""Markdown special elements parser."""

from __future__ import annotations

import re

from src.agent._elements_types import (
    CITATION_GROUP_PATTERN,
    CITATION_PATTERN,
    DISPLAY_MATH_PATTERN,
    IMAGE_PATTERN,
    IMAGE_PATTERN_FALLBACK,
    INLINE_MATH_PATTERN,
    TABLE_PATTERN,
    ElementInfo,
)


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
            if alt:
                self.elements.append(ElementInfo(
                    element_type="image",
                    raw=match.group(0),
                    index=match.start(),
                    content=match.group(2),
                    metadata={"alt": alt},
                ))

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
        existing_citation_raws = {e.raw for e in self.elements}
        for match in CITATION_GROUP_PATTERN.finditer(text):
            raw = match.group(0)
            if raw not in existing_citation_raws:
                all_keys_text = match.group(1)
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

        self.elements.sort(key=lambda e: e.index)
        return self.elements

    def _parse_table_metadata(self, table_text: str) -> dict:
        """解析表格元数据"""
        lines = table_text.strip().split("\n")
        if not lines:
            return {"rows": 0, "cols": 0}

        header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
        col_count = len(header_cells)
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
