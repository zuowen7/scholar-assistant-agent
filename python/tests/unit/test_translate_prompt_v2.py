"""Phase A — RED phase unit tests for translate prompt v2 + citation protection.

RED state (before Phase A GREEN implementation):
  A1-A12  SKIP  — src.translator._prompt_loader not yet created
  A13     PASS  — protect_citations numeric patterns (regression baseline)
  A14     FAIL  — author-year citations not yet in protect_citations regex
  A15     PASS  — restore_citations numeric (regression baseline)

After GREEN all 15 should PASS.  Run with:
    cd python && pytest tests/unit/test_translate_prompt_v2.py -v
"""
from __future__ import annotations

import pytest

from src.cleaner.pipeline import protect_citations, restore_citations


# ── _prompt_loader fixture ─────────────────────────────────────────────────
# If Phase A GREEN is not yet implemented this fixture skips A1-A12
# without affecting A13-A15.

@pytest.fixture(scope="module")
def load_fn():
    """Return load_translate_prompt, skipping if module not yet created."""
    mod = pytest.importorskip(
        "src.translator._prompt_loader",
        reason="Phase A GREEN not yet implemented — create src/translator/_prompt_loader.py",
    )
    return mod.load_translate_prompt


def _p(load_fn, section: str = "unknown", glossary: str = "") -> str:
    return load_fn(section=section, glossary_text=glossary)


# ─────────────────────────────────────────────────────────────────────────────
# A1-A3  Template loading + core identity rules
# ─────────────────────────────────────────────────────────────────────────────

class TestTemplateAndCoreRules:

    def test_A1_prompt_loaded_from_template(self, load_fn):
        """A1: System prompt must carry the new template header '## 翻译五原则'."""
        prompt = _p(load_fn)
        assert "## 翻译五原则" in prompt, (
            "Template not loaded — '## 翻译五原则' header missing. "
            "Create prompts/tasks_translate/academic_translate.md."
        )

    def test_A2_rule1_accuracy_first(self, load_fn):
        """A2: Rule 1 — accuracy-first instruction present."""
        prompt = _p(load_fn)
        assert "准确性优先" in prompt, (
            "Rule 1 missing: add '准确性优先' to academic_translate.md."
        )

    def test_A3_rule2_glossary_injected(self, load_fn):
        """A3: Rule 2 — glossary text injected when provided."""
        glossary = "attention mechanism → 注意力机制\ntransformer → 变换器"
        prompt = _p(load_fn, glossary=glossary)
        assert "已确定的术语翻译" in prompt, (
            "Glossary header '已确定的术语翻译' missing from prompt with glossary."
        )
        assert "attention mechanism" in prompt, (
            "Glossary content not injected into prompt."
        )


# ─────────────────────────────────────────────────────────────────────────────
# A4-A7  Rule 3 — Code + math preservation instructions
# ─────────────────────────────────────────────────────────────────────────────

class TestRule3ProtectionInstructions:

    def test_A4_rule3_code_block_instruction(self, load_fn):
        """A4: System prompt must explicitly instruct to preserve fenced code blocks."""
        prompt = _p(load_fn)
        assert "代码块" in prompt, (
            "Rule 3 code-block instruction missing. "
            "Add '代码块 (```...```) 不翻译' to academic_translate.md."
        )

    def test_A5_rule3_inline_code_instruction(self, load_fn):
        """A5: System prompt must mention inline code (backtick) preservation."""
        prompt = _p(load_fn)
        assert "行内代码" in prompt, (
            "Rule 3 inline-code instruction missing. "
            "Add '行内代码 (`...`) 不翻译' to academic_translate.md."
        )

    def test_A6_rule3_math_instruction(self, load_fn):
        """A6: System prompt must mention math formula preservation ($...$)."""
        prompt = _p(load_fn)
        assert "数学公式" in prompt, (
            "Rule 3 math instruction missing. "
            "Add '数学公式 ($...$, $$...$$) 不翻译' to academic_translate.md."
        )

    def test_A7_rule3_display_math_instruction(self, load_fn):
        """A7: System prompt must specifically mention display math ($$...$$)."""
        prompt = _p(load_fn)
        has_display = "$$" in prompt or "display math" in prompt or "块级公式" in prompt
        assert has_display, (
            "Rule 3 display-math instruction missing. "
            "Add '$$...$$' block math rule to academic_translate.md."
        )


# ─────────────────────────────────────────────────────────────────────────────
# A8-A9  Rule 4 — Section-aware context injection
# ─────────────────────────────────────────────────────────────────────────────

class TestRule4SectionContext:

    def test_A8_abstract_section_injected(self, load_fn):
        """A8: '[SECTION: ABSTRACT]' included when section='abstract'."""
        prompt = _p(load_fn, section="abstract")
        assert "[SECTION: ABSTRACT]" in prompt, (
            "Abstract section partial not injected. "
            "Load _partials/section_abstract.md for section='abstract'."
        )

    def test_A9_methods_section_injected(self, load_fn):
        """A9: '[SECTION: METHODS]' included when section='methods'."""
        prompt = _p(load_fn, section="methods")
        assert "[SECTION: METHODS]" in prompt, (
            "Methods section partial not injected. "
            "Load _partials/section_methods.md for section='methods'."
        )

    def test_A9b_unknown_section_no_header(self, load_fn):
        """Bonus: section='unknown' should not inject any [SECTION: ...] header."""
        prompt = _p(load_fn, section="unknown")
        assert "[SECTION:" not in prompt, (
            "Section header unexpectedly present for section='unknown'."
        )


# ─────────────────────────────────────────────────────────────────────────────
# A10-A12  Rule 5 — Markdown format preservation instructions
# ─────────────────────────────────────────────────────────────────────────────

class TestRule5FormatInstructions:

    def test_A10_markdown_heading_instruction(self, load_fn):
        """A10: Template must instruct to preserve Markdown headings (# ## ###)."""
        prompt = _p(load_fn)
        has_heading = "标题" in prompt or "heading" in prompt.lower()
        assert has_heading, (
            "Rule 5 heading instruction missing. "
            "Add Markdown heading preservation rule to academic_translate.md."
        )

    def test_A11_list_instruction(self, load_fn):
        """A11: Template must instruct to preserve Markdown list structure."""
        prompt = _p(load_fn)
        has_list = "列表" in prompt or "list" in prompt.lower()
        assert has_list, (
            "Rule 5 list instruction missing. "
            "Add list structure (- item, 1. item) preservation rule."
        )

    def test_A12_table_instruction(self, load_fn):
        """A12: Template must instruct to preserve Markdown table structure."""
        prompt = _p(load_fn)
        has_table = "表格" in prompt or "table" in prompt.lower()
        assert has_table, (
            "Rule 5 table instruction missing. "
            "Add Markdown table (|col|col|) preservation rule."
        )


# ─────────────────────────────────────────────────────────────────────────────
# A13-A15  Citation protection — no _prompt_loader dependency
# ─────────────────────────────────────────────────────────────────────────────

class TestCitationProtection:

    # A13 — regression baseline, must PASS in RED
    @pytest.mark.parametrize("text,expected_placeholders", [
        ("[1]",            ["[1]"]),
        ("(1)",            ["(1)"]),
        ("(1,3)",          ["(1,3)"]),
        ("[1,3]",          ["[1,3]"]),
        ("(1-5)",          ["(1-5)"]),
        ("see [1] and [2,3]", ["[1]", "[2,3]"]),
    ])
    def test_A13_citation_protect_numeric(self, text, expected_placeholders):
        """A13: Existing numeric citation patterns protected — regression."""
        result, placeholders = protect_citations(text)
        assert placeholders == expected_placeholders
        assert "⟦C" in result

    # A14 — MUST FAIL in RED (author-year regex not yet implemented)
    @pytest.mark.parametrize("text,n_expected", [
        ("[Smith, 2020]",              1),
        ("[Smith et al., 2020]",       1),
        ("[Smith et al., 2020a]",      1),
        ("(Smith and Jones, 2019)",    1),
        ("[Smith, 2020] and [Jones, 2021]", 2),
    ])
    def test_A14_citation_protect_author_year(self, text, n_expected):
        """A14: Author-year citations must be protected — NEW regex required."""
        result, placeholders = protect_citations(text)
        assert len(placeholders) == n_expected, (
            f"Expected {n_expected} placeholder(s) for '{text}', "
            f"got {len(placeholders)}. "
            "Extend protect_citations regex in src/cleaner/pipeline.py."
        )
        assert "⟦C" in result

    # A15 — regression baseline, must PASS in RED
    @pytest.mark.parametrize("original", [
        "[1]",
        "(1,3)",
        "(1-5)",
        "text [1] and [2] here",
        "[1] start and end [2]",
    ])
    def test_A15_citation_restore_idempotent(self, original):
        """A15: protect → restore must return the exact original string."""
        result, placeholders = protect_citations(original)
        restored = restore_citations(result, placeholders)
        assert restored == original, (
            f"restore_citations lost data: {original!r} → {restored!r}"
        )
