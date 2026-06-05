"""Plugin 系统 — YAML 配置驱动的可扩展插件。

参考 claw-code plugins/src/lib.rs: PluginLifecycle + bundled plugins。

Plugin manifest 格式 (plugin.yaml):
  name: my_plugin
  version: 1.0.0
  description: Plugin description
  skills:
    - name: skill_name
      layer: agents
      content: |
        Skill content injected into system prompt
  hooks:
    - name: pre_write_check
      point: PreToolUse
      command: python scripts/pre_write_check.py
      priority: 50
  tools:
    - name: custom_tool
      description: Custom tool description
      input_schema: {type: object, properties: {}}
      command: python scripts/custom_tool.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.agent_v2.hooks import HookDecision, HookDefinition, HookEvent, HookPoint, HookRunner
from src.agent_v2.skills import Skill, SkillRegistry
from src.agent_v2.tools.registry import ToolRegistry, ToolResult
from src.agent_v2.types import ToolDefinition

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    name: str
    version: str = "1.0.0"
    description: str = ""
    skills: list[dict[str, Any]] = field(default_factory=list)
    hooks: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    source_file: str = ""


class PluginManager:
    """插件管理器。参考 claw-code PluginLifecycle。"""

    def __init__(self, plugins_dir: str | Path | None = None):
        self._plugins: dict[str, PluginManifest] = {}
        self._enabled: set[str] = set()
        self._plugins_dir = Path(plugins_dir) if plugins_dir else None

    def load_dir(self, directory: Path) -> int:
        """加载目录中所有 plugin.yaml 文件。"""
        if not directory.is_dir():
            return 0
        count = 0
        for plugin_dir in sorted(directory.iterdir()):
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "plugin.yaml"
            if manifest_path.is_file():
                try:
                    manifest = self._load_manifest(manifest_path)
                    self._plugins[manifest.name] = manifest
                    self._enabled.add(manifest.name)
                    count += 1
                except Exception as e:
                    logger.warning("Failed to load plugin from %s: %s", plugin_dir, e)
        return count

    def _load_manifest(self, path: Path) -> PluginManifest:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return PluginManifest(
            name=data.get("name", path.parent.name),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            skills=data.get("skills", []),
            hooks=data.get("hooks", []),
            tools=data.get("tools", []),
            source_file=str(path),
        )

    def enable(self, name: str) -> bool:
        if name in self._plugins:
            self._enabled.add(name)
            return True
        return False

    def disable(self, name: str) -> bool:
        self._enabled.discard(name)
        return True

    def list_all(self) -> list[dict[str, Any]]:
        return [{
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "enabled": m.name in self._enabled,
            "skills": len(m.skills),
            "hooks": len(m.hooks),
            "tools": len(m.tools),
        } for m in self._plugins.values()]

    def register_skills(self, skill_registry: SkillRegistry) -> int:
        """将所有启用的插件的 skills 注册到 SkillRegistry。"""
        count = 0
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin is None:
                continue
            for skill_data in plugin.skills:
                skill_name = skill_data.get("name", f"{plugin.name}_skill_{count}")
                skill = Skill(
                    name=skill_name,
                    description=skill_data.get("description", ""),
                    layer=skill_data.get("layer", "agents"),
                    content=skill_data.get("content", ""),
                    source_file=plugin.source_file,
                )
                skill_registry.register(skill)
                count += 1
        return count

    def register_hooks(self, hook_runner: HookRunner) -> int:
        """将所有启用的插件的 hooks 注册到 HookRunner。"""
        count = 0
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin is None:
                continue
            for hook_data in plugin.hooks:
                point_str = hook_data.get("point", "PreToolUse")
                try:
                    point = HookPoint(point_str)
                except ValueError:
                    continue
                hook_name = hook_data.get("name", f"{plugin.name}_hook_{count}")
                command = hook_data.get("command", "")
                priority = int(hook_data.get("priority", 50))
                hook_runner.register(HookDefinition(
                    name=hook_name, hook_point=point,
                    command=command, priority=priority,
                ))
                count += 1
        return count

    def register_tools(self, tool_registry: ToolRegistry) -> int:
        """将所有启用的插件的 tools 注册到 ToolRegistry。"""
        count = 0
        for name in self._enabled:
            plugin = self._plugins.get(name)
            if plugin is None:
                continue
            for tool_data in plugin.tools:
                tool_name = tool_data.get("name", f"{plugin.name}_tool_{count}")
                description = tool_data.get("description", "")
                input_schema = tool_data.get("input_schema", {})
                command = tool_data.get("command", "")

                async def _plugin_tool(args: dict, cmd=command) -> ToolResult:
                    try:
                        proc = await asyncio.create_subprocess_shell(
                            cmd,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        input_json = json.dumps(args, ensure_ascii=False)
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(input_json.encode()), timeout=30.0,
                        )
                        output = stdout.decode("utf-8", errors="replace")
                        if len(output) > 4000:
                            output = output[:4000] + "..."
                        return ToolResult(output or stderr.decode("utf-8", errors="replace")[:4000])
                    except asyncio.TimeoutError:
                        return ToolResult("error: plugin tool timed out", is_error=True)
                    except Exception as e:
                        return ToolResult(f"error: {e}", is_error=True)

                tool_registry.register(tool_name, description, input_schema,
                                       _plugin_tool, permission="workspace-write")
                count += 1
        return count

    def apply_all(self, skill_registry: SkillRegistry, hook_runner: HookRunner,
                  tool_registry: ToolRegistry) -> dict[str, int]:
        """一键注册：skills + hooks + tools。"""
        return {
            "skills": self.register_skills(skill_registry),
            "hooks": self.register_hooks(hook_runner),
            "tools": self.register_tools(tool_registry),
        }


# ── 内置插件 ──
def _ensure_plugins_dir() -> Path:
    d = Path(__file__).resolve().parent.parent.parent / "data" / "agent_v2" / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_default_plugin_manager() -> PluginManager:
    mgr = PluginManager()
    plugins_dir = _ensure_plugins_dir()

    # Create example plugin if none exist
    if not any(plugins_dir.iterdir()):
        example = plugins_dir / "example_academic"
        example.mkdir(parents=True, exist_ok=True)
        (example / "plugin.yaml").write_text("""\
name: example_academic
version: "1.0.0"
description: "Example academic plugin with cite-check and format-check hooks"

skills:
  - name: citation_guide
    layer: agents
    description: "Citation formatting guide"
    content: |
      Citation Formatting:
      - Use \\cite{key} for inline citations
      - All citations must have corresponding entries in References
      - Prefer recent papers (last 5 years) where possible

hooks:
  - name: check_file_write
    point: PreToolUse
    command: "echo allow"
    priority: 30

  - name: notify_file_change
    point: PostToolUse
    command: "echo ok"
    priority: 90
""", encoding="utf-8")

    mgr.load_dir(plugins_dir)
    return mgr
