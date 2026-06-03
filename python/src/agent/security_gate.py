"""SecurityGate — 工具调用前的统一安全闸门。

职责:
1. 判定操作风险级别 (ToolRiskLevel)
2. 检查是否需要审批
3. 命令黑/白名单检查

安全分层:
- SAFE: 直放 (read_file, list_directory, git status/diff/log)
- MODERATE: 需要审批，可 allow_session (run_command 非白名单首词)
- DESTRUCTIVE: 每次都需要审批 (str_replace, write_file 覆盖, git commit)
- BANNED: 直接拒绝 (rm -rf /, sudo, dd 等)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ToolRiskLevel(Enum):
    SAFE = auto()
    MODERATE = auto()
    DESTRUCTIVE = auto()
    BANNED = auto()


# ---------------------------------------------------------------------------
# 命令黑名单 / 白名单
# ---------------------------------------------------------------------------

_CMD_BLACKLIST = frozenset({
    "rm", "rmdir", "del",  # 文件删除 — 走 str_replace/write_file 工具有备份
    "sudo", "su", "runas",
    "dd", "mkfs", "format",
    "shutdown", "reboot", "halt", "poweroff",
    "ssh", "scp", "sftp",
    "chmod", "chown", "chattr",
    "curl", "wget",  # 网络下载 — 用 _web_fetch 工具
    "nc", "ncat", "netcat",
})

_CMD_SAFELIST = frozenset({
    "ls", "dir", "cat", "head", "tail", "wc", "echo", "type",
    "find", "grep", "rg", "sort", "uniq", "cut", "tr", "tee",
    "pwd", "whoami", "date", "uname", "hostname",
    "python", "python3", "pip", "pip3", "uv",
    "node", "npm", "npx", "yarn", "pnpm",
    "cargo", "rustc", "rustup",
    "go", "java", "javac", "mvn", "gradle",
    "git",
    "pytest", "vitest", "jest", "mocha",
    "echo", "env", "printenv", "which", "where",
})

_SHELL_METACHAR_RE = re.compile(r'[&|;`$]|\bredirect\b|>/dev')

_GIT_DESTRUCTIVE_OPS = frozenset({
    "commit", "restore", "checkout", "add", "stash",
    "reset", "merge", "rebase", "pull", "push", "fetch",
})

_GIT_SAFE_OPS = frozenset({
    "status", "diff", "log", "show", "branch", "tag", "remote",
})

_TOOL_DEFAULT_RISK: dict[str, ToolRiskLevel] = {
    "read_file": ToolRiskLevel.SAFE,
    "list_directory": ToolRiskLevel.SAFE,
    "search_files": ToolRiskLevel.SAFE,
    "rag_retrieve": ToolRiskLevel.SAFE,
    "web_search": ToolRiskLevel.SAFE,
    "arxiv_search": ToolRiskLevel.SAFE,
    "str_replace": ToolRiskLevel.DESTRUCTIVE,
    "write_file": ToolRiskLevel.DESTRUCTIVE,
    "undo_last_change": ToolRiskLevel.DESTRUCTIVE,
    "run_command": ToolRiskLevel.MODERATE,
    "git_op": ToolRiskLevel.MODERATE,
    "shell_exec": ToolRiskLevel.MODERATE,
    "python_exec": ToolRiskLevel.MODERATE,
}

# 文件工具路径参数名映射 — 用于 workspace 逃逸检测
_FILE_TOOL_PATH_ARGS: dict[str, str] = {
    "read_file": "file_path",
    "write_file": "file_path",
    "str_replace": "file_path",
    "grep_files": "path",
    "glob_files": "path",
    "list_directory": "path",
}


@dataclass
class GateResult:
    """SecurityGate 判定结果。"""
    risk: ToolRiskLevel
    reason: str = ""
    needs_approval: bool = False
    is_banned: bool = False
    force_approval: bool = False


class SecurityGate:
    """工具调用安全闸门。

    用法:
        gate = SecurityGate()
        result = gate.classify("run_command", {"command": "pytest tests/"})
        if result.needs_approval:
            # 触发 await_approval 流程
    """

    def __init__(self, safe_tools: set[str] | None = None, workspace_root: str = ""):
        self._safe_tools = safe_tools or set()
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else None

    def classify(self, tool_name: str, args: dict[str, Any]) -> GateResult:
        """判定单个工具调用的风险级别，含 workspace 逃逸检测。

        Scope: Agent tool-call risk gating (BANNED/MODERATE/DESTRUCTIVE/SAFE).
        Enforces: command blacklist, path restrictions for file tools, network restrictions.
        For translate/editor path validation see api_factory._validate_file_path().
        For agent workspace path resolution see WorkspaceEnv.resolve().
        """
        result = self._classify_raw(tool_name, args)
        # Workspace-escape check: override to force_approval (unless already banned)
        if not result.is_banned and self._check_workspace_escape(tool_name, args):
            return GateResult(
                risk=ToolRiskLevel.MODERATE,
                reason=f"'{tool_name}' accesses path outside workspace root — requires user approval",
                needs_approval=True,
                force_approval=True,
            )
        return result

    def _check_workspace_escape(self, tool_name: str, args: dict) -> bool:
        """Return True if the tool would access a path outside workspace_root."""
        if self._workspace_root is None:
            return False
        arg_name = _FILE_TOOL_PATH_ARGS.get(tool_name)
        if not arg_name:
            return False
        p_str = str(args.get(arg_name, "")).strip()
        if not p_str:
            return False
        raw = Path(p_str)
        candidate = raw if raw.is_absolute() else (self._workspace_root / raw)
        try:
            resolved = candidate.resolve(strict=False)
        except Exception as e:
            logger.warning("path resolution failed for security check: %s", e)
            return False
        try:
            resolved.relative_to(self._workspace_root)
            return False  # within workspace
        except ValueError:
            return True  # outside workspace — needs approval

    def _classify_raw(self, tool_name: str, args: dict[str, Any]) -> GateResult:
        """内部风险分类（不含 workspace 逃逸检测）。"""
        # 1. 检查工具默认风险
        base_risk = _TOOL_DEFAULT_RISK.get(tool_name)

        if base_risk == ToolRiskLevel.SAFE or tool_name in self._safe_tools:
            return GateResult(risk=ToolRiskLevel.SAFE)

        if base_risk is None:
            return GateResult(risk=ToolRiskLevel.MODERATE, reason="unknown tool")

        # 2. 工具特定逻辑
        if tool_name == "run_command":
            return self._classify_command(args)

        if tool_name == "git_op":
            return self._classify_git_op(args)

        if tool_name == "str_replace":
            return self._classify_str_replace(args)

        if tool_name == "write_file":
            return self._classify_write_file(args)

        if tool_name == "undo_last_change":
            return GateResult(
                risk=ToolRiskLevel.DESTRUCTIVE,
                reason="undo reverses a destructive operation",
                needs_approval=True,
            )

        if tool_name in ("shell_exec", "python_exec"):
            return GateResult(risk=ToolRiskLevel.MODERATE, needs_approval=True)

        # 默认按 base_risk
        return GateResult(
            risk=base_risk,
            needs_approval=base_risk != ToolRiskLevel.SAFE,
        )

    def _classify_command(self, args: dict) -> GateResult:
        command = args.get("command", "").strip()
        if not command:
            return GateResult(risk=ToolRiskLevel.SAFE)

        # 提取首词
        parts = command.split(None, 1)
        first_word = parts[0].lower() if parts else ""

        # 黑名单检查
        if first_word in _CMD_BLACKLIST:
            return GateResult(
                risk=ToolRiskLevel.BANNED,
                reason=f"command '{first_word}' is blacklisted",
                is_banned=True,
            )

        # rm -rf / 特殊拦截
        if first_word == "rm" and "-rf" in command and "/" in command:
            return GateResult(
                risk=ToolRiskLevel.BANNED,
                reason="rm -rf / is permanently banned",
                is_banned=True,
            )

        # Windows 特殊拦截
        if first_word == "del" and "/s" in command.lower() and "/q" in command.lower():
            return GateResult(
                risk=ToolRiskLevel.BANNED,
                reason="del /s /q is permanently banned",
                is_banned=True,
            )

        # 白名单首词 — safe
        if first_word in _CMD_SAFELIST and not _SHELL_METACHAR_RE.search(command):
            return GateResult(risk=ToolRiskLevel.SAFE)

        # Shell 元字符升级为 MODERATE
        if _SHELL_METACHAR_RE.search(command):
            return GateResult(
                risk=ToolRiskLevel.MODERATE,
                reason="command contains shell metacharacters",
                needs_approval=True,
            )

        # 未知命令
        return GateResult(
            risk=ToolRiskLevel.MODERATE,
            reason=f"command '{first_word}' not in safelist",
            needs_approval=True,
        )

    def _classify_git_op(self, args: dict) -> GateResult:
        operation = args.get("operation", "").strip().lower()
        if not operation:
            return GateResult(risk=ToolRiskLevel.SAFE)

        # 永久禁止的危险 git 操作
        forbidden_flags = {"--no-verify", "--no-gpg-sign", "--force", "--hard"}
        args_str = str(args)
        for flag in forbidden_flags:
            if flag in args_str:
                return GateResult(
                    risk=ToolRiskLevel.BANNED,
                    reason=f"git flag '{flag}' is permanently banned",
                    is_banned=True,
                )

        if operation in _GIT_SAFE_OPS:
            return GateResult(risk=ToolRiskLevel.SAFE)

        if operation in _GIT_DESTRUCTIVE_OPS:
            return GateResult(
                risk=ToolRiskLevel.DESTRUCTIVE,
                reason=f"SmartPause: git '{operation}' changes repository state",
                needs_approval=True,
                force_approval=True,
            )

        return GateResult(
            risk=ToolRiskLevel.BANNED,
            reason=f"git operation '{operation}' is not allowed",
            is_banned=True,
        )

    def _classify_str_replace(self, args: dict) -> GateResult:
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        # 大量删除行 → destructive
        old_lines = old_string.count("\n") + 1
        new_lines = new_string.count("\n") + 1 if new_string else 0
        if old_lines - new_lines > 50:
            return GateResult(
                risk=ToolRiskLevel.DESTRUCTIVE,
                reason=f"SmartPause: str_replace deletes {old_lines - new_lines} lines (>50)",
                needs_approval=True,
                force_approval=True,
            )
        return GateResult(
            risk=ToolRiskLevel.DESTRUCTIVE,
            reason="str_replace modifies file content",
            needs_approval=True,
            force_approval=True,
        )

    def _classify_write_file(self, args: dict) -> GateResult:
        must_not_exist = args.get("must_not_exist", False)
        file_path = str(args.get("file_path", "")).strip()
        exists = self._file_exists(file_path)
        content = str(args.get("content", ""))
        content_lines = content.count("\n") + 1 if content else 0

        # 文件已存在 → 覆盖操作 → 需要审批
        if exists and not must_not_exist:
            return GateResult(
                risk=ToolRiskLevel.DESTRUCTIVE,
                reason="SmartPause: write_file overwrites existing file",
                needs_approval=True,
                force_approval=True,
            )

        # 新建文件
        if len(content) > 12000 or content_lines > 250:
            return GateResult(
                risk=ToolRiskLevel.MODERATE,
                reason="SmartPause: write_file creates a large file",
                needs_approval=True,
                force_approval=True,
            )
        return GateResult(
            risk=ToolRiskLevel.MODERATE,
            reason="write_file creating new file",
            needs_approval=True,
            force_approval=True,
        )

    def _file_exists(self, file_path: str) -> bool:
        """Check if a file exists at the given workspace-relative or absolute path."""
        if not file_path or not self._workspace_root:
            return False
        raw = Path(file_path)
        candidate = raw if raw.is_absolute() else (self._workspace_root / raw)
        try:
            return candidate.resolve(strict=False).is_file()
        except (OSError, ValueError):
            return False
