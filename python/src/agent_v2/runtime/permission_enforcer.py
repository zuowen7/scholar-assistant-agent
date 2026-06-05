"""PermissionEnforcer — 工具执行门控层。

参考 claw-code runtime/permission_enforcer.rs:
  - check(): 通用权限检查
  - check_file_write(): 文件写入 + workspace boundary
  - check_bash(): ReadOnly 下允许只读命令 (cat, grep, ls, git log...)
  - is_read_only_command(): 命令分类启发式
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.agent_v2.runtime.permissions import (
    AllowResult,
    DenyResult,
    PermissionMode,
    PermissionPolicy,
)

# Read-only commands allowed even in ReadOnly mode
_READ_ONLY_COMMANDS: frozenset[str] = frozenset({
    "cat", "head", "tail", "less", "more", "wc", "ls", "find",
    "grep", "rg", "awk", "sed",
    "echo", "printf", "which", "where", "whoami", "pwd",
    "env", "printenv", "date", "cal", "df", "du", "free", "uptime",
    "uname", "file", "stat", "diff", "sort", "uniq", "tr", "cut", "paste",
    "tee", "xargs", "test", "true", "false", "type",
    "readlink", "realpath", "basename", "dirname",
    "sha256sum", "md5sum", "b3sum", "xxd", "hexdump", "od", "strings",
    "tree", "jq", "yq",
    "python", "python3", "node", "ruby", "cargo", "rustc",
    "git", "gh",
})

# Flag patterns that make a command NOT read-only
_WRITE_FLAGS = ("-i ", "--in-place ", " > ", " >> ", " 2> ", " 2>> ")


def is_read_only_command(command: str) -> bool:
    """保守启发式：判断 bash 命令是否为只读。参考 claw-code is_read_only_command。"""
    if not command.strip():
        return False
    first_token = command.strip().split(None, 1)[0].rsplit("/", 1)[-1]
    if first_token not in _READ_ONLY_COMMANDS:
        return False
    # Check for write-like flags
    for flag in _WRITE_FLAGS:
        if flag in command:
            return False
    return True


@dataclass
class EnforcementResult:
    allowed: bool
    reason: str = ""
    tool: str = ""
    active_mode: str = ""
    required_mode: str = ""


class PermissionEnforcer:
    """工具执行门控。

    参考 claw-code PermissionEnforcer:
      - 在 PermissionPolicy 之上添加特定工具的语义检查
      - check_file_write: workspace boundary
      - check_bash: ReadOnly 下只允许只读命令
    """

    def __init__(self, policy: PermissionPolicy):
        self.policy = policy

    def active_mode(self) -> PermissionMode:
        return self.policy.active_mode

    def check(self, tool_name: str, input_str: str) -> EnforcementResult:
        mode = self.policy.active_mode

        # Prompt mode defers to caller's interactive flow
        if mode == PermissionMode.PROMPT:
            return EnforcementResult(allowed=True)

        result = self.policy.authorize(tool_name, input_str)
        if isinstance(result, DenyResult):
            return EnforcementResult(
                allowed=False,
                reason=result.reason,
                tool=tool_name,
                active_mode=mode.value,
                required_mode=self.policy.required_mode_for(tool_name).value,
            )
        return EnforcementResult(allowed=True)

    def check_file_write(self, path: str, workspace_root: str) -> EnforcementResult:
        mode = self.policy.active_mode

        if mode == PermissionMode.READ_ONLY:
            return EnforcementResult(
                allowed=False,
                reason=f"file writes are not allowed in '{mode.value}' mode",
                tool="write_file",
                active_mode=mode.value,
                required_mode="workspace-write",
            )

        if mode == PermissionMode.WORKSPACE_WRITE:
            if _is_within_workspace(path, workspace_root):
                return EnforcementResult(allowed=True)
            return EnforcementResult(
                allowed=False,
                reason=f"path '{path}' is outside workspace root '{workspace_root}'",
                tool="write_file",
                active_mode=mode.value,
                required_mode="danger-full-access",
            )

        # Allow and DangerFullAccess permit all writes
        if mode in (PermissionMode.ALLOW, PermissionMode.DANGER_FULL_ACCESS):
            return EnforcementResult(allowed=True)

        # Prompt mode
        return EnforcementResult(
            allowed=False,
            reason="file write requires confirmation in prompt mode",
            tool="write_file",
            active_mode=mode.value,
            required_mode="workspace-write",
        )

    def check_bash(self, command: str) -> EnforcementResult:
        mode = self.policy.active_mode

        if mode == PermissionMode.READ_ONLY:
            if is_read_only_command(command):
                return EnforcementResult(allowed=True)
            return EnforcementResult(
                allowed=False,
                reason=f"command may modify state; not allowed in '{mode.value}' mode",
                tool="bash",
                active_mode=mode.value,
                required_mode="workspace-write",
            )

        if mode == PermissionMode.PROMPT:
            return EnforcementResult(
                allowed=False,
                reason="bash requires confirmation in prompt mode",
                tool="bash",
                active_mode=mode.value,
                required_mode="danger-full-access",
            )

        # WorkspaceWrite, Allow, DangerFullAccess: permit bash
        return EnforcementResult(allowed=True)


def _is_within_workspace(path: str, workspace_root: str) -> bool:
    """Simple workspace boundary check via string prefix. 参考 claw-code is_within_workspace。"""
    import os
    normalized = path if path.startswith("/") or path.startswith("\\") or (len(path) > 1 and path[1] == ":") else os.path.join(workspace_root, path)
    root = workspace_root.rstrip("/").rstrip("\\")
    norm = os.path.normpath(normalized)
    return norm.startswith(root) or norm == root
