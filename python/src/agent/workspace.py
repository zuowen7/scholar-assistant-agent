"""工作区环境抽象 — 把 Agent 的世界从 ~/scholar_agent_files 切到调用方传入的项目目录。

WorkspaceEnv 作为 Agent 工具层的路径校验和权限网关：
- resolve() 方法将外部路径映射到项目根内的绝对路径
- denied_globs 拦截 .env / *.key 等敏感文件
- allowed_dirs 支持显式扩展（如 ~/.zotero）
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


class WorkspaceViolation(Exception):
    """路径违反工作区约束时抛出。"""


# Set to True (via token) when user has approved an out-of-workspace tool call.
workspace_escape_allowed: ContextVar[bool] = ContextVar('workspace_escape_allowed', default=False)


@dataclass(frozen=True)
class WorkspaceEnv:
    """Agent 工作区环境，把项目根目录作为所有路径操作的一等公民。

    Attributes:
        root: 项目根目录（必填，从 /api/agent/chat 请求传入）。
        allowed_dirs: 允许访问的目录列表，默认仅 root。
        denied_globs: 禁止访问的 glob 模式列表。
        max_file_bytes: 单文件最大字节数。
    """

    root: Path
    allowed_dirs: tuple[Path, ...] = ()
    denied_globs: tuple[str, ...] = (
        ".env",
        ".env.*",
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "*.secret",
        "*.credentials",
        ".git/objects/**",
        "node_modules/**",
        ".venv/**",
        "__pycache__/**",
    )
    max_file_bytes: int = 5_000_000  # 5MB

    def __post_init__(self):
        # frozen dataclass workaround
        object.__setattr__(self, "root", Path(self.root).resolve())
        if not self.allowed_dirs:
            object.__setattr__(self, "allowed_dirs", (self.root,))
        else:
            resolved = tuple(Path(d).resolve() for d in self.allowed_dirs)
            object.__setattr__(self, "allowed_dirs", resolved)

    def resolve(self, p: str) -> Path:
        """将外部传入路径校验后映射到 root 内的绝对路径。

        Scope: AWA v2 file-editing tools (read_file, write_file, str_replace, etc.).
        Enforces: path stays within allowed_dirs, no denied_globs, no symlink escapes.
        For translate/editor path validation see api_factory._validate_file_path().
        For command/tool risk classification see SecurityGate.classify().

        When workspace_escape_allowed ContextVar is True (set after user approval),
        out-of-workspace paths are allowed and symlink/denied_glob checks are skipped.

        Raises:
            WorkspaceViolation: 路径逃逸、命中 denied_globs、symlink 逃逸时。
        """
        raw = Path(p)
        candidate = raw if raw.is_absolute() else (self.root / raw)
        resolved = candidate.resolve(strict=False)

        within_workspace = any(self._is_within(resolved, base) for base in self.allowed_dirs)

        if not within_workspace:
            if not workspace_escape_allowed.get():
                raise WorkspaceViolation(f"path outside workspace: {p}")
            # User approved out-of-workspace access — return immediately,
            # skip symlink and denied_glob checks (which assume workspace-relative paths).
            return resolved

        # 逐级检查 symlink 是否逃出 allowed_dirs
        cur = candidate
        while True:
            if cur.is_symlink():
                try:
                    link_target = Path(os.readlink(cur)).resolve()
                except OSError:
                    link_target = cur.resolve(strict=False)
                if not any(self._is_within(link_target, base) for base in self.allowed_dirs):
                    raise WorkspaceViolation(f"symlink escape detected: {cur} -> {link_target}")
            parent = cur.parent
            if parent == cur:
                break
            cur = parent

        for pat in self.denied_globs:
            if self._matches_glob(resolved, pat):
                raise WorkspaceViolation(f"path matches denied glob '{pat}': {p}")

        # 二进制检测在 read_file 工具层做，这里只做路径校验
        return resolved

    def is_within(self, p: Path) -> bool:
        """检查路径是否在 allowed_dirs 内。"""
        resolved = Path(p).resolve()
        return any(self._is_within(resolved, base) for base in self.allowed_dirs)

    @staticmethod
    def _is_within(path: Path, base: Path) -> bool:
        try:
            path.relative_to(base)
            return True
        except ValueError:
            return False

    def _matches_glob(self, resolved: Path, pattern: str) -> bool:
        """检查路径是否匹配 denied glob 模式（使用 PurePath.match）。"""
        from pathlib import PurePosixPath

        try:
            rel = resolved.relative_to(self.root)
        except ValueError:
            return False

        rel_posix = PurePosixPath(rel.as_posix())

        # 直接用 pathlib match（支持 ** 通配符）
        if rel_posix.match(pattern):
            return True

        # 同时匹配纯文件名（e.g. ".env" 匹配任意深度的 .env 文件）
        if PurePosixPath(resolved.name).match(pattern):
            return True

        return False

    def ensure_backup_dir(self, backup_id: str) -> Path:
        """在 root/.agent_backup/ 下创建一个备份目录。"""
        backup_root = self.root / ".agent_backup"
        backup_dir = backup_root / backup_id / "files"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def backup_root_path(self) -> Path:
        """返回 .agent_backup/ 根目录。"""
        return self.root / ".agent_backup"
