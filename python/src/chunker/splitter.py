"""文本切块器 - 将长文本切分为适合模型处理的块"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 粗略估算: 1 token ≈ 4 个英文字符 或 1.5 个中文字符
CHARS_PER_TOKEN_EN = 4
CHARS_PER_TOKEN_ZH = 1.5


@dataclass
class Chunk:
    """文本块"""

    index: int
    text: str
    char_count: int
    estimated_tokens: int


@dataclass
class ChunkResult:
    """切块结果"""

    chunks: list[Chunk]
    references_text: str  # 未翻译的引用区原文


def _estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数"""
    en_chars = sum(1 for c in text if c.isascii() and c.isprintable())
    zh_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - en_chars - zh_chars
    return max(
        1,
        int(en_chars / CHARS_PER_TOKEN_EN + zh_chars / CHARS_PER_TOKEN_ZH + other_chars / 2),
    )


def chunk_text(
    text: str,
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
    strategy: str = "sentence",
    skip_references: bool = True,
) -> list[Chunk]:
    """将文本切分为多个块

    Args:
        text: 清洗后的文本
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        strategy: 切块策略 - sentence | paragraph | fixed
        skip_references: 是否跳过引用区不切块

    Returns:
        Chunk 列表（不含引用区）
    """
    result = chunk_text_full(text, max_tokens, overlap_tokens, strategy, skip_references)
    return result.chunks


def chunk_text_full(
    text: str,
    max_tokens: int = 2048,
    overlap_tokens: int = 128,
    strategy: str = "sentence",
    skip_references: bool = True,
) -> ChunkResult:
    """完整切块，返回引用区原文

    Args:
        text: 清洗后的文本
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        strategy: 切块策略 - sentence | paragraph | fixed
        skip_references: 是否跳过引用区不切块

    Returns:
        ChunkResult 包含 chunks 和 references_text
    """
    body_text = text
    references_text = ""

    if skip_references:
        body_text, references_text = _split_references(text)

    if not body_text.strip():
        return ChunkResult(chunks=[], references_text=references_text)

    if strategy == "sentence":
        segments = _split_sentences(body_text)
    elif strategy == "paragraph":
        segments = _split_paragraphs(body_text)
    elif strategy == "fixed":
        segments = _split_fixed(body_text, chunk_chars=max_tokens * CHARS_PER_TOKEN_EN)
    else:
        raise ValueError(f"未知切块策略: {strategy}")

    chunks = _merge_segments(segments, max_tokens, overlap_tokens)
    return ChunkResult(chunks=chunks, references_text=references_text)


# ---------------------------------------------------------------------------
# 引用区分离
# ---------------------------------------------------------------------------

_REFERENCE_PATTERNS = [
    r"REFERENCES\s+AND\s+NOTES\s*$",
    r"REFERENCES\s*$",
    r"BIBLIOGRAPHY\s*$",
    r"LITERATURE\s+CITED\s*$",
    r"WORKS\s+CITED\s*$",
]


def _split_references(text: str) -> tuple[str, str]:
    """将正文和引用区拆分（查找最后一个匹配，避免误截多篇文章）

    Returns:
        (body_text, references_text)
    """
    best_pos = -1
    for pattern in _REFERENCE_PATTERNS:
        for m in re.finditer(r"^" + pattern, text, re.MULTILINE | re.IGNORECASE):
            if m.start() > best_pos:
                best_pos = m.start()

    if best_pos >= 0:
        body = text[:best_pos].rstrip()
        refs = text[best_pos:]
        # 如果"引用区"占比过大（>50%），可能是多篇文章误判，不切割
        if len(refs) > len(text) * 0.5:
            return text, ""
        return body, refs
    return text, ""


# ---------------------------------------------------------------------------
# 切块策略
# ---------------------------------------------------------------------------

# 常见学术缩写，这些缩写后的句号不代表句子结束
_ACADEMIC_ABBREVS = [
    "et al", "etc", "fig", "figs", "eq", "eqs", "ref", "refs",
    "vol", "no", "pp", "cf", "e.g", "i.e", "vs", "al",
    "ed", "eds", "rev", "proc", "inst", "dept", "univ",
    "sci", "tech", "phys", "chem", "biol", "med",
    "hum", "evol", "anthrop", "soc", "pol", "econ", "psych",
    "nat", "int", "inc", "ltd", "co", "st", "dr", "mr", "mrs",
    "prof", "sr", "jr", "ph", "dc", "ba", "ma",
    "approx", "max", "min", "avg", "std", "var",
    "def", "thm", "lem", "cor", "prop",
]


def _split_sentences(text: str) -> list[str]:
    """按句子拆分文本，保护学术缩写不被误切

    处理步骤:
    1. 保护单字母缩写 (A. B. C. 等)
    2. 保护已知学术缩写 (et al. Fig. Vol. 等)
    3. 按句子边界切分
    4. 还原占位符
    5. 合并过短碎片
    """
    placeholders: list[str] = []
    protected = text

    # 保护单字母 + 句号 (人名首字母 J. A. 等)
    protected = re.sub(
        r"\b([A-Z])\.\s",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )

    # 保护已知缩写 + 句号
    for abbr in _ACADEMIC_ABBREVS:
        protected = re.sub(
            rf"\b{abbr}\.\s",
            lambda m: _ph(m.group(0), placeholders),
            protected,
            flags=re.IGNORECASE,
        )

    # 保护数字 + 句号 (如 "10.5", "3.14")
    protected = re.sub(
        r"(\d)\.(\d)",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )

    # 按句子边界切分: 句号/问号/感叹号后跟空格或换行
    parts = re.split(r"(?<=[.!?])\s+", protected)

    # 还原占位符
    sentences = []
    for p in parts:
        restored = p.strip()
        for i, ph in enumerate(placeholders):
            restored = restored.replace(f"\x00PH{i}\x00", ph)
        if restored:
            sentences.append(restored)

    # 合并过短碎片 (< 20 字符且不以大写开头)
    merged: list[str] = []
    for s in sentences:
        if merged and len(s) < 20 and not re.match(r"^[A-Z]", s):
            merged[-1] += " " + s
        else:
            merged.append(s)

    return [s for s in merged if s.strip()]


def _ph(match_text: str, placeholders: list[str]) -> str:
    """创建占位符保护缩写不被切分"""
    idx = len(placeholders)
    placeholders.append(match_text)
    return f"\x00PH{idx}\x00"


def _split_paragraphs(text: str) -> list[str]:
    """按段落拆分文本"""
    parts = text.split("\n\n")
    return [p.strip() for p in parts if p.strip()]


def _split_fixed(text: str, chunk_chars: int) -> list[str]:
    """按固定字符数拆分，尽量在句子边界处切割"""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_chars
        if end >= len(text):
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break
        # 在 chunk_chars 范围内找最后一个句子边界
        boundary = -1
        for sep in (". ", "! ", "? ", "。", "！", "？", "\n"):
            pos = text.rfind(sep, start, end)
            if pos > boundary:
                boundary = pos
        if boundary > start:
            end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


def _merge_segments(
    segments: list[str],
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """将小片段合并为大块，控制 token 上限，重叠保持完整句子"""
    if not segments:
        return []

    max_chars = max_tokens * CHARS_PER_TOKEN_EN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN_EN

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    idx = 0

    for seg in segments:
        seg_len = len(seg)
        # 单个片段就超限 → 独立成块
        if seg_len > max_chars:
            if current_parts:
                chunks.append(_make_chunk(idx, current_parts))
                idx += 1
                current_parts = []
                current_len = 0
            chunks.append(_make_chunk(idx, [seg]))
            idx += 1
            continue

        if current_len + seg_len + 1 > max_chars and current_parts:
            chunks.append(_make_chunk(idx, current_parts))
            idx += 1
            # 重叠: 保留末尾完整的句子 (从后往前找足够长的一段)
            current_parts = _get_overlap_parts(current_parts, overlap_chars)
            current_len = sum(len(p) for p in current_parts) + len(current_parts)

        current_parts.append(seg)
        current_len += seg_len + 1

    if current_parts:
        chunks.append(_make_chunk(idx, current_parts))

    return chunks


def _get_overlap_parts(parts: list[str], overlap_chars: int) -> list[str]:
    """从已有片段中取末尾的完整句子作为重叠上下文"""
    if overlap_chars <= 0 or not parts:
        return []

    # 从后往前累加，直到超过 overlap_chars
    overlap: list[str] = []
    total = 0
    for p in reversed(parts):
        if total + len(p) > overlap_chars and overlap:
            break
        overlap.insert(0, p)
        total += len(p) + 1

    return overlap


def _make_chunk(index: int, parts: list[str]) -> Chunk:
    """创建一个 Chunk"""
    text = " ".join(parts)
    return Chunk(
        index=index,
        text=text,
        char_count=len(text),
        estimated_tokens=_estimate_tokens(text),
    )
