"""翻译后 QA — 单元测试"""
from __future__ import annotations

import pytest
from src.translator.post_qa import (
    QAFlag,
    QAResult,
    check_overclaim,
    check_sentence_length,
    check_results_discussion_mixing,
    check_verb_strength,
    get_hedging_tier_for_section,
    run_post_translation_qa,
)


class TestCheckOverclaim:
    """check_overclaim() — 过度宣称词检测"""

    def test_detects_prove_as_overclaim(self) -> None:
        flags = check_overclaim("Our results prove that the hypothesis is correct.")
        assert len(flags) >= 1
        assert flags[0].type == "overclaim"

    def test_detects_first_as_overclaim(self) -> None:
        flags = check_overclaim("This is the first study to demonstrate this effect.")
        assert len(flags) >= 1
        assert any("first" in f.message.lower() for f in flags)

    def test_detects_completely_as_overclaim(self) -> None:
        flags = check_overclaim("The mechanism is completely understood.")
        assert len(flags) >= 1

    def test_detects_superior_as_overclaim(self) -> None:
        flags = check_overclaim("Our approach is superior to existing methods.")
        assert len(flags) >= 1

    def test_allows_show_without_flag(self) -> None:
        flags = check_overclaim("Our data show a strong correlation.")
        assert len(flags) == 0

    def test_allows_suggest_without_flag(self) -> None:
        flags = check_overclaim("These findings suggest a novel pathway.")
        assert len(flags) == 0

    def test_returns_qaflag_objects(self) -> None:
        flags = check_overclaim("We prove this conclusively.")
        for f in flags:
            assert isinstance(f, QAFlag)

    def test_each_flag_has_required_fields(self) -> None:
        flags = check_overclaim("We prove this conclusively.")
        for f in flags:
            assert f.type == "overclaim"
            assert f.severity in ("warning", "error", "info")
            assert len(f.message) > 0
            assert len(f.location) > 0

    def test_empty_text_no_flags(self) -> None:
        flags = check_overclaim("")
        assert len(flags) == 0


class TestCheckSentenceLength:
    """check_sentence_length() — 句子长度检查"""

    def test_flags_sentence_over_30_words(self) -> None:
        long_sentence = " ".join([f"word{i}" for i in range(35)])
        flags = check_sentence_length(long_sentence)
        assert len(flags) >= 1
        assert flags[0].type == "sentence_length"

    def test_allows_short_sentence(self) -> None:
        flags = check_sentence_length("Short sentence.")
        assert len(flags) == 0

    def test_allows_30_word_sentence(self) -> None:
        sentence = " ".join([f"word{i}" for i in range(30)])
        flags = check_sentence_length(sentence)
        assert len(flags) == 0

    def test_flags_long_sentence_in_paragraph(self) -> None:
        long = " ".join([f"word{i}" for i in range(40)])
        text = f"Short intro. {long}"
        flags = check_sentence_length(text)
        assert len(flags) >= 1


class TestCheckResultsDiscussionMixing:
    """check_results_discussion_mixing() — Results/Discussion 混用检测"""

    def test_allows_observation_in_results(self) -> None:
        text = "We observed a 2.5-fold increase in luciferase activity."
        flags = check_results_discussion_mixing(text, section_type="results")
        assert len(flags) == 0

    def test_returns_empty_for_non_results(self) -> None:
        text = "This demonstrates that the mechanism involves phosphorylation."
        flags = check_results_discussion_mixing(text, section_type="discussion")
        # Discussion section should tolerate interpretive language
        assert len(flags) == 0


class TestCheckVerbStrength:
    """check_verb_strength() — 动词强度校准"""

    def test_returns_flags_list(self) -> None:
        flags = check_verb_strength(
            "This finding proves the hypothesis.",
            expected_tier="moderate",
        )
        assert isinstance(flags, list)

    def test_no_flags_for_matching_tier(self) -> None:
        flags = check_verb_strength(
            "These data suggest a possible mechanism.",
            expected_tier="moderate",
        )
        assert len(flags) == 0


class TestHedgingTiers:
    """get_hedging_tier_for_section()"""

    def test_results_is_strong(self) -> None:
        assert get_hedging_tier_for_section("results") == "strong"

    def test_discussion_is_moderate(self) -> None:
        assert get_hedging_tier_for_section("discussion") == "moderate"

    def test_introduction_is_moderate(self) -> None:
        assert get_hedging_tier_for_section("introduction") == "moderate"

    def test_unknown_defaults_to_moderate(self) -> None:
        assert get_hedging_tier_for_section("unknown") == "moderate"


class TestRunPostTranslationQA:
    """run_post_translation_qa() — 综合 QA"""

    def test_returns_qaresult(self) -> None:
        result = run_post_translation_qa("We observed a significant increase.")
        assert isinstance(result, QAResult)
        assert isinstance(result.flags, list)
        assert isinstance(result.score, int)

    def test_score_between_0_and_100(self) -> None:
        result = run_post_translation_qa("Clean observation with proper hedging.")
        assert 0 <= result.score <= 100

    def test_overclaim_lowers_score(self) -> None:
        clean = run_post_translation_qa("The data show an increase.")
        overclaim = run_post_translation_qa(
            "This is the first method that proves everything conclusively."
        )
        assert overclaim.score < clean.score

    def test_accepts_source_lang_cn(self) -> None:
        result = run_post_translation_qa(
            translated="我们首次证明了该机制。",
            source_lang="zh",
        )
        assert isinstance(result, QAResult)

    def test_handles_empty_translated(self) -> None:
        result = run_post_translation_qa("")
        assert result.score == 100
        assert len(result.flags) == 0
