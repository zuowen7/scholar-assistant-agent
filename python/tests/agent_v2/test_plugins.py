"""Plugin 测试 — 加载/注册/边缘/故障。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.agent_v2.plugins import PluginManager, create_default_plugin_manager
from src.agent_v2.skills import SkillRegistry
from src.agent_v2.hooks import HookRunner
from src.agent_v2.tools.registry import ToolRegistry


def _create_plugin(tmp_path: Path, name: str, **extra) -> Path:
    d = tmp_path / name
    d.mkdir()
    manifest = {
        "name": name,
        "version": "1.0.0",
        "description": f"Test plugin {name}",
        **extra,
    }
    (d / "plugin.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
    return tmp_path


class TestLoadManifest:
    def test_load_valid_plugin(self, tmp_path: Path):
        _create_plugin(tmp_path, "test_plugin", skills=[
            {"name": "s1", "layer": "agents", "content": "skill content"}
        ])
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 1
        assert mgr._plugins["test_plugin"].version == "1.0.0"

    def test_load_multiple_plugins(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1")
        _create_plugin(tmp_path, "p2")
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 2
        assert len(mgr._enabled) == 2

    def test_load_empty_dir(self, tmp_path: Path):
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 0

    def test_load_missing_manifest(self, tmp_path: Path):
        d = tmp_path / "no_manifest"
        d.mkdir()
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 0

    def test_load_malformed_yaml(self, tmp_path: Path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "plugin.yaml").write_text("{{{ bad yaml :::", encoding="utf-8")
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 0  # skipped, not crashed

    def test_enable_disable(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1")
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        assert mgr.enable("p1")  # already enabled
        assert mgr.disable("p1")
        assert "p1" not in mgr._enabled
        assert not mgr.enable("nonexistent")


class TestRegisterSkills:
    def test_register_skills_to_registry(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", skills=[
            {"name": "s1", "layer": "agents", "content": "Content A"},
            {"name": "s2", "layer": "soul", "content": "Content B"},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        reg = SkillRegistry()
        n = mgr.register_skills(reg)
        assert n == 2
        assert reg.get("s1") is not None
        assert reg.get("s2") is not None

    def test_disabled_plugin_skills_not_registered(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", skills=[
            {"name": "s1", "content": "c"},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        mgr.disable("p1")
        reg = SkillRegistry()
        n = mgr.register_skills(reg)
        assert n == 0


class TestRegisterHooks:
    def test_register_hooks(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", hooks=[
            {"name": "h1", "point": "PreToolUse", "command": "echo ok", "priority": 30},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        runner = HookRunner()
        n = mgr.register_hooks(runner)
        assert n == 1
        assert len(runner._hooks) == 1

    def test_invalid_hook_point_skipped(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", hooks=[
            {"name": "h1", "point": "InvalidPoint", "command": "echo ok"},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        runner = HookRunner()
        n = mgr.register_hooks(runner)
        assert n == 0


class TestRegisterTools:
    def test_register_plugin_tool(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", tools=[
            {"name": "hello", "description": "Say hello",
             "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
             "command": "echo hello"},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        reg = ToolRegistry()
        n = mgr.register_tools(reg)
        assert n == 1
        assert reg.get("hello") is not None

    @pytest.mark.asyncio
    async def test_execute_plugin_tool(self, tmp_path: Path):
        import sys
        _create_plugin(tmp_path, "p1", tools=[
            {"name": "greet", "description": "Greet",
             "input_schema": {},
             "command": f"{sys.executable} -c \"print('hello from plugin')\""},
        ])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        reg = ToolRegistry()
        mgr.register_tools(reg)
        result = await reg.execute("greet", {})
        assert "hello from plugin" in result.output


class TestPluginLifecycle:
    def test_apply_all(self, tmp_path: Path):
        _create_plugin(tmp_path, "full_plugin",
                       skills=[{"name": "sk", "content": "c"}],
                       hooks=[{"name": "hk", "point": "PostToolUse", "command": "echo ok"}],
                       tools=[{"name": "tk", "description": "d", "input_schema": {}, "command": "echo hi"}])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        reg_skill = SkillRegistry()
        reg_tool = ToolRegistry()
        runner = HookRunner()
        result = mgr.apply_all(reg_skill, runner, reg_tool)
        assert result == {"skills": 1, "hooks": 1, "tools": 1}

    def test_list_all(self, tmp_path: Path):
        _create_plugin(tmp_path, "p1", skills=[{"name": "s", "content": "c"}],
                       hooks=[{"name": "h", "point": "PreToolUse", "command": "echo"}],
                       tools=[{"name": "t", "description": "d", "input_schema": {}, "command": "echo"}])
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        items = mgr.list_all()
        assert len(items) == 1
        assert items[0]["name"] == "p1"
        assert items[0]["skills"] == 1
        assert items[0]["hooks"] == 1
        assert items[0]["tools"] == 1


class TestDefaultPluginManager:
    def test_create_default(self, tmp_path: Path):
        # Remove example dir so we get the default creation
        # The default plugin manager creates example in the real plugins dir
        mgr = create_default_plugin_manager()
        items = mgr.list_all()
        # Should have at least the example plugin
        assert len(items) >= 1
        names = {i["name"] for i in items}
        assert "example_academic" in names


class TestPluginEdge:
    def test_plugin_with_no_extras(self, tmp_path: Path):
        _create_plugin(tmp_path, "minimal")
        mgr = PluginManager()
        mgr.load_dir(tmp_path)
        reg_s = SkillRegistry()
        reg_t = ToolRegistry()
        runner = HookRunner()
        result = mgr.apply_all(reg_s, runner, reg_t)
        assert result == {"skills": 0, "hooks": 0, "tools": 0}

    def test_100_plugins_load(self, tmp_path: Path):
        for i in range(100):
            _create_plugin(tmp_path, f"p{i:03d}")
        mgr = PluginManager()
        n = mgr.load_dir(tmp_path)
        assert n == 100
        assert len(mgr.list_all()) == 100
