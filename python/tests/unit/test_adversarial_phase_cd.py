"""Adversarial tests for Phase C/D code — edge cases designed to break things.

Categories:
1. _skill_migrate.py edge cases (tests 1-6)
2. _skill_persistence.py save/reload round-trips (tests 7-10)
3. _reviewer_perspectives.py + aggregate_perspectives edge cases (tests 11-17)
4. prompt_builder.py _build_skill_section edge cases (tests 18-20)
5. Deeper adversarial edge cases found by code analysis (tests 21-40)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Category 1: _skill_migrate.py edge cases ─────────────────────────────────


class TestSkillMigrateEdgeCases:
    """Adversarial tests for _skill_migrate.migrate_skills_dir."""

    def _make_skills_dir(self, tmp_path: Path) -> Path:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        return skills_dir

    def test_01_empty_steps_and_notes(self, tmp_path: Path) -> None:
        """SKILL.md has frontmatter but no steps or notes sections.
        Migration should produce valid IDENTITY/SOUL/AGENTS files without crash.
        """
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "myskill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\ntrigger: hello\n---\n\n# Test Skill\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1
        assert result["errors"] == []

        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        assert "name: test" in identity
        soul = (skill_dir / "SOUL.md").read_text(encoding="utf-8")
        assert soul.strip() == "# Core"
        agents = (skill_dir / "AGENTS.md").read_text(encoding="utf-8")
        assert agents.strip() == "# Extended"

    def test_02_special_chars_in_trigger(self, tmp_path: Path) -> None:
        """Trigger value contains colons, brackets, commas.
        Migration should preserve trigger exactly.
        """
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "special"
        skill_dir.mkdir()
        trigger_val = 'hello, world: test [brackets]'
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: special\ntrigger: {trigger_val}\n---\n\n# Special\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1
        assert result["errors"] == []

        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        # The trigger line uses partition(":") which splits at the FIRST colon.
        # So "trigger: hello, world: test [brackets]" becomes key="trigger", value="hello, world: test [brackets]"
        assert f"trigger: {trigger_val}" in identity

    def test_03_multiline_step_content(self, tmp_path: Path) -> None:
        """A step with quotes and continuation lines.
        Migration should handle it without crash.
        """
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "multiline"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: multi\ntrigger: multi\n---\n\n# Multi\n\n"
            "## 步骤\n"
            '1. This is a "quoted" step\n'
            "2. Another step\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1
        assert result["errors"] == []

        soul = (skill_dir / "SOUL.md").read_text(encoding="utf-8")
        assert '"quoted"' in soul
        assert "1." in soul
        assert "2." in soul

    def test_04_idempotency(self, tmp_path: Path) -> None:
        """Run migration twice. Second run should skip (IDENTITY.md exists)."""
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "idem"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: idem\ntrigger: idem\n---\n\n# Idem\n",
            encoding="utf-8",
        )

        result1 = migrate_skills_dir(skills_dir)
        assert result1["migrated"] == 1

        # After first migration, SKILL.md was renamed to SKILL.md.bak
        # and IDENTITY.md exists, so it should be skipped
        result2 = migrate_skills_dir(skills_dir)
        assert result2["migrated"] == 0
        assert result2["skipped"] == 1

    def test_05_no_frontmatter_at_all(self, tmp_path: Path) -> None:
        """SKILL.md containing no frontmatter — just body text with headings.
        Should be handled gracefully.
        """
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "nofm"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# Just a heading\n\nSome body text here.\n\n## 步骤\n\n1. Do something\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        # The code only checks if SKILL.md exists (not if it has frontmatter)
        # _parse_legacy handles missing frontmatter: _FM_RE.match returns None, body stays as full content
        assert result["migrated"] == 1
        assert result["errors"] == []
        # Verify IDENTITY.md was created
        assert (skill_dir / "IDENTITY.md").exists()

    def test_06_dry_run_no_files_written(self, tmp_path: Path) -> None:
        """dry_run=True should report migration but not write files."""
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "dryrun"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: dryrun\ntrigger: dry\n---\n\n# DryRun\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir, dry_run=True)
        assert result["migrated"] == 1
        # No files should be written
        assert not (skill_dir / "IDENTITY.md").exists()
        assert not (skill_dir / "SOUL.md").exists()
        assert not (skill_dir / "AGENTS.md").exists()
        # Original file should still exist (not renamed)
        assert (skill_dir / "SKILL.md").exists()


# ── Category 2: _skill_persistence.py save/reload round-trips ───────────────


class TestSkillPersistenceRoundTrips:
    """Adversarial tests for SkillPersistenceMixin save/reload."""

    def _make_registry(self, skills_dir: Path):
        """Create a minimal SkillRegistry-like object with persistence mixin."""
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        class FakeRegistry(SkillPersistenceMixin):
            def __init__(self, sd: Path):
                self.skills_dir = sd
                self._skills: dict[str, Skill] = {}

        return FakeRegistry(skills_dir)

    def test_07_create_skill_saves_as_skill_md(self, tmp_path: Path) -> None:
        """Creating a new skill via _save_skill() should write SKILL.md and reload correctly."""
        from src.agent._skill_model import Skill

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        reg = self._make_registry(skills_dir)

        skill = Skill(
            name="test_create",
            trigger="create me",
            description="A test skill",
            steps=["Step 1", "Step 2"],
            notes=["Note A"],
        )
        reg._save_skill(skill)

        # Verify file exists
        skill_file = skills_dir / "test_create" / "SKILL.md"
        assert skill_file.exists()

        # Reload from disk
        reloaded = reg._parse_skill_file(skill_file)
        assert reloaded is not None
        assert reloaded.name == "test_create"
        assert reloaded.trigger == "create me"
        assert reloaded.description == "A test skill"
        assert reloaded.steps == ["Step 1", "Step 2"]
        assert reloaded.notes == ["Note A"]

    def test_08_update_three_layer_skill(self, tmp_path: Path) -> None:
        """update_skill() on a three-layer skill should update IDENTITY.md and reload correctly."""
        from src.agent._skill_model import Skill

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        reg = self._make_registry(skills_dir)

        skill_dir = skills_dir / "threelayer"
        skill_dir.mkdir()
        # Create IDENTITY.md
        identity_content = (
            "---\nname: old_name\ntrigger: old_trigger\ncreated: \n"
            "updated: \nlast_used: \nuse_count: 0\ndeprecated: false\n---\nOld description"
        )
        (skill_dir / "IDENTITY.md").write_text(identity_content, encoding="utf-8")
        (skill_dir / "SOUL.md").write_text("# Core\n1. Do thing\n", encoding="utf-8")
        (skill_dir / "AGENTS.md").write_text("# Extended\n- Be careful\n", encoding="utf-8")

        # Load it
        loaded = reg._load_three_layer_skill(skill_dir)
        assert loaded is not None
        assert loaded.name == "old_name"
        assert loaded.trigger == "old_trigger"

        # Modify and save
        loaded.name = "new_name"
        loaded.trigger = "new_trigger"
        loaded.description = "New desc"
        reg._save_skill(loaded)

        # Reload from disk
        reloaded = reg._load_three_layer_skill(skill_dir)
        assert reloaded is not None
        assert reloaded.name == "new_name"
        assert reloaded.trigger == "new_trigger"
        # Description comes from IDENTITY.md body
        identity_reloaded = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        assert "name: new_name" in identity_reloaded
        assert "trigger: new_trigger" in identity_reloaded

    def test_09_soul_md_whitespace_only(self, tmp_path: Path) -> None:
        """Three-layer skill with SOUL.md containing only whitespace.
        Verify it loads without crash and prompt_builder handles empty soul.
        """
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "whitespace_soul"
        skill_dir.mkdir()
        (skill_dir / "IDENTITY.md").write_text(
            "---\nname: ws\ntrigger: ws\ncreated: \nupdated: \n"
            "last_used: \nuse_count: 0\ndeprecated: false\n---\nWS Skill",
            encoding="utf-8",
        )
        (skill_dir / "SOUL.md").write_text("   \n\n  ", encoding="utf-8")
        (skill_dir / "AGENTS.md").write_text("# Extended\n", encoding="utf-8")

        reg = self._make_registry(skills_dir)
        loaded = reg._load_three_layer_skill(skill_dir)
        assert loaded is not None
        assert loaded.name == "ws"

        # Now test that prompt_builder handles this gracefully
        from src.agent.prompt_builder import PromptBuilder, PromptConfig

        builder = PromptBuilder()
        config = PromptConfig(
            active_skills=[loaded],
            relevant_skill_names=set(),
            skill_token_budget=4000,
        )
        prompt = builder.build(config)
        # Should not crash; SOUL.md content is whitespace, so after strip() it's ""
        # _build_skill_section reads the file, strips it, and if empty adds nothing
        assert isinstance(prompt, str)

    def test_10_coexistence_legacy_and_three_layer(self, tmp_path: Path) -> None:
        """Directory has both a legacy SKILL.md skill and a three-layer IDENTITY.md skill.
        Both should load correctly.
        """
        from src.agent._skill_model import Skill

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        reg = self._make_registry(skills_dir)

        # Legacy skill
        legacy_dir = skills_dir / "legacy_skill"
        legacy_dir.mkdir()
        (legacy_dir / "SKILL.md").write_text(
            "---\nname: legacy\ntrigger: old stuff\n---\n\n# Legacy Skill\n\n"
            "## 步骤\n1. Legacy step\n\n## 注意事项\n- Legacy note\n",
            encoding="utf-8",
        )

        # Three-layer skill
        three_dir = skills_dir / "new_skill"
        three_dir.mkdir()
        (three_dir / "IDENTITY.md").write_text(
            "---\nname: new\ntrigger: new stuff\ncreated: \nupdated: \n"
            "last_used: \nuse_count: 0\ndeprecated: false\n---\nNew Skill",
            encoding="utf-8",
        )
        (three_dir / "SOUL.md").write_text("# Core\n1. New step\n", encoding="utf-8")
        (three_dir / "AGENTS.md").write_text("# Extended\n- New note\n", encoding="utf-8")

        reg._load_all()

        assert "legacy" in reg._skills
        assert "new" in reg._skills
        assert reg._skills["legacy"].trigger == "old stuff"
        assert reg._skills["new"].trigger == "new stuff"
        assert reg._skills["legacy"].steps == ["Legacy step"]
        assert reg._skills["legacy"].notes == ["Legacy note"]
        # Three-layer skill: soul_path and agents_path are set
        assert reg._skills["new"].soul_path != ""


# ── Category 3: _reviewer_perspectives.py + aggregate_perspectives edge cases ─


class TestReviewerPerspectivesEdgeCases:
    """Adversarial tests for aggregate_perspectives and _parse_llm_points."""

    def _make_review_point(self, title="Test", category="other", severity="minor",
                           detail="detail", source="llm") -> "ReviewPoint":
        from src.argument.companion_models import ReviewPoint
        return ReviewPoint(
            severity=severity,  # type: ignore
            category=category,  # type: ignore
            title=title,
            detail=detail,
            source=source,  # type: ignore
        )

    def test_11_mixed_severity_same_title(self) -> None:
        """Same title+category but different severity — first one wins."""
        from src.argument._reviewer_perspectives import aggregate_perspectives

        p1 = self._make_review_point(title="Missing baseline", category="baseline", severity="minor")
        p2 = self._make_review_point(title="Missing baseline", category="baseline", severity="fatal")
        p3 = self._make_review_point(title="Missing baseline", category="baseline", severity="major")

        # p1 and p2 have same (title.lower(), category) — p1 wins
        result = aggregate_perspectives([p1, p2], [], [p3])
        assert len(result) == 1
        # The first occurrence wins
        assert result[0].severity == "minor"

    def test_12_100_plus_points_performance(self) -> None:
        """300 total points should complete in < 1 second."""
        from src.argument._reviewer_perspectives import aggregate_perspectives

        method_pts = [
            self._make_review_point(title=f"Method point {i}", category="soundness")
            for i in range(100)
        ]
        experiment_pts = [
            self._make_review_point(title=f"Exp point {i}", category="experiment_design")
            for i in range(100)
        ]
        writing_pts = [
            self._make_review_point(title=f"Writing point {i}", category="writing_clarity")
            for i in range(100)
        ]

        start = time.monotonic()
        result = aggregate_perspectives(method_pts, experiment_pts, writing_pts)
        elapsed = time.monotonic() - start

        assert len(result) == 300
        assert elapsed < 1.0, f"aggregate_perspectives took {elapsed:.3f}s, expected < 1s"

    def test_13_malformed_json_prose(self) -> None:
        """LLM returns prose instead of JSON — _parse_llm_points should return []."""
        from src.argument.reviewer import _parse_llm_points

        result = _parse_llm_points("Not JSON at all, just prose", source="llm")
        assert result == []

    def test_14_json_object_not_array(self) -> None:
        """LLM returns JSON object instead of array — should return []."""
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps({"severity": "major", "title": "T", "detail": "d"})
        result = _parse_llm_points(raw, source="llm")
        assert result == []

    def test_15_nested_array(self) -> None:
        """LLM returns nested array [[{...}]] — should return []."""
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([[{"severity": "major", "title": "T", "detail": "d", "category": "other"}]])
        result = _parse_llm_points(raw, source="llm")
        # The first item is a list (not dict), so it gets skipped
        assert result == []

    @pytest.mark.asyncio
    async def test_16_empty_text(self) -> None:
        """run_method_perspective with empty text should not crash."""
        from src.argument._reviewer_perspectives import run_method_perspective

        # Mock the LLM call to return empty array
        with patch("src.argument._reviewer_perspectives.call_llm_chat",
                    new_callable=AsyncMock, return_value="[]"):
            result = await run_method_perspective(
                text="", venue_profile="top venue"
            )
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_17_very_long_text(self) -> None:
        """run_method_perspective with >100K chars text — should truncate and not OOM."""
        from src.argument._reviewer_perspectives import run_method_perspective

        # 150K chars of text
        long_text = "x" * 150_000

        with patch("src.argument._reviewer_perspectives.call_llm_chat",
                    new_callable=AsyncMock, return_value="[]"):
            start = time.monotonic()
            result = await run_method_perspective(
                text=long_text, venue_profile="top venue"
            )
            elapsed = time.monotonic() - start

        assert isinstance(result, list)
        assert elapsed < 2.0, f"Took too long: {elapsed:.3f}s — truncation may be broken"


# ── Category 4: prompt_builder.py _build_skill_section edge cases ────────────


class TestPromptBuilderSkillSection:
    """Adversarial tests for PromptBuilder._build_skill_section."""

    def test_18_nonexistent_soul_path(self, tmp_path: Path) -> None:
        """skill with soul_path pointing to nonexistent file — no crash, graceful skip."""
        from src.agent.prompt_builder import PromptBuilder, PromptConfig
        from src.agent._skill_model import Skill

        builder = PromptBuilder()
        skill = Skill(
            name="ghost",
            soul_path="/tmp/nonexistent_soul_path_12345/SOUL.md",
            agents_path="/tmp/nonexistent_agents_path_12345/AGENTS.md",
        )
        config = PromptConfig(
            active_skills=[skill],
            relevant_skill_names={"ghost"},
            skill_token_budget=4000,
        )
        prompt = builder.build(config)
        # Should not crash, and no skills section injected since file doesn't exist
        assert isinstance(prompt, str)
        # No <skills> tag should appear since file doesn't exist
        assert "<skills>" not in prompt

    def test_19_skill_token_budget_zero(self, tmp_path: Path) -> None:
        """skill_token_budget=0 — should return empty string (no skills injected)."""
        from src.agent.prompt_builder import PromptBuilder, PromptConfig
        from src.agent._skill_model import Skill

        # Create a real SOUL.md file
        skill_dir = tmp_path / "budget_skill"
        skill_dir.mkdir()
        (skill_dir / "SOUL.md").write_text("# Core\n1. A step\n", encoding="utf-8")

        builder = PromptBuilder()
        skill = Skill(
            name="budget_test",
            soul_path=str(skill_dir / "SOUL.md"),
        )
        config = PromptConfig(
            active_skills=[skill],
            relevant_skill_names=set(),
            skill_token_budget=0,
        )
        prompt = builder.build(config)
        assert isinstance(prompt, str)
        # With budget=0, even reading SOUL content will have len > 0 > budget, so skipped
        assert "<skills>" not in prompt

    def test_20_two_skills_same_soul_content(self, tmp_path: Path) -> None:
        """Two skills with identical SOUL content — both should be injected (no dedup)."""
        from src.agent.prompt_builder import PromptBuilder, PromptConfig
        from src.agent._skill_model import Skill

        soul_content = "# Core\n1. Shared step\n2. Another step\n"

        skill_dir1 = tmp_path / "skill_a"
        skill_dir1.mkdir()
        (skill_dir1 / "SOUL.md").write_text(soul_content, encoding="utf-8")

        skill_dir2 = tmp_path / "skill_b"
        skill_dir2.mkdir()
        (skill_dir2 / "SOUL.md").write_text(soul_content, encoding="utf-8")

        builder = PromptBuilder()
        skill_a = Skill(name="skill_a", soul_path=str(skill_dir1 / "SOUL.md"))
        skill_b = Skill(name="skill_b", soul_path=str(skill_dir2 / "SOUL.md"))

        config = PromptConfig(
            active_skills=[skill_a, skill_b],
            relevant_skill_names=set(),
            skill_token_budget=8000,
        )
        prompt = builder.build(config)
        assert isinstance(prompt, str)

        skills_section = prompt[prompt.find("<skills>"):]
        # Count occurrences of "Shared step" — should appear twice (once per skill)
        count = skills_section.count("Shared step")
        assert count == 2, f"Expected 2 occurrences of 'Shared step', got {count}"


# ── Category 5: Deeper adversarial edge cases found by code analysis ─────────

def _make_review_point(title="Test", category="other", severity="minor",
                       detail="detail", source="llm"):
    """Helper: create a ReviewPoint for testing."""
    from src.argument.companion_models import ReviewPoint
    return ReviewPoint(
        severity=severity,  # type: ignore
        category=category,  # type: ignore
        title=title,
        detail=detail,
        source=source,  # type: ignore
    )


class TestDeeperAdversarial:
    """Additional adversarial tests targeting subtle bugs discovered by code analysis."""

    def _make_skills_dir(self, tmp_path: Path) -> Path:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        return skills_dir

    # --- Bug hunt: _parse_legacy description vs body parsing ---

    def test_21_migration_description_truncation_200_chars(self, tmp_path: Path) -> None:
        """Migration truncates description to 200 chars. Verify exact boundary."""
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "long_desc"
        skill_dir.mkdir()
        long_desc = "A" * 250
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: long\ntrigger: long\n---\n\n# {long_desc}\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1

        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        # The description body after --- should be truncated to 200 chars
        # Extract body after frontmatter
        body_start = identity.find("---", 3) + 3  # skip second ---
        body = identity[body_start:].strip()
        assert len(body) <= 200, f"Body length {len(body)} exceeds 200 chars"

    def test_22_migration_unicode_description(self, tmp_path: Path) -> None:
        """Migration with Chinese/unicode description. Verify no encoding corruption."""
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "unicode_skill"
        skill_dir.mkdir()
        cn_desc = "这是一个中文描述，包含特殊字符：①②③ 和 emoji \U0001f600"
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: unicode\ntrigger: unicode\n---\n\n# {cn_desc}\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1
        assert result["errors"] == []

        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        assert cn_desc in identity

    def test_23_migration_frontmatter_empty_name_no_fallback_to_dirname(self, tmp_path: Path) -> None:
        """BUG: Frontmatter 'name:   ' (whitespace-only) gets stored as '' by
        partition(':').strip(). Then fm.get('name', skill_dir.name) returns ''
        because the key IS present (just empty). The directory-name fallback
        never fires. IDENTITY.md ends up with 'name: ' (empty name).
        """
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "empty_fm"
        skill_dir.mkdir()
        # name: with trailing whitespace only
        (skill_dir / "SKILL.md").write_text(
            "---\nname:   \ntrigger:\n---\n\n# Fallback Title\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 1
        assert result["errors"] == []

        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        # BUG: name is empty, fallback to directory name did NOT activate
        # Expected: name should fall back to directory name "empty_fm"
        # Actual: name is empty string because fm.get("name") returns ""
        assert "empty_fm" in identity, (
            "BUG: When SKILL.md frontmatter has 'name:   ' (empty after strip), "
            "migration does not fall back to directory name. IDENTITY.md gets "
            "'name: ' (empty). The fallback in fm.get('name', skill_dir.name) "
            "doesn't fire because the key exists with value ''."
        )

    # --- BUG CONFIRMED: _save_skill fallback when IDENTITY.md has no frontmatter ---

    def test_24_save_three_layer_skill_no_frontmatter_identity(self, tmp_path: Path) -> None:
        """BUG: _save_skill on a three-layer skill whose IDENTITY.md has NO frontmatter
        falls through to legacy path, creating a SKILL.md alongside IDENTITY.md.
        This causes data split — future loads will load stale IDENTITY.md (three-layer
        path takes priority) and miss the updated SKILL.md data.
        """
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "no_fm_identity"
        skill_dir.mkdir()
        # IDENTITY.md with NO frontmatter — just body text
        (skill_dir / "IDENTITY.md").write_text(
            "Just some body text with no frontmatter at all.\n",
            encoding="utf-8",
        )
        (skill_dir / "SOUL.md").write_text("# Core\n1. Step\n", encoding="utf-8")

        class FakeRegistry(SkillPersistenceMixin):
            def __init__(self, sd: Path):
                self.skills_dir = sd
                self._skills: dict[str, Skill] = {}

        reg = FakeRegistry(skills_dir)

        skill = Skill(
            name="no_fm_identity",
            trigger="test",
            identity_path=str(skill_dir / "IDENTITY.md"),
        )
        # This calls _save_skill. identity_path exists, so it enters the three-layer
        # branch. But IDENTITY.md has no frontmatter, so fm_match is None.
        # The code does: if fm_match: ... else: falls through to legacy path.
        # This means it creates a NEW SKILL.md file under skills_dir/no_fm_identity/
        reg._save_skill(skill)

        # BUG: A SKILL.md is created ALONGSIDE IDENTITY.md — data split
        legacy_file = skill_dir / "SKILL.md"
        identity_file = skill_dir / "IDENTITY.md"

        # Both files now exist — this is the bug (dual representation)
        if legacy_file.exists() and identity_file.exists():
            pytest.fail(
                "BUG FOUND: _save_skill created SKILL.md alongside IDENTITY.md "
                "when IDENTITY.md lacks frontmatter. This causes data split — "
                "future loads will load the stale IDENTITY.md (three-layer path) "
                "and miss the updated SKILL.md data."
            )

    # --- BUG CONFIRMED: _parse_llm_points missing category defaults to "other" ---

    def test_25_parse_llm_points_missing_category_accepted_instead_of_rejected(self) -> None:
        """BUG: _parse_llm_points accepts items without 'category' field.
        The code does: category = item.get("category", "other"), then checks
        'if not title or not detail or not category'. Since category defaults
        to "other" (non-empty), the check passes. This means items missing
        the category field are silently accepted with category="other" instead
        of being rejected. This is a data quality issue — LLM may return
        incomplete items that get accepted with wrong category.
        """
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([
            {"severity": "major", "title": "Good title", "detail": "Good detail"},
        ])
        result = _parse_llm_points(raw, source="llm")
        # BUG: item without 'category' is accepted with category="other"
        assert result == [], (
            "BUG: _parse_llm_points accepted item without 'category' field, "
            "defaulting to 'other'. Items missing the category field should be "
            "rejected to prevent data quality degradation from incomplete LLM output. "
            f"Got: {result}"
        )

    def test_26_parse_llm_points_missing_detail(self) -> None:
        """_parse_llm_points: item missing 'detail' field should be discarded."""
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([
            {"severity": "major", "title": "Good title", "category": "soundness"},
        ])
        result = _parse_llm_points(raw, source="llm")
        assert result == [], f"Expected [] for item without detail, got {result}"

    def test_27_parse_llm_points_empty_title(self) -> None:
        """_parse_llm_points: item with empty title string should be discarded."""
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([
            {"severity": "major", "title": "", "detail": "d", "category": "soundness"},
        ])
        result = _parse_llm_points(raw, source="llm")
        assert result == [], "Expected [] for item with empty title"

    def test_28_parse_llm_points_invalid_category_rejected(self) -> None:
        """_parse_llm_points: item with invalid category (not in Literal) should crash
        or be rejected. ReviewPoint.category is a Literal type — Pydantic should reject."""
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([
            {"severity": "major", "title": "T", "detail": "d", "category": "totally_invalid_category"},
        ])
        result = _parse_llm_points(raw, source="llm")
        # If Pydantic raises ValidationError, it's caught by the generic except.
        # So the item should be silently dropped.
        assert result == [], (
            "BUG: _parse_llm_points accepted invalid category 'totally_invalid_category'. "
            "ReviewPoint.category is a Literal type and should reject unknown values."
        )

    # --- Bug hunt: aggregate_perspectives title case sensitivity ---

    def test_29_aggregate_case_insensitive_title_dedup(self) -> None:
        """aggregate_perspectives uses title.lower() for dedup.
        'Missing Baseline' and 'missing baseline' should be considered same.
        """
        from src.argument._reviewer_perspectives import aggregate_perspectives

        p1 = _make_review_point(title="Missing Baseline", category="baseline", severity="major")
        p2 = _make_review_point(title="missing baseline", category="baseline", severity="minor")

        result = aggregate_perspectives([p1], [p2], [])
        # title.lower() is the same, so should deduplicate
        assert len(result) == 1, f"Expected 1 (deduped), got {len(result)}"

    # --- Bug hunt: _load_three_layer_skill with empty IDENTITY.md ---

    def test_30_load_empty_identity_md(self, tmp_path: Path) -> None:
        """Three-layer skill with completely empty IDENTITY.md — should not crash."""
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "empty_identity"
        skill_dir.mkdir()
        (skill_dir / "IDENTITY.md").write_text("", encoding="utf-8")

        class FakeRegistry(SkillPersistenceMixin):
            def __init__(self, sd: Path):
                self.skills_dir = sd
                self._skills: dict[str, Skill] = {}

        reg = FakeRegistry(skills_dir)
        loaded = reg._load_three_layer_skill(skill_dir)
        # Should return a Skill (not None), using directory name as fallback
        assert loaded is not None
        assert loaded.name == "empty_identity"  # fallback to dir name
        assert loaded.description == ""
        assert loaded.trigger == ""

    def test_31_load_identity_md_only_whitespace(self, tmp_path: Path) -> None:
        """Three-layer skill with IDENTITY.md containing only whitespace."""
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "ws_identity"
        skill_dir.mkdir()
        (skill_dir / "IDENTITY.md").write_text("   \n\n  \n", encoding="utf-8")

        class FakeRegistry(SkillPersistenceMixin):
            def __init__(self, sd: Path):
                self.skills_dir = sd
                self._skills: dict[str, Skill] = {}

        reg = FakeRegistry(skills_dir)
        loaded = reg._load_three_layer_skill(skill_dir)
        assert loaded is not None
        assert loaded.name == "ws_identity"

    # --- Bug hunt: _parse_llm_points with markdown code fence ---

    def test_32_parse_llm_points_markdown_code_fence(self) -> None:
        """_parse_llm_points: LLM returns JSON wrapped in markdown code fence."""
        from src.argument.reviewer import _parse_llm_points

        raw = '```json\n[{"severity":"major","title":"T","detail":"d","category":"soundness"}]\n```'
        result = _parse_llm_points(raw, source="llm")
        assert len(result) == 1
        assert result[0].title == "T"

    def test_33_parse_llm_points_code_fence_no_language(self) -> None:
        """_parse_llm_points: code fence without language tag."""
        from src.argument.reviewer import _parse_llm_points

        raw = '```\n[{"severity":"major","title":"T","detail":"d","category":"soundness"}]\n```'
        result = _parse_llm_points(raw, source="llm")
        assert len(result) == 1

    # --- Bug hunt: _skill_migrate with both SKILL.md and IDENTITY.md pre-existing ---

    def test_34_migration_skips_when_identity_exists_alongside_skill(self, tmp_path: Path) -> None:
        """If both SKILL.md and IDENTITY.md exist, migration should skip (not re-migrate)."""
        from src.agent._skill_migrate import migrate_skills_dir

        skills_dir = self._make_skills_dir(tmp_path)
        skill_dir = skills_dir / "dual"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: dual\ntrigger: dual\n---\n\n# Dual\n",
            encoding="utf-8",
        )
        (skill_dir / "IDENTITY.md").write_text(
            "---\nname: already_migrated\ntrigger: done\n---\nAlready done\n",
            encoding="utf-8",
        )

        result = migrate_skills_dir(skills_dir)
        assert result["migrated"] == 0
        assert result["skipped"] == 1
        # IDENTITY.md should NOT be overwritten
        identity = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
        assert "already_migrated" in identity

    # --- Bug hunt: aggregate_perspectives preserves order ---

    def test_35_aggregate_preserves_method_experiment_writing_order(self) -> None:
        """aggregate_perspectives should preserve method -> experiment -> writing order."""
        from src.argument._reviewer_perspectives import aggregate_perspectives

        p_m = _make_review_point(title="Method issue", category="soundness", source="llm")
        p_e = _make_review_point(title="Experiment issue", category="experiment_design", source="llm")
        p_w = _make_review_point(title="Writing issue", category="writing_clarity", source="llm")

        result = aggregate_perspectives([p_m], [p_e], [p_w])
        assert len(result) == 3
        assert result[0].title == "Method issue"
        assert result[1].title == "Experiment issue"
        assert result[2].title == "Writing issue"

    # --- Bug hunt: _parse_llm_points with mixed valid/invalid items ---

    def test_36_parse_llm_points_mixed_valid_invalid(self) -> None:
        """_parse_llm_points: array with some valid and some invalid items.
        Only valid ones should be returned.
        """
        from src.argument.reviewer import _parse_llm_points

        raw = json.dumps([
            "not a dict",                                    # invalid: string
            42,                                              # invalid: int
            {"severity": "major", "title": "", "detail": "d", "category": "soundness"},  # invalid: empty title
            {"severity": "major", "title": "Valid", "detail": "d", "category": "soundness"},  # valid
            {"severity": "major", "title": "Also Valid", "detail": "d", "category": "other"},  # valid
            None,                                            # invalid: null
        ])
        result = _parse_llm_points(raw, source="llm")
        assert len(result) == 2
        titles = [r.title for r in result]
        assert "Valid" in titles
        assert "Also Valid" in titles

    # --- Bug hunt: _save_skill for legacy creates skill dir with name containing special chars ---

    def test_37_save_skill_name_with_slash(self, tmp_path: Path) -> None:
        """_save_skill with a skill name containing path separator.
        This could create unintended nested directories.
        """
        from src.agent._skill_model import Skill
        from src.agent._skill_persistence import SkillPersistenceMixin

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        class FakeRegistry(SkillPersistenceMixin):
            def __init__(self, sd: Path):
                self.skills_dir = sd
                self._skills: dict[str, Skill] = {}

        reg = FakeRegistry(skills_dir)

        # On Windows, "/" is not a valid path separator in dir names,
        # but Path.mkdir(parents=True) could create nested dirs
        skill = Skill(name="evil/../pwned", trigger="test")
        reg._save_skill(skill)

        # Check what was actually created
        # skills_dir / "evil/../pwned" resolves to skills_dir / "pwned"
        pwned_dir = (skills_dir / "pwned").resolve()
        if pwned_dir.exists():
            # This means the path traversal worked — potential security issue
            skill_file = pwned_dir / "SKILL.md"
            if skill_file.exists():
                # Verify the skill name in the file
                content = skill_file.read_text(encoding="utf-8")
                # The name in frontmatter is "evil/../pwned" which is misleading
                assert "evil" in content or "pwned" in content

    # --- Bug hunt: _build_skill_section budget overflow ---

    def test_38_skill_section_budget_partial_injection(self, tmp_path: Path) -> None:
        """_build_skill_section: two skills where first fits budget but second doesn't.
        Only first should be injected.
        """
        from src.agent.prompt_builder import PromptBuilder, PromptConfig
        from src.agent._skill_model import Skill

        # Skill A: small SOUL
        skill_dir_a = tmp_path / "small_a"
        skill_dir_a.mkdir()
        (skill_dir_a / "SOUL.md").write_text("# Core\n1. Small step\n", encoding="utf-8")

        # Skill B: large SOUL
        skill_dir_b = tmp_path / "large_b"
        skill_dir_b.mkdir()
        big_content = "# Core\n" + "\n".join(f"{i}. {'X' * 100}" for i in range(1, 50))
        (skill_dir_b / "SOUL.md").write_text(big_content, encoding="utf-8")

        builder = PromptBuilder()
        skill_a = Skill(name="small_a", soul_path=str(skill_dir_a / "SOUL.md"))
        skill_b = Skill(name="large_b", soul_path=str(skill_dir_b / "SOUL.md"))

        # Budget enough for A but not B
        config = PromptConfig(
            active_skills=[skill_a, skill_b],
            relevant_skill_names=set(),
            skill_token_budget=200,
        )
        prompt = builder.build(config)
        assert "<skills>" in prompt
        assert "Small step" in prompt
        # Large skill should NOT be injected (over budget)
        assert "X" * 100 not in prompt

    # --- Bug hunt: _parse_llm_points with empty JSON array ---

    def test_39_parse_llm_points_empty_array(self) -> None:
        """_parse_llm_points with '[]' should return empty list."""
        from src.argument.reviewer import _parse_llm_points

        result = _parse_llm_points("[]", source="llm")
        assert result == []

    def test_40_parse_llm_points_whitespace_only(self) -> None:
        """_parse_llm_points with only whitespace should return []."""
        from src.argument.reviewer import _parse_llm_points

        result = _parse_llm_points("   \n\t  ", source="llm")
        assert result == []
