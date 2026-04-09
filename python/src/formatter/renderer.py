"""输出格式化 - 生成双语对照文档

核心优化:
1. 合并 chunk 时恢复模型丢失的段落结构
2. 双语对照模式保护标题层级 (#/##/###) 和数学公式 ($$...$$)
3. 严格原文-译文段落对齐
"""

from __future__ import annotations

import re
from pathlib import Path

from src.translator.ollama_client import TranslationResult, _restore_paragraphs


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
    """合并所有 chunk 的段落，去除 overlap 导致的重复段落

    增强点:
    1. 对译文恢复段落结构（模型常合并多段为一段）
    2. 去除 overlap 时保护标题和公式
    3. 严格对齐原文/译文段落数

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

        # 恢复译文段落结构: 如果原文有 N 段但译文只有 1 段，尝试按比例拆分
        if len(orig_paras) > 1 and len(trans_paras) == 1:
            restored = _restore_paragraphs(
                "\n\n".join(orig_paras),
                trans_paras[0],
            )
            trans_paras = _split_paragraphs(restored)

        # 对齐: 如果原文比译文多，补空字符串；反之亦然
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


def _strip_overlap(
    orig_paras: list[str],
    trans_paras: list[str],
    prev_last_orig: str,
) -> tuple[list[str], list[str]]:
    """去除 chunk 开头与前一个 chunk 末尾因 overlap 重复的段落

    策略: 逐个比较当前 chunk 开头的段落与前一个 chunk 末尾段落，
    要求前缀匹配 >= 70% **且** 整体相似度 >= 60%，避免公式段落仅因前缀相同被误删。
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

        # 标题和公式段落不参与 overlap 去重
        if _is_heading_or_math(para_stripped):
            break

        # 前缀匹配: 从头逐字比较
        shorter = min(len(prev_stripped), len(para_stripped))
        match_len = 0
        for j in range(shorter):
            if prev_stripped[j].lower() == para_stripped[j].lower():
                match_len += 1
            else:
                break

        # 前缀匹配比例
        prefix_ratio = match_len / shorter if shorter > 0 else 0

        # 整体相似度: 用较短文本的长度做归一化
        longer = max(len(prev_stripped), len(para_stripped))
        overall_ratio = shorter / longer if longer > 0 else 0

        # 要求前缀匹配 >= 70% 且整体长度相似度 >= 60%（避免公式段落误删）
        if prefix_ratio >= 0.7 and overall_ratio >= 0.6:
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
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    return text


def save_output(content: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
