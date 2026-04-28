"""输出格式化 - 生成双语对照文档

核心优化:
1. 合并 chunk 时恢复模型丢失的段落结构
2. 双语对照模式保护标题层级 (#/##/###) 和数学公式 ($$...$$)
3. 严格原文-译文段落对齐
"""

from __future__ import annotations

import re
from pathlib import Path

from src.translator._helpers import TranslationResult, _restore_paragraphs


def format_output(
    results: list[TranslationResult],
    output_format: str = "bilingual",
    file_format: str = "markdown",
) -> str:
    """将翻译结果格式化为输出文档

    Args:
        results: 翻译结果列表（每项含原文和译文）
        output_format: 输出格式 — ``bilingual`` (逐段对照)、``parallel`` (表格对照)、``translated_only`` (纯译文)
        file_format: 文件格式 — ``markdown`` 或 ``plain``

    Returns:
        格式化后的字符串内容
    """
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
    """双语对照格式 — 先合并所有 chunk 并去重 overlap，再按段落对照输出

    标题行和数学公式块不使用引用格式，保持原始 Markdown 层级。
    """
    merged_orig, merged_trans = _merge_chunks(results)

    parts: list[str] = []
    max_paras = max(len(merged_orig), len(merged_trans))
    for j in range(max_paras):
        orig = merged_orig[j] if j < len(merged_orig) else ""
        trans = merged_trans[j] if j < len(merged_trans) else ""

        if orig:
            # 标题行或数学公式块: 不使用引用格式，保留层级
            if _is_heading_or_math(orig):
                parts.append(orig)
            else:
                for line in orig.split("\n"):
                    parts.append(f"> {line}")
            parts.append("")
        if trans:
            parts.append(trans)
            parts.append("")

    return "\n".join(parts)


def _is_heading_or_math(text: str) -> bool:
    """判断段落是否为标题或数学公式块，不应被引用包裹"""
    stripped = text.strip()
    # Markdown 标题: # / ## / ###
    if re.match(r"^#{1,6}\s+\S", stripped):
        return True
    # 数学公式块: $$ ... $$
    if stripped.startswith("$$") and stripped.endswith("$$"):
        return True
    # LaTeX 环境
    if re.match(r"^\\(?:begin|end)\{", stripped):
        return True
    return False


def _merge_chunks(
    results: list[TranslationResult],
) -> tuple[list[str], list[str]]:
    """合并所有 chunk 的段落（无 overlap 模式，简单直接拼接）

    Returns:
        (merged_orig_paragraphs, merged_trans_paragraphs)
    """
    all_orig: list[str] = []
    all_trans: list[str] = []

    for r in results:
        orig_paras = _split_paragraphs(r.original)
        trans_paras = _split_paragraphs(r.translated)

        # 恢复译文段落结构
        if len(orig_paras) > 1 and len(trans_paras) == 1:
            restored = _restore_paragraphs(
                "\n\n".join(orig_paras),
                trans_paras[0],
            )
            trans_paras = _split_paragraphs(restored)

        # 对齐原文和译文段落数
        max_len = max(len(orig_paras), len(trans_paras))
        while len(orig_paras) < max_len:
            orig_paras.append("")
        while len(trans_paras) < max_len:
            trans_paras.append("")

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
    return "\n\n".join(t for t in merged_trans if t.strip())


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
    """按双换行拆分段落，保护数学公式块和 LaTeX 环境不被误拆"""
    # 先保护 $$...$$ 块内的换行
    placeholders: list[str] = []
    protected = text

    # 保护 $$...$$ 块
    protected = re.sub(
        r"\$\$[\s\S]*?\$\$",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )
    # 保护 \begin{...}...\end{...} 块
    protected = re.sub(
        r"\\begin\{[^}]+\}[\s\S]*?\\end\{[^}]+\}",
        lambda m: _ph(m.group(0), placeholders),
        protected,
    )

    paras = re.split(r"\n{2,}", protected.strip())

    # 还原占位符
    restored = []
    for p in paras:
        p = p.strip()
        for i in range(len(placeholders) - 1, -1, -1):
            p = p.replace(f"\x00PH{i}\x00", placeholders[i])
        if p:
            restored.append(p)

    return restored


def _ph(text: str, placeholders: list[str]) -> str:
    """占位符替换辅助"""
    idx = len(placeholders)
    placeholders.append(text)
    return f"\x00PH{idx}\x00"


def _md_table_escape(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def save_output(content: str, output_path: str | Path) -> Path:
    """将内容写入文件

    Args:
        content: 要写入的文本内容
        output_path: 输出文件路径

    Returns:
        实际写入的 Path 对象
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
