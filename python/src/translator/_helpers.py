"""翻译后处理辅助函数 — 跨模块共享的文本处理工具。

本模块集中管理 OllamaClient / CloudClient / Renderer 共同依赖的
文本处理函数，避免重复定义和循环导入。

包含:
- 术语提取 (_extract_term_pairs)
- 文本清洗 (_strip_think_tags, _strip_code_block_wrapping, _strip_preamble, _strip_context_leak)
- 翻译质量校验 (_validate_translation, _repair_truncation)
- 去重与整理 (_deduplicate_repetition, _deduplicate_line_repetition, _strip_trailing_summary, _strip_empty_parentheses)
- 段落恢复 (_restore_paragraphs)
- 工具函数 (_is_similar_sentences, _lines_match)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from dataclasses import dataclass

if TYPE_CHECKING:
    from src.translator.glossary_store import GlossaryStore


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    """翻译结果数据结构。"""
    original: str = ""
    translated: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---------------------------------------------------------------------------
# 术语提取（保留作为兜底学习，结果仅为建议）
# ---------------------------------------------------------------------------

def _extract_term_pairs(original: str, translated: str) -> list[tuple[str, str]]:
    """从原文-译文对中提取可能的术语翻译对。

    结果仅作为建议注入 GlossaryStore，不具有强制力。
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    pattern = re.compile(
        r"([一-鿿][一-鿿\w\s]{1,20})"
        r"[（(]"
        r"([A-Za-z][A-Za-z\s\-/]+[A-Za-z])"
        r"[）)]"
    )
    for m in pattern.finditer(translated):
        zh_term = m.group(1).strip()
        en_term = m.group(2).strip()
        key = en_term.lower()
        if key not in seen and len(en_term) > 2:
            pairs.append((en_term, zh_term))
            seen.add(key)

    return pairs


# ---------------------------------------------------------------------------
# 术语锚点 Prompt 构建
# ---------------------------------------------------------------------------

def build_glossary_prompt(
    glossary_store: "GlossaryStore | None" = None,
    learned_pairs: list[tuple[str, str]] | None = None,
    max_entries: int = 50,
) -> str:
    """合并权威术语表 + 兜底学习术语对，生成 system prompt 注入文本。

    权威表（GlossaryStore）中的 locked 条目为强制，非 locked 为建议。
    learned_pairs（来自 _extract_term_pairs）仅在没有权威条目时作为弱建议。
    """
    parts: list[str] = []

    if glossary_store and len(glossary_store) > 0:
        prompt_text = glossary_store.build_prompt_text(max_entries=max_entries)
        if prompt_text:
            parts.append(prompt_text)

    if learned_pairs:
        # 只添加 glossary_store 中不存在的条目
        existing_sources: set[str] = set()
        if glossary_store:
            existing_sources = {e.source.lower() for e in glossary_store.all_entries()}
        new_pairs = [(s, t) for s, t in learned_pairs if s.lower() not in existing_sources]
        if new_pairs:
            parts.append("## 自动提取的术语（建议沿用）")
            for source, target in new_pairs[:max_entries]:
                parts.append(f"- {source} → {target}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 后处理 — 文本清洗
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """移除推理模型常见思考段，避免进入正文。"""
    for tag in ("think", "redacted_thinking", "redacted_reasoning"):
        pat = rf"<{tag}\b[^>]*>.*?</{tag}\s*>"
        text = re.sub(pat, "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def _strip_code_block_wrapping(text: str) -> str:
    """移除 LLM 用 markdown 代码块包裹翻译结果的格式幻觉"""
    stripped = text.strip()
    m = re.match(r"^```(?:\w+)?\s*\n(.*?)\n```\s*$", stripped, re.DOTALL)
    if m:
        inner = m.group(1).strip()
        if inner.count("```") == 0:
            return inner
    return text


def _strip_preamble(text: str) -> str:
    """移除翻译开头的引导语（如 Here is the translation: / 以下是翻译）"""
    preamble_pattern = re.compile(
        r"^(?:"
        r"(?:Here|Below|Following)\s+(?:is|are)\s+(?:the\s+)?(?:translation|result|translated\s+text)[：:]*\s*"
        r"|以下是翻译[：:]*\s*"
        r"|翻译如下[：:]*\s*"
        r"|这是翻译结果(?:[：:]+\s*|\n+\s*)"
        r"|下面是(?:翻译|译文)[：:]*\s*"
        r"|这是(?:翻译|译文)(?:[：:]+\s*|\n+\s*)"
        r"|(?:Sure|Certainly|Of\s+course)[，,\s]*(?:here|below)\s+(?:is|are)[^。\n]*[。.\n]\s*"
        r"|(?:好的|没问题|收到)[，,]?\s*(?:以下是翻译|以下是译文|翻译如下|下面是翻译|下面是译文)[：:]*\s*"
        r")",
        re.IGNORECASE,
    )
    return preamble_pattern.sub("", text).strip()


def _strip_context_leak(text: str) -> str:
    """去掉开头附近的指令回声；仅在扫描窗口内匹配，避免误伤正文。"""
    scan_len = 500
    head = text[:scan_len]
    ctx_markers = [
        "[文档背景",
        "[前文翻译参考",
        "（不要翻译此部分",
        "（仅用于保持术语",
        "[请翻译以下内容]",
    ]
    for marker in ctx_markers:
        idx = head.find(marker)
        if idx < 0:
            continue
        rest = text[idx:]
        if "\n\n" in rest[:2500]:
            _, sep, tail = rest.partition("\n\n")
            if sep:
                return tail.lstrip()
        return text[idx + len(marker) :].lstrip()
    return text.strip()


# ---------------------------------------------------------------------------
# 后处理 — 质量校验与修复
# ---------------------------------------------------------------------------

def _validate_translation(result: "TranslationResult | Any") -> bool:
    """校验翻译结果质量

    多层校验: 空值/截断/未翻译/语言检测/格式幻觉/重复检测
    """
    translated = getattr(result, "translated", "") or ""
    original = getattr(result, "original", "") or ""

    if not translated:
        return False

    orig_len = len(original)
    trans_len = len(translated)

    if orig_len < 30:
        return trans_len >= 1 and len(translated.strip()) > 0

    latexish = sum(1 for c in original if c in "\\{}$[]_^") / max(orig_len, 1)
    if latexish > 0.04:
        return trans_len >= max(3, int(orig_len * 0.03))

    if orig_len > 100 and trans_len < orig_len * 0.03:
        return False

    orig_no_space = re.sub(r"\s+", "", original)
    trans_no_space = re.sub(r"\s+", "", translated)
    if orig_no_space and orig_no_space == trans_no_space:
        return False

    cjk_n = sum(1 for c in translated if "一" <= c <= "鿿")
    cjk_ratio = cjk_n / max(trans_len, 1)
    if cjk_ratio < 0.05 and orig_len > 100:
        ascii_ratio = sum(1 for c in translated if c.isascii() and c.isalpha()) / max(trans_len, 1)
        if ascii_ratio > 0.95:
            return False

    stripped = translated.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return False

    if trans_len > 400:
        half = trans_len // 2
        first_half = stripped[:half]
        second_half = stripped[half:half * 2]
        if first_half and second_half and len(first_half) > 50:
            shorter_len = min(len(first_half), len(second_half), 100)
            overlap = sum(1 for a, b in zip(first_half[:shorter_len], second_half[:shorter_len]) if a == b)
            if overlap / shorter_len > 0.8:
                return False

    # 循环重复检测 — 优化：早期退出，限制检测范围
    if trans_len > 600:
        sents = re.split(r"(?<=[。！？])", stripped)
        sents = [s.strip() for s in sents if s.strip()]
        if len(sents) >= 6:
            max_unit = min(len(sents) // 3, 10)  # 限制最大单元数减少计算量
            for unit_sz in range(1, max_unit + 1):
                unit = sents[:unit_sz]
                repeats = 0
                for si in range(unit_sz, len(sents), unit_sz):
                    chunk = sents[si:si + unit_sz]
                    if not chunk:
                        continue
                    if _is_similar_sentences(unit, chunk):
                        repeats += 1
                    else:
                        break
                if repeats >= 2:
                    return False

    return True


def _repair_truncation(text: str) -> str:
    """修复截断的翻译结果。"""
    if not text:
        return text

    n = len(text)
    if n < 100:
        return text

    zh_endings = ["。", "！", "？", "；", "…"]
    en_endings = ["!", "?"]

    last_zh = max((text.rfind(c) for c in zh_endings), default=-1)
    last_en = max((text.rfind(c) for c in en_endings), default=-1)

    last_dot = text.rfind(".")
    if last_dot >= 0:
        before = text[:last_dot].rstrip()
        if before and before[-1].isdigit():
            last_dot = -1
        elif before and before[-1] == ".":
            last_dot = -1
        elif before and re.search(
            r"(?:Fig|Eq|Ref|Vol|No|Dr|Mr|Mrs|Prof|Sr|Jr|St|vs|etc|al|ed|e\.g|i\.e)$",
            before, re.IGNORECASE
        ):
            last_dot = -1

    last_en = max(last_en, last_dot)
    last_sentence_end = max(last_zh, last_en)

    if last_sentence_end >= 0 and last_sentence_end < n - 1 and last_sentence_end >= int(n * 0.75):
        tail = text[last_sentence_end + 1 :].strip()
        tail_cjk = sum(1 for c in tail if "一" <= c <= "鿿")
        if (
            0 < len(tail) < min(120, int(n * 0.12))
            and tail_cjk == 0
            and not re.search(r"[\w一-鿿]{6,}", tail)
        ):
            return text[: last_sentence_end + 1].rstrip()
    return text


def _strip_empty_parentheses(text: str) -> str:
    """移除翻译中残留的空括号。"""
    text = re.sub(r"（\s*）", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text


def _strip_trailing_summary(text: str) -> str:
    """移除译文末尾的总结段落。"""
    if not text or len(text) < 200:
        return text

    summary_patterns = [
        r"\n[（(]?总之[，,]?\s*",
        r"\n[（(]?总而言之[，,]?\s*",
        r"\n[（(]?综上所述[，,]?\s*",
        r"\n[（(]?总的来说[，,]?\s*",
        r"\n[（(]?概括来说[，,]?\s*",
        r"\n[（(]?简而言之[，,]?\s*",
        r"\n[（(]?总之[，,]?.*?(?:总结|概括|回顾)",
        r"\n[（(]?In\s+summary[,.]?\s*",
        r"\n[（(]?To\s+summarize[,.]?\s*",
        r"\n[（(]?In\s+conclusion[,.]?\s*",
        r"\n[（(]?Overall[,.]?\s*",
    ]
    for pattern in summary_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            if m.start() >= len(text) * 0.6:
                return text[: m.start()].rstrip()
    return text


# ---------------------------------------------------------------------------
# 后处理 — 去重
# ---------------------------------------------------------------------------

def _deduplicate_repetition(text: str) -> str:
    """检测并移除译文中的循环重复内容（行级 + 句级）。"""
    if not text or len(text) < 300:
        return text

    line_result = _deduplicate_line_repetition(text)
    if len(line_result) < len(text) * 0.7:
        return line_result

    sentences = re.split(r"(?<=[。！？])", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) < 6:
        return text

    text_len = len(sentences)
    for unit_size in range(1, text_len // 2 + 1):
        if text_len < unit_size * 3:
            break
        unit = sentences[:unit_size]
        is_repetitive = True
        repeat_count = 0
        for i in range(unit_size, text_len, unit_size):
            chunk = sentences[i : i + unit_size]
            if not chunk:
                continue
            if not _is_similar_sentences(unit, chunk):
                is_repetitive = False
                break
            repeat_count += 1

        if is_repetitive and repeat_count >= 2:
            return "".join(unit)

    return text


def _deduplicate_line_repetition(text: str) -> str:
    """行级重复检测: 在文本任意位置检测连续重复的行块。"""
    lines = text.split("\n")
    if len(lines) < 8:
        return text

    for start in range(len(lines)):
        for pat_size in range(1, 5):
            if start + pat_size * 4 > len(lines):
                break

            pattern = [l.strip() for l in lines[start : start + pat_size]]
            if all(not p for p in pattern):
                continue
            avg_len = sum(len(p) for p in pattern) / pat_size
            if avg_len < 5:
                continue

            repeat_count = 0
            pos = start + pat_size
            while pos + pat_size <= len(lines):
                chunk = [l.strip() for l in lines[pos : pos + pat_size]]
                if _lines_match(pattern, chunk):
                    repeat_count += 1
                    pos += pat_size
                else:
                    break

            if repeat_count >= 3:
                kept = lines[: start + pat_size]
                remaining = lines[pos:]
                if remaining:
                    non_empty = sum(1 for l in remaining if l.strip())
                    if non_empty > 3:
                        kept.extend(remaining)
                return "\n".join(kept)

    return text


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _lines_match(a: list[str], b: list[str]) -> bool:
    """判断两组行是否高度相似（80% 字符相同）"""
    if len(a) != len(b):
        return False
    for la, lb in zip(a, b):
        if not la and not lb:
            continue
        if not la or not lb:
            return False
        shorter = min(len(la), len(lb))
        check_len = max(int(shorter * 0.8), 1)
        match = sum(1 for ca, cb in zip(la[:check_len], lb[:check_len]) if ca == cb)
        if match / check_len < 0.7:
            return False
    return True


def _is_similar_sentences(a: list[str], b: list[str]) -> bool:
    """判断两组句子是否高度相似（允许轻微差异）"""
    if len(a) != len(b):
        return False
    for sa, sb in zip(a, b):
        if not sa or not sb:
            continue
        shorter = min(len(sa), len(sb))
        longer = max(len(sa), len(sb))
        if longer == 0:
            continue
        check_len = int(shorter * 0.8)
        if check_len == 0:
            continue
        match = sum(1 for ca, cb in zip(sa[:check_len], sb[:check_len]) if ca == cb)
        if match / check_len < 0.7:
            return False
    return True


# ---------------------------------------------------------------------------
# 段落恢复
# ---------------------------------------------------------------------------

def _restore_paragraphs(original: str, translated: str) -> str:
    """译文缺少段落分隔时，按原文段落比例恢复 \\n\\n 分段。"""
    orig_paras = [p.strip() for p in original.split("\n\n") if p.strip()]
    trans_paras = [p.strip() for p in translated.split("\n\n") if p.strip()]

    if len(orig_paras) <= 1 or len(trans_paras) <= 1:
        return translated

    # 计算原文各段字符数比例
    orig_lens = [len(p) for p in orig_paras]
    total_orig = sum(orig_lens)
    if total_orig == 0:
        return translated

    # 找出译文中已经天然有段落分隔的位置（保留）
    trans_text = translated
    if "\n\n" not in translated:
        # 按原文段落数均分译文
        trans_lens = [len(p) for p in trans_paras]
        total_trans = sum(trans_lens)
        if total_trans == 0:
            return translated

        result: list[str] = []
        acc = 0
        target_acc = 0
        for i, orig_len in enumerate(orig_lens):
            target_acc += orig_len / total_orig * total_trans
            boundary = int(target_acc)
            chunk = translated[acc:boundary]
            result.append(chunk)
            acc = boundary

        # 最后一段包含剩余内容
        result.append(translated[acc:])
        trans_text = "\n\n".join(result)

    return trans_text