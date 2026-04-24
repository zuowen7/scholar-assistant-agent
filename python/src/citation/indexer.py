"""文献索引服务 — 处理 Markdown 中的引用文献

功能：
1. 提取文档中的 [@key] 引用
2. 按出现顺序建立索引
3. 生成带编号的文献列表
4. 支持多种引用格式：[@key], [@key, p.123], [key] 等
"""

from __future__ import annotations

import re
from typing import Literal


class CitationEntry:
    """单条文献条目"""

    def __init__(
        self,
        key: str,
        number: int,
        raw_citation: str = "",
        page_ref: str = "",
    ):
        self.key = key
        self.number = number
        self.raw_citation = raw_citation
        self.page_ref = page_ref

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "number": self.number,
            "raw_citation": self.raw_citation,
            "page_ref": self.page_ref,
        }


class CitationIndexer:
    """文献引用索引器"""

    # 引用格式的正则表达式
    # 支持: [@key], [@key, p.123], [@key, pp. 123-125]
    CITATION_PATTERN = re.compile(
        r"""
        \[@(\w+)           # [@key
        (?:,\s*            # 可选的逗号和空格
            (p\.\s*\d+(?:-\d+)?)  # 页码: p.123 或 pp.123-125
        )?                  # 页码是可选的
        \]                 # ]
        """,
        re.VERBOSE,
    )

    # 备选格式: [key] 或 [key, p.123]
    ALT_CITATION_PATTERN = re.compile(
        r"""
        \[(\w+)             # [key
        (?:,\s*
            (p\.\s*\d+(?:-\d+)?)
        )?
        \]
        """,
        re.VERBOSE,
    )

    def __init__(self):
        self.citations: list[CitationEntry] = []
        self.bibliography: dict[str, dict] = {}

    def extract_citations(self, text: str) -> list[str]:
        """从文本中提取所有引用 key

        Returns:
            按出现顺序排列的 key 列表，可能有重复
        """
        keys: list[str] = []

        # 主格式 [@key]
        for match in self.CITATION_PATTERN.finditer(text):
            keys.append(match.group(1))

        # 备选格式 [key]
        for match in self.ALT_CITATION_PATTERN.finditer(text):
            key = match.group(1)
            # 排除已匹配的 [@key] 格式
            full_match = match.group(0)
            if not full_match.startswith("[@"):
                keys.append(key)

        return keys

    def build_index(self, text: str) -> dict[str, int]:
        """建立引用索引

        Returns:
            {key: number} 映射，按出现顺序编号
        """
        keys = self.extract_citations(text)
        seen: dict[str, int] = {}
        index: dict[str, int] = {}

        for key in keys:
            if key not in seen:
                seen[key] = len(seen) + 1
            index[key] = seen[key]

        return index

    def set_bibliography(self, bibtex_entries: list[dict]) -> None:
        """设置参考文献库

        Args:
            bibtex_entries: BibTeX 格式的文献条目列表
                例如: [{"key": "smith2020", "type": "article", "title": "...", ...}]
        """
        self.bibliography = {entry.get("key", ""): entry for entry in bibtex_entries}

    def render_citation(self, key: str, number: int) -> str:
        """渲染单条引用

        Returns:
            例如: "[1]" 或 "[1, p.123]"
        """
        return f"[{number}]"

    def render_bibliography(
        self,
        index: dict[str, int],
        style: Literal["apa", "ieee", "gbt7714"] = "ieee",
    ) -> str:
        """生成参考文献列表

        Args:
            index: build_index() 返回的索引映射
            style: 引用格式风格

        Returns:
            Markdown 格式的参考文献节
        """
        if not index:
            return ""

        lines = ["\n---\n\n## 参考文献\n"]

        # 按编号排序
        sorted_keys = sorted(index.keys(), key=lambda k: index[k])

        for key in sorted_keys:
            number = index[key]
            entry = self.bibliography.get(key, {})

            if style == "ieee":
                rendered = self._render_ieee(key, number, entry)
            elif style == "apa":
                rendered = self._render_apa(key, number, entry)
            elif style == "gbt7714":
                rendered = self._render_gbt7714(key, number, entry)
            else:
                rendered = f"[{number}] {entry.get('title', key)}"

            lines.append(rendered)

        return "\n".join(lines)

    def _render_ieee(self, key: str, number: int, entry: dict) -> str:
        """IEEE 引用格式"""
        authors = entry.get("author", key)
        title = entry.get("title", "[No Title]")
        journal = entry.get("journal", "")
        year = entry.get("year", "")
        volume = entry.get("volume", "")
        pages = entry.get("pages", "")

        parts = [f"[{number}] "]
        if authors:
            parts.append(f"{authors}. ")
        parts.append(f'"{title}." ')
        if journal:
            parts.append(f"*{journal}*")
            if volume:
                parts.append(f", vol. {volume}")
            if pages:
                parts.append(f", pp. {pages}")
            parts.append(". ")
        if year:
            parts.append(f"{year}.")

        return "".join(parts).strip()

    def _render_apa(self, key: str, number: int, entry: dict) -> str:
        """APA 引用格式"""
        authors = entry.get("author", key)
        year = entry.get("year", "")
        title = entry.get("title", "[No Title]")
        journal = entry.get("journal", "")
        volume = entry.get("volume", "")
        pages = entry.get("pages", "")

        parts = [f"[{number}] "]
        parts.append(f"{authors} ")
        if year:
            parts.append(f"({year}). ")
        parts.append(f"{title}. ")
        if journal:
            parts.append(f"*{journal}*")
            if volume:
                parts.append(f", {volume}")
            if pages:
                parts.append(f", {pages}")
            parts.append(".")

        return "".join(parts).strip()

    def _render_gbt7714(self, key: str, number: int, entry: dict) -> str:
        """GB/T 7714 中文引用格式"""
        authors = entry.get("author", key)
        year = entry.get("year", "")
        title = entry.get("title", "[No Title]")
        journal = entry.get("journal", "")
        volume = entry.get("volume", "")
        pages = entry.get("pages", "")
        doi = entry.get("doi", "")

        parts = [f"[{number}] "]
        parts.append(f"{authors}. ")
        parts.append(f"{title}. ")
        if journal:
            parts.append(f"*{journal}*")
            if volume:
                parts.append(f", {volume}")
            if pages:
                parts.append(f": {pages}")
            parts.append(". ")
        if year:
            parts.append(f"{year}.")
        if doi:
            parts.append(f" DOI: {doi}")

        return "".join(parts).strip()

    def replace_citations(self, text: str, index: dict[str, int]) -> str:
        """将原文中的 [@key] 替换为 [编号]

        Args:
            text: 原始 Markdown 文本
            index: build_index() 返回的索引映射

        Returns:
            替换后的文本
        """
        def replacer(match):
            key = match.group(1)
            page_ref = match.group(2) or ""
            if key in index:
                number = index[key]
                if page_ref:
                    return f"[{number}, {page_ref}]"
                return f"[{number}]"
            return match.group(0)  # 未找到的引用保持原样

        return self.CITATION_PATTERN.sub(replacer, text)

    def process(
        self,
        text: str,
        bibliography: list[dict] | None = None,
        style: Literal["apa", "ieee", "gbt7714"] = "ieee",
        include_reference_section: bool = True,
    ) -> dict:
        """完整处理流程

        Args:
            text: 原始 Markdown 文本
            bibliography: 文献库（可选）
            style: 引用格式
            include_reference_section: 是否在结果中包含参考文献节

        Returns:
            {
                "text": 替换引用后的文本,
                "citations": [{"key": "...", "number": 1, ...}],
                "index": {"key": number, ...},
                "bibliography": "参考文献节内容"
            }
        """
        if bibliography:
            self.set_bibliography(bibliography)

        # 提取并索引
        keys = self.extract_citations(text)
        index = self.build_index(text)

        # 替换原文中的引用
        replaced_text = self.replace_citations(text, index)

        # 构建引用信息
        citations = []
        for key, number in sorted(index.items(), key=lambda x: x[1]):
            citations.append({
                "key": key,
                "number": number,
                "raw_citation": f"[@{key}]",
                "found": key in self.bibliography,
            })

        # 生成参考文献节
        bib_section = ""
        if include_reference_section:
            bib_section = self.render_bibliography(index, style)

        return {
            "text": replaced_text,
            "citations": citations,
            "index": index,
            "bibliography": bib_section,
        }
