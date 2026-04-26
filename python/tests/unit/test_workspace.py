"""WorkspaceEnv 单元测试 — 路径校验、denied_globs、allowed_dirs。"""

import pytest
from pathlib import Path

from src.agent.workspace import WorkspaceEnv, WorkspaceViolation


@pytest.fixture
def workspace(tmp_path):
    """创建临时工作区。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Hello", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123", encoding="utf-8")
    (tmp_path / "config.key").write_text("key-data", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "objects").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "foo.js").write_text("// foo", encoding="utf-8")
    return WorkspaceEnv(root=tmp_path)


class TestResolve:
    def test_relative_path_inside(self, workspace):
        resolved = workspace.resolve("src/main.py")
        assert resolved == workspace.root / "src" / "main.py"

    def test_absolute_path_inside(self, workspace):
        abs_path = str(workspace.root / "src" / "main.py")
        resolved = workspace.resolve(abs_path)
        assert resolved == workspace.root / "src" / "main.py"

    def test_path_escape_with_dotdot(self, workspace):
        with pytest.raises(WorkspaceViolation, match="outside workspace"):
            workspace.resolve("../../etc/passwd")

    def test_path_escape_absolute(self, workspace):
        with pytest.raises(WorkspaceViolation, match="outside workspace"):
            workspace.resolve("/etc/passwd")


class TestDeniedGlobs:
    def test_deny_env_file(self, workspace):
        with pytest.raises(WorkspaceViolation, match="denied glob"):
            workspace.resolve(".env")

    def test_deny_key_file(self, workspace):
        with pytest.raises(WorkspaceViolation, match="denied glob"):
            workspace.resolve("config.key")

    def test_deny_pem_file(self, workspace):
        with pytest.raises(WorkspaceViolation, match="denied glob"):
            workspace.resolve("cert.pem")

    def test_deny_node_modules(self, workspace):
        with pytest.raises(WorkspaceViolation, match="denied glob"):
            workspace.resolve("node_modules/foo.js")

    def test_allow_normal_file(self, workspace):
        resolved = workspace.resolve("src/main.py")
        assert resolved.is_file()


class TestAllowedDirs:
    def test_default_only_root(self, tmp_path):
        ws = WorkspaceEnv(root=tmp_path)
        assert ws.allowed_dirs == (tmp_path.resolve(),)

    def test_explicit_allowed_dirs(self, tmp_path):
        extra = tmp_path / "external"
        extra.mkdir()
        ws = WorkspaceEnv(root=tmp_path, allowed_dirs=(tmp_path, extra))
        assert len(ws.allowed_dirs) == 2

        # 路径在 extra 下也应通过
        (extra / "data.txt").write_text("data", encoding="utf-8")
        resolved = ws.resolve(str(extra / "data.txt"))
        assert resolved == extra / "data.txt"


class TestIsWithin:
    def test_inside(self, workspace):
        assert workspace.is_within(workspace.root / "src")

    def test_outside(self, workspace):
        assert not workspace.is_within(Path("/etc/passwd"))


class TestBackupDir:
    def test_ensure_backup_dir(self, workspace):
        d = workspace.ensure_backup_dir("test_backup_123")
        assert d.exists()
        assert d.parent.name == "test_backup_123"
        assert d.parent.parent.name == ".agent_backup"
