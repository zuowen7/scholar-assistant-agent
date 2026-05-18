"""Unit tests for Skill three-layer file decomposition (Phase C)."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from src.agent.skill_system import SkillRegistry


def _make_three_layer_skill(skills_root: Path, name: str, trigger: str = "",
                              description: str = "Test skill",
                              soul_content: str = "# Soul\nCore content",
                              agents_content: str = "# Agents\nExtended content") -> Path:
    """Helper: create a three-layer skill directory for tests."""
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    identity_body = description[:200]
    (skill_dir / "IDENTITY.md").write_text(
        f"---\nname: {name}\ntrigger: {trigger or name}\ncreated: 2024-01-01\n"
        f"updated: 2024-01-01\nlast_used: 2024-01-01\nuse_count: 0\ndeprecated: false\n---\n"
        f"{identity_body}",
        encoding="utf-8"
    )
    (skill_dir / "SOUL.md").write_text(soul_content, encoding="utf-8")
    (skill_dir / "AGENTS.md").write_text(agents_content, encoding="utf-8")
    return skill_dir


# C1 — skill loads from three files
def test_skill_loads_from_three_files(tmp_path):
    _make_three_layer_skill(tmp_path / "skills", "my_skill", trigger="test skill")
    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill = reg.get("my_skill")
    assert skill is not None
    assert skill.soul_path.endswith("SOUL.md")
    assert skill.agents_path.endswith("AGENTS.md")
    assert skill.identity_path.endswith("IDENTITY.md")


# C2 — IDENTITY body is truncated to ≤ 200 chars
def test_identity_under_200_chars(tmp_path):
    skill_dir = tmp_path / "skills" / "verbose_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "IDENTITY.md").write_text(
        "---\nname: verbose_skill\ntrigger: verbose\ncreated: 2024-01-01\n"
        "updated: 2024-01-01\nlast_used: 2024-01-01\nuse_count: 0\ndeprecated: false\n---\n"
        + "V" * 300,
        encoding="utf-8"
    )
    (skill_dir / "SOUL.md").write_text("Soul content", encoding="utf-8")
    (skill_dir / "AGENTS.md").write_text("Agents content", encoding="utf-8")
    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill = reg.get("verbose_skill")
    assert skill is not None
    assert len(skill.description) <= 200


# C3 — SOUL always in context (tested via PromptBuilder)
def test_soul_always_in_context(tmp_path):
    _make_three_layer_skill(
        tmp_path / "skills", "soul_skill", trigger="soul test",
        soul_content="SOUL_MARKER_UNIQUE_XYZ123",
        agents_content="AGENTS_MARKER_UNIQUE_XYZ456"
    )
    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill = reg.get("soul_skill")
    assert skill is not None

    from src.agent.prompt_builder import PromptBuilder, PromptConfig
    builder = PromptBuilder()
    config = PromptConfig(active_skills=[skill], relevant_skill_names=set())
    prompt = builder.build(config)
    assert "SOUL_MARKER_UNIQUE_XYZ123" in prompt
    assert "AGENTS_MARKER_UNIQUE_XYZ456" not in prompt


# C4 — AGENTS only when skill is in relevant_skill_names
def test_agents_only_when_relevant(tmp_path):
    _make_three_layer_skill(tmp_path / "skills", "skill_a",
                             soul_content="SOUL_A_CONTENT", agents_content="AGENTS_A_CONTENT")
    _make_three_layer_skill(tmp_path / "skills", "skill_b",
                             soul_content="SOUL_B_CONTENT", agents_content="AGENTS_B_CONTENT")

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill_a = reg.get("skill_a")
    skill_b = reg.get("skill_b")
    assert skill_a and skill_b

    from src.agent.prompt_builder import PromptBuilder, PromptConfig
    builder = PromptBuilder()
    config = PromptConfig(
        active_skills=[skill_a, skill_b],
        relevant_skill_names={"skill_a"},
    )
    prompt = builder.build(config)
    assert "SOUL_A_CONTENT" in prompt
    assert "SOUL_B_CONTENT" in prompt
    assert "AGENTS_A_CONTENT" in prompt
    assert "AGENTS_B_CONTENT" not in prompt


# C5 — matching does not read SOUL/AGENTS files
def test_matching_reads_only_identity(tmp_path):
    _make_three_layer_skill(tmp_path / "skills", "io_test_skill",
                             trigger="io test, match me",
                             soul_content="SOUL_SHOULD_NOT_BE_READ",
                             agents_content="AGENTS_SHOULD_NOT_BE_READ")

    reads_after_init: list[str] = []

    # First load the registry normally (IDENTITY.md will be read)
    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))

    # Now spy on read_text AFTER init
    original_read_text = Path.read_text
    def spy_read(self, *args, **kwargs):
        reads_after_init.append(str(self))
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", spy_read):
        reg.match("io test match me")

    soul_or_agents_reads = [r for r in reads_after_init
                             if "SOUL.md" in r or "AGENTS.md" in r]
    assert soul_or_agents_reads == [], (
        f"match() read SOUL/AGENTS files (should only use in-memory data): {soul_or_agents_reads}"
    )


# C6 — token budget respected in prompt_builder
def test_token_budget_respected(tmp_path):
    for name in ["big_skill_1", "big_skill_2"]:
        _make_three_layer_skill(tmp_path / "skills", name,
                                 soul_content="S" * 800,
                                 agents_content="A" * 400)

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skills = [reg.get("big_skill_1"), reg.get("big_skill_2")]
    assert all(skills)

    from src.agent.prompt_builder import PromptBuilder, PromptConfig
    builder = PromptBuilder()
    config = PromptConfig(
        active_skills=skills,
        relevant_skill_names={"big_skill_1", "big_skill_2"},
        skill_token_budget=1000,
    )
    prompt = builder.build(config)

    # Extract skill section
    start = prompt.find("<skills>")
    end = prompt.find("</skills>")
    if start >= 0 and end >= 0:
        skill_section = prompt[start : end + len("</skills>")]
        # Budget is 1000 chars; section (incl tags) should not wildly exceed it
        assert len(skill_section) <= 1200, (
            f"Skill section ({len(skill_section)} chars) exceeded budget+overhead of 1200"
        )


# C7 — migration from legacy SKILL.md
def test_migration_from_legacy_single_file(tmp_path):
    skill_dir = tmp_path / "skills" / "legacy_skill"
    skill_dir.mkdir(parents=True)
    legacy_content = (
        "---\n"
        "name: legacy_skill\n"
        "trigger: legacy, migration test\n"
        "created: 2024-01-01\n"
        "updated: 2024-01-01\n"
        "last_used: 2024-01-01\n"
        "use_count: 3\n"
        "deprecated: false\n"
        "---\n\n"
        "# Legacy Skill Description\n\n"
        "## 步骤\n"
        "1. Do step one\n"
        "2. Do step two\n\n"
        "## 注意事项\n"
        "- Note one\n"
        "- Note two\n"
    )
    (skill_dir / "SKILL.md").write_text(legacy_content, encoding="utf-8")

    from src.agent._skill_migrate import migrate_skills_dir
    result = migrate_skills_dir(tmp_path / "skills", dry_run=False)

    assert result["migrated"] == 1
    assert result["errors"] == []
    assert (skill_dir / "IDENTITY.md").exists()
    assert (skill_dir / "SOUL.md").exists()
    assert (skill_dir / "AGENTS.md").exists()
    # Original backed up
    assert (skill_dir / "SKILL.md.bak").exists()
    # IDENTITY body mentions skill
    identity_text = (skill_dir / "IDENTITY.md").read_text(encoding="utf-8")
    assert "legacy_skill" in identity_text


# C8 — missing SOUL.md is handled gracefully
def test_missing_soul_graceful(tmp_path):
    skill_dir = tmp_path / "skills" / "no_soul"
    skill_dir.mkdir(parents=True)
    (skill_dir / "IDENTITY.md").write_text(
        "---\nname: no_soul\ntrigger: no soul\ncreated: 2024-01-01\n"
        "updated: 2024-01-01\nlast_used: 2024-01-01\nuse_count: 0\ndeprecated: false\n---\n"
        "No soul skill",
        encoding="utf-8"
    )
    (skill_dir / "AGENTS.md").write_text("Agents content", encoding="utf-8")
    # SOUL.md intentionally missing

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill = reg.get("no_soul")
    assert skill is not None  # Should load without crash


# C9 — missing AGENTS.md is handled gracefully
def test_missing_agents_graceful(tmp_path):
    skill_dir = tmp_path / "skills" / "no_agents"
    skill_dir.mkdir(parents=True)
    (skill_dir / "IDENTITY.md").write_text(
        "---\nname: no_agents\ntrigger: no agents\ncreated: 2024-01-01\n"
        "updated: 2024-01-01\nlast_used: 2024-01-01\nuse_count: 0\ndeprecated: false\n---\n"
        "No agents skill",
        encoding="utf-8"
    )
    (skill_dir / "SOUL.md").write_text("Soul content", encoding="utf-8")
    # AGENTS.md intentionally missing

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    skill = reg.get("no_agents")
    assert skill is not None


# C10 — empty skill directory is skipped
def test_empty_skill_directory(tmp_path):
    empty_dir = tmp_path / "skills" / "empty_skill"
    empty_dir.mkdir(parents=True)
    # No files

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    assert reg.get("empty_skill") is None


# C11 — invalid YAML frontmatter in IDENTITY.md does not crash
def test_invalid_identity_yaml(tmp_path):
    skill_dir = tmp_path / "skills" / "bad_yaml"
    skill_dir.mkdir(parents=True)
    (skill_dir / "IDENTITY.md").write_text(
        "---\nname: bad_yaml\ntrigger: [invalid yaml: {\n---\nBad YAML skill",
        encoding="utf-8"
    )
    (skill_dir / "SOUL.md").write_text("Soul", encoding="utf-8")
    (skill_dir / "AGENTS.md").write_text("Agents", encoding="utf-8")

    # Should not raise
    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    # May or may not load (implementation choice), but must not crash


# C12 — IDENTITY.md without frontmatter uses directory name as skill name
def test_identity_no_frontmatter(tmp_path):
    skill_dir = tmp_path / "skills" / "no_frontmatter_skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "IDENTITY.md").write_text(
        "Just a plain description, no frontmatter",
        encoding="utf-8"
    )
    (skill_dir / "SOUL.md").write_text("Soul", encoding="utf-8")
    (skill_dir / "AGENTS.md").write_text("Agents", encoding="utf-8")

    reg = SkillRegistry(skills_dir=str(tmp_path / "skills"))
    # Should fall back to directory name
    skill = reg.get("no_frontmatter_skill")
    assert skill is not None
    assert skill.name == "no_frontmatter_skill"
