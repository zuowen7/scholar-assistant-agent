"""章节感知翻译 — 根据段落所属章节类型注入不同的翻译策略指令。

借鉴 nature-polishing 的 section responsibilities 框架：
- Introduction: 建立重要性 → 指出知识缺口 → 陈述研究问题
- Results: 报告观察结果（过去时），不解释意义
- Discussion: 解释意义 + 与已有工作对比 + 声明边界
- Methods: 可复现性检查
- Conclusion: 重述贡献 + 关键证据 + 带边界的含义
- Abstract: mini-paper 结构

核心原则：翻译不仅要准确传达字面意思，还要让译文服务于对应章节的修辞任务。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class SectionType(str, Enum):
    INTRODUCTION = "introduction"
    RESULTS = "results"
    DISCUSSION = "discussion"
    METHODS = "methods"
    CONCLUSION = "conclusion"
    ABSTRACT = "abstract"
    REFERENCES = "references"
    UNKNOWN = "unknown"


# ── 章节检测关键词 ──────────────────────────────────────────────────────────

_SECTION_PATTERNS: list[tuple[SectionType, re.Pattern]] = [
    (SectionType.ABSTRACT, re.compile(
        r"^(?:abstract|摘要|概要)\s*$", re.IGNORECASE
    )),
    (SectionType.INTRODUCTION, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:introduction|引言|绪论|前言|背景|研究背景|问题提出)"
        r"|(?:\d+[\.\s]+)?(?:background|related\s*work|文献综述))",
        re.IGNORECASE,
    )),
    (SectionType.METHODS, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:methods?|materials?\s*(?:and|&)\s*methods?|实验方法|方法|材料与方法|实验部分|研究方法)"
        r"|(?:\d+[\.\s]+)?(?:experimental|implementation|实验设计|技术路线|数据来源))",
        re.IGNORECASE,
    )),
    (SectionType.RESULTS, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:results?|findings?|实验结果|结果与分析|结果|研究结果)"
        r"|(?:\d+[\.\s]+)?(?:evaluation|实验评估|性能评估))",
        re.IGNORECASE,
    )),
    (SectionType.DISCUSSION, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:discussion|讨论|分析与讨论|综合讨论|结果讨论)"
        r"|(?:\d+[\.\s]+)?(?:interpretation|implications?))",
        re.IGNORECASE,
    )),
    (SectionType.CONCLUSION, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:conclusion|总结|结论|结语|小结|展望)"
        r"|(?:\d+[\.\s]+)?(?:summary|future\s*work|concluding\s*remarks))",
        re.IGNORECASE,
    )),
    (SectionType.REFERENCES, re.compile(
        r"^(?:(?:\d+[\.\s]+)?(?:references?|bibliography|参考文献|引用文献))",
        re.IGNORECASE,
    )),
]

# ── 各章节翻译策略指令 ──────────────────────────────────────────────────────

_SECTION_PROMPTS: dict[SectionType, str] = {
    SectionType.INTRODUCTION: """
[SECTION: INTRODUCTION]
This is an INTRODUCTION section. The translation should:
- Establish why this research area matters to the reader
- Clearly signal the knowledge gap or unresolved question
- State the study's aim or approach with precision
- Use present tense for established knowledge, present perfect for gap statements
- Hedge appropriately: use "remains poorly understood" rather than "is completely unknown"
- Preserve citation markers and author-year references exactly as in the original
""",

    SectionType.RESULTS: """
[SECTION: RESULTS]
This is a RESULTS section. The translation should:
- Report observations factually — state WHAT was observed, not WHAT IT MEANS
- Use past tense predominantly ("was detected", "showed", "increased")
- Include quantitative details (p-values, effect sizes, percentages) without altering them
- Do NOT add mechanistic interpretations or discussion language
- Do NOT use hedging verbs like "may reflect" or "could indicate" unless the original does
- Reference figures and tables exactly as in the original (Fig. X, Table Y)
""",

    SectionType.DISCUSSION: """
[SECTION: DISCUSSION]
This is a DISCUSSION section. The translation should:
- Interpret findings — state WHAT THEY MEAN, not just what happened
- Use hedging appropriately: "suggest", "may reflect", "could indicate", "is likely due to"
- Compare with prior work explicitly: "consistent with", "in contrast to", "extends"
- State limitations candidly — do not soften or remove them
- Maintain the boundary between association and causation
- Keep the author's own degree of certainty — do not weaken or strengthen claims
""",

    SectionType.METHODS: """
[SECTION: METHODS]
This is a METHODS section. The translation should:
- Ensure reproducibility: another researcher should be able to repeat the work from this description
- Use past tense / passive voice as appropriate for the discipline
- Preserve exact parameters, settings, versions, model numbers, concentrations
- Do NOT translate vague phrases like "under standard conditions" literally — flag them
- Keep statistical tests and software versions exactly as in the original
- Preserve ethical approval statements verbatim if present
""",

    SectionType.CONCLUSION: """
[SECTION: CONCLUSION]
This is a CONCLUSION section. The translation should:
- Restate the central contribution clearly
- Summarize the decisive evidence without introducing new data
- State implications with a clear boundary ("in this cohort", "under these conditions")
- Run implicit overclaim check: avoid "prove", "conclusively", "unprecedented", unqualified "first"
- End with a forward-looking statement if the original does
""",

    SectionType.ABSTRACT: """
[SECTION: ABSTRACT]
This is an ABSTRACT. The translation should:
- Follow the context→gap→approach→key result→implication structure
- Be concise — every sentence must carry information weight
- Include key quantitative results if present in the original
- Avoid vague language — prefer specific findings
- Maintain the original's word budget (abstracts are often length-limited)
""",

    SectionType.REFERENCES: """
[SECTION: REFERENCES]
This is a REFERENCES section. Do NOT translate reference entries. Preserve them exactly as-is.
""",

    SectionType.UNKNOWN: "",
}


@dataclass
class SectionContext:
    """当前翻译上下文所属的章节信息"""
    section_type: SectionType = SectionType.UNKNOWN
    confidence: float = 0.0
    matched_heading: str = ""


def detect_section(
    text: str,
    prev_section: SectionType = SectionType.UNKNOWN,
) -> SectionContext:
    """检测一段文本所属的章节类型。

    策略：扫描文本开头（前500字符）寻找章节标题关键词，
    如果找不到，保持前一个章节类型（段落通常延续上一节的类型）。

    Args:
        text: 待检测的文本段落
        prev_section: 前一个段落的章节类型（用于延续）

    Returns:
        SectionContext 包含检测到的章节类型和置信度
    """
    head = text[:500].strip()

    for section_type, pattern in _SECTION_PATTERNS:
        m = pattern.search(head)
        if m:
            return SectionContext(
                section_type=section_type,
                confidence=0.85 if len(m.group()) > 5 else 0.6,
                matched_heading=m.group().strip(),
            )

    # 没有匹配到新章节标题 → 保持前一章节类型
    if prev_section != SectionType.UNKNOWN:
        return SectionContext(
            section_type=prev_section,
            confidence=0.5,
            matched_heading="",
        )

    return SectionContext()


def detect_section_from_heading(heading_text: str) -> SectionContext:
    """从标题文本检测章节类型（用于 Block type=heading 的块）"""
    for section_type, pattern in _SECTION_PATTERNS:
        m = pattern.search(heading_text.strip())
        if m:
            return SectionContext(
                section_type=section_type,
                confidence=0.9,
                matched_heading=heading_text.strip(),
            )
    return SectionContext()


def get_section_prompt(section_type: SectionType) -> str:
    """获取指定章节类型的翻译策略指令"""
    return _SECTION_PROMPTS.get(section_type, "")


def classify_document_type(text: str) -> str:
    """根据全文内容推断论文类型。

    Returns:
        论文类型标签: research_paper | methods_paper | review | unknown
    """
    head = text[:3000].lower()

    # Methods paper signals
    methods_signals = [
        "novel method", "new algorithm", "we propose", "benchmark",
        "outperforms", "state-of-the-art", "相比于", "我们的方法",
        "提出.*方法", "新.*算法", "框架.*模型",
    ]
    methods_score = sum(1 for s in methods_signals if s in head)

    # Review paper signals
    review_signals = [
        "this review", "we review", "literature review", "综述",
        "survey", "systematic review", "meta-analysis", "荟萃分析",
        "we survey", "this survey",
    ]
    review_score = sum(1 for s in review_signals if s in head)

    if review_score >= 2:
        return "review"
    if methods_score >= 3:
        return "methods_paper"
    return "research_paper"
