"""句法感知切块 — 在句子内按从句/分句边界二次切分"""

from __future__ import annotations

import re


# English clause/subordinate conjunction patterns
_EN_CLAUSE_CONNECTORS = [
    r"\bwhich\b", r"\bthat\b", r"\bwhere\b", r"\bwhen\b",
    r"\bbecause\b", r"\balthough\b", r"\bwhile\b", r"\bif\b",
    r"\bsince\b", r"\bunless\b", r"\bafter\b", r"\bbefore\b",
    r"\bthough\b", r"\bas\b", r"\bonce\b",
    r"\bhowever\b", r"\btherefore\b", r"\bfurthermore\b",
    r"\bmoreover\b", r"\bnevertheless\b", r"\bconsequently\b",
    r"\bspecifically\b", r"\bparticularly\b", r"\badditionally\b",
    r"\bcompared\b", r"\bhowever\b", r"\boverall\b",
]
_EN_PATTERN = "|".join(_EN_CLAUSE_CONNECTORS)

# Chinese clause separators (全角标点 + 复合虚词)
_CN_SEPARATORS = [
    "；", "：",
    "，但是", "，然而", "，因此", "，所以",
    "，并且", "，而且", "，同时", "，此外",
    "，由于", "，既然", "，虽然", "，即使",
    "，如果", "，只要", "，除非",
    "，于是", "，从而", "，故",
]


def _is_inside_paren(text: str, pos: int) -> bool:
    """检查位置 pos 是否在括号对内部"""
    depth = 0
    i = 0
    while i < len(text) and i < pos:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth = max(0, depth - 1)
        i += 1
    return depth > 0


def _split_long_sentence(text: str, max_chars: int) -> list[str]:
    """对超长句子在从句边界二次切分，返回子句列表

    策略:
    - 括号 (...) 内不切分
    - 数字格式 "10.5" 不触发切分
    - 只在自然停顿点（逗号/分号+空格、连接词）切分
    """
    if len(text) <= max_chars:
        return [text]

    # 预保护: 数字+句号格式
    protected: list[str] = []
    def _dig(m):
        idx = len(protected)
        protected.append(m.group(0))
        return f"\x00D{idx}\x00"
    t = re.sub(r"\d+\.\d+", _dig, text)

    candidates: dict[int, str] = {}

    # English clause connectors (不在括号内，前面有自然停顿)
    for m in re.finditer(_EN_PATTERN, t, re.IGNORECASE):
        pos = m.start()
        if _is_inside_paren(t, pos):
            continue
        before = t[max(0, pos - 2):pos]
        if before and re.match(r"[，;,\s]", before[-1]):
            candidates[pos] = m.group(0)

    # Chinese clause separators
    for sep in _CN_SEPARATORS:
        for m in re.finditer(re.escape(sep), t):
            if not _is_inside_paren(t, m.start()):
                candidates[m.start()] = sep

    # 英文逗号/分号 + 空格 + 大写字母（自然停顿）
    for m in re.finditer(r"[;,](?=\s+[A-Z])", t):
        if not _is_inside_paren(t, m.start()):
            candidates[m.start()] = m.group(0)

    if not candidates:
        # 无法找到切分点，返回原句（可能超限但已尽力）
        return [text]

    # 还原数字占位符
    def _restore(s: str) -> str:
        for i in range(len(protected) - 1, -1, -1):
            s = s.replace(f"\x00D{i}\x00", protected[i])
        return s

    # 在切分点切分
    positions = sorted(candidates.keys())
    parts: list[str] = []
    prev = 0
    for pos in positions:
        sub = t[prev:pos].strip()
        if sub:
            parts.append(_restore(sub))
        prev = pos
    last = t[prev:].strip()
    if last:
        parts.append(_restore(last))

    # 递归: 子句仍超限时继续切
    result: list[str] = []
    for part in parts:
        if len(part) > max_chars:
            result.extend(_split_long_sentence(part, max_chars))
        else:
            result.append(part)

    return [p for p in result if p.strip()]
