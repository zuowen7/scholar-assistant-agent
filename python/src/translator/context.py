"""文档上下文提取 - 从原文中提取标题、摘要、学科领域，用于翻译时保持全局一致性"""

from __future__ import annotations

import re


def extract_document_context(raw_text: str, max_chars: int = 600) -> str:
    """从原文开头提取文档级上下文（标题 + 摘要）

    这个上下文会随每个翻译 chunk 一起发给模型，让模型知道：
    1. 这篇文章讲什么
    2. 属于什么学科
    3. 核心研究对象是什么

    Args:
        raw_text: 文档原始文本（清洗前即可）
        max_chars: 上下文最大字符数，避免占用过多 token

    Returns:
        精简的文档上下文字符串
    """
    if not raw_text.strip():
        return ""

    lines = raw_text.strip().split("\n")
    title = _extract_title(lines)
    abstract = _extract_abstract(raw_text)

    parts = []
    if title:
        parts.append(f"标题: {title}")
    if abstract:
        parts.append(f"摘要: {abstract}")

    context = " | ".join(parts)
    if len(context) > max_chars:
        context = context[: max_chars - 3] + "..."
    return context


def _extract_title(lines: list[str]) -> str:
    """提取文档标题（通常是第一个非空、较短的行）"""
    for line in lines[:20]:
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) < 5:
            continue
        if re.match(r"^\d+$", stripped):
            continue
        if re.match(r"^(Page|Vol|DOI|http)", stripped, re.IGNORECASE):
            continue
        if len(stripped) > 200:
            continue
        if stripped.isupper() and len(stripped) > 20:
            continue
        return stripped
    return ""


def _extract_abstract(text: str) -> str:
    """提取摘要内容"""
    patterns = [
        r"(?:^|\n)\s*Abstract\s*[.:：]?\s*\n?(.*?)(?=\n\s*(?:Introduction|1\.?\s|Keywords|Key\s+words|1\s+Introduction|\Z))",
        r"(?:^|\n)\s*ABSTRACT\s*[.:：]?\s*\n?(.*?)(?=\n\s*(?:INTRODUCTION|1\.?\s|KEYWORDS|\Z))",
        r"(?:^|\n)\s*摘要\s*[.:：]?\s*\n?(.*?)(?=\n\s*(?:引言|1\.?\s|关键词|1\s|Introduction|\Z))",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            abstract = m.group(1).strip()
            abstract = re.sub(r"\s+", " ", abstract)
            if len(abstract) > 30:
                if len(abstract) > 300:
                    abstract = abstract[:300] + "..."
                return abstract

    return ""
