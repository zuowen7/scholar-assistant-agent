"""输出格式化 - 生成双语对照文档"""

from __future__ import annotations

import re
from pathlib import Path

from src.translator.ollama_client import TranslationResult


def format_output(
    results: list[TranslationResult],
    output_format: str = "bilingual",
    file_format: str = "markdown",
) -> str:
    if file_format == "markdown":
        return _format_markdown(results, output_format)
    return _format_plain(results, output_format)


def _format_markdown(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    if output_format == "bilingual":
        return _format_bilingual_md(results)
    if output_format == "parallel":
        return _format_parallel_md(results)
    return _format_translated_only_md(results)


def _format_bilingual_md(results: list[TranslationResult]) -> str:
    """双语对照格式 — 先合并所有 chunk 并去重 overlap，再按段落对照输出"""
    # 合并所有 chunk，去除 overlap 重复
    merged_orig, merged_trans = _merge_chunks(results)

    parts: list[str] = []
    max_paras = max(len(merged_orig), len(merged_trans))
    for j in range(max_paras):
        orig = merged_orig[j] if j < len(merged_orig) else ""
        trans = merged_trans[j] if j < len(merged_trans) else ""

        if orig:
            for line in orig.split("\n"):
                parts.append(f"> {line}")
            parts.append("")
        if trans:
            parts.append(trans)
            parts.append("")

    return "\n".join(parts)


def _merge_chunks(
    results: list[TranslationResult],
) -> tuple[list[str], list[str]]:
    """合并所有 chunk 的段落，去除 overlap 导致的重复段落

    Returns:
        (merged_orig_paragraphs, merged_trans_paragraphs)
    """
    all_orig: list[str] = []
    all_trans: list[str] = []

    for i, r in enumerate(results):
        orig_paras = _split_paragraphs(r.original)
        trans_paras = _split_paragraphs(r.translated)

        # 去除与前一个 chunk 重叠的段落
        if all_orig and orig_paras:
            orig_paras, trans_paras = _strip_overlap(
                orig_paras, trans_paras, all_orig[-1]
            )

        all_orig.extend(orig_paras)
        all_trans.extend(trans_paras)

    return all_orig, all_trans


def _format_parallel_md(results: list[TranslationResult]) -> str:
    lines: list[str] = []
    lines.append("| 原文 | 译文 |")
    lines.append("| --- | --- |")

    merged_orig, merged_trans = _merge_chunks(results)
    max_paras = max(len(merged_orig), len(merged_trans))
    for j in range(max_paras):
        orig = merged_orig[j] if j < len(merged_orig) else ""
        trans = merged_trans[j] if j < len(merged_trans) else ""
        lines.append(f"| {_md_table_escape(orig)} | {_md_table_escape(trans)} |")

    lines.append("")
    return "\n".join(lines)


def _format_translated_only_md(results: list[TranslationResult]) -> str:
    """只输出译文，合并所有 chunk 并去除 overlap"""
    _, merged_trans = _merge_chunks(results)
    return "\n\n".join(merged_trans)


def _format_plain(
    results: list[TranslationResult],
    output_format: str,
) -> str:
    lines: list[str] = []

    if output_format == "bilingual":
        merged_orig, merged_trans = _merge_chunks(results)
        max_paras = max(len(merged_orig), len(merged_trans))
        for j in range(max_paras):
            orig = merged_orig[j] if j < len(merged_orig) else ""
            trans = merged_trans[j] if j < len(merged_trans) else ""
            if orig:
                lines.append("[原文]")
                lines.append(orig)
                lines.append("")
            if trans:
                lines.append("[译文]")
                lines.append(trans)
                lines.append("")
    else:
        _, merged_trans = _merge_chunks(results)
        for t in merged_trans:
            if t.strip():
                lines.append(t)
                lines.append("")

    return "\n".join(lines)


def _split_paragraphs(text: str) -> list[str]:
    paras = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in paras if p.strip()]


def _strip_overlap(
    orig_paras: list[str],
    trans_paras: list[str],
    prev_last_orig: str,
) -> tuple[list[str], list[str]]:
    """去除 chunk 开头与前一个 chunk 末尾因 overlap 重复的段落

    策略: 逐个比较当前 chunk 开头的段落与前一个 chunk 末尾段落，
    如果高度相似（前缀匹配 >= 50%），则同时去除该原文段落及其对应的译文。
    处理多段 overlap 的情况，且安全处理 orig/trans 段落数不一致。
    """
    if not prev_last_orig or not orig_paras:
        return orig_paras, trans_paras

    prev_stripped = prev_last_orig.strip()
    if len(prev_stripped) < 10:
        return orig_paras, trans_paras

    # 计算需要去除的段落数量
    strip_count = 0
    for para in orig_paras:
        para_stripped = para.strip()
        if len(para_stripped) < 10:
            break

        # 前缀匹配: 从头逐字比较
        shorter = min(len(prev_stripped), len(para_stripped))
        match_len = 0
        for j in range(shorter):
            if prev_stripped[j].lower() == para_stripped[j].lower():
                match_len += 1
            else:
                break

        if match_len >= shorter * 0.7:
            strip_count += 1
        else:
            break

    if strip_count == 0:
        return orig_paras, trans_paras

    # 安全去除: 取 orig 和 trans 中较小的 strip 数，避免越界
    safe_strip_orig = min(strip_count, len(orig_paras))
    safe_strip_trans = min(strip_count, len(trans_paras))

    return orig_paras[safe_strip_orig:], trans_paras[safe_strip_trans:]


def _md_table_escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def save_output(content: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
