"""Skills 测试 — 加载/解析/注入/边缘/并发。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent_v2.skills import Skill, SkillRegistry, _BUILTIN_SKILLS


class TestSkillParsing:
    def test_parse_frontmatter(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text("---\nname: my_skill\ndescription: test desc\nlayer: soul\n---\n# Content\n\nActual content here.", encoding="utf-8")
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

    def test_skill_inject_prompt(self):
        skill = Skill(name="test", layer="agents", content="## Test\nContent")
        inj = skill.inject_prompt()
        assert "<!-- SKILL: test" in inj
        assert "Content" in inj

    def test_empty_skill_no_inject(self):
        skill = Skill(name="empty")
        assert skill.inject_prompt() == ""


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
        reg.register(Skill(name="a", layer="agents", content="Agent A"))
        reg.register(Skill(name="b", layer="soul", content="Soul B"))
        all_inj = reg.build_prompt_injection()
        assert "Agent A" in all_inj
        assert "Soul B" in all_inj
        # Filter by layer
        agents_only = reg.build_prompt_injection(layer="agents")
        assert "Agent A" in agents_only
        assert "Soul B" not in agents_only

    def test_build_injection_respects_active(self):
        reg = SkillRegistry()
        reg.register(Skill(name="active", content="Active"))
        reg.register(Skill(name="inactive", content="Inactive"))
        reg.deactivate("inactive")
        inj = reg.build_prompt_injection()
        assert "Active" in inj
        assert "Inactive" not in inj

    def test_list_all(self):
        reg = SkillRegistry()
        reg.register(Skill(name="s1", description="d1"))
        reg.register(Skill(name="s2"))
        reg.deactivate("s2")
        items = reg.list_all()
        assert len(items) == 2
        assert {i["active"] for i in items} == {True, False}

    def test_duplicate_register_overwrites(self):
        reg = SkillRegistry()
        reg.register(Skill(name="s", content="first"))
        reg.register(Skill(name="s", content="second"))
        assert reg.get("s").content == "second"


class TestBuiltinSkills:
    def test_all_builtins_present(self):
        assert len(_BUILTIN_SKILLS) == 5
        names = {s.name for s in _BUILTIN_SKILLS}
        assert "academic_writing" in names
        assert "paper_review" in names
        assert "chinese_academic" in names

    def test_all_builtins_have_content(self):
        for s in _BUILTIN_SKILLS:
            assert s.content.strip(), f"{s.name} has empty content"
            assert s.layer in ("soul", "agents", "identity")

    def test_register_builtins_into_registry(self):
        reg = SkillRegistry()
        for s in _BUILTIN_SKILLS:
            reg.register(s)
        assert len(reg.list_all()) == 5

    def test_builtins_inject_into_prompt(self):
        reg = SkillRegistry()
        for s in _BUILTIN_SKILLS:
            reg.register(s)
        inj = reg.build_prompt_injection(layer="agents")
        assert len(inj) > 100


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
        assert reg.get("long") is not None

    def test_unicode_skill_name(self, tmp_path: Path):
        f = tmp_path / "中文技能.md"
        f.write_text("中文内容", encoding="utf-8")
        reg = SkillRegistry()
        reg.load_dir(tmp_path)
        assert reg.get("中文技能") is not None

    def test_100_skills_injection(self):
        reg = SkillRegistry()
        for i in range(100):
            reg.register(Skill(name=f"s{i:03d}", content=f"Content {i}"))
        inj = reg.build_prompt_injection()
        assert len(inj) > 0
