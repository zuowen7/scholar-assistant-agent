"""Tests for _build_git_command and _REF_PATTERN in workspace_tools.

Covers:
- Correct argument lists for every allowed git operation
- Ref validation (valid and injection attempts)
- Return type verification (list[str] for success, JSON error string for rejection)
"""

from __future__ import annotations

import json

import pytest

from src.agent.tools.workspace_tools import _build_git_command, _REF_PATTERN


# -- Helpers -----------------------------------------------------------------

def _is_error_json(result) -> bool:
    """Check that result is a JSON string containing an 'error' key."""
    assert isinstance(result, str), f"expected str, got {type(result)}"
    parsed = json.loads(result)
    return "error" in parsed


def _is_cmd_list(result) -> bool:
    """Check that result is a list of strings."""
    assert isinstance(result, list), f"expected list, got {type(result)}"
    assert all(isinstance(x, str) for x in result), "all items must be str"
    return True


# -- 1. Command building: correct argument lists -----------------------------


class TestBuildGitCommand:
    """Verify each operation produces the exact expected argument list."""

    def test_status(self):
        result = _build_git_command("status", {})
        assert _is_cmd_list(result)
        assert result == ["git", "status", "--short"]

    def test_diff_with_path(self):
        result = _build_git_command("diff", {"path": "some/path"})
        assert _is_cmd_list(result)
        assert result == ["git", "diff", "--", "some/path"]

    def test_diff_staged(self):
        result = _build_git_command("diff", {"staged": True})
        assert _is_cmd_list(result)
        assert result == ["git", "diff", "--staged", "--", ""]

    def test_diff_staged_with_path(self):
        result = _build_git_command("diff", {"staged": True, "path": "foo.py"})
        assert _is_cmd_list(result)
        assert result == ["git", "diff", "--staged", "--", "foo.py"]

    def test_log_default_count(self):
        result = _build_git_command("log", {})
        assert _is_cmd_list(result)
        assert result == ["git", "log", "--oneline", "-10"]

    def test_log_custom_count(self):
        result = _build_git_command("log", {"count": 5})
        assert _is_cmd_list(result)
        assert result == ["git", "log", "--oneline", "-5"]

    def test_show_default_ref(self):
        result = _build_git_command("show", {})
        assert _is_cmd_list(result)
        assert result == ["git", "show", "--stat", "HEAD"]

    def test_show_custom_ref(self):
        result = _build_git_command("show", {"ref": "HEAD"})
        assert _is_cmd_list(result)
        assert result == ["git", "show", "--stat", "HEAD"]

    def test_branch(self):
        result = _build_git_command("branch", {})
        assert _is_cmd_list(result)
        assert result == ["git", "branch", "-a"]

    def test_tag(self):
        result = _build_git_command("tag", {})
        assert _is_cmd_list(result)
        assert result == ["git", "tag", "-l"]

    def test_remote(self):
        result = _build_git_command("remote", {})
        assert _is_cmd_list(result)
        assert result == ["git", "remote", "-v"]

    def test_commit_default_message(self):
        result = _build_git_command("commit", {})
        assert _is_cmd_list(result)
        assert result == ["git", "commit", "-a", "-m", "agent commit"]

    def test_commit_custom_message(self):
        result = _build_git_command("commit", {"message": "test msg"})
        assert _is_cmd_list(result)
        assert result == ["git", "commit", "-a", "-m", "test msg"]

    def test_commit_with_files(self):
        result = _build_git_command("commit", {"message": "msg", "files": ["file1.txt"]})
        assert _is_cmd_list(result)
        assert result == ["git", "commit", "file1.txt", "-m", "msg"]

    def test_commit_with_multiple_files(self):
        result = _build_git_command(
            "commit", {"message": "msg", "files": ["a.py", "b.py"]}
        )
        assert _is_cmd_list(result)
        assert result == ["git", "commit", "a.py", "b.py", "-m", "msg"]

    def test_add_with_files(self):
        result = _build_git_command("add", {"files": ["file1.txt", "file2.txt"]})
        assert _is_cmd_list(result)
        assert result == ["git", "add", "file1.txt", "file2.txt"]

    def test_add_without_files(self):
        result = _build_git_command("add", {})
        assert _is_cmd_list(result)
        assert result == ["git", "add", "-A"]

    def test_add_empty_files_list(self):
        result = _build_git_command("add", {"files": []})
        assert _is_cmd_list(result)
        assert result == ["git", "add", "-A"]

    def test_restore_default_source(self):
        result = _build_git_command("restore", {"path": "path"})
        assert _is_cmd_list(result)
        assert result == ["git", "restore", "--source=HEAD", "--", "path"]

    def test_restore_custom_source(self):
        result = _build_git_command("restore", {"path": "path", "source": "HEAD"})
        assert _is_cmd_list(result)
        assert result == ["git", "restore", "--source=HEAD", "--", "path"]

    def test_checkout_branch(self):
        result = _build_git_command("checkout", {"branch": "main"})
        assert _is_cmd_list(result)
        assert result == ["git", "checkout", "main"]

    def test_checkout_path(self):
        result = _build_git_command("checkout", {"path": "path"})
        assert _is_cmd_list(result)
        assert result == ["git", "checkout", "--", "path"]

    def test_checkout_branch_takes_priority_over_path(self):
        """When both branch and path are given, branch wins."""
        result = _build_git_command("checkout", {"branch": "main", "path": "file.txt"})
        assert _is_cmd_list(result)
        assert result == ["git", "checkout", "main"]

    def test_stash_push_default(self):
        result = _build_git_command("stash", {})
        assert _is_cmd_list(result)
        assert result == ["git", "stash", "push", "-u"]

    def test_stash_push_explicit(self):
        result = _build_git_command("stash", {"action": "push"})
        assert _is_cmd_list(result)
        assert result == ["git", "stash", "push", "-u"]

    def test_stash_pop(self):
        result = _build_git_command("stash", {"action": "pop"})
        assert _is_cmd_list(result)
        assert result == ["git", "stash", "pop"]

    def test_stash_list(self):
        result = _build_git_command("stash", {"action": "list"})
        assert _is_cmd_list(result)
        assert result == ["git", "stash", "list"]

    def test_unknown_operation_falls_back_to_status(self):
        result = _build_git_command("nonexistent", {})
        assert _is_cmd_list(result)
        assert result == ["git", "status"]


# -- 2. Ref validation -------------------------------------------------------


class TestRefValidation:
    """Verify _REF_PATTERN accepts valid refs and rejects injection attempts."""

    # --- valid refs ---

    @pytest.mark.parametrize(
        "ref",
        ["HEAD", "main", "v1.0.0", "abc123", "origin/main", "refs/heads/feature"],
    )
    def test_valid_refs_accepted(self, ref):
        assert _REF_PATTERN.match(ref) is not None, f"{ref} should be valid"

    # --- invalid refs (command injection) ---

    @pytest.mark.parametrize(
        "ref",
        [
            "HEAD; rm -rf /",
            "$(whoami)",
            "`id`",
            "HEAD && echo pwned",
            "HEAD|cat /etc/passwd",
            "HEAD$(echo 1)",
            "main`whoami`",
            "HEAD\nwhoami",
        ],
    )
    def test_invalid_refs_rejected(self, ref):
        assert _REF_PATTERN.match(ref) is None, f"{ref} should be rejected"

    # --- invalid ref in show -> returns JSON error ---

    @pytest.mark.parametrize(
        "ref",
        ["HEAD; rm -rf /", "$(whoami)", "`id`", "HEAD && echo pwned"],
    )
    def test_show_rejects_invalid_ref(self, ref):
        result = _build_git_command("show", {"ref": ref})
        assert isinstance(result, str), "error must be a string"
        parsed = json.loads(result)
        assert "error" in parsed
        assert "invalid git ref" in parsed["error"]

    # --- invalid source in restore -> returns JSON error ---

    @pytest.mark.parametrize(
        "source",
        ["HEAD; rm -rf /", "$(whoami)", "`id`", "HEAD && echo pwned"],
    )
    def test_restore_rejects_invalid_source(self, source):
        result = _build_git_command("restore", {"path": "file.txt", "source": source})
        assert isinstance(result, str), "error must be a string"
        parsed = json.loads(result)
        assert "error" in parsed
        assert "invalid git source ref" in parsed["error"]


# -- 3. Return type verification ---------------------------------------------


class TestReturnTypes:
    """Verify that successful returns are list[str] and errors are JSON strings."""

    @pytest.mark.parametrize(
        "operation, args",
        [
            ("status", {}),
            ("diff", {"path": "x"}),
            ("diff", {"staged": True}),
            ("log", {}),
            ("log", {"count": 3}),
            ("show", {"ref": "HEAD"}),
            ("show", {"ref": "v2.0"}),
            ("branch", {}),
            ("tag", {}),
            ("remote", {}),
            ("commit", {"message": "m"}),
            ("commit", {"message": "m", "files": ["f"]}),
            ("add", {}),
            ("add", {"files": ["a", "b"]}),
            ("restore", {"path": "p"}),
            ("restore", {"path": "p", "source": "HEAD"}),
            ("checkout", {"branch": "dev"}),
            ("checkout", {"path": "f"}),
            ("stash", {}),
            ("stash", {"action": "pop"}),
            ("stash", {"action": "list"}),
        ],
    )
    def test_successful_returns_are_list_of_str(self, operation, args):
        result = _build_git_command(operation, args)
        assert isinstance(result, list)
        assert all(isinstance(item, str) for item in result)

    def test_error_returns_are_json_strings_with_error_key(self):
        """Every error path returns a JSON string containing 'error'."""
        # show with bad ref
        r1 = _build_git_command("show", {"ref": "$(evil)"})
        assert isinstance(r1, str)
        parsed1 = json.loads(r1)
        assert "error" in parsed1

        # restore with bad source
        r2 = _build_git_command("restore", {"path": "x", "source": "$(evil)"})
        assert isinstance(r2, str)
        parsed2 = json.loads(r2)
        assert "error" in parsed2

    def test_error_returns_are_never_list(self):
        """Error paths never return a list."""
        result = _build_git_command("show", {"ref": "HEAD; evil"})
        assert not isinstance(result, list)

    def test_no_successful_return_is_string(self):
        """Success paths never return a plain string."""
        result = _build_git_command("status", {})
        assert not isinstance(result, str)
