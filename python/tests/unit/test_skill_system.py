"""Unit tests for SkillRegistry — pattern tracking and auto-generation."""
from __future__ import annotations

from pathlib import Path

from src.agent.skill_system import SkillRegistry


class TestPatternAutoGeneration:
    """Tests for record_pattern() → auto-generate skill after 3+ repetitions."""

    def test_pattern_key_normalization(self):
        reg = SkillRegistry.__new__(SkillRegistry)
        k1 = reg._pattern_key("fix import errors", "fix import errors")
        k2 = reg._pattern_key("Fix Import Errors in agent.py", "fix import errors")
        # Both should normalize to similar keys (digit/case insensitive)
        assert "pat_" in k1
        assert "pat_" in k2

    def test_no_skill_below_threshold(self, tmp_path: Path):
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        for _ in range(2):
            result = reg.record_pattern(
                query="fix import errors", task_title="fix imports", success=True,
                tools_used=["read_file", "str_replace"],
            )
            assert result is None

    def test_auto_generate_on_third_repeat(self, tmp_path: Path):
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        # Run same pattern 3 times
        result = None
        for i in range(3):
            result = reg.record_pattern(
                query="fix Python import errors",
                task_title=f"fix imports pass {i}",
                success=True,
                tools_used=["read_file", "str_replace"],
            )
        # Third call should trigger auto-generation
        assert result is not None
        assert result.name.startswith("auto_")
        # Skill should be saved to disk
        skill_file = tmp_path / "skills" / result.name / "SKILL.md"
        assert skill_file.exists()

    def test_auto_generate_only_once(self, tmp_path: Path):
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        # 4th call should NOT generate another skill for same pattern
        for i in range(4):
            reg.record_pattern(
                query="fix import errors", task_title=f"fix pass {i}",
                success=True, tools_used=["str_replace"],
            )
        assert len(reg._auto_generated) == 1

    def test_pattern_includes_failure_info(self, tmp_path: Path):
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        result = None
        for i in range(3):
            result = reg.record_pattern(
                query="connect to database failed",
                task_title=f"db connect pass {i}",
                success=(i == 2),  # first two fail, third succeeds
                tools_used=["run_command"],
                error_type="ConnectionError" if i < 2 else None,
            )
        assert result is not None
        # Should mention the error type in steps
        assert "ConnectionError" in str(result.steps)

    def test_different_patterns_dont_merge(self, tmp_path: Path):
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        # Pattern A — 2 repetitions
        for _ in range(2):
            reg.record_pattern(query="fix import", task_title="fix",
                               success=True, tools_used=["read_file"])
        # Pattern B — 2 repetitions
        for _ in range(2):
            reg.record_pattern(query="translate document", task_title="translate",
                               success=True, tools_used=["translate_text"])
        # Neither reached threshold of 3
        assert len(reg._auto_generated) == 0

    def test_skill_name_does_not_clobber_existing(self, tmp_path: Path):
        """Auto-generated skill name should not conflict with existing skill."""
        reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
        # Manually create a skill first
        reg.create_skill(
            name="auto_test",
            trigger="test",
            description="existing test skill",
            steps=["step 1"],
        )
        # Now trigger a pattern
        for i in range(3):
            reg.record_pattern(
                query="test pattern", task_title=f"test pass {i}",
                success=True, tools_used=[],
            )
        # Existing skill should remain unchanged
        existing = reg.get("auto_test")
        assert existing is not None
        assert existing.description == "existing test skill"
