"""ToolRegistry — 工具注册、发现、执行。

参考 claw-code:
  - tools/lib.rs: GlobalToolRegistry, ToolSpec, permission_specs
  - tools/tests/path_scope_enforcement.rs: workspace boundary enforcement
  - claw-analog dispatch_tool: join_under_root, assert_workspace_path,
    ignore-aware directory listing (WalkBuilder with .gitignore/.clawignore)
"""

from __future__ import annotations

import fnmatch
import locale
import logging
import os
import re
import shlex
import shutil
import sys
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.agent_v2.runtime.file_mutations import atomic_write_text, read_text_exact
from src.agent_v2.runtime.process_control import process_group_kwargs, terminate_process_tree
from src.agent_v2.types import ToolDefinition, ToolError

if TYPE_CHECKING:
    # 仅用于 set_permission_mode 的参数注解；运行时在
    # _permission_policy_check 内局部导入以规避循环依赖。
    from src.agent_v2.runtime.permissions import PermissionMode

logger = logging.getLogger(__name__)

# Windows reserved names
_WINDOWS_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)

_MAX_READ_BYTES = 8 * 1024 * 1024
_READ_PAGE_CHARS = 3500
_MAX_GREP_LINES = 200
_MAX_GLOB_RESULTS = 2000
_MAX_LIST_ENTRIES = 500
_TOOL_RESULT_MAX = 4000


def _python_index_for_monaco_column(line: str, column: int) -> int:
    """Convert Monaco's 1-based UTF-16 column into a Python string index."""
    target_units = column - 1
    if target_units < 0:
        raise ValueError("column must be at least 1")
    used_units = 0
    for index, char in enumerate(line):
        if used_units == target_units:
            return index
        width = 2 if ord(char) > 0xFFFF else 1
        if used_units + width > target_units:
            raise ValueError("column points inside a UTF-16 surrogate pair")
        used_units += width
    if used_units == target_units:
        return len(line)
    raise ValueError("column is outside the line")


def _offset_for_monaco_position(content: str, line_number: int, column: int) -> int:
    lines = content.splitlines(keepends=True)
    if not lines:
        lines = [""]
    elif content.endswith(("\n", "\r")):
        lines.append("")
    if line_number < 1 or line_number > len(lines):
        raise ValueError("line is outside the document")
    raw_line = lines[line_number - 1]
    logical_line = raw_line.rstrip("\r\n")
    return sum(len(line) for line in lines[: line_number - 1]) + _python_index_for_monaco_column(
        logical_line, column
    )


@dataclass
class ToolResult:
    output: str
    is_error: bool = False
    status: str = ""
    truncated: bool = False
    original_chars: int = 0
    returned_chars: int = 0
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "error" if self.is_error else "success"
        if self.status in {"error", "denied"}:
            self.is_error = True
        if self.original_chars <= 0:
            self.original_chars = len(self.output)
        if self.returned_chars <= 0:
            self.returned_chars = len(self.output)

    def limit_output(self, max_chars: int = _TOOL_RESULT_MAX) -> ToolResult:
        if len(self.output) <= max_chars:
            return self
        return ToolResult(
            output=self.output[:max_chars] + "\n... [truncated]",
            is_error=self.is_error,
            status=self.status,
            truncated=True,
            original_chars=len(self.output),
            returned_chars=max_chars,
            metadata=dict(self.metadata or {}),
        )


def _normalize_schema(schema: dict) -> None:
    """规范化 JSON Schema。参考 claw-code normalize_object_schema。

    给所有 object 类型添加 additionalProperties: false 和 properties: {}。
    部分 provider（DeepSeek 等）对 schema 格式校验严格，缺少这些字段会拒绝工具定义。
    """
    if schema.get("type") == "object":
        schema.setdefault("properties", {})
        if "additionalProperties" not in schema:
            schema["additionalProperties"] = False
    # Recurse into nested properties
    for v in schema.get("properties", {}).values():
        if isinstance(v, dict):
            _normalize_schema(v)
    # Handle array items
    items = schema.get("items")
    if isinstance(items, dict):
        _normalize_schema(items)


# Tool function signature: async (args: dict) -> ToolResult
ToolFunc = Callable[[dict[str, Any]], Awaitable[ToolResult]]
ToolPreflight = Callable[[dict[str, Any]], ToolResult | None]


class ToolSpec:
    """A registered tool with its definition, execution function, and permission level."""

    def __init__(
        self,
        definition: ToolDefinition,
        func: ToolFunc,
        permission: str = "read-only",
        effects: Iterable[str] | None = None,
        approval_scope: str = "exact-input",
        network_scope: Iterable[str] | None = None,
        rollback_capability: str = "none",
        preflight: ToolPreflight | None = None,
    ):
        self.definition = definition
        self.func = func
        self.permission = permission
        self.effects = frozenset(effects or ())
        self.approval_scope = approval_scope
        self.network_scope = frozenset(network_scope or ())
        self.rollback_capability = rollback_capability
        self.preflight = preflight

    @property
    def requires_approval(self) -> bool:
        return bool(
            self.effects
            & {
                "filesystem_write",
                "process",
                "network",
                "external_side_effect",
                "cost",
            }
        )


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
        # Provider injected by the runtime; used by tools that need LLM access
        # (e.g., sub_agent). Set via set_provider() — do NOT assign _provider
        # directly from outside the class.
        self._provider: Any = None
        self._runtime_context: dict[str, Any] = {}

    def set_provider(self, provider: Any) -> None:
        """Inject the LLM provider for tools that need it (e.g., sub_agent).

        Replaces the previous pattern of ``registry._provider = provider``
        which bypassed encapsulation and would break if ``_provider`` is
        renamed or ``__slots__`` is added.
        """
        self._provider = provider

    def get_provider(self) -> Any:
        """Return the injected provider, or None if not set."""
        return self._provider

    def set_runtime_context(self, **context: Any) -> None:
        self._runtime_context = dict(context)

    def get_runtime_context(self) -> dict[str, Any]:
        return dict(self._runtime_context)

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        func: ToolFunc,
        permission: str = "read-only",
        effects: Iterable[str] | None = None,
        approval_scope: str = "exact-input",
        network_scope: Iterable[str] | None = None,
        rollback_capability: str = "none",
        preflight: ToolPreflight | None = None,
    ) -> None:
        key = name.lower()
        if key in self._tools:
            raise ToolError(f"tool '{name}' is already registered")
        _normalize_schema(input_schema)
        self._tools[key] = ToolSpec(
            definition=ToolDefinition(
                name=name, description=description, input_schema=input_schema
            ),
            func=func,
            permission=permission,
            effects=effects,
            approval_scope=approval_scope,
            network_scope=network_scope,
            rollback_capability=rollback_capability,
            preflight=preflight,
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
            return result.limit_output()
        except Exception as e:
            return ToolResult(output=f"tool '{name}' error: {e}", is_error=True)

    @staticmethod
    def _schema_preflight(spec: ToolSpec, args: dict[str, Any]) -> ToolResult | None:
        schema = spec.definition.input_schema
        properties = schema.get("properties", {})
        errors: list[str] = []
        invalid_fields: list[str] = []

        for field_name in schema.get("required", []):
            if field_name not in args or args[field_name] is None:
                errors.append(f"{field_name} is required")
                invalid_fields.append(field_name)

        type_checks: dict[str, Callable[[Any], bool]] = {
            "string": lambda value: isinstance(value, str),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": lambda value: isinstance(value, bool),
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
        }
        type_labels = {
            "string": "a string",
            "integer": "an integer",
            "number": "a number",
            "boolean": "a boolean",
            "object": "an object",
            "array": "an array",
        }
        for field_name, field_schema in properties.items():
            if field_name not in args or args[field_name] is None:
                continue
            value = args[field_name]
            expected_type = field_schema.get("type")
            checker = type_checks.get(str(expected_type))
            if checker is not None and not checker(value):
                errors.append(f"{field_name} must be {type_labels[str(expected_type)]}")
                invalid_fields.append(field_name)
                continue
            if isinstance(value, str):
                min_length = field_schema.get("minLength")
                if isinstance(min_length, int) and len(value) < min_length:
                    errors.append(f"{field_name} must not be empty")
                    invalid_fields.append(field_name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                minimum = field_schema.get("minimum")
                maximum = field_schema.get("maximum")
                if isinstance(minimum, (int, float)) and value < minimum:
                    errors.append(f"{field_name} must be at least {minimum}")
                    invalid_fields.append(field_name)
                if isinstance(maximum, (int, float)) and value > maximum:
                    errors.append(f"{field_name} must be at most {maximum}")
                    invalid_fields.append(field_name)
            choices = field_schema.get("enum")
            if isinstance(choices, list) and value not in choices:
                errors.append(f"{field_name} must be one of {choices}")
                invalid_fields.append(field_name)

        if not errors:
            return None
        fields = sorted(set(invalid_fields))
        return ToolResult(
            output="error: invalid tool arguments: " + "; ".join(errors),
            is_error=True,
            metadata={
                "code": "invalid_tool_arguments",
                "fields": fields,
            },
        )

    def preflight(self, name: str, args: dict[str, Any]) -> ToolResult | None:
        """Validate a tool call before asking the user to approve it."""
        spec = self.get(name)
        if spec is None:
            return ToolResult(output=f"tool '{name}' not found", is_error=True)
        schema_error = self._schema_preflight(spec, args)
        if schema_error is not None:
            return schema_error
        if spec.preflight is None:
            return None
        try:
            return spec.preflight(args)
        except Exception as exc:
            return ToolResult(output=f"tool '{name}' preflight error: {exc}", is_error=True)

    def _permission_policy_check(self, command: str) -> tuple[PermissionMode,]:
        """Derive the current effective PermissionMode for bash validation.

        Returns a 1-tuple for destructuring convenience.
        Defaults to WORKSPACE_WRITE if no policy is configured.
        """
        from src.agent_v2.runtime.permissions import PermissionMode

        return (getattr(self, "_active_permission_mode", None) or PermissionMode.WORKSPACE_WRITE,)

    def set_permission_mode(self, mode: PermissionMode) -> None:
        self._active_permission_mode = mode

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
            raise ValueError(
                f"path '{path_str}' resolved to '{resolved}' — outside workspace root '{self._workspace_root}'"
            )
        return resolved

    def _load_ignore_patterns(self) -> list[tuple[str, bool]]:
        """Load ignore patterns from .gitignore and .clawignore。参考 claw-code WalkBuilder。"""
        patterns = []
        for fname in (".gitignore", ".clawignore"):
            ignore_file = self._workspace_root / fname if self._workspace_root else None
            if ignore_file and ignore_file.is_file():
                try:
                    for line in ignore_file.read_text(
                        encoding="utf-8", errors="ignore"
                    ).splitlines():
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
            if size > _MAX_READ_BYTES:
                return ToolResult(
                    f"error: file exceeds the {_MAX_READ_BYTES}-byte Agent read limit: {path_str}",
                    is_error=True,
                )
            text = raw.decode("utf-8", errors="replace")
            try:
                offset = int(args.get("offset", 0))
                requested_limit = int(args.get("limit", _READ_PAGE_CHARS))
            except (TypeError, ValueError):
                return ToolResult("error: offset and limit must be integers", is_error=True)
            if offset < 0 or requested_limit <= 0:
                return ToolResult(
                    "error: offset must be non-negative and limit must be positive",
                    is_error=True,
                )
            limit = min(requested_limit, _READ_PAGE_CHARS)
            end = min(len(text), offset + limit)
            if offset > len(text):
                return ToolResult(
                    f"error: offset {offset} is beyond end of file ({len(text)} chars)",
                    is_error=True,
                )
            page = text[offset:end]
            if end < len(text):
                marker = (
                    f"\n... [truncated; chars {offset}:{end} of {len(text)}; "
                    f"continue with offset={end}]"
                )
                return ToolResult(
                    page + marker,
                    truncated=True,
                    original_chars=len(text),
                    returned_chars=len(page),
                )
            return ToolResult(
                page,
                original_chars=len(text),
                returned_chars=len(page),
            )
        except Exception as e:
            return ToolResult(f"error reading file: {e}", is_error=True)

    async def write_file(args: dict) -> ToolResult:
        path_str = str(args.get("file_path", ""))
        content = str(args.get("content", ""))
        mode = str(args.get("mode", "overwrite")).lower()
        if not path_str:
            return ToolResult("error: file_path is required", is_error=True)
        if mode not in {"overwrite", "append"}:
            return ToolResult("error: mode must be overwrite or append", is_error=True)
        if registry.check_workspace_escape(path_str):
            return ToolResult(f"error: path '{path_str}' is outside workspace", is_error=True)
        if registry.check_windows_reserved(path_str):
            return ToolResult(f"error: '{path_str}' is a reserved name on Windows", is_error=True)
        try:
            full = registry._resolve_path(path_str)
            existing = read_text_exact(full) if mode == "append" and full.is_file() else ""
            combined = existing + content if mode == "append" else content
            atomic_write_text(full, combined)
            return ToolResult(
                f"ok: {mode} wrote {len(content)} chars to {path_str}",
                metadata={
                    "mode": mode,
                    "written_chars": len(content),
                    "total_chars": len(combined),
                    "final_chunk": bool(args.get("final_chunk", True)),
                },
            )
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
        try:
            full = registry._resolve_path(path_str)
            if not full.is_file():
                return ToolResult(f"error: file not found: {path_str}", is_error=True)
            anchor_keys = ("start_line", "start_column", "end_line", "end_column")
            has_anchor = all(key in args for key in anchor_keys)
            if has_anchor:
                content = read_text_exact(full)
                try:
                    start = _offset_for_monaco_position(
                        content,
                        int(args["start_line"]),
                        int(args["start_column"]),
                    )
                    end = _offset_for_monaco_position(
                        content,
                        int(args["end_line"]),
                        int(args["end_column"]),
                    )
                except (TypeError, ValueError) as exc:
                    return ToolResult(f"error: invalid selection anchor: {exc}", is_error=True)
                if end < start:
                    return ToolResult("error: invalid selection anchor: end precedes start", True)
                if content[start:end] != old_string:
                    return ToolResult(
                        "error: selected text changed on disk; save the document and select it again",
                        is_error=True,
                    )
                if old_string == new_string:
                    return ToolResult(
                        f"no change: selected text is already identical in {path_str}",
                        status="no_change",
                    )
                atomic_write_text(full, content[:start] + new_string + content[end:])
                return ToolResult(f"ok: replaced selected range in {path_str}")

            content = full.read_text(encoding="utf-8")
            count = content.count(old_string)
            if count == 0:
                return ToolResult(f"error: old_string not found in {path_str}", is_error=True)
            if count > 1:
                return ToolResult(
                    f"error: old_string found {count} times in {path_str}, expected exactly 1",
                    is_error=True,
                )
            if old_string == new_string:
                return ToolResult(
                    f"no change: old_string and new_string are identical in {path_str}",
                    status="no_change",
                )
            new_content = content.replace(old_string, new_string, 1)
            atomic_write_text(full, new_content)
            return ToolResult(f"ok: replaced in {path_str}")
        except Exception as e:
            return ToolResult(f"error in str_replace: {e}", is_error=True)

    async def grep_files(args: dict) -> ToolResult:
        pattern = str(args.get("pattern", ""))
        path_str = str(args.get("path", "."))
        if not pattern:
            return ToolResult("error: pattern is required", is_error=True)
        try:
            root = registry._resolve_path(path_str)
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)
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

    registry.register(
        "read_file",
        "Read file contents",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Path to file",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Character offset for paginated reads",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _READ_PAGE_CHARS,
                    "default": _READ_PAGE_CHARS,
                    "description": "Maximum characters to return",
                },
            },
            "required": ["file_path"],
        },
        read_file,
        permission="read-only",
    )

    registry.register(
        "write_file",
        (
            "Atomically overwrite or append content to a file; missing parent directories are "
            "created automatically. Split large model payloads into compact chunks."
        ),
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "default": "overwrite",
                    "description": (
                        "Use overwrite for a complete file or first chunk; use append for later "
                        "chunks."
                    ),
                },
                "final_chunk": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "Set false while a multi-call write is incomplete and true only on the "
                        "last chunk."
                    ),
                },
            },
            "required": ["file_path", "content"],
        },
        write_file,
        permission="workspace-write",
        effects={"filesystem_write"},
        approval_scope="path",
        rollback_capability="journaled",
    )

    registry.register(
        "str_replace",
        "Replace text in file",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "minLength": 1},
                "old_string": {"type": "string", "minLength": 1},
                "new_string": {"type": "string"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        str_replace,
        permission="workspace-write",
        effects={"filesystem_write"},
        approval_scope="path",
        rollback_capability="journaled",
    )

    registry.register(
        "list_dir",
        "List files in directory (ignore-aware)",
        {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "."}},
        },
        list_dir,
        permission="read-only",
    )

    # ---- run_command — 执行经过预检的直接命令（不启动 shell） ----
    def _prepare_run_command(
        args: dict,
    ) -> tuple[str, list[str], Path, float] | ToolResult:
        command = str(args.get("command", ""))
        if not command:
            return ToolResult("error: command is required", is_error=True)
        cwd = str(args.get("cwd", "."))
        try:
            root = (
                registry._resolve_path(cwd)
                if cwd != "."
                else (registry._workspace_root or Path.cwd())
            )
        except ValueError as e:
            return ToolResult(f"error: {e}", is_error=True)

        from src.agent_v2.runtime.bash_validation import validate_command

        perm_result = registry._permission_policy_check(command)
        workspace_boundary = registry._workspace_root or root
        validation = validate_command(
            command,
            perm_result[0],
            workspace_boundary,
            direct_exec=True,
        )
        if validation.is_blocked:
            return ToolResult(
                f"error: command blocked by workspace safety policy: {validation.reason}",
                is_error=True,
                metadata={"code": "command_policy_blocked"},
            )
        if validation.is_warn:
            return ToolResult(
                f"error: command blocked by workspace safety policy: {validation.message}",
                is_error=True,
                metadata={"code": "command_policy_blocked"},
            )

        try:
            argv = shlex.split(command, posix=os.name != "nt")
            if os.name == "nt":
                argv = [
                    token[1:-1]
                    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'"
                    else token
                    for token in argv
                ]
            if not argv:
                return ToolResult("error: command is empty after parsing", is_error=True)

            if os.name == "nt":
                builtin = re.split(r"[\\/]", argv[0])[-1].lower()
                builtin_replacements = {
                    "dir": (
                        "list_dir",
                        "Windows 'dir' is a shell builtin and cannot run in direct-exec mode. "
                        "Use list_dir instead.",
                    ),
                    "mkdir": (
                        "write_file",
                        "Windows 'mkdir' is a shell builtin. write_file creates missing parent "
                        "directories automatically, so write the target file directly.",
                    ),
                    "md": (
                        "write_file",
                        "Windows 'md' is a shell builtin. write_file creates missing parent "
                        "directories automatically, so write the target file directly.",
                    ),
                }
                replacement = builtin_replacements.get(builtin)
                if replacement is not None:
                    suggested_next_action, message = replacement
                    return ToolResult(
                        f"error: {message}",
                        is_error=True,
                        metadata={
                            "code": "windows_shell_builtin",
                            "suggested_next_action": suggested_next_action,
                        },
                    )

            timeout_raw = args.get("timeout_seconds", 120)
            try:
                timeout_seconds = float(timeout_raw)
            except (TypeError, ValueError):
                return ToolResult("error: timeout_seconds must be a number", is_error=True)
            if not 1 <= timeout_seconds <= 300:
                return ToolResult(
                    "error: timeout_seconds must be between 1 and 300",
                    is_error=True,
                )

            executable_name = re.split(r"[\\/]", argv[0])[-1].lower()
            if re.fullmatch(r"(?:python(?:\d+(?:\.\d+)?)?|py)(?:\.exe)?", executable_name):
                # Use the same environment as the Scholar Assistant backend so
                # installed plotting/export dependencies are deterministic.
                executable = sys.executable
            elif executable_name in {"pip", "pip.exe", "pip3", "pip3.exe"}:
                executable = sys.executable
                argv = [argv[0], "-m", "pip", *argv[1:]]
            elif executable_name == "echo":
                executable = "echo"
            else:
                executable = shutil.which(argv[0])
            if executable is None:
                return ToolResult(f"error: executable not found: {argv[0]}", is_error=True)
            return executable, argv[1:], root, timeout_seconds
        except ValueError as exc:
            return ToolResult(f"error: command arguments could not be parsed: {exc}", is_error=True)

    def _preflight_run_command(args: dict) -> ToolResult | None:
        prepared = _prepare_run_command(args)
        return prepared if isinstance(prepared, ToolResult) else None

    async def run_command(args: dict) -> ToolResult:
        prepared = _prepare_run_command(args)
        if isinstance(prepared, ToolResult):
            return prepared
        executable, command_args, root, timeout_seconds = prepared

        import asyncio as _aio

        proc = None
        try:
            if re.split(r"[\\/]", executable)[-1].lower() == "echo":
                return ToolResult(" ".join(command_args) + "\n")
            proc = await _aio.create_subprocess_exec(
                executable,
                *command_args,
                cwd=str(root),
                env={
                    **os.environ,
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
                stdout=_aio.subprocess.PIPE,
                stderr=_aio.subprocess.STDOUT,
                **process_group_kwargs(),
            )
            stdout, _ = await _aio.wait_for(proc.communicate(), timeout=timeout_seconds)
            try:
                output = stdout.decode("utf-8", errors="strict")
                encoding_source = "utf-8"
            except UnicodeDecodeError:
                preferred = locale.getpreferredencoding(False) or "utf-8"
                output = stdout.decode(preferred, errors="replace")
                encoding_source = preferred.lower()
            if proc.returncode != 0:
                return ToolResult(
                    f"{output}\nexit code: {proc.returncode}",
                    is_error=True,
                    metadata={"encoding_source": encoding_source, "code": "process_exit_nonzero"},
                )
            return ToolResult(
                output or "(no output)",
                metadata={"encoding_source": encoding_source},
            )
        except _aio.CancelledError:
            if proc is not None:
                await terminate_process_tree(proc)
            raise
        except TimeoutError:
            if proc is not None:
                await terminate_process_tree(proc)
            return ToolResult(
                f"error: command timed out ({timeout_seconds:g}s)",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(f"error running command: {e}", is_error=True)

    registry.register(
        "run_command",
        (
            "Execute one direct command in the workspace after approval (no shell). "
            "Use list_dir instead of dir/ls chains. Python aliases run with Scholar Assistant's "
            "backend interpreter; execute a concrete workspace .py file, never python -c/-m."
        ),
        {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "One direct executable plus arguments. Shell operators, inline interpreter "
                        "code, and paths outside the workspace are rejected before approval."
                    ),
                },
                "cwd": {"type": "string", "default": ".", "description": "Working directory"},
                "timeout_seconds": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 120,
                    "description": "Execution timeout in seconds (1-300)",
                },
            },
            "required": ["command"],
        },
        run_command,
        permission="workspace-write",
        effects={"process"},
        approval_scope="exact-input",
        preflight=_preflight_run_command,
    )

    registry.register(
        "grep_files",
        "Search for pattern in files",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "path": {"type": "string", "default": "."},
            },
            "required": ["pattern"],
        },
        grep_files,
        permission="read-only",
    )

    registry.register(
        "glob_files",
        "Find files matching glob pattern",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "default": "*"},
                "path": {"type": "string", "default": "."},
            },
        },
        glob_files,
        permission="read-only",
    )


def create_default_registry(
    workspace_root: str | Path | None = None,
    *,
    include_run_command: bool = True,
) -> ToolRegistry:
    """Create a registry with all builtin tools."""
    registry = ToolRegistry(workspace_root=workspace_root)
    _create_file_ops(registry)
    if not include_run_command:
        registry._tools.pop("run_command", None)
    return registry
