"""Phase 4 tests: Socratic prompt identity + intent detection."""
from __future__ import annotations

import pytest


class TestSocraticPrompt:
    """Socratic mode prompt validation."""

    def test_identity_contains_iron_rule(self):
        """Socratic identity must contain 'never give direct answers' rule."""
        from src.agent.socratic_prompt import _SOCRATIC_IDENTITY
        assert len(_SOCRATIC_IDENTITY) > 50
        assert "不要直接给" in _SOCRATIC_IDENTITY or "never give" in _SOCRATIC_IDENTITY.lower()

    def test_identity_contains_5_layers(self):
        """Socratic identity describes 5 layers of dialogue."""
        from src.agent.socratic_prompt import _SOCRATIC_IDENTITY
        # Should mention layers or stages
        assert "层" in _SOCRATIC_IDENTITY or "Layer" in _SOCRATIC_IDENTITY

    def test_allowed_tools_are_readonly(self):
        """Socratic mode only allows read-only tools."""
        from src.agent.socratic_prompt import SOCRATIC_ALLOWED_TOOLS

        read_only = {"read_file", "list_directory", "grep_files", "glob_files",
                      "search_documents", "read_argument_graph", "read_argument_ledger"}
        # All allowed tools should be read-only
        for tool in SOCRATIC_ALLOWED_TOOLS:
            assert tool in read_only, f"{tool} is not read-only"

        # Write tools should NOT be in the allowed list
        assert "write_file" not in SOCRATIC_ALLOWED_TOOLS
        assert "str_replace" not in SOCRATIC_ALLOWED_TOOLS
        assert "shell_exec" not in SOCRATIC_ALLOWED_TOOLS
        assert "run_command" not in SOCRATIC_ALLOWED_TOOLS

    def test_build_socratic_prompt(self):
        """build_socratic_prompt returns a valid prompt string."""
        from src.agent.socratic_prompt import build_socratic_prompt

        prompt = build_socratic_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "苏格拉底" in prompt or "Socratic" in prompt


class TestSocraticIntent:
    """Socratic intent detection in router."""

    @pytest.fixture
    def detect_fn(self):
        from src.agent.socratic_prompt import _has_socratic_intent

        def _fn(msg: str) -> bool:
            return _has_socratic_intent(msg)

        return _fn

    def test_socratic_triggers(self, detect_fn):
        """Known Socratic triggers are detected."""
        triggers = [
            "帮我思考",
            "引导我",
            "帮我思考一下论文选题",
            "help me think",
            "guide me",
            "苏格拉底",
            "socratic",
        ]
        for t in triggers:
            assert detect_fn(t), f"'{t}' should trigger Socratic mode"

    def test_non_socratic_rejected(self, detect_fn):
        """Non-Socratic messages are not falsely triggered."""
        non_triggers = [
            "帮我写论文",
            "翻译这段话",
            "润色一下",
            "总结这篇文档",
            "run test.py",
            "hello",
        ]
        for t in non_triggers:
            assert not detect_fn(t), f"'{t}' should NOT trigger Socratic mode"

    def test_case_insensitive(self, detect_fn):
        """Socratic detection is case-insensitive."""
        assert detect_fn("Socratic mode please")
        assert detect_fn("SOCRATIC")
        assert detect_fn("Help Me Think about research")


class TestPipelineStageDetection:
    """Stage detection keywords."""

    @pytest.fixture
    def detect_fn(self):
        from src.agent.socratic_prompt import _detect_pipeline_stage

        return _detect_pipeline_stage

    def test_detect_research(self, detect_fn):
        result = detect_fn("帮我调研一下深度学习的现状")
        assert result == "research"

    def test_detect_outline(self, detect_fn):
        result = detect_fn("帮我写个论文大纲")
        assert result == "outline"

    def test_detect_draft(self, detect_fn):
        result = detect_fn("帮我写初稿")
        assert result == "draft"

    def test_detect_review(self, detect_fn):
        result = detect_fn("帮我审稿")
        assert result == "review"

    def test_detect_revise(self, detect_fn):
        result = detect_fn("帮我修改论文")
        assert result == "revise"

    def test_detect_finalize(self, detect_fn):
        result = detect_fn("定稿")
        assert result == "finalize"

    def test_detect_no_match(self, detect_fn):
        result = detect_fn("今天天气真好")
        assert result is None

    def test_detect_english(self, detect_fn):
        assert detect_fn("research on ML") == "research"
        assert detect_fn("write an outline") == "outline"
        assert detect_fn("review this paper") == "review"
