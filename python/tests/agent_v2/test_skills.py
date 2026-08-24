"""Skills 测试 — 加载/解析/注入/边缘/并发。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent_v2.skills import _BUILTIN_SKILLS, Skill, SkillRegistry, parse_skill_document
from src.agent_v2.tools.registry import ToolRegistry
from src.agent_v2.tools.skill_tools import register_skill_tools


class TestSkillParsing:
    def test_parse_frontmatter(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text(
            "---\nname: my_skill\ndescription: test desc\nlayer: soul\n---\n# Content\n\nActual content here.",
            encoding="utf-8",
        )
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        skill = reg.get("my_skill")
        assert skill is not None
        assert skill.layer == "soul"
        assert skill.description == "test desc"
        assert "Actual content" in skill.content
        assert "---" not in skill.content  # frontmatter stripped

    def test_no_frontmatter(self, tmp_path: Path):
        f = tmp_path / "plain.md"
        f.write_text("Just plain markdown content without frontmatter.", encoding="utf-8")
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        skill = reg.get("plain")
        assert skill is not None
        assert "Just plain markdown" in skill.content
        assert skill.layer == "agents"  # default
        assert skill.default_active is False

    def test_skill_inject_prompt(self):
        skill = Skill(name="test", layer="agents", content="## Test\nContent")
        inj = skill.inject_prompt()
        assert "<!-- SKILL: test" in inj
        assert "Content" in inj

    def test_empty_skill_no_inject(self):
        skill = Skill(name="empty")
        assert skill.inject_prompt() == ""

    def test_standard_skill_package_requires_valid_frontmatter(self, tmp_path: Path):
        package = tmp_path / "learned_skill"
        package.mkdir()
        (package / "SKILL.md").write_text(
            "---\nname: learned_skill\ndescription: Reusable workflow\n---\n# Procedure\nDo it.",
            encoding="utf-8",
        )
        invalid = tmp_path / "invalid"
        invalid.mkdir()
        (invalid / "SKILL.md").write_text("# No frontmatter", encoding="utf-8")

        registry = SkillRegistry()
        assert registry.load_dir(tmp_path) == 1
        assert registry.get("learned_skill") is not None
        assert registry.get("invalid") is None

    def test_parse_standard_document_rejects_missing_description(self):
        with pytest.raises(ValueError, match="name and description"):
            parse_skill_document("---\nname: incomplete\n---\n# Procedure")


class TestSkillRegistry:
    def test_load_dir(self, tmp_path: Path):
        (tmp_path / "a.md").write_text("content a", encoding="utf-8")
        (tmp_path / "b.md").write_text("content b", encoding="utf-8")
        reg = SkillRegistry()
        n = reg.load_dir(tmp_path)
        assert n == 2
        assert reg.get("a").content == "content a"
        assert reg.get("b").content == "content b"

    def test_load_empty_dir(self, tmp_path: Path):
        reg = SkillRegistry()
        n = reg.load_dir(tmp_path)
        assert n == 0

    def test_load_nonexistent_dir(self):
        reg = SkillRegistry()
        n = reg.load_dir(Path("/no/such/dir"))
        assert n == 0

    def test_activate_deactivate(self):
        reg = SkillRegistry()
        reg.register(Skill(name="s1", content="c1"))
        assert reg.activate("s1")
        assert not reg.activate("nonexistent")
        assert reg.deactivate("s1")
        assert not reg.deactivate("nonexistent")

    def test_build_injection(self):
        reg = SkillRegistry()
        reg.register(Skill(name="a", layer="agents", content="Agent A", default_active=True))
        reg.register(Skill(name="b", layer="soul", content="Soul B", default_active=True))
        all_inj = reg.build_prompt_injection()
        assert "Agent A" in all_inj
        assert "Soul B" in all_inj
        # Filter by layer
        agents_only = reg.build_prompt_injection(layer="agents")
        assert "Agent A" in agents_only
        assert "Soul B" not in agents_only

    def test_build_injection_respects_active(self):
        reg = SkillRegistry()
        reg.register(Skill(name="active", content="Active", default_active=True))
        reg.register(Skill(name="inactive", content="Inactive", default_active=False))
        inj = reg.build_prompt_injection()
        assert "Active" in inj
        assert "Inactive" not in inj

    def test_list_all(self):
        reg = SkillRegistry()
        reg.register(Skill(name="s1", description="d1"))
        reg.register(Skill(name="s2"))
        reg.activate("s1")
        reg.deactivate("s2")
        items = reg.list_all()
        assert len(items) == 2
        assert {i["active"] for i in items} == {True, False}

    def test_duplicate_register_overwrites(self):
        reg = SkillRegistry()
        reg.register(Skill(name="s", content="first"))
        reg.register(Skill(name="s", content="second"))
        assert reg.get("s").content == "second"

    def test_discovery_prompt_lists_inactive_skill_without_full_content(self):
        reg = SkillRegistry()
        reg.register(Skill(name="available", description="Short summary", content="SECRET BODY"))

        prompt = reg.build_discovery_prompt()

        assert 'name="available"' in prompt
        assert "Short summary" in prompt
        assert "SECRET BODY" not in prompt


@pytest.mark.asyncio
async def test_skill_tools_list_and_load_exact_skill():
    skills = SkillRegistry()
    skills.register(Skill(name="workflow", description="Reusable", content="# Steps\n1. Verify"))
    tools = ToolRegistry()
    register_skill_tools(tools, skills)

    listed = await tools.execute("skills_list", {})
    viewed = await tools.execute("skill_view", {"name": "workflow"})
    missing = await tools.execute("skill_view", {"name": "../workflow"})

    assert json.loads(listed.output)[0]["name"] == "workflow"
    assert json.loads(viewed.output)["content"].startswith("# Steps")
    assert missing.is_error is True


class TestBuiltinSkills:
    def test_all_builtins_present(self):
        names = {s.name for s in _BUILTIN_SKILLS}
        assert names == {
            "academic_writing",
            "paper_review",
            "latex_formatting",
            "chinese_academic",
            "methodology_critique",
            "nature_writing",
            "nature_polishing",
            "nature_reviewer",
            "nature_response",
            "nature_citation",
            "nature_data",
            "nature_reader",
            "nature_figure",
        }

    def test_all_builtins_have_content(self):
        for s in _BUILTIN_SKILLS:
            assert s.content.strip(), f"{s.name} has empty content"
            assert s.layer in ("soul", "agents", "identity")

    def test_register_builtins_into_registry(self):
        reg = SkillRegistry()
        for s in _BUILTIN_SKILLS:
            reg.register(s)
        assert {item["name"] for item in reg.list_all()} == {s.name for s in _BUILTIN_SKILLS}

    def test_builtins_inject_into_prompt(self):
        reg = SkillRegistry()
        for s in _BUILTIN_SKILLS:
            reg.register(s)
            reg.activate(s.name)
        inj = reg.build_prompt_injection(layer="agents")
        assert len(inj) > 100

    def test_builtins_are_opt_in_because_core_safety_lives_in_the_runtime_prompt(self):
        assert all(skill.default_active is False for skill in _BUILTIN_SKILLS)

    def test_source_grounding_guards_cover_observed_live_failures(self):
        content = {skill.name: skill.content for skill in _BUILTIN_SKILLS}

        assert "does not establish the number of retained components" in content["latex_formatting"]
        assert "not independent evidence" in content["nature_reviewer"]
        assert "Do not mine sibling generated drafts" in content["nature_reviewer"]
        assert "not recorded" in content["nature_response"]
        assert "does not imply held-out" in content["nature_reader"]
        assert "Do not relabel PCA explained variance" in content["nature_figure"]


class TestSkillEdge:
    def test_malformed_yaml(self, tmp_path: Path):
        f = tmp_path / "bad.md"
        f.write_text("---\n: bad yaml\n{{{{\n---\ncontent", encoding="utf-8")
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        # Should not crash
        assert reg.get("bad") is not None

    def test_very_long_skill(self, tmp_path: Path):
        f = tmp_path / "long.md"
        f.write_text("x" * 100_000, encoding="utf-8")
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        assert reg.get("long") is None

    def test_unicode_skill_name(self, tmp_path: Path):
        f = tmp_path / "中文技能.md"
        f.write_text("中文内容", encoding="utf-8")
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        assert reg.get("中文技能") is not None

    def test_100_skills_injection(self):
        reg = SkillRegistry()
        for i in range(100):
            reg.register(Skill(name=f"s{i:03d}", content=f"Content {i}", default_active=True))
        with pytest.raises(ValueError, match="active skill limit"):
            reg.build_prompt_injection()
