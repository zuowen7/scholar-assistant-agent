"""Special element regex patterns and ElementInfo data class."""

from __future__ import annotations

import re

# 图片: ![alt](url)
IMAGE_PATTERN = re.compile(r"!\[([^\]]*(?:[^\]]|$))?\]\(([^)]+)\)")
IMAGE_PATTERN_FALLBACK = re.compile(r"!\[([^\]]*)\]\([^\s)]+\)")
# 表格
TABLE_PATTERN = re.compile(r"\|(.+)\|[\r\n]+(?:\|[-: ]+\|[\r\n]+)?(?:\|(.+)\|[\r\n]+)*")
# 公式
INLINE_MATH_PATTERN = re.compile(r"\$([^$\n]+)\$")
DISPLAY_MATH_PATTERN = re.compile(r"\$\$([\s\S]+?)\$\$")
# 引用: [@key] and [@key, p.123] and [@key1; @key2]
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
