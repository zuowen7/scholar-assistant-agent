"""翻译后质量保证 — 借鉴 nature-polishing style-guardrails 的机械化检查。

检查项：
1. 过度宣称词检测 (overclaim) — 自动标黄译文中可能过强的断言
2. 句子长度检查 — 标记超过 30 词的句子
3. Results/Discussion 语法混用检测
4. 动词强度校准 — 根据证据强度建议替换动词
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ── 过度宣称词列表 ───────────────────────────────────────────────────────────

_OVERCLAIM_PATTERNS: list[tuple[str, str, str]] = [
    # (英文模式, 中文模式, 建议替换)
    ("prove", r"证明|证实", "show / demonstrate / 表明 / 显示"),
    ("conclusively", r"确定无疑地|终局性地", "最终 / in conclusion"),
    ("unprecedented", r"前所未有|史无前例|空前", "to our knowledge / 据我们所知"),
    (r"\bfirst\b(?!\s+(?:author|author's|two|three|step|stage|line|round|half|quarter|year|order|edition|page|name))",
     r"\b第一(?:次|个)\b(?!作者|作者|步|阶段|行|轮|年|页)", "initial / early / 首次 / among the first"),
    (r"\bbest\b(?!\s+(?:of|practice|fit|known|effort|performing|result|performance|possible|available))",
     r"\b最好|最佳\b(?!实践|拟合)", "strong / leading / among the strongest / 领先的"),
    (r"\bsuperior\b", r"\b优越(?:的)?\b", "advantageous / favorable / 有利的"),
    ("completely", r"完全|彻底", ""),
    ("totally", r"完全|彻底地", ""),
    ("always", r"总是|始终|永远", "typically / generally / 通常"),
    ("never", r"从不|永不|绝不", "rarely / 极少"),
    ("absolutely", r"绝对(?:地)?", ""),
    ("undoubtedly", r"毫无疑问地", "likely / 很可能"),
    ("certainly", r"肯定地|必然地", "appears to / 似乎"),
]


@dataclass
class QAFlag:
    """QA 检查标志"""
    type: str  # overclaim / sentence_length / mixed_tense / hedging
    severity: str  # warning / suggestion
    location: str  # 定位文本片段
    message: str  # 中文说明
    suggestion: str = ""  # 建议修改


@dataclass
class QAResult:
    """QA 检查结果"""
    flags: list[QAFlag] = field(default_factory=list)
    score: int = 100  # 0-100, 扣分制

    @property
    def has_warnings(self) -> bool:
        return len(self.flags) > 0

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "warning")

    @property
    def suggestion_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "suggestion")


# ── 检查函数 ─────────────────────────────────────────────────────────────────

def check_overclaim(text: str, source_lang: str = "en") -> list[QAFlag]:
    """检测译文中的过度宣称词"""
    flags: list[QAFlag] = []

    for en_pat, zh_pat, suggestion in _OVERCLAIM_PATTERNS:
        # 英文检测
        if source_lang != "zh":
            for m in re.finditer(en_pat, text, re.IGNORECASE):
                ctx_start = max(0, m.start() - 30)
                ctx_end = min(len(text), m.end() + 30)
                ctx = text[ctx_start:ctx_end].replace("\n", " ")
                flags.append(QAFlag(
                    type="overclaim",
                    severity="warning",
                    location=f"...{ctx}...",
                    message=f"检测到可能过度宣称的词: '{m.group()}'",
                    suggestion=f"建议替换为: {suggestion}" if suggestion else "建议软化表述",
                ))

        # 中文检测
        if source_lang != "en" and zh_pat:
            for m in re.finditer(zh_pat, text):
                ctx_start = max(0, m.start() - 15)
                ctx_end = min(len(text), m.end() + 15)
                ctx = text[ctx_start:ctx_end]
                flags.append(QAFlag(
                    type="overclaim",
                    severity="warning",
                    location=f"...{ctx}...",
                    message=f"中文检测到可能过度宣称的词: '{m.group()}'",
                    suggestion=f"建议替换为: {suggestion}" if suggestion else "建议软化表述",
                ))

    return flags


def check_sentence_length(text: str, max_words: int = 30) -> list[QAFlag]:
    """检查句子长度（英语以空格分词，中文以标点分句后按字符估算）"""
    flags: list[QAFlag] = []

    # 按句子分割
    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        # 英文: 按空格分词
        words = sent.split()
        word_count = len(words)

        # 中文: 粗略按字符数/2 估算词数
        cjk_chars = sum(1 for c in sent if '一' <= c <= '鿿')
        if cjk_chars > len(words) * 0.5:
            word_count = max(word_count, cjk_chars // 2)

        if word_count > max_words:
            flags.append(QAFlag(
                type="sentence_length",
                severity="suggestion",
                location=sent[:80] + ("..." if len(sent) > 80 else ""),
                message=f"句子过长 ({word_count} 词, 建议 ≤ {max_words})",
                suggestion="考虑拆分为两个或多个短句，或检查是否包含多个命题",
            ))

    return flags


def check_results_discussion_mixing(
    text: str,
    section_type: str = "unknown",
) -> list[QAFlag]:
    """检测 Results 和 Discussion 语法是否混用"""
    flags: list[QAFlag] = []

    results_verbs = [
        r"\bwas\s+detected\b", r"\bincreased\b", r"\bshowed\b",
        r"\benabled\b", r"\bachieved\b", r"\bobserved\b",
        r"\b(?:显著|明显)(?:增加|减少|提高|降低|改善)",
        r"\b检测到\b", r"\b观察到\b",
    ]
    discussion_verbs = [
        r"\bmay\s+reflect\b", r"\bsuggests?\s+that\b",
        r"\bcould\s+indicate\b", r"\bis\s+likely\s+due\s+to\b",
        r"\bmay\s+facilitate\b", r"\bmight\s+be\s+explained\b",
        r"\b可能反映了?\b", r"\b表明.*可能\b", r"\b暗示\b",
    ]

    if section_type == "results":
        for pat in discussion_verbs:
            for m in re.finditer(pat, text, re.IGNORECASE):
                ctx = text[max(0, m.start() - 20):min(len(text), m.end() + 20)]
                flags.append(QAFlag(
                    type="mixed_tense",
                    severity="suggestion",
                    location=f"...{ctx}...",
                    message=f"Results 段落中出现 Discussion 语法: '{m.group()}'",
                    suggestion="Results 应报告观察结果而非解释意义，考虑移入 Discussion",
                ))

    if section_type == "discussion":
        for pat in results_verbs[:3]:  # 只检查最显著的几个
            for m in re.finditer(pat, text, re.IGNORECASE):
                flags.append(QAFlag(
                    type="mixed_tense",
                    severity="suggestion",
                    location=f"...{text[max(0,m.start()-20):min(len(text),m.end()+20)]}...",
                    message=f"Discussion 段落中出现纯报告语法: '{m.group()}'",
                    suggestion="Discussion 应解释含义而非仅复述结果",
                ))

    return flags


# ── 动词强度校准 ─────────────────────────────────────────────────────────────

# 三级动词体系（来自 nature-polishing phrasebank-playbook）
_HEDGING_TIERS: dict[str, list[str]] = {
    "strong": ["show", "demonstrate", "establish", "reveal", "identify",
               "证明", "表明", "确立", "揭示", "鉴定"],
    "moderate": ["suggest", "indicate", "support the view that",
                 "are consistent with", "point to",
                 "提示", "指示", "支持", "与...一致", "指向"],
    "speculative": ["may reflect", "could arise from", "appears to",
                    "seems likely", "might be explained by",
                    "可能反映", "可能源于", "似乎", "很可能", "可能被解释为"],
}

# 中文动词到强度级别的反向映射
_CN_VERB_TIER: dict[str, str] = {}
for tier, verbs in _HEDGING_TIERS.items():
    for v in verbs:
        _CN_VERB_TIER[v] = tier

# 英文动词到强度级别的反向映射（小写）
_EN_VERB_TIER: dict[str, str] = {}
for tier, verbs in _HEDGING_TIERS.items():
    for v in verbs:
        _EN_VERB_TIER[v.lower()] = tier


def check_verb_strength(
    text: str,
    expected_tier: str = "moderate",
    source_lang: str = "en",
) -> list[QAFlag]:
    """检查译文的动词强度是否与预期匹配。

    Args:
        text: 译文
        expected_tier: 预期强度 (strong / moderate / speculative)
        source_lang: 源语言
    """
    flags: list[QAFlag] = []

    # 检查是否使用了比预期更强的动词
    tier_rank = {"speculative": 0, "moderate": 1, "strong": 2}
    expected_rank = tier_rank.get(expected_tier, 1)

    for verb, tier in _EN_VERB_TIER.items():
        tier_rank_val = tier_rank.get(tier, 1)
        if tier_rank_val > expected_rank:
            for m in re.finditer(r'\b' + re.escape(verb) + r'\b', text, re.IGNORECASE):
                ctx = text[max(0, m.start() - 20):min(len(text), m.end() + 20)]
                stronger = [v for v in _HEDGING_TIERS.get(expected_tier, [])[:3]]
                flags.append(QAFlag(
                    type="hedging",
                    severity="suggestion",
                    location=f"...{ctx}...",
                    message=f"动词 '{m.group()}' 为 {tier} 级别，当前上下文建议 {expected_tier} 级别",
                    suggestion=f"考虑替换为: {', '.join(stronger)}" if stronger else "",
                ))

    return flags


def run_post_translation_qa(
    translated: str,
    original: str = "",
    section_type: str = "unknown",
    source_lang: str = "en",
    expected_hedging_tier: str = "moderate",
) -> QAResult:
    """对单段翻译结果运行全部 QA 检查。

    Args:
        translated: 译文
        original: 原文（可选，用于对比）
        section_type: 章节类型
        source_lang: 源语言
        expected_hedging_tier: 期望的动词强度级别

    Returns:
        QAResult 包含所有检测到的 flag
    """
    result = QAResult()

    # 1. 过度宣称检查
    overclaim_flags = check_overclaim(translated, source_lang)
    result.flags.extend(overclaim_flags)
    result.score -= len(overclaim_flags) * 5

    # 2. 句子长度检查
    length_flags = check_sentence_length(translated)
    result.flags.extend(length_flags)
    result.score -= len(length_flags) * 2

    # 3. Results/Discussion 混用检查
    mixing_flags = check_results_discussion_mixing(translated, section_type)
    result.flags.extend(mixing_flags)
    result.score -= len(mixing_flags) * 3

    # 4. 动词强度校准
    if expected_hedging_tier != "strong":
        hedging_flags = check_verb_strength(translated, expected_hedging_tier, source_lang)
        result.flags.extend(hedging_flags)
        result.score -= len(hedging_flags) * 2

    result.score = max(0, result.score)
    return result


def get_hedging_tier_for_section(section_type: str) -> str:
    """根据章节类型返回推荐的动词强度级别"""
    tier_map = {
        "introduction": "moderate",
        "results": "strong",
        "discussion": "moderate",
        "methods": "strong",
        "conclusion": "moderate",
        "abstract": "moderate",
    }
    return tier_map.get(section_type, "moderate")
