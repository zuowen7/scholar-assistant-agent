"""BashSession 单元测试 — cwd 跟踪、env 覆盖、超时、workspace 边界。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from src.agent.bash_session import BashSession, BashSessionManager


@pytest.fixture
def workspace(tmp_path):
    """创建临时工作区。"""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested").mkdir()
    (tmp_path / "test.txt").write_text("hello", encoding="utf-8")
    return tmp_path


@pytest.fixture
def session(workspace):
    return BashSession(workspace_root=workspace, session_id="test_sess")


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------


class TestInit:
    def test_default_cwd(self, session, workspace):
        assert session.cwd == workspace

    def test_session_id(self, session):
        assert session.session_id == "test_sess"

    def test_auto_id(self, workspace):
        s = BashSession(workspace_root=workspace)
        assert s.session_id == ""

    def test_initial_command_count(self, session):
        assert session.command_count == 0


# ---------------------------------------------------------------------------
# 命令执行
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_echo(self, session):
        r = session.run_command("echo hello")
        assert r.exit_code == 0
        assert "hello" in r.stdout
        assert r.duration_ms >= 0

    def test_exit_code(self, session):
        r = session.run_command("exit 42")
        assert r.exit_code == 42

    def test_stderr(self, session):
        r = session.run_command("echo error >&2")
        assert "error" in r.stderr

    def test_command_count_increments(self, session):
        session.run_command("echo 1")
        session.run_command("echo 2")
        assert session.command_count == 2

    def test_result_to_json(self, session):
        r = session.run_command("echo test")
        j = r.to_json()
        assert '"exit_code": 0' in j
        assert '"command"' in j


# ---------------------------------------------------------------------------
# CWD 跟踪
# ---------------------------------------------------------------------------


class TestCwdTracking:
    def test_cd_subdir(self, session, workspace):
        session.run_command("cd subdir")
        assert session.cwd == workspace / "subdir"

    def test_cd_nested(self, session, workspace):
        session.run_command("cd subdir/nested")
        assert session.cwd == workspace / "subdir" / "nested"

    def test_cd_absolute_within(self, session, workspace):
        session.run_command(f"cd {workspace / 'subdir'}")
        assert session.cwd == workspace / "subdir"

    def test_cd_escape_rejected(self, session, workspace):
        original = session.cwd
        session.run_command("cd ..")
        # 不应逃出 workspace
        assert session.cwd == original

    def test_cd_nonexistent_rejected(self, session, workspace):
        original = session.cwd
        session.run_command("cd no_such_dir")
        assert session.cwd == original

    def test_cwd_override_param(self, session, workspace):
        r = session.run_command("pwd", cwd="subdir")
        assert r.exit_code == 0
        assert "subdir" in r.stdout

    def test_cwd_after_param(self, session, workspace):
        session.run_command("echo hi", cwd="subdir")
        assert session.cwd == workspace / "subdir"

    def test_cd_tilde_maps_to_root(self, session, workspace):
        session.run_command("cd subdir")
        session.run_command("cd ~")
        assert session.cwd == workspace

    def test_pwd_updates_cwd(self, session, workspace):
        # pwd 命令的 stdout 会被解析更新 cwd
        session.run_command("pwd")
        assert session.cwd == workspace


# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------


class TestEnvOverrides:
    def test_export_sets_env(self, session):
        session.run_command("export MY_VAR=hello")
        r = session.run_command("echo $MY_VAR")
        # env 覆盖被记录（但 subprocess 子进程不会继承 export 设置）
        # 这里主要测试 _parse_env_changes 逻辑
        assert session._env_overrides.get("MY_VAR") == "hello"

    def test_proxy_vars_cleared(self, session):
        os.environ["HTTP_PROXY"] = "http://proxy.test:8080"
        try:
            env = session._build_env()
            assert "HTTP_PROXY" not in env
            assert "http_proxy" not in env
        finally:
            del os.environ["HTTP_PROXY"]


# ---------------------------------------------------------------------------
# 超时
# ---------------------------------------------------------------------------


class TestTimeout:
    def test_timeout_returns_error(self, session):
        r = session.run_command("sleep 30", timeout=1)
        assert r.exit_code == -1
        assert "timed out" in r.stderr.lower()

    def test_max_timeout_clamped(self, session):
        r = session.run_command("echo ok", timeout=9999)
        # 不应超时（被 clamp 到 600）
        assert r.exit_code == 0


# ---------------------------------------------------------------------------
# BashSessionManager
# ---------------------------------------------------------------------------


class TestBashSessionManager:
    def test_get_or_create(self, workspace):
        mgr = BashSessionManager(workspace_root=workspace)
        s1 = mgr.get_or_create("sess_a")
        s2 = mgr.get_or_create("sess_a")
        assert s1 is s2

    def test_different_sessions(self, workspace):
        mgr = BashSessionManager(workspace_root=workspace)
        s1 = mgr.get_or_create("sess_a")
        s2 = mgr.get_or_create("sess_b")
        assert s1 is not s2

    def test_remove(self, workspace):
        mgr = BashSessionManager(workspace_root=workspace)
        mgr.get_or_create("sess_a")
        mgr.remove("sess_a")
        assert mgr.active_count == 0

    def test_active_count(self, workspace):
        mgr = BashSessionManager(workspace_root=workspace)
        mgr.get_or_create("a")
        mgr.get_or_create("b")
        assert mgr.active_count == 2
