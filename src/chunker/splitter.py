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
) -> list[Chunk]:
    """将文本切分为多个块

    Args:
        text: 清洗后的文本
        max_tokens: 每块最大 token 数
        overlap_tokens: 块间重叠 token 数
        strategy: 切块策略 - sentence | paragraph | fixed

    Returns:
        Chunk 列表
    """
    if strategy == "sentence":
        segments = _split_sentences(text)
    elif strategy == "paragraph":
        segments = _split_paragraphs(text)
    elif strategy == "fixed":
        segments = _split_fixed(text, chunk_chars=max_tokens * CHARS_PER_TOKEN_EN)
    else:
        raise ValueError(f"未知切块策略: {strategy}")

    return _merge_segments(segments, max_tokens, overlap_tokens)


def _split_sentences(text: str) -> list[str]:
    """按句子拆分文本"""
    # 以句号、问号、感叹号加空格/换行为分隔点
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """按段落拆分文本"""
    parts = text.split("\n\n")
    return [p.strip() for p in parts if p.strip()]


def _split_fixed(text: str, chunk_chars: int) -> list[str]:
    """按固定字符数拆分"""
    chunks: list[str] = []
    for i in range(0, len(text), chunk_chars):
        chunk = text[i : i + chunk_chars].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _merge_segments(
    segments: list[str],
    max_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """将小片段合并为大块，控制 token 上限"""
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
            # 重叠: 保留末尾部分
            overlap_text = " ".join(current_parts)
            if overlap_chars > 0 and len(overlap_text) > overlap_chars:
                tail = overlap_text[-overlap_chars:]
                current_parts = [tail]
                current_len = len(tail)
            else:
                current_parts = []
                current_len = 0

        current_parts.append(seg)
        current_len += seg_len + 1

    if current_parts:
        chunks.append(_make_chunk(idx, current_parts))

    return chunks


def _make_chunk(index: int, parts: list[str]) -> Chunk:
    """创建一个 Chunk"""
    text = " ".join(parts)
    return Chunk(
        index=index,
        text=text,
        char_count=len(text),
        estimated_tokens=_estimate_tokens(text),
    )
