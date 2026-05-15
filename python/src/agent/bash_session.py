"""BashSessionManager — 持久 Shell 会话管理器。

通过 subprocess 维护跨命令的 cwd 和 env 状态，避免每条命令
重新建进程时丢失工作目录。

设计:
- 每个 AgentSession 持有一个 BashSession
- 每次 run_command 记录 cwd 变化（解析 cd/pushd/popd）
- env 变化通过 export/set 记录
- 工作目录强制限制在 workspace root 内
- 清空 HTTP_PROXY 等环境变量（Windows 兼容）
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_COMMAND_TIMEOUT = 600  # 硬上限 10 分钟
_DEFAULT_TIMEOUT = 120
_MAX_OUTPUT_BYTES = 100_000  # 输出截断阈值

# Windows 上需要清空的代理环境变量
_PROXY_ENV_VARS = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
})

# cd 命令拆分：用于 _extract_cd_target 中提取第一段命令（&& / ; / | 之前的部分）
_CMD_SPLIT_RE = re.compile(r'\s*(?:&&|;|\|)\s*')

# Shell 注入检测：禁止命令替换、换行符注入等危险模式
_INJECTION_RE = re.compile(
    r'\$\(|`|(?<!\w)eval\s|[\n\r\x00]|\$\{IFS\}|>\(|<\(',
    re.IGNORECASE,
)

# 不允许通过 export/set 覆盖的系统关键环境变量
_FORBIDDEN_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "COMSPEC",
    "PATHEXT", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "PYTHONHOME", "PYTHONPATH",
})

_IS_WINDOWS = platform.system() == "Windows"


def _detect_injection(command: str) -> str | None:
    """检查命令是否含有 shell 注入模式。返回错误信息或 None（通过）。"""
    if _INJECTION_RE.search(command):
        return "禁止使用命令替换、换行注入等危险模式 — shell 注入防护"
    return None


def _build_shell_args(command: str) -> list[str]:
    """将命令字符串包装为 shell 调用参数列表（shell=False 安全模式）。"""
    if _IS_WINDOWS:
        return ["cmd", "/c", command]
    return ["/bin/sh", "-c", command]


@dataclass
class CommandResult:
    """单条命令的执行结果。"""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    cwd_after: str
    truncated: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "cwd_after": self.cwd_after,
            "truncated": self.truncated,
        }, ensure_ascii=False)


class BashSession:
    """单个持久 shell 会话。

    跟踪 cwd 和 env 跨命令持久化。不使用 pexpect/pywinpty，
    而是在每次命令后解析 cwd 变化，保持跨平台兼容。
    """

    def __init__(self, workspace_root: str | Path, session_id: str = ""):
        self.session_id = session_id
        self._root = Path(workspace_root).resolve()
        self._cwd = self._root
        self._env_overrides: dict[str, str] = {}
        self._command_count = 0

    @property
    def cwd(self) -> Path:
        return self._cwd

    @property
    def command_count(self) -> int:
        return self._command_count

    def run_command(
        self,
        command: str,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> CommandResult:
        """同步执行命令，返回结果。"""
        timeout = min(timeout, _MAX_COMMAND_TIMEOUT)
        self._command_count += 1

        # 解析 cwd 覆盖
        if cwd:
            override = (self._root / cwd).resolve()
            if self._is_within(override):
                self._cwd = override

        # 解析 cd/pushd（提取目标目录并预更新 cwd）
        cd_target = self._extract_cd_target(command)
        if cd_target:
            new_cwd = self._resolve_cd(cd_target)
            if new_cwd:
                self._cwd = new_cwd

        # 构建环境变量
        env = self._build_env()

        # 注入防护：拒绝命令替换模式
        injection_err = _detect_injection(command)
        if injection_err:
            logger.warning("bash_session injection guard blocked command: %r", command)
            return CommandResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"安全拒绝: {injection_err}",
                duration_ms=0,
                cwd_after=str(self._cwd),
            )

        start = time.monotonic()
        try:
            proc = subprocess.run(
                _build_shell_args(command),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
                cwd=str(self._cwd),
                env=env,
            )
            exit_code = proc.returncode
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=duration_ms,
                cwd_after=str(self._cwd),
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=duration_ms,
                cwd_after=str(self._cwd),
            )

        duration_ms = int((time.monotonic() - start) * 1000)

        # 解析命令导致的 cwd 变化（从 stdout 提取或信任预更新）
        # shell=True 中的 cd 只影响子进程，但我们已经预更新了
        # 对于 pwd 命令，从 stdout 提取真实 cwd
        if command.strip().startswith("pwd"):
            pwd_result = stdout.strip()
            if pwd_result and self._is_within(Path(pwd_result)):
                self._cwd = Path(pwd_result)

        # 解析 export/set env 变化
        self._parse_env_changes(command)

        truncated = False
        if len(stdout) > _MAX_OUTPUT_BYTES:
            stdout = stdout[:_MAX_OUTPUT_BYTES] + "\n...[stdout truncated]"
            truncated = True
        if len(stderr) > _MAX_OUTPUT_BYTES:
            stderr = stderr[:_MAX_OUTPUT_BYTES // 4] + "\n...[stderr truncated]"
            truncated = True

        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            cwd_after=str(self._cwd),
            truncated=truncated,
        )

    async def arun_command(
        self,
        command: str,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> CommandResult:
        """异步执行命令。"""
        return await asyncio.to_thread(
            self.run_command, command, timeout=timeout, cwd=cwd,
        )

    def _build_env(self) -> dict[str, str]:
        """构建命令环境变量。"""
        env = os.environ.copy()
        # 清空代理变量（Windows httpx 兼容）
        for var in _PROXY_ENV_VARS:
            env.pop(var, None)
        # 应用覆盖
        env.update(self._env_overrides)
        return env

    def _extract_cd_target(self, command: str) -> str | None:
        """从命令中提取 cd/pushd 目标，用 shlex 正确处理带空格的引号路径。

        posix=not _IS_WINDOWS: Windows 路径含反斜杠，不能使用 POSIX 转义规则。
        非 POSIX 模式下 shlex 保留引号，故额外剥离首尾单/双引号。
        """
        first = _CMD_SPLIT_RE.split(command.strip(), maxsplit=1)[0].strip()
        try:
            parts = shlex.split(first, posix=not _IS_WINDOWS)
        except ValueError:
            parts = first.split()
        if len(parts) >= 2 and parts[0] in ("cd", "pushd"):
            target = parts[1]
            # Non-POSIX mode keeps surrounding quotes; strip them
            if len(target) >= 2 and target[0] == target[-1] and target[0] in ('"', "'"):
                target = target[1:-1]
            return target
        return None

    def _resolve_cd(self, target: str) -> Path | None:
        """解析 cd 目标路径，校验不逃出 workspace。"""
        if target == "-":
            return None  # OLDPWD 不跟踪
        if target == "~":
            return self._root  # 不允许逃到 home

        candidate = (self._cwd / target).resolve()
        if self._is_within(candidate) and candidate.is_dir():
            return candidate

        # 绝对路径且在 root 内
        abs_path = Path(target).resolve()
        if self._is_within(abs_path) and abs_path.is_dir():
            return abs_path

        return None

    def _parse_env_changes(self, command: str) -> None:
        """从 export/set 命令提取环境变量变更（带白名单过滤）。"""
        stripped = command.strip()
        m = re.match(r'^(?:export|set)\s+(\w+)=(.*)$', stripped)
        if not m:
            return
        key = m.group(1)
        value = m.group(2)
        if key in _FORBIDDEN_ENV_KEYS:
            logger.warning("Blocked env override of protected key: %s", key)
            return
        if any(c in value for c in ('\n', '\r', '\x00')) or '$(' in value or '`' in value:
            logger.warning("Blocked env override with dangerous value for key: %s", key)
            return
        self._env_overrides[key] = value

    def _is_within(self, path: Path) -> bool:
        try:
            path.relative_to(self._root)
            return True
        except ValueError:
            return False


class BashSessionManager:
    """管理多个 BashSession 实例。

    每个 AgentSession 对应一个 BashSession，通过 session_id 索引。
    """

    def __init__(self, workspace_root: str | Path):
        self._root = str(workspace_root)
        self._sessions: dict[str, BashSession] = {}

    def get_or_create(self, session_id: str) -> BashSession:
        """获取或创建会话。"""
        if session_id not in self._sessions:
            self._sessions[session_id] = BashSession(
                workspace_root=self._root,
                session_id=session_id,
            )
            logger.info("BashSession created: %s", session_id)
        return self._sessions[session_id]

    def remove(self, session_id: str) -> None:
        """清理会话。"""
        self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
