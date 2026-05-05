"""命题提取与逻辑重建 — CN→EN 翻译前的结构化预处理。

借鉴 nature-polishing Chinese-to-English mode 的核心原则：
- 先提取核心命题，不逐句机械翻译
- 显式重建逻辑连接（对比/因果/含义/局限）
- 保持关键术语稳定
- 验证术语、因果、hedging、学科细微差异

这个模块在 chunker → translator 之间运行，输出增强后的翻译提示。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── 中文逻辑连接词模式 ────────────────────────────────────────────────────────

# (中文模式, 英文对应连接词, 逻辑类型)
_LOGIC_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # 因果
    (re.compile(r"(?:因此|所以|因而|故此|由此可见)"), "therefore / thus", "cause-effect"),
    (re.compile(r"(?:由于|因为|鉴于)"), "because / since / given that", "cause-effect"),
    (re.compile(r"(?:导致|引起|造成|引发|触发)"), "lead to / cause / trigger", "cause-effect"),
    (re.compile(r"(?:归因于|源于|取决于)"), "attributed to / stem from / depend on", "cause-effect"),
    # 对比/转折
    (re.compile(r"(?:然而|但是|可是|不过|却)"), "however / nevertheless / yet", "contrast"),
    (re.compile(r"(?:与此相反|相比之下|反之|相反)"), "in contrast / conversely", "contrast"),
    (re.compile(r"(?:尽管|虽然|即使|纵然)"), "although / despite / even though", "concession"),
    (re.compile(r"(?:而(?!且|后|是|已|将))"), "whereas / while", "contrast"),
    # 递进/补充
    (re.compile(r"(?:此外|另外|不仅如此|再者|况且)"), "furthermore / moreover / in addition", "addition"),
    (re.compile(r"(?:同时|与此同时)"), "meanwhile / at the same time", "addition"),
    # 含义/推论
    (re.compile(r"(?:这意味着|这说明|这暗示|这表明|由此可见)"), "this suggests / this indicates / implying that", "implication"),
    (re.compile(r"(?:换言之|换句话说|也就是说)"), "in other words / that is", "clarification"),
    # 局限/让步
    (re.compile(r"(?:需要注意的是|应当指出|必须承认)"), "it should be noted that / it must be acknowledged that", "limitation"),
    (re.compile(r"(?:然而.*局限|尽管.*但|不过.*仍)"), "", "limitation"),
    (re.compile(r"(?:尚需|仍有待|还需|有待于)"), "remains to be / requires further", "future-work"),
    # 条件/假设
    (re.compile(r"(?:如果|假如|倘若|若|如)"), "if / provided that / in the case of", "condition"),
    (re.compile(r"(?:除非)"), "unless", "condition"),
]


@dataclass
class Proposition:
    """一个提取出的核心命题"""
    text: str
    logic_type: str = ""          # cause-effect / contrast / implication / limitation / addition
    connector_cn: str = ""        # 中文连接词
    connector_en: str = ""        # 建议英文连接词
    key_terms: list[str] = field(default_factory=list)  # 关键术语
    needs_hedging: bool = False   # 是否需要软化


@dataclass
class ExtractedLogic:
    """从中文段落提取的逻辑结构"""
    propositions: list[Proposition] = field(default_factory=list)
    dominant_logic: str = ""      # 主要逻辑类型
    has_explicit_causality: bool = False
    has_contrast: bool = False
    has_limitation: bool = False
    key_terms_global: list[str] = field(default_factory=list)


def extract_propositions(text: str) -> ExtractedLogic:
    """从中文文本中提取核心命题和逻辑结构。

    Args:
        text: 待分析的中文文本

    Returns:
        ExtractedLogic 包含提取的命题和逻辑关系
    """
    result = ExtractedLogic()

    # 按句号/分号粗分句子
    sentences = re.split(r'(?<=[。；！？])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    logic_type_counts: dict[str, int] = {}

    for sent in sentences:
        prop = Proposition(text=sent)

        # 检测逻辑连接词
        for pattern, en_connector, logic_type in _LOGIC_PATTERNS:
            m = pattern.search(sent)
            if m:
                prop.logic_type = logic_type
                prop.connector_cn = m.group()
                prop.connector_en = en_connector
                logic_type_counts[logic_type] = logic_type_counts.get(logic_type, 0) + 1

                if logic_type == "cause-effect":
                    result.has_explicit_causality = True
                elif logic_type == "contrast" or logic_type == "concession":
                    result.has_contrast = True
                elif logic_type == "limitation" or logic_type == "future-work":
                    result.has_limitation = True
                break  # 每个句子只取第一个匹配的逻辑

        result.propositions.append(prop)

    # 确定主导逻辑类型
    if logic_type_counts:
        result.dominant_logic = max(logic_type_counts, key=logic_type_counts.get)

    return result


def build_logic_aware_prompt(
    text: str,
    extracted: ExtractedLogic,
    target_lang: str = "en",
) -> str:
    """生成包含逻辑重建指令的翻译提示。

    Args:
        text: 原文
        extracted: 提取的逻辑结构
        target_lang: 目标语言

    Returns:
        增强后的翻译提示
    """
    parts: list[str] = []

    # 1. 逻辑结构提示
    if extracted.has_explicit_causality:
        parts.append(
            "[LOGIC: CAUSALITY] "
            "This text contains explicit cause-effect relationships. "
            "Make these causal links clear in the translation using "
            "'therefore', 'thus', 'lead to', 'because', 'consequently', etc. "
            "Do not weaken causal claims unless the original does so."
        )

    if extracted.has_contrast:
        parts.append(
            "[LOGIC: CONTRAST] "
            "This text contains contrast or comparison. "
            "Use 'however', 'in contrast', 'whereas', 'by contrast', "
            "'nevertheless' to make the contrast explicit."
        )

    if extracted.has_limitation:
        parts.append(
            "[LOGIC: LIMITATION] "
            "This text contains limitation or boundary statements. "
            "Translate these carefully — do not soften or remove limitations. "
            "Use 'should be interpreted with caution', 'a limitation is', "
            "'remains to be determined', etc."
        )

    if extracted.dominant_logic:
        parts.append(f"[DOMINANT LOGIC] The dominant rhetorical move is: {extracted.dominant_logic}")

    # 2. 命题结构提示
    prop_count = len(extracted.propositions)
    if prop_count > 1:
        parts.append(
            f"[PROPOSITION COUNT] This text contains approximately {prop_count} "
            "propositions. Ensure each proposition is clearly expressed in the translation. "
            "Do not merge distinct propositions into a single sentence."
        )

    # 3. 组装
    logic_instruction = "\n".join(parts)
    return f"{logic_instruction}\n\n[请翻译以下内容]\n{text}" if parts else f"[请翻译以下内容]\n{text}"


# ── 术语稳定性检查 ────────────────────────────────────────────────────────────

def extract_key_terms_cn(text: str) -> list[str]:
    """从中文文本中提取关键术语（用于保持翻译一致性）。

    策略：识别大写英文缩写、引号内的术语、括号内的英文对应词。
    """
    terms: list[str] = []

    # 英文缩写 (如 RNA, DNA, LSTM, BERT)
    for m in re.finditer(r'\b[A-Z]{2,}(?:\s*-\s*\d+)?\b', text):
        terms.append(m.group())

    # 中文引号内的术语
    for m in re.finditer(r'[「「]([^」」]{2,20})[」」]', text):
        terms.append(m.group(1))

    # 带英文括号的术语：中文(English)
    for m in re.finditer(r'([一-鿿\w]{1,20})[（(]([A-Za-z][A-Za-z\s\-/]{1,30})[）)]', text):
        terms.append(f"{m.group(1)}({m.group(2)})")

    return list(dict.fromkeys(terms))  # 去重保序


def check_term_consistency(
    current_text: str,
    previous_terms: dict[str, str],
) -> dict[str, str]:
    """检查当前段落中的术语是否与已确定的术语翻译一致。

    Returns:
        {术语: 建议翻译} 映射，仅包含不一致的术语
    """
    current_terms = set(extract_key_terms_cn(current_text))
    inconsistencies: dict[str, str] = {}

    for term in current_terms:
        if term in previous_terms:
            inconsistencies[term] = previous_terms[term]

    return inconsistencies
