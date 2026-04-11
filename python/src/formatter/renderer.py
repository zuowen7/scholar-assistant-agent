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
        orig_text = r.original
        trans_text = r.translated

        # 去除与前一个 chunk 重叠的内容（基于文本前缀匹配）
        if all_orig:
            prev_orig_joined = "\n\n".join(
                p for p in all_orig[-min(len(all_orig), 10):] if p.strip()
            )
            if prev_orig_joined.strip():
                orig_text, trans_text = _strip_text_overlap(
                    orig_text, trans_text, prev_orig_joined,
                )

        orig_paras = _split_paragraphs(orig_text)
        trans_paras = _split_paragraphs(trans_text)

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
    prev_orig_tail: list[str],
) -> tuple[list[str], list[str]]:
    """去除 chunk 开头与前一个 chunk 末尾因 overlap 重复的段落

    策略: 在 prev_orig_tail 中找最长的连续子序列，使其与当前 chunk 开头的
    段落逐段匹配。这样可以正确处理跨多个段落的 overlap。
    """
    if not prev_orig_tail or not orig_paras:
        return orig_paras, trans_paras

    # 过滤掉过短的尾部段落
    prev_tail = [p.strip() for p in prev_orig_tail if p.strip() and len(p.strip()) >= 10]
    if not prev_tail:
        return orig_paras, trans_paras

    best_strip = 0
    # 尝试从 prev_tail 的每个位置开始匹配
    for start in range(len(prev_tail)):
        match_count = 0
        for k in range(min(len(prev_tail) - start, len(orig_paras))):
            prev_p = prev_tail[start + k]
            curr_p = orig_paras[k].strip()
            if len(curr_p) < 10:
                break
            if _is_heading_or_math(curr_p):
                break
            if _paragraphs_match(prev_p, curr_p):
                match_count += 1
            else:
                break
        # 必须匹配至少 1 段，且匹配数要大于之前的最佳结果
        if match_count > best_strip:
            best_strip = match_count

    if best_strip == 0:
        return orig_paras, trans_paras

    safe_strip_orig = min(best_strip, len(orig_paras))
    safe_strip_trans = min(best_strip, len(trans_paras))
    return orig_paras[safe_strip_orig:], trans_paras[safe_strip_trans:]


def _strip_text_overlap(
    orig_text: str,
    trans_text: str,
    prev_orig_text: str,
) -> tuple[str, str]:
    """在原始文本层面去除 chunk 间 overlap 导致的重复

    策略: 在 prev_orig_text 的尾部寻找一个最长后缀，
    该后缀与 orig_text 的前缀匹配。找到后按相同比例剥离两者。
    """
    if not prev_orig_text.strip() or not orig_text.strip():
        return orig_text, trans_text

    prev_tail = prev_orig_text[-1000:].strip()
    if len(prev_tail) < 30:
        return orig_text, trans_text

    orig_stripped = orig_text.strip()
    if not orig_stripped:
        return orig_text, trans_text

    # 核心策略: 找 prev_tail 的最长后缀，该后缀是 orig_stripped 的前缀
    # 只在句子边界处尝试，减少搜索次数
    best_suffix_len = 0

    # 找 prev_tail 中所有句子边界位置
    sentence_starts = [0]
    for m in re.finditer(r"(?<=[.!?。！？\n])\s+", prev_tail):
        sentence_starts.append(m.end())

    for start in sentence_starts:
        suffix = prev_tail[start:]
        if len(suffix) < 30:
            break

        match_len = _prefix_match_len(suffix, orig_stripped)
        if match_len > best_suffix_len:
            best_suffix_len = match_len

        if len(suffix) < best_suffix_len:
            break

    # 匹配长度需有实际意义
    if best_suffix_len < 30:
        return orig_text, trans_text

    # 确保匹配不会吃掉整篇内容
    if best_suffix_len > len(orig_stripped) * 0.8:
        return orig_text, trans_text

    # 找最近的句子边界作为切割点
    cut_pos = _find_sentence_boundary(orig_stripped, best_suffix_len)
    if cut_pos <= 0:
        return orig_text, trans_text

    # 按相同比例从 trans_text 中剥离
    orig_ratio = cut_pos / max(len(orig_stripped), 1)
    trans_cut = int(len(trans_text) * orig_ratio)
    trans_cut = _find_sentence_boundary(trans_text, trans_cut)

    new_orig = orig_stripped[cut_pos:].strip()
    new_trans = trans_text[trans_cut:].strip()

    return new_orig, new_trans


def _prefix_match_len(a: str, b: str) -> int:
    """计算 a 的前缀与 b 的前缀的连续匹配字符数（忽略空白差异，容许少量错误）

    用于检测 overlap: a 是 prev_tail 的后缀，b 是 orig_text 的开头。
    """
    ia = 0
    ib = 0
    match = 0
    mismatch_streak = 0

    while ia < len(a) and ib < len(b):
        ca = a[ia]
        cb = b[ib]
        # 跳过空白
        if ca in " \t\n\r":
            ia += 1
            continue
        if cb in " \t\n\r":
            ib += 1
            continue
        if ca.lower() == cb.lower():
            match += 1
            mismatch_streak = 0
        else:
            mismatch_streak += 1
            if mismatch_streak > 8:
                break
            match += 1  # 容许少量不匹配（OCR/编码差异）
        ia += 1
        ib += 1

    # 匹配率太低则视为无效
    if match < 30 or match < len(a) * 0.5:
        return 0

    return match


def _find_sentence_boundary(text: str, target_pos: int) -> int:
    """在 target_pos 附近找最近的句子边界（中英文句末标点后）"""
    if target_pos <= 0 or target_pos >= len(text):
        return target_pos

    # 在 target_pos 附近 ±50 字符范围内找句末标点
    search_start = max(0, target_pos - 50)
    search_end = min(len(text), target_pos + 50)

    best_pos = target_pos
    best_dist = abs(target_pos - target_pos)  # 0

    for i in range(search_start, search_end):
        if text[i] in ".!?。！？；\n":
            pos = i + 1
            dist = abs(pos - target_pos)
            if dist < best_dist or best_dist == 0:
                best_pos = pos
                best_dist = dist

    # 如果没找到好的句末标点，在 target_pos 后找第一个空格或换行
    if best_dist > 30:
        for i in range(target_pos, min(len(text), target_pos + 30)):
            if text[i] in " \n":
                return i + 1
        return target_pos

    return best_pos


def _paragraphs_match(a: str, b: str) -> bool:
    """判断两个段落是否是同一段文字（可能是原文的同一片段）

    策略: 前缀匹配 >= 50% 且整体长度比在 0.4~2.5 之间
    """
    a_s = a.strip()
    b_s = b.strip()
    if not a_s or not b_s:
        return False

    shorter = min(len(a_s), len(b_s))
    longer = max(len(a_s), len(b_s))

    # 长度差异过大不匹配
    if shorter / longer < 0.4:
        return False

    # 前缀匹配
    match_len = 0
    check_len = min(shorter, 200)  # 只检查前 200 字符
    for i in range(check_len):
        if a_s[i].lower() == b_s[i].lower():
            match_len += 1
        else:
            break

    prefix_ratio = match_len / check_len if check_len > 0 else 0
    return prefix_ratio >= 0.5


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
