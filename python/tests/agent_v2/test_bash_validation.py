"""TDD tests for Bash Validation Pipeline.

Reference: claw-code rust/crates/runtime/src/bash_validation.rs

6 submodules under test:
  1. readOnlyValidation  — block write-like commands in read-only mode
  2. destructiveCommandWarning — flag dangerous destructive commands
  3. modeValidation — enforce permission mode constraints
  4. sedValidation — validate sed expressions
  5. pathValidation — detect suspicious path patterns
  6. commandSemantics — classify command intent
  7. validate_command — full pipeline (integration)
"""
from __future__ import annotations

import pytest


# ============================================================================
# 1. readOnlyValidation
# ============================================================================

class TestReadOnlyValidation:
    """Port of claw-code bash_validation.rs readOnlyValidation tests."""

    def test_blocks_rm_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("rm -rf /tmp/x", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "rm" in result.reason

    def test_allows_rm_in_workspace_write(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("rm -rf /tmp/x", PermissionMode.WORKSPACE_WRITE)
        assert result.is_allowed

    def test_blocks_write_redirections_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("echo hello > file.txt", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "redirection" in result.reason

    def test_blocks_append_redirection_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("echo hello >> file.txt", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_allows_read_commands_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        for cmd in ("ls -la", "cat /etc/hosts", "grep -r pattern .", "find . -name '*.rs'"):
            result = validate_read_only(cmd, PermissionMode.READ_ONLY)
            assert result.is_allowed, f"'{cmd}' should be allowed in read-only mode"

    def test_blocks_sudo_write_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("sudo rm -rf /tmp/x", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "rm" in result.reason

    def test_blocks_sudo_with_flags_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("sudo -u root chmod 777 /etc/hosts", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_git_push_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("git push origin main", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "push" in result.reason

    def test_allows_git_status_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("git status", PermissionMode.READ_ONLY)
        assert result.is_allowed

    def test_allows_git_log_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        for cmd in ("git log --oneline", "git diff HEAD~1", "git show abc123",
                     "git branch -a", "git blame file.py"):
            result = validate_read_only(cmd, PermissionMode.READ_ONLY)
            assert result.is_allowed, f"'{cmd}' should be allowed"

    def test_blocks_git_commit_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("git commit -m 'wip'", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_git_reset_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("git reset --hard HEAD~1", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_package_install_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("npm install express", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "npm" in result.reason

    def test_blocks_pip_install_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("pip install requests", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_cp_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("cp a.txt b.txt", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_mkdir_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("mkdir -p /tmp/newdir", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_blocks_touch_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_read_only("touch newfile.txt", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_allows_in_non_read_only_modes(self):
        from src.agent_v2.runtime.bash_validation import validate_read_only
        from src.agent_v2.runtime.permissions import PermissionMode

        for mode in (PermissionMode.WORKSPACE_WRITE, PermissionMode.DANGER_FULL_ACCESS,
                     PermissionMode.ALLOW, PermissionMode.PROMPT):
            result = validate_read_only("rm -rf /tmp/x", mode)
            assert result.is_allowed, f"Should be allowed in {mode.value}"


# ============================================================================
# 2. destructiveCommandWarning
# ============================================================================

class TestDestructiveCommandWarning:
    """Port of claw-code bash_validation.rs destructiveCommandWarning tests."""

    def test_warns_rm_rf_root(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("rm -rf /")
        assert result.is_warn
        assert "root" in result.message.lower() or "root" in result.message

    def test_warns_rm_rf_home(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("rm -rf ~")
        assert result.is_warn
        assert "home" in result.message.lower() or "home" in result.message

    def test_warns_rm_rf_star(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("rm -rf *")
        assert result.is_warn

    def test_warns_rm_rf_dot(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("rm -rf .")
        assert result.is_warn

    def test_warns_mkfs(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("mkfs.ext4 /dev/sda1")
        assert result.is_warn

    def test_warns_dd(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("dd if=/dev/zero of=/dev/sda")
        assert result.is_warn

    def test_warns_shred(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("shred /dev/sda")
        assert result.is_warn
        assert "destructive" in result.message.lower() or "destructive" in result.message

    def test_warns_fork_bomb(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive(":(){ :|:& };:")
        assert result.is_warn
        assert "Fork bomb" in result.message

    def test_warns_chmod_777_recursive(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("chmod -R 777 /")
        assert result.is_warn

    def test_warns_any_rm_rf(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        result = check_destructive("rm -rf /tmp/mydir")
        assert result.is_warn

    def test_allows_safe_commands(self):
        from src.agent_v2.runtime.bash_validation import check_destructive

        for cmd in ("ls -la", "echo hello", "cat file.txt", "grep pattern ."):
            result = check_destructive(cmd)
            assert result.is_allowed, f"'{cmd}' should be allowed"


# ============================================================================
# 3. modeValidation
# ============================================================================

class TestModeValidation:
    """Port of claw-code bash_validation.rs modeValidation tests."""

    def test_workspace_write_warns_system_paths(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_mode("cp file.txt /etc/config", PermissionMode.WORKSPACE_WRITE)
        assert result.is_warn
        assert "outside" in result.message.lower() or "workspace" in result.message.lower()

    def test_workspace_write_allows_local_writes(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_mode("cp file.txt ./backup/", PermissionMode.WORKSPACE_WRITE)
        assert result.is_allowed

    def test_read_only_mode_inherits_read_only_validation(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_mode("rm -rf /tmp/x", PermissionMode.READ_ONLY)
        assert result.is_blocked

    def test_danger_full_access_allows_all(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_mode("rm -rf /", PermissionMode.DANGER_FULL_ACCESS)
        assert result.is_allowed

    def test_system_paths_detection(self):
        from src.agent_v2.runtime.bash_validation import validate_mode
        from src.agent_v2.runtime.permissions import PermissionMode

        for path in ("/etc/passwd", "/usr/bin/hack", "/var/log/evil", "/boot/grub"):
            result = validate_mode(f"cp file {path}", PermissionMode.WORKSPACE_WRITE)
            assert result.is_warn, f"Should warn about system path {path}"


# ============================================================================
# 4. sedValidation
# ============================================================================

class TestSedValidation:
    """Port of claw-code bash_validation.rs sedValidation tests."""

    def test_blocks_sed_inplace_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_sed
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_sed("sed -i 's/old/new/' file.txt", PermissionMode.READ_ONLY)
        assert result.is_blocked
        assert "sed -i" in result.reason

    def test_allows_sed_stdout_in_read_only(self):
        from src.agent_v2.runtime.bash_validation import validate_sed
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_sed("sed 's/old/new/' file.txt", PermissionMode.READ_ONLY)
        assert result.is_allowed

    def test_allows_sed_inplace_in_write_mode(self):
        from src.agent_v2.runtime.bash_validation import validate_sed
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_sed("sed -i 's/old/new/' file.txt", PermissionMode.WORKSPACE_WRITE)
        assert result.is_allowed

    def test_allows_non_sed_commands(self):
        from src.agent_v2.runtime.bash_validation import validate_sed
        from src.agent_v2.runtime.permissions import PermissionMode

        result = validate_sed("grep pattern file", PermissionMode.READ_ONLY)
        assert result.is_allowed


# ============================================================================
# 5. pathValidation
# ============================================================================

class TestPathValidation:
    """Port of claw-code bash_validation.rs pathValidation tests."""

    def test_warns_directory_traversal(self):
        from src.agent_v2.runtime.bash_validation import validate_paths
        from pathlib import Path

        result = validate_paths("cat ../../../etc/passwd", Path("/workspace/project"))
        assert result.is_warn
        assert "traversal" in result.message.lower()

    def test_warns_home_directory_reference(self):
        from src.agent_v2.runtime.bash_validation import validate_paths
        from pathlib import Path

        result = validate_paths("cat ~/.ssh/id_rsa", Path("/workspace/project"))
        assert result.is_warn
        assert "home" in result.message.lower()

    def test_warns_dollar_home(self):
        from src.agent_v2.runtime.bash_validation import validate_paths
        from pathlib import Path

        result = validate_paths("cat $HOME/.bashrc", Path("/workspace/project"))
        assert result.is_warn

    def test_allows_normal_paths(self):
        from src.agent_v2.runtime.bash_validation import validate_paths
        from pathlib import Path

        result = validate_paths("cat src/main.py", Path("/workspace/project"))
        assert result.is_allowed


# ============================================================================
# 6. commandSemantics
# ============================================================================

class TestCommandSemantics:
    """Port of claw-code bash_validation.rs commandSemantics tests."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.bash_validation import classify_command, CommandIntent
        self.classify = classify_command
        self.Intent = CommandIntent

    def test_classifies_read_only_commands(self):
        for cmd in ("ls -la", "cat file.txt", "grep -r pattern .",
                     "find . -name '*.rs'", "head -20 file", "wc -l file"):
            assert self.classify(cmd) == self.Intent.READ_ONLY, f"'{cmd}' should be READ_ONLY"

    def test_classifies_write_commands(self):
        for cmd in ("cp a.txt b.txt", "mv old.txt new.txt", "mkdir -p /tmp/dir"):
            assert self.classify(cmd) == self.Intent.WRITE, f"'{cmd}' should be WRITE"

    def test_classifies_destructive_commands(self):
        for cmd in ("rm -rf /tmp/x", "shred /dev/sda"):
            assert self.classify(cmd) == self.Intent.DESTRUCTIVE, f"'{cmd}' should be DESTRUCTIVE"

    def test_classifies_network_commands(self):
        for cmd in ("curl https://example.com", "wget file.zip", "ssh user@host"):
            assert self.classify(cmd) == self.Intent.NETWORK, f"'{cmd}' should be NETWORK"

    def test_classifies_process_commands(self):
        assert self.classify("kill -9 1234") == self.Intent.PROCESS_MANAGEMENT
        assert self.classify("pkill -f python") == self.Intent.PROCESS_MANAGEMENT

    def test_classifies_package_commands(self):
        for cmd in ("npm install", "pip install requests", "cargo build"):
            assert self.classify(cmd) == self.Intent.PACKAGE_MANAGEMENT, f"'{cmd}' should be PACKAGE"

    def test_classifies_system_admin_commands(self):
        for cmd in ("sudo ls", "mount /dev/sda /mnt", "systemctl restart nginx"):
            assert self.classify(cmd) == self.Intent.SYSTEM_ADMIN, f"'{cmd}' should be SYSTEM_ADMIN"

    def test_classifies_sed_inplace_as_write(self):
        assert self.classify("sed -i 's/old/new/' file.txt") == self.Intent.WRITE

    def test_classifies_sed_stdout_as_read_only(self):
        assert self.classify("sed 's/old/new/' file.txt") == self.Intent.READ_ONLY

    def test_classifies_git_status_as_read_only(self):
        assert self.classify("git status") == self.Intent.READ_ONLY
        assert self.classify("git log --oneline") == self.Intent.READ_ONLY

    def test_classifies_git_push_as_write(self):
        assert self.classify("git push origin main") == self.Intent.WRITE

    def test_classifies_git_commit_as_write(self):
        assert self.classify("git commit -m 'msg'") == self.Intent.WRITE

    def test_classifies_unknown_commands(self):
        assert self.classify("my_custom_tool --flag") == self.Intent.UNKNOWN

    def test_classifies_empty_command(self):
        assert self.classify("") == self.Intent.UNKNOWN

    def test_classifies_env_prefixed_commands(self):
        assert self.classify("FOO=bar ls -la") == self.Intent.READ_ONLY
        assert self.classify("A=1 B=2 echo hello") == self.Intent.READ_ONLY


# ============================================================================
# 7. validate_command — full pipeline
# ============================================================================

class TestValidateCommandPipeline:
    """Integration: full validation pipeline runs all 6 checks in order."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.bash_validation import validate_command
        self.validate = validate_command

    def test_pipeline_blocks_write_in_read_only(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path

        result = self.validate("rm -rf /tmp/x", PermissionMode.READ_ONLY, Path("/workspace"))
        assert result.is_blocked

    def test_pipeline_warns_destructive_in_write_mode(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path

        result = self.validate("rm -rf /", PermissionMode.WORKSPACE_WRITE, Path("/workspace"))
        assert result.is_warn

    def test_pipeline_allows_safe_read_in_read_only(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path

        result = self.validate("ls -la", PermissionMode.READ_ONLY, Path("/workspace"))
        assert result.is_allowed

    def test_pipeline_warns_traversal_in_write_mode(self):
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path

        result = self.validate("cat ../../../etc/passwd", PermissionMode.WORKSPACE_WRITE, Path("/workspace"))
        assert result.is_warn

    def test_pipeline_first_non_allow_wins(self):
        """First validation that returns non-Allow should stop the pipeline."""
        from src.agent_v2.runtime.permissions import PermissionMode
        from pathlib import Path

        # read-only blocks rm before we even check for destructiveness
        result = self.validate("rm -rf /", PermissionMode.READ_ONLY, Path("/workspace"))
        assert result.is_blocked  # Block, not Warn


# ============================================================================
# 8. Shell metacharacter hardening (anti-bypass)
# ============================================================================

class TestShellMetacharHardening:
    """Anti-bypass: ensure read-only commands can't launder destructive ones."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.bash_validation import is_read_only_command
        self.is_ro = is_read_only_command

    def test_rejects_command_chaining_semicolon(self):
        assert not self.is_ro("cat foo; rm -rf bar")

    def test_rejects_command_chaining_and(self):
        assert not self.is_ro("cat foo && rm -rf bar")

    def test_rejects_command_chaining_or(self):
        assert not self.is_ro("ls || rm bar")

    def test_rejects_pipe_to_shell(self):
        assert not self.is_ro("cat foo | sh")

    def test_rejects_command_substitution_dollar(self):
        assert not self.is_ro("echo $(rm bar)")

    def test_rejects_backtick_substitution(self):
        assert not self.is_ro("echo `rm bar`")

    def test_rejects_redirect_without_spaces(self):
        assert not self.is_ro("echo x>file")

    def test_rejects_subshell(self):
        assert not self.is_ro("(rm -rf /)")

    def test_rejects_newline_injection(self):
        assert not self.is_ro("echo hi\nrm -rf /")

    def test_rejects_interpreters(self):
        """python/node/ruby execute arbitrary code — not read-only."""
        for cmd in (
            'python3 -c "import os; os.system(\'rm -rf .\')"',
            "python script.py",
            "node app.js",
            "ruby x.rb",
            "cargo run",
            "rustc evil.rs",
        ):
            assert not self.is_ro(cmd), f"'{cmd}' should not be read-only"

    def test_rejects_find_with_delete(self):
        assert not self.is_ro("find . -delete")

    def test_rejects_find_with_exec(self):
        assert not self.is_ro("find . -exec rm {} \\;")

    def test_allows_plain_find(self):
        assert self.is_ro("find . -name '*.rs'")

    def test_allows_git_read_only_subcommands(self):
        for cmd in ("git status", "git diff HEAD~1", "git show abc123", "git log --oneline"):
            assert self.is_ro(cmd), f"'{cmd}' should be read-only"

    def test_rejects_git_mutating_subcommands(self):
        for cmd in ("git commit -m x", "git push origin main",
                     "git reset --hard", "git clean -fd"):
            assert not self.is_ro(cmd), f"'{cmd}' should not be read-only"

    def test_empty_command_not_read_only(self):
        assert not self.is_ro("")
        assert not self.is_ro("   ")

    def test_full_path_command(self):
        assert self.is_ro("/usr/bin/cat Cargo.toml")
        assert self.is_ro("/usr/local/bin/git status")

    def test_redirect_blocks_read_only(self):
        assert not self.is_ro("cat Cargo.toml > out.txt")
        assert not self.is_ro("echo test >> out.txt")

    def test_in_place_flag_blocks(self):
        assert not self.is_ro("python -i script.py")
        assert not self.is_ro("sed --in-place 's/a/b/' file.txt")


# ============================================================================
# 9. Helper: extract_first_command
# ============================================================================

class TestExtractFirstCommand:
    """Test the internal command extraction helper."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.bash_validation import extract_first_command
        self.extract = extract_first_command

    def test_extracts_plain_command(self):
        assert self.extract("grep -r pattern .") == "grep"

    def test_extracts_from_env_prefix(self):
        assert self.extract("FOO=bar ls -la") == "ls"

    def test_extracts_from_multiple_env_vars(self):
        assert self.extract("A=1 B=2 echo hello") == "echo"

    def test_extracts_sudo_inner(self):
        from src.agent_v2.runtime.bash_validation import extract_sudo_inner
        result = extract_sudo_inner("sudo rm -rf /tmp/x")
        assert "rm" in result

    def test_extracts_sudo_with_flags(self):
        from src.agent_v2.runtime.bash_validation import extract_sudo_inner
        result = extract_sudo_inner("sudo -u root chmod 777 file")
        assert "chmod" in result

    def test_empty_string(self):
        assert self.extract("") == ""

    def test_only_whitespace(self):
        assert self.extract("   ") == ""

    def test_only_env_vars(self):
        """KEY=val with no actual command."""
        assert self.extract("FOO=bar") == ""

    def test_quoted_env_value(self):
        assert self.extract('FOO="hello world" ls') == "ls"

    def test_single_quoted_env_value(self):
        assert self.extract("FOO='hello world' ls") == "ls"

    def test_strips_leading_path(self):
        assert self.extract("/usr/bin/git status") == "git"


# ============================================================================
# 10. ValidationResult / CommandIntent types
# ============================================================================

class TestTypes:
    """Smoke tests for the result and enum types."""

    def test_validation_result_allow(self):
        from src.agent_v2.runtime.bash_validation import ValidationResult
        r = ValidationResult.allow()
        assert r.is_allowed
        assert not r.is_blocked
        assert not r.is_warn

    def test_validation_result_block(self):
        from src.agent_v2.runtime.bash_validation import ValidationResult
        r = ValidationResult.block("bad command")
        assert r.is_blocked
        assert not r.is_allowed
        assert r.reason == "bad command"

    def test_validation_result_warn(self):
        from src.agent_v2.runtime.bash_validation import ValidationResult
        r = ValidationResult.warn("careful")
        assert r.is_warn
        assert not r.is_allowed
        assert r.message == "careful"

    def test_command_intent_values(self):
        from src.agent_v2.runtime.bash_validation import CommandIntent
        expected = {"READ_ONLY", "WRITE", "DESTRUCTIVE", "NETWORK",
                     "PROCESS_MANAGEMENT", "PACKAGE_MANAGEMENT",
                     "SYSTEM_ADMIN", "UNKNOWN"}
        actual = {e.name for e in CommandIntent}
        assert actual == expected
