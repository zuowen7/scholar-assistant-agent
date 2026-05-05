"""章节感知翻译 — 单元测试"""
from __future__ import annotations

import pytest
from src.translator.section_aware import (
    SectionType,
    SectionContext,
    detect_section,
    detect_section_from_heading,
    get_section_prompt,
    classify_document_type,
)


class TestSectionType:
    def test_all_section_types_exist(self) -> None:
        assert SectionType.INTRODUCTION.value == "introduction"
        assert SectionType.RESULTS.value == "results"
        assert SectionType.DISCUSSION.value == "discussion"
        assert SectionType.METHODS.value == "methods"
        assert SectionType.CONCLUSION.value == "conclusion"
        assert SectionType.ABSTRACT.value == "abstract"
        assert SectionType.REFERENCES.value == "references"
        assert SectionType.UNKNOWN.value == "unknown"

    def test_eight_types(self) -> None:
        assert len(SectionType) == 8

    def test_string_coercion(self) -> None:
        assert SectionType("results") == SectionType.RESULTS
        assert SectionType("unknown") == SectionType.UNKNOWN


class TestDetectSection:
    """detect_section(text, prev_section) — 基于文本内容的章节检测"""

    def test_returns_section_context(self) -> None:
        ctx = detect_section("Some text without a heading")
        assert isinstance(ctx, SectionContext)
        # No heading found, no prev_section → UNKNOWN, confidence 0.0
        assert ctx.section_type == SectionType.UNKNOWN
        assert ctx.confidence == 0.0

    def test_detects_results_heading(self) -> None:
        ctx = detect_section("Results\nWe observed a significant increase.")
        assert ctx.section_type == SectionType.RESULTS
        assert ctx.confidence >= 0.6

    def test_detects_introduction_heading(self) -> None:
        ctx = detect_section("Introduction\nThis paper addresses...")
        assert ctx.section_type == SectionType.INTRODUCTION
        assert ctx.confidence >= 0.6

    def test_detects_methods_heading(self) -> None:
        ctx = detect_section("Methods\nCells were cultured in DMEM.")
        assert ctx.section_type == SectionType.METHODS
        assert ctx.confidence >= 0.6

    def test_detects_discussion_heading(self) -> None:
        ctx = detect_section("Discussion\nThese findings suggest...")
        assert ctx.section_type == SectionType.DISCUSSION

    def test_detects_conclusion_heading(self) -> None:
        ctx = detect_section("Conclusion\nIn summary...")
        assert ctx.section_type == SectionType.CONCLUSION

    def test_detects_abstract_heading(self) -> None:
        ctx = detect_section("Abstract")
        assert ctx.section_type == SectionType.ABSTRACT

    def test_inherits_prev_section_when_no_heading(self) -> None:
        ctx = detect_section(
            "This paragraph continues the discussion.",
            prev_section=SectionType.DISCUSSION,
        )
        assert ctx.section_type == SectionType.DISCUSSION
        assert ctx.confidence == 0.5

    def test_heading_overrides_prev_section(self) -> None:
        ctx = detect_section(
            "Results\nWe found...",
            prev_section=SectionType.METHODS,
        )
        assert ctx.section_type == SectionType.RESULTS


class TestDetectSectionFromHeading:
    """detect_section_from_heading() — 基于标题关键词的章节检测"""

    def test_introduction(self) -> None:
        ctx = detect_section_from_heading("Introduction")
        assert ctx.section_type == SectionType.INTRODUCTION
        assert ctx.confidence == 0.9

    def test_results_and_discussion(self) -> None:
        ctx = detect_section_from_heading("Results and Discussion")
        assert ctx.section_type == SectionType.RESULTS
        assert ctx.confidence == 0.9

    def test_materials_and_methods(self) -> None:
        ctx = detect_section_from_heading("Materials and Methods")
        assert ctx.section_type == SectionType.METHODS

    def test_conclusion(self) -> None:
        ctx = detect_section_from_heading("Conclusion")
        assert ctx.section_type == SectionType.CONCLUSION

    def test_abstract(self) -> None:
        ctx = detect_section_from_heading("Abstract")
        assert ctx.section_type == SectionType.ABSTRACT

    def test_references(self) -> None:
        ctx = detect_section_from_heading("References")
        assert ctx.section_type == SectionType.REFERENCES

    def test_case_insensitive(self) -> None:
        ctx = detect_section_from_heading("results")
        assert ctx.section_type == SectionType.RESULTS

    def test_unknown_for_arbitrary_text(self) -> None:
        ctx = detect_section_from_heading("Random Non-Section Text 123")
        assert ctx.section_type == SectionType.UNKNOWN
        assert ctx.confidence == 0.0

    def test_empty_heading(self) -> None:
        ctx = detect_section_from_heading("")
        assert ctx.section_type == SectionType.UNKNOWN
        assert ctx.confidence == 0.0


class TestGetSectionPrompt:
    """get_section_prompt() — 每种章节类型的翻译指令"""

    def test_introduction_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.INTRODUCTION)
        assert "INTRODUCTION" in prompt
        assert len(prompt) > 50

    def test_results_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.RESULTS)
        assert "RESULTS" in prompt

    def test_discussion_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.DISCUSSION)
        assert "DISCUSSION" in prompt

    def test_methods_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.METHODS)
        assert "METHODS" in prompt

    def test_conclusion_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.CONCLUSION)
        assert "CONCLUSION" in prompt

    def test_abstract_prompt(self) -> None:
        prompt = get_section_prompt(SectionType.ABSTRACT)
        assert "ABSTRACT" in prompt

    def test_unknown_returns_empty_string(self) -> None:
        prompt = get_section_prompt(SectionType.UNKNOWN)
        assert prompt == ""

    def test_all_known_types_return_non_empty_strings(self) -> None:
        for st in SectionType:
            if st == SectionType.UNKNOWN:
                continue
            prompt = get_section_prompt(st)
            assert isinstance(prompt, str)
            assert len(prompt) > 0, f"{st} prompt is empty"


class TestClassifyDocumentType:
    """classify_document_type(text) — 文档类型分类"""

    def test_returns_string(self) -> None:
        result = classify_document_type("Some plain text.")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_detects_methods_paper(self) -> None:
        text = (
            "We developed a novel method for detecting protein interactions. "
            "The protocol consists of the following steps: first, cells are lysed..."
        )
        result = classify_document_type(text)
        assert result in ("research_paper", "methods_paper", "review", "unknown")

    def test_detects_review_paper(self) -> None:
        text = (
            "In this review, we summarize recent advances in the field. "
            "We survey key findings from multiple studies spanning the last decade."
        )
        result = classify_document_type(text)
        assert result in ("research_paper", "methods_paper", "review", "unknown")

    def test_empty_text(self) -> None:
        result = classify_document_type("")
        assert result in ("research_paper", "methods_paper", "review", "unknown")
