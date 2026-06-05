"""ToolRegistry — 工具注册、发现、执行。

参考 claw-code:
  - tools/lib.rs: GlobalToolRegistry, ToolSpec, permission_specs
  - tools/tests/path_scope_enforcement.rs: workspace boundary enforcement
  - claw-analog dispatch_tool: join_under_root, assert_workspace_path,
    ignore-aware directory listing (WalkBuilder with .gitignore/.clawignore)
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from src.agent_v2.types import ToolDefinition, ToolError

logger = logging.getLogger(__name__)

# Windows reserved names
_WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})

_MAX_READ_BYTES = 256 * 1024
_MAX_GREP_LINES = 200
_MAX_GLOB_RESULTS = 2000
_TOOL_RESULT_MAX = 4000


@dataclass
class ToolResult:
    output: str
    is_error: bool = False

    def truncated(self, max_chars: int = _TOOL_RESULT_MAX) -> ToolResult:
        if len(self.output) <= max_chars:
            return self
        return ToolResult(output=self.output[:max_chars] + "\n... [truncated]", is_error=self.is_error)


# Tool function signature: async (args: dict) -> ToolResult
ToolFunc = Callable[[dict[str, Any]], Awaitable[ToolResult]]


class ToolSpec:
    """A registered tool with its definition, execution function, and permission level."""

    def __init__(self, definition: ToolDefinition, func: ToolFunc, permission: str = "read-only"):
        self.definition = definition
        self.func = func
        self.permission = permission


class ToolRegistry:
    """Tool registry with registration, lookup, and execution.

    参考 claw-code GlobalToolRegistry:
      - 名称唯一性检查（冲突报错）
      - 大小写不敏感查找
      - workspace boundary enforcement
    """

    def __init__(self, workspace_root: str | Path | None = None):
        self._tools: dict[str, ToolSpec] = {}
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else None

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        func: ToolFunc,
        permission: str = "read-only",
    ) -> None:
        key = name.lower()
        if key in self._tools:
            raise ToolError(f"tool '{name}' is already registered")
        self._tools[key] = ToolSpec(
            definition=ToolDefinition(name=name, description=description, input_schema=input_schema),
            func=func,
            permission=permission,
        )

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name.lower())

    def definitions(self) -> list[ToolDefinition]:
        return [spec.definition for spec in self._tools.values()]

    def permission_specs(self) -> list[tuple[str, str]]:
        return [(spec.definition.name, spec.permission) for spec in self._tools.values()]

    async def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        spec = self.get(name)
        if spec is None:
            return ToolResult(output=f"tool '{name}' not found", is_error=True)
        try:
            result = await spec.func(args)
            return result.truncated()
        except Exception as e:
            return ToolResult(output=f"tool '{name}' error: {e}", is_error=True)

    def check_workspace_escape(self, path_str: str) -> bool:
        if self._workspace_root is None:
            return False
        try:
            self._resolve_path(path_str)
            return False
        except ValueError:
            return True

    def _resolve_path(self, path_str: str) -> Path:
        """Resolve and validate a workspace path. 参考 claw-code join_under_root + assert_workspace_path。"""
        if self._workspace_root is None:
            return Path(path_str).resolve()
        p = Path(path_str)
        candidate = self._workspace_root / p if not p.is_absolute() else p
        try:
            resolved = candidate.resolve(strict=False)
        except Exception as e:
            raise ValueError(f"invalid path '{path_str}': {e}")
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            raise ValueError(f"path '{path_str}' resolved to '{resolved}' — outside workspace root '{self._workspace_root}'")
        return resolved

    def _load_ignore_patterns(self) -> list[tuple[str, bool]]:
        """Load ignore patterns from .gitignore and .clawignore。参考 claw-code WalkBuilder。"""
        patterns = []
        for fname in (".gitignore", ".clawignore"):
            ignore_file = self._workspace_root / fname if self._workspace_root else None
            if ignore_file and ignore_file.is_file():
                try:
                    for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            negate = line.startswith("!")
                            pat = line[1:] if negate else line
                            patterns.append((pat, negate))
                except Exception:
                    pass
        return patterns

    def _is_ignored(self, rel_path: str, patterns: list[tuple[str, bool]]) -> bool:
        """Check if a relative path should be ignored。"""
        ignored = False
        for pat, negate in patterns:
            if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(f"{rel_path}/", pat):
                ignored = not negate
        return ignored

    @staticmethod
    def check_windows_reserved(path_str: str) -> bool:
        name = Path(path_str).name.upper().split(".")[0]
        return name in _WINDOWS_RESERVED


# ---------------------------------------------------------------------------
# Builtin tool implementations
# ---------------------------------------------------------------------------

def _create_file_ops(registry: ToolRegistry) -> None:
    ws = registry._workspace_root

    async def read_file(args: dict) -> ToolResult:
        path_str = str(args.get("file_path", ""))
        if not path_str:
            return ToolResult("error: file_path is required", is_error=True)
        if registry.check_windows_reserved(path_str):
            return ToolResult(f"error: '{path_str}' is a reserved name on Windows", is_error=True)
        try:
            full = registry._resolve_path(path_str)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
        try:
            if not full.is_file():
                return ToolResult(f"error: file not found: {path_str}", is_error=True)
            raw = full.read_bytes()
            if b"\x00" in raw[:8192]:
                return ToolResult(f"error: file is binary: {path_str}", is_error=True)
            size = len(raw)
            text = raw.decode("utf-8", errors="replace")
            if size > _MAX_READ_BYTES:
                return ToolResult(f"{text[:_MAX_READ_BYTES]}\n... [truncated at {_MAX_READ_BYTES} bytes]")
            return ToolResult(text)
        except Exception as e:
            return ToolResult(f"error reading file: {e}", is_error=True)

    async def write_file(args: dict) -> ToolResult:
        path_str = str(args.get("file_path", ""))
        content = str(args.get("content", ""))
        if not path_str:
            return ToolResult("error: file_path is required", is_error=True)
        if registry.check_workspace_escape(path_str):
            return ToolResult(f"error: path '{path_str}' is outside workspace", is_error=True)
        if registry.check_windows_reserved(path_str):
            return ToolResult(f"error: '{path_str}' is a reserved name on Windows", is_error=True)
        p = Path(path_str)
        full = p if p.is_absolute() else (ws / p) if ws else p
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return ToolResult(f"ok: wrote {len(content)} chars to {path_str}")
        except Exception as e:
            return ToolResult(f"error writing file: {e}", is_error=True)

    async def str_replace(args: dict) -> ToolResult:
        path_str = str(args.get("file_path", ""))
        old_string = str(args.get("old_string", ""))
        new_string = str(args.get("new_string", ""))
        if not path_str or not old_string:
            return ToolResult("error: file_path and old_string are required", is_error=True)
        if registry.check_workspace_escape(path_str):
            return ToolResult(f"error: path '{path_str}' is outside workspace", is_error=True)
        p = Path(path_str)
        full = p if p.is_absolute() else (ws / p) if ws else p
        try:
            if not full.is_file():
                return ToolResult(f"error: file not found: {path_str}", is_error=True)
            content = full.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return ToolResult(f"error: old_string not found in {path_str}", is_error=True)
            if count > 1:
                return ToolResult(f"error: old_string found {count} times in {path_str}, expected exactly 1", is_error=True)
            new_content = content.replace(old_string, new_string, 1)
            full.write_text(new_content, encoding="utf-8")
            return ToolResult(f"ok: replaced in {path_str}")
        except Exception as e:
            return ToolResult(f"error in str_replace: {e}", is_error=True)

    async def grep_files(args: dict) -> ToolResult:
        pattern = str(args.get("pattern", ""))
        path_str = str(args.get("path", "."))
        if not pattern:
            return ToolResult("error: pattern is required", is_error=True)
        p = Path(path_str)
        root = p if p.is_absolute() else (ws / p) if ws else p
        if not root.exists():
            return ToolResult(f"error: path not found: {path_str}", is_error=True)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return ToolResult(f"error: invalid regex: {e}", is_error=True)
        lines: list[str] = []

        def _search_file(file_path: Path) -> None:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        lines.append(f"{file_path}:{i}:{line.rstrip()}")
                        if len(lines) >= _MAX_GREP_LINES:
                            lines.append(f"... [truncated at {_MAX_GREP_LINES} lines]")
            except Exception:
                pass

        try:
            if root.is_file():
                _search_file(root)
            else:
                for file_path in sorted(root.rglob("*")):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        _search_file(file_path)
                        if len(lines) > _MAX_GREP_LINES:
                            break
        except Exception as e:
            return ToolResult(f"error during grep: {e}", is_error=True)
        if not lines:
            return ToolResult(f"no matches for pattern '{pattern}'")
        return ToolResult("\n".join(lines))

    async def list_dir(args: dict) -> ToolResult:
        path_str = str(args.get("path", ".")).strip() or "."
        try:
            root = registry._resolve_path(path_str)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
        if not root.is_dir():
            return ToolResult(f"error: not a directory: {path_str}", is_error=True)
        ignore = registry._load_ignore_patterns()
        entries: list[str] = []
        try:
            with os.scandir(root) as it:
                for entry in it:
                    try:
                        rel = str(Path(entry.name))
                    except Exception:
                        rel = entry.name
                    if registry._is_ignored(rel, ignore):
                        continue
                    tag = "d" if entry.is_dir() else "f"
                    size = ""
                    if entry.is_file():
                        try:
                            s = entry.stat().st_size
                            if s < 1024:
                                size = f" {s}B"
                            elif s < 1024 * 1024:
                                size = f" {s // 1024}KB"
                            else:
                                size = f" {s // 1024 // 1024}MB"
                        except Exception:
                            pass
                    entries.append(f"[{tag}]{size} {rel}")
                    if len(entries) >= _MAX_LIST_ENTRIES:
                        entries.append(f"... [truncated at {_MAX_LIST_ENTRIES} entries]")
                        break
        except Exception as e:
            return ToolResult(f"error listing directory: {e}", is_error=True)
        entries.sort()
        return ToolResult("\n".join(entries) if entries else "(empty directory)")

    async def glob_files(args: dict) -> ToolResult:
        pattern_str = str(args.get("pattern", "*"))
        path_str = str(args.get("path", "."))
        try:
            root = registry._resolve_path(path_str)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
        if not root.exists():
            return ToolResult(f"error: path not found: {path_str}", is_error=True)
        ignore = registry._load_ignore_patterns()
        matches: list[str] = []
        try:
            for match in sorted(root.rglob(pattern_str)):
                try:
                    rel = match.relative_to(registry._workspace_root or root)
                except ValueError:
                    rel = match
                if registry._is_ignored(str(rel), ignore):
                    continue
                matches.append(str(rel))
                if len(matches) >= _MAX_GLOB_RESULTS:
                    matches.append(f"... [truncated at {_MAX_GLOB_RESULTS} results]")
                    break
        except Exception as e:
            return ToolResult(f"error during glob: {e}", is_error=True)
        if not matches:
            return ToolResult(f"no files matching '{pattern_str}'")
        return ToolResult("\n".join(matches))

    registry.register("read_file", "Read file contents", {
        "type": "object",
        "properties": {"file_path": {"type": "string", "description": "Path to file"}},
        "required": ["file_path"],
    }, read_file, permission="read-only")

    registry.register("write_file", "Write content to file", {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["file_path", "content"],
    }, write_file, permission="workspace-write")

    registry.register("str_replace", "Replace text in file", {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
        },
        "required": ["file_path", "old_string", "new_string"],
    }, str_replace, permission="workspace-write")

    registry.register("list_dir", "List files in directory (ignore-aware)", {
        "type": "object",
        "properties": {"path": {"type": "string", "default": "."}},
    }, list_dir, permission="read-only")

    registry.register("grep_files", "Search for pattern in files", {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
        },
        "required": ["pattern"],
    }, grep_files, permission="read-only")

    registry.register("glob_files", "Find files matching glob pattern", {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "default": "*"},
            "path": {"type": "string", "default": "."},
        },
    }, glob_files, permission="read-only")


def create_default_registry(workspace_root: str | Path | None = None) -> ToolRegistry:
    """Create a registry with all builtin tools."""
    registry = ToolRegistry(workspace_root=workspace_root)
    _create_file_ops(registry)
    return registry
