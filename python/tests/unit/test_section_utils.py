"""Phase 3 TDD — section_utils unit tests."""

from __future__ import annotations

import pytest

from src.argument.section_utils import find_section, split_paragraphs, has_contrast_marker


# ── find_section ─────────────────────────────────────────────────────────────

SAMPLE_PAPER = """\
# Abstract

This paper proposes a new method for X. We show that Y improves performance by 30%.

# Introduction

Many researchers have studied Y. However, existing methods suffer from Z.
Our approach addresses this gap by introducing W.

## Related Work

Smith (2022) did A. Jones (2023) did B. However, none of them considered C.

# Methodology

We propose the following approach: ...

# Experiments

We evaluate on dataset D with metric M.

# Conclusion

In this paper, we demonstrated that our method achieves state-of-the-art performance.
"""

CHINESE_PAPER = """\
# 摘要

本文提出了一种新方法。我们证明了Y能提升30%的性能。

# 引言

许多研究者已经研究了Y。然而，现有方法存在Z的问题。

## 相关工作

Smith（2022）做了A。Jones（2023）做了B。然而，他们没有考虑C。

# 方法

我们提出了以下方案：...

# 实验

我们在数据集D上评估了指标M。

# 结论

本文证明了我们的方法达到了最先进的性能。
"""

NO_HEADINGS_PAPER = """\
This paper proposes a new method for X. We show that Y improves performance by 30%.
Many researchers have studied Y. However, existing methods suffer from Z.
We propose the following approach.
We evaluate on dataset D.
In conclusion, we demonstrated that our method achieves state-of-the-art performance.
"""


class TestFindSection:
    def test_finds_abstract_english(self):
        text = find_section(SAMPLE_PAPER, ["abstract"])
        assert text is not None
        assert "This paper proposes" in text

    def test_finds_introduction_english(self):
        text = find_section(SAMPLE_PAPER, ["introduction"])
        assert text is not None
        assert "Many researchers" in text

    def test_finds_conclusion_english(self):
        text = find_section(SAMPLE_PAPER, ["conclusion"])
        assert text is not None
        assert "demonstrated" in text

    def test_finds_related_work_english(self):
        text = find_section(SAMPLE_PAPER, ["related work", "related-work"])
        assert text is not None
        assert "Smith" in text

    def test_finds_abstract_chinese(self):
        text = find_section(CHINESE_PAPER, ["摘要", "abstract"])
        assert text is not None
        assert "新方法" in text

    def test_finds_introduction_chinese(self):
        text = find_section(CHINESE_PAPER, ["引言", "introduction"])
        assert text is not None
        assert "许多研究者" in text

    def test_finds_conclusion_chinese(self):
        text = find_section(CHINESE_PAPER, ["结论", "conclusion"])
        assert text is not None
        assert "证明" in text

    def test_finds_related_work_chinese(self):
        text = find_section(CHINESE_PAPER, ["相关工作", "related work"])
        assert text is not None
        assert "Smith" in text

    def test_returns_none_when_section_not_found(self):
        text = find_section(SAMPLE_PAPER, ["nonexistent_section_xyz"])
        assert text is None

    def test_fallback_for_no_headings(self):
        # No matching headings → return first ~25% of text (or None, acceptable)
        text = find_section(NO_HEADINGS_PAPER, ["abstract"])
        # Either None or first portion of text; both are acceptable per spec
        # The important thing is no crash
        assert isinstance(text, (str, type(None)))

    def test_section_stops_before_next_heading(self):
        text = find_section(SAMPLE_PAPER, ["introduction"])
        # Should not contain content from Methodology
        assert "We propose the following approach" not in text

    def test_case_insensitive(self):
        text = find_section(SAMPLE_PAPER, ["ABSTRACT"])
        assert text is not None
        assert "This paper proposes" in text


# ── split_paragraphs ──────────────────────────────────────────────────────────

class TestSplitParagraphs:
    def test_splits_by_blank_lines(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        paras = split_paragraphs(text)
        assert len(paras) == 3

    def test_strips_empty_strings(self):
        text = "\n\nFirst.\n\n\n\nSecond.\n\n"
        paras = split_paragraphs(text)
        assert all(p.strip() for p in paras)

    def test_single_paragraph(self):
        text = "Just one paragraph with no blank lines."
        paras = split_paragraphs(text)
        assert len(paras) == 1

    def test_empty_string(self):
        paras = split_paragraphs("")
        assert paras == []


# ── has_contrast_marker ───────────────────────────────────────────────────────

class TestHasContrastMarker:
    @pytest.mark.parametrize("text", [
        "However, our method is different.",
        "In contrast to previous work, we propose...",
        "Unlike Smith (2022), our approach...",
        "Whereas existing methods fail, ours succeeds.",
        "But existing approaches lack X.",
        "然而，我们的方法不同。",
        "与此不同，我们提出...",
        "相比之下，本文方法...",
        "前人工作主要关注A，而本文聚焦B。",
    ])
    def test_detects_contrast_markers(self, text: str):
        assert has_contrast_marker(text) is True

    @pytest.mark.parametrize("text", [
        "Smith (2022) proposed method A for task B.",
        "Jones (2023) achieved 90% accuracy on dataset D.",
        "Liu (2021) extended the framework to handle multi-modal inputs.",
        "Previous methods use attention mechanisms.",
    ])
    def test_no_false_positives_on_plain_summaries(self, text: str):
        assert has_contrast_marker(text) is False

    def test_empty_string(self):
        assert has_contrast_marker("") is False
