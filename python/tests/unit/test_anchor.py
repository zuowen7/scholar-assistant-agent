"""Phase 1 TDD — anchor.py 锚定与模糊重定位契约测试。

运行：cd python && pytest tests/unit/test_anchor.py -v
全部应当 FAIL（ImportError / NotImplementedError），实现后才能通过。
"""

from __future__ import annotations

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────


def _anchor():
    from src.argument.anchor import (
        Anchor,
        CONTEXT_CHARS,
        FUZZY_THRESHOLD,
        make_anchor,
        make_anchor_from_quote,
        relocate,
        relocate_all,
        section_path_at,
    )
    return Anchor, CONTEXT_CHARS, FUZZY_THRESHOLD, make_anchor, make_anchor_from_quote, relocate, relocate_all, section_path_at


# ── 常量契约 ─────────────────────────────────────────────────────────────────


class TestConstants:
    def test_context_chars_value(self):
        _, CONTEXT_CHARS, _, *_ = _anchor()
        assert CONTEXT_CHARS == 48

    def test_fuzzy_threshold_value(self):
        _, _, FUZZY_THRESHOLD, *_ = _anchor()
        assert FUZZY_THRESHOLD == 0.62


# ── Anchor 模型 ───────────────────────────────────────────────────────────────


class TestAnchorModel:
    def test_default_id_prefix(self):
        Anchor, *_ = _anchor()
        a = Anchor(doc_id="d1", quote="hello")
        assert a.id.startswith("a_")

    def test_default_status_is_anchored(self):
        Anchor, *_ = _anchor()
        a = Anchor(doc_id="d1", quote="hello", char_start=0, char_end=5)
        assert a.status == "anchored"

    def test_status_literal_values(self):
        Anchor, *_ = _anchor()
        for s in ("anchored", "drifted", "lost"):
            a = Anchor(doc_id="d1", quote="q", status=s)
            assert a.status == s

    def test_invalid_status_raises(self):
        Anchor, *_ = _anchor()
        with pytest.raises(Exception):
            Anchor(doc_id="d1", quote="q", status="unknown_status")

    def test_optional_fields_default_to_none(self):
        Anchor, *_ = _anchor()
        a = Anchor(doc_id="d1", quote="hello")
        assert a.char_start is None
        assert a.char_end is None
        assert a.section_path is None


# ── make_anchor ───────────────────────────────────────────────────────────────


class TestMakeAnchor:
    TEXT = "Introduction\n\nThis paper proposes a novel method. The method is efficient."

    def test_quote_equals_slice(self):
        _, _, _, make_anchor, *_ = _anchor()
        a = make_anchor("doc1", self.TEXT, 14, 46)
        assert a.quote == self.TEXT[14:46]

    def test_char_positions_stored(self):
        _, _, _, make_anchor, *_ = _anchor()
        a = make_anchor("doc1", self.TEXT, 14, 46)
        assert a.char_start == 14
        assert a.char_end == 46

    def test_context_before_captured(self):
        _, CONTEXT_CHARS, _, make_anchor, *_ = _anchor()
        text = "A" * 100 + "TARGET" + "B" * 100
        start = 100
        end = 106
        a = make_anchor("d", text, start, end)
        assert a.context_before == text[max(0, start - CONTEXT_CHARS):start]

    def test_context_after_captured(self):
        _, CONTEXT_CHARS, _, make_anchor, *_ = _anchor()
        text = "A" * 100 + "TARGET" + "B" * 100
        start = 100
        end = 106
        a = make_anchor("d", text, start, end)
        assert a.context_after == text[end:end + CONTEXT_CHARS]

    def test_doc_id_stored(self):
        _, _, _, make_anchor, *_ = _anchor()
        a = make_anchor("my_doc", self.TEXT, 0, 5)
        assert a.doc_id == "my_doc"

    def test_status_anchored(self):
        _, _, _, make_anchor, *_ = _anchor()
        a = make_anchor("d", self.TEXT, 0, 5)
        assert a.status == "anchored"


# ── make_anchor_from_quote ────────────────────────────────────────────────────


class TestMakeAnchorFromQuote:
    TEXT = "We propose a method for parsing. The parser uses dynamic programming."

    def test_exact_quote_found(self):
        _, _, _, _, make_anchor_from_quote, *_ = _anchor()
        a = make_anchor_from_quote("d", self.TEXT, "method for parsing")
        assert a.status == "anchored"
        assert a.char_start is not None
        assert self.TEXT[a.char_start:a.char_end] == "method for parsing"

    def test_quote_not_found_yields_lost(self):
        _, _, _, _, make_anchor_from_quote, *_ = _anchor()
        a = make_anchor_from_quote("d", self.TEXT, "completely absent phrase xyz999")
        assert a.status == "lost"
        assert a.char_start is None
        assert a.char_end is None

    def test_lost_anchor_preserves_quote(self):
        _, _, _, _, make_anchor_from_quote, *_ = _anchor()
        q = "xyzzy not here at all"
        a = make_anchor_from_quote("d", self.TEXT, q)
        assert a.quote == q

    def test_empty_quote_yields_lost(self):
        _, _, _, _, make_anchor_from_quote, *_ = _anchor()
        a = make_anchor_from_quote("d", self.TEXT, "")
        assert a.status == "lost"


# ── relocate — three-state contract ──────────────────────────────────────────


class TestRelocate:
    def _make(self, text, quote):
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        return make_anchor_from_quote("d", text, quote), relocate

    def test_exact_match_returns_anchored(self):
        text = "The model achieves state-of-the-art results on three benchmarks."
        a, relocate = self._make(text, "state-of-the-art results")
        new_text = "Prefix added. The model achieves state-of-the-art results on three benchmarks."
        a2 = relocate(a, new_text)
        assert a2.status == "anchored"
        assert new_text[a2.char_start:a2.char_end] == "state-of-the-art results"

    def test_exact_match_updates_offsets(self):
        text = "Hello world foo bar."
        a, relocate = self._make(text, "foo bar")
        new_text = "XXXXXX Hello world foo bar."
        a2 = relocate(a, new_text)
        assert a2.char_start == new_text.index("foo bar")
        assert a2.char_end == a2.char_start + len("foo bar")

    def test_context_window_helps_find_moved_quote(self):
        # quote appears in two places; context_before disambiguates
        _, _, _, make_anchor, _, relocate, *_ = _anchor()
        text = "Alpha target Beta. Gamma target Delta."
        # anchor to first "target" with context "Alpha "
        a = make_anchor("d", text, text.index("target"), text.index("target") + 6)
        # new_text: first occurrence removed, second remains
        new_text = "Gamma target Delta."
        a2 = relocate(a, new_text)
        # Should find "target" somewhere (anchored or drifted), not lost
        assert a2.status in ("anchored", "drifted")
        assert a2.char_start is not None

    def test_fuzzy_match_returns_drifted(self):
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        original = "Our approach significantly outperforms existing methods."
        a = make_anchor_from_quote("d", original, "significantly outperforms")
        # New text: quote slightly changed (minor edit)
        new_text = "Our approach significantly outperform existing methods."
        a2 = relocate(a, new_text)
        assert a2.status in ("drifted", "anchored")  # fuzzy should catch it
        assert a2.char_start is not None

    def test_totally_removed_returns_lost(self):
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        original = "We introduce a novel transformer architecture for NLP."
        a = make_anchor_from_quote("d", original, "novel transformer architecture")
        new_text = "This paper is about deep learning in general."
        a2 = relocate(a, new_text)
        assert a2.status == "lost"
        assert a2.char_start is None
        assert a2.char_end is None

    def test_lost_anchor_preserves_quote_and_context(self):
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        original = "We introduce a novel transformer architecture for NLP."
        a = make_anchor_from_quote("d", original, "novel transformer architecture")
        new_text = "Completely different text with no overlap whatsoever."
        a2 = relocate(a, new_text)
        assert a2.quote == a.quote
        assert a2.context_before == a.context_before or a2.status == "lost"

    def test_relocate_is_pure_function(self):
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        original = "The quick brown fox jumps over the lazy dog."
        a = make_anchor_from_quote("d", original, "quick brown fox")
        original_status = a.status
        original_start = a.char_start
        new_text = "Now: the quick brown fox jumps over the lazy dog."
        a2 = relocate(a, new_text)
        # Original anchor unchanged
        assert a.status == original_status
        assert a.char_start == original_start
        # New anchor is a different object
        assert a2 is not a

    def test_relocate_updates_context(self):
        _, CONTEXT_CHARS, _, make_anchor, _, relocate, *_ = _anchor()
        text = "AAA TARGET BBB"
        a = make_anchor("d", text, 4, 10)
        new_text = "CCCCCC AAA TARGET BBB"
        a2 = relocate(a, new_text)
        if a2.status == "anchored":
            assert a2.context_before == new_text[max(0, a2.char_start - CONTEXT_CHARS):a2.char_start]


# ── relocate_all ──────────────────────────────────────────────────────────────


class TestRelocateAll:
    def test_returns_same_count(self):
        _, _, _, _, make_anchor_from_quote, _, relocate_all, _ = _anchor()
        text = "Alpha beta gamma delta."
        a1 = make_anchor_from_quote("d", text, "Alpha")
        a2 = make_anchor_from_quote("d", text, "gamma")
        result = relocate_all([a1, a2], text)
        assert len(result) == 2

    def test_empty_list(self):
        *_, relocate_all, _ = _anchor()
        assert relocate_all([], "some text") == []

    def test_each_anchor_independently_relocated(self):
        _, _, _, _, make_anchor_from_quote, _, relocate_all, _ = _anchor()
        text = "We show X. We also show Y."
        a1 = make_anchor_from_quote("d", text, "show X")
        a2 = make_anchor_from_quote("d", text, "show Y")
        new_text = "Preface. We show X. We also show Y."
        results = relocate_all([a1, a2], new_text)
        for r in results:
            assert r.char_start is not None
            assert r.status in ("anchored", "drifted")


# ── section_path_at ───────────────────────────────────────────────────────────


class TestSectionPathAt:
    MD_TEXT = "# Introduction\n\nSome intro text.\n\n## 2.1 Related Work\n\nMore text here.\n\n### 2.1.1 Deep Learning\n\nDL text."

    def test_returns_nearest_header(self):
        *_, section_path_at = _anchor()
        # offset inside "DL text." section
        offset = self.MD_TEXT.index("DL text.")
        path = section_path_at(self.MD_TEXT, offset)
        assert path is not None
        assert "2.1.1" in path or "Deep Learning" in path

    def test_returns_none_before_any_header(self):
        *_, section_path_at = _anchor()
        path = section_path_at("No header here. Just text.", 5)
        # Either None or empty string is acceptable
        assert path is None or path == ""

    def test_returns_string_type(self):
        *_, section_path_at = _anchor()
        result = section_path_at(self.MD_TEXT, 20)
        assert result is None or isinstance(result, str)

    def test_within_subsection(self):
        *_, section_path_at = _anchor()
        offset = self.MD_TEXT.index("More text here.")
        path = section_path_at(self.MD_TEXT, offset)
        assert path is not None
        assert "Related Work" in path or "2.1" in path

    def test_zero_offset(self):
        *_, section_path_at = _anchor()
        # Should not crash at offset 0
        result = section_path_at(self.MD_TEXT, 0)
        assert result is None or isinstance(result, str)


# ── performance: long text doesn't hang ──────────────────────────────────────


class TestPerformance:
    def test_relocate_long_text_completes(self):
        import time
        _, _, _, _, make_anchor_from_quote, relocate, *_ = _anchor()
        long_text = ("This is a sentence about neural networks. " * 1500)  # ~60k chars
        quote = "sentence about neural networks"
        a = make_anchor_from_quote("d", long_text, quote)
        new_text = "PREPENDED CONTENT. " + long_text
        t0 = time.monotonic()
        a2 = relocate(a, new_text)
        elapsed = time.monotonic() - t0
        assert elapsed < 5.0, f"relocate took {elapsed:.2f}s on 60k-char text — too slow"
        assert a2 is not None
