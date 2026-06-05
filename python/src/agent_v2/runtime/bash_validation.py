"""Bash command validation pipeline — 6 submodules.

Port of claw-code rust/crates/runtime/src/bash_validation.rs.

Submodules:
  1. readOnlyValidation — block write-like commands in read-only mode
  2. destructiveCommandWarning — flag dangerous destructive commands
  3. modeValidation — enforce permission mode constraints
  4. sedValidation — validate sed expressions
  5. pathValidation — detect suspicious path patterns
  6. commandSemantics — classify command intent
  7. validate_command — full pipeline
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from src.agent_v2.runtime.permissions import PermissionMode


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class CommandIntent(Enum):
    READ_ONLY = "read-only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    NETWORK = "network"
    PROCESS_MANAGEMENT = "process-management"
    PACKAGE_MANAGEMENT = "package-management"
    SYSTEM_ADMIN = "system-admin"
    UNKNOWN = "unknown"


class ValidationResult:
    """Result of validating a bash command."""

    __slots__ = ("_kind", "reason", "message")

    def __init__(self, kind: str, reason: str = "", message: str = ""):
        self._kind = kind
        self.reason = reason
        self.message = message

    @staticmethod
    def allow() -> ValidationResult:
        return ValidationResult("allow")

    @staticmethod
    def block(reason: str) -> ValidationResult:
        return ValidationResult("block", reason=reason)

    @staticmethod
    def warn(message: str) -> ValidationResult:
        return ValidationResult("warn", message=message)

    @property
    def is_allowed(self) -> bool:
        return self._kind == "allow"

    @property
    def is_blocked(self) -> bool:
        return self._kind == "block"

    @property
    def is_warn(self) -> bool:
        return self._kind == "warn"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValidationResult):
            return NotImplemented
        return self._kind == other._kind

    def __repr__(self) -> str:
        return f"ValidationResult({self._kind!r}, reason={self.reason!r}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Command classification tables
# ---------------------------------------------------------------------------

WRITE_COMMANDS = frozenset({
    "cp", "mv", "rm", "mkdir", "rmdir", "touch", "chmod", "chown", "chgrp",
    "ln", "install", "tee", "truncate", "shred", "mkfifo", "mknod", "dd",
})

STATE_MODIFYING_COMMANDS = frozenset({
    "apt", "apt-get", "yum", "dnf", "pacman", "brew", "pip", "pip3",
    "npm", "yarn", "pnpm", "bun", "cargo", "gem", "go", "rustup",
    "docker", "systemctl", "service", "mount", "umount",
    "kill", "pkill", "killall", "reboot", "shutdown", "halt", "poweroff",
    "useradd", "userdel", "usermod", "groupadd", "groupdel",
    "crontab", "at",
})

WRITE_REDIRECTIONS = (">", ">>", ">&")

GIT_READ_ONLY_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "tag", "stash", "remote",
    "fetch", "ls-files", "ls-tree", "cat-file", "rev-parse", "describe",
    "shortlog", "blame", "bisect", "reflog", "config",
})

DESTRUCTIVE_PATTERNS: list[tuple[str, str]] = [
    ("rm -rf /", "Recursive forced deletion at root — this will destroy the system"),
    ("rm -rf ~", "Recursive forced deletion of home directory"),
    ("rm -rf *", "Recursive forced deletion of all files in current directory"),
    ("rm -rf .", "Recursive forced deletion of current directory"),
    ("mkfs", "Filesystem creation will destroy existing data on the device"),
    ("dd if=", "Direct disk write — can overwrite partitions or devices"),
    ("> /dev/sd", "Writing to raw disk device"),
    ("chmod -R 777", "Recursively setting world-writable permissions"),
    ("chmod -R 000", "Recursively removing all permissions"),
    (":(){ :|:& };:", "Fork bomb — will crash the system"),
]

ALWAYS_DESTRUCTIVE_COMMANDS = frozenset({"shred", "wipefs"})

SYSTEM_PATHS = ("/etc/", "/usr/", "/var/", "/boot/", "/sys/", "/proc/",
                 "/dev/", "/sbin/", "/lib/", "/opt/")

SEMANTIC_READ_ONLY_COMMANDS = frozenset({
    "ls", "cat", "head", "tail", "less", "more", "wc", "sort", "uniq",
    "grep", "egrep", "fgrep", "find", "which", "whereis", "whatis",
    "man", "info", "file", "stat", "du", "df", "free", "uptime",
    "uname", "hostname", "whoami", "id", "groups", "env", "printenv",
    "echo", "printf", "date", "cal", "bc", "expr", "test", "true",
    "false", "pwd", "tree", "diff", "cmp", "md5sum", "sha256sum",
    "sha1sum", "xxd", "od", "hexdump", "strings", "readlink", "realpath",
    "basename", "dirname", "seq", "yes", "tput", "column", "jq", "yq",
    "xargs", "tr", "cut", "paste", "awk", "sed",
})

NETWORK_COMMANDS = frozenset({
    "curl", "wget", "ssh", "scp", "rsync", "ftp", "sftp", "nc", "ncat",
    "telnet", "ping", "traceroute", "dig", "nslookup", "host", "whois",
    "ifconfig", "ip", "netstat", "ss", "nmap",
})

PROCESS_COMMANDS = frozenset({
    "kill", "pkill", "killall", "ps", "top", "htop", "bg", "fg",
    "jobs", "nohup", "disown", "wait", "nice", "renice",
})

PACKAGE_COMMANDS = frozenset({
    "apt", "apt-get", "yum", "dnf", "pacman", "brew", "pip", "pip3",
    "npm", "yarn", "pnpm", "bun", "cargo", "gem", "go", "rustup",
    "snap", "flatpak",
})

SYSTEM_ADMIN_COMMANDS = frozenset({
    "sudo", "su", "chroot", "mount", "umount", "fdisk", "parted",
    "lsblk", "blkid", "systemctl", "service", "journalctl", "dmesg",
    "modprobe", "insmod", "rmmod", "iptables", "ufw", "firewall-cmd",
    "sysctl", "crontab", "at", "useradd", "userdel", "usermod",
    "groupadd", "groupdel", "passwd", "visudo",
})

# Shell metacharacters that enable chaining, substitution, piping, redirection
SHELL_METACHARS = set(";|&$`><(){}\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_first_command(command: str) -> str:
    """Extract the first bare command, stripping env vars."""
    trimmed = command.strip()
    if not trimmed:
        return ""

    remaining = trimmed
    # Skip leading KEY=val assignments
    while True:
        next_str = remaining.lstrip()
        eq_pos = next_str.find("=")
        if eq_pos <= 0:
            break
        before_eq = next_str[:eq_pos]
        if not all(c.isalnum() or c == "_" for c in before_eq):
            break
        after_eq = next_str[eq_pos + 1:]
        end = _find_end_of_value(after_eq)
        if end is None:
            return ""
        remaining = after_eq[end:]
        if not remaining.strip():
            return ""

    token = remaining.split()[0] if remaining.split() else ""
    # Strip leading path: /usr/bin/git -> git
    return token.rsplit("/", 1)[-1] if "/" in token else token


def extract_sudo_inner(command: str) -> str:
    """Extract the command after sudo (skip flags and their arguments)."""
    parts = command.split()
    try:
        sudo_idx = parts.index("sudo")
    except ValueError:
        return ""
    # Flags that take an argument (skip the next token too)
    flags_with_arg = {"-u", "-U", "-g", "-G", "-p", "-r", "-t", "-T", "-h"}
    i = sudo_idx + 1
    while i < len(parts):
        part = parts[i]
        if part.startswith("-"):
            if part in flags_with_arg:
                i += 2
                continue
            i += 1
            continue
        break
    if i >= len(parts):
        return ""
    return " ".join(parts[i:])


def _find_end_of_value(s: str) -> int | None:
    """Find end of a value in KEY=value rest (handles quoting)."""
    s = s.lstrip()
    if not s:
        return None

    if s[0] in ('"', "'"):
        quote = s[0]
        i = 1
        while i < len(s):
            if s[i] == quote and (i == 0 or s[i - 1] != "\\"):
                i += 1
                while i < len(s) and not s[i].isspace():
                    i += 1
                return i if i < len(s) else None
            i += 1
        return None
    else:
        idx = 0
        for ch in s:
            if ch.isspace():
                return idx
            idx += 1
        return None


def _get_git_subcommand(command: str) -> str | None:
    """Get the git subcommand (skip flags like -C /path)."""
    parts = command.split()
    sub = None
    found_git = False
    for p in parts:
        if not found_git:
            if p == "git":
                found_git = True
            continue
        if p.startswith("-"):
            continue
        sub = p
        break
    return sub


# ---------------------------------------------------------------------------
# 1. readOnlyValidation
# ---------------------------------------------------------------------------

def validate_read_only(command: str, mode: PermissionMode) -> ValidationResult:
    if mode != PermissionMode.READ_ONLY:
        return ValidationResult.allow()

    first = extract_first_command(command)

    # Write commands
    if first in WRITE_COMMANDS:
        return ValidationResult.block(
            f"Command '{first}' modifies the filesystem and is not allowed in read-only mode"
        )

    # State-modifying commands
    if first in STATE_MODIFYING_COMMANDS:
        return ValidationResult.block(
            f"Command '{first}' modifies system state and is not allowed in read-only mode"
        )

    # sudo wrapping
    if first == "sudo":
        inner = extract_sudo_inner(command)
        if inner:
            inner_result = validate_read_only(inner, mode)
            if not inner_result.is_allowed:
                return inner_result

    # Write redirections
    for redir in WRITE_REDIRECTIONS:
        if redir in command:
            return ValidationResult.block(
                f"Command contains write redirection '{redir}' which is not allowed in read-only mode"
            )

    # Git commands
    if first == "git":
        return _validate_git_read_only(command)

    return ValidationResult.allow()


def _validate_git_read_only(command: str) -> ValidationResult:
    sub = _get_git_subcommand(command)
    if sub is None or sub in GIT_READ_ONLY_SUBCOMMANDS:
        return ValidationResult.allow()
    return ValidationResult.block(
        f"Git subcommand '{sub}' modifies repository state and is not allowed in read-only mode"
    )


# ---------------------------------------------------------------------------
# 2. destructiveCommandWarning
# ---------------------------------------------------------------------------

def check_destructive(command: str) -> ValidationResult:
    for pattern, warning in DESTRUCTIVE_PATTERNS:
        if pattern in command:
            return ValidationResult.warn(f"Destructive command detected: {warning}")

    first = extract_first_command(command)
    if first in ALWAYS_DESTRUCTIVE_COMMANDS:
        return ValidationResult.warn(
            f"Command '{first}' is inherently destructive and may cause data loss"
        )

    if "rm " in command and "-r" in command and "-f" in command:
        return ValidationResult.warn(
            "Recursive forced deletion detected — verify the target path is correct"
        )

    return ValidationResult.allow()


# ---------------------------------------------------------------------------
# 3. modeValidation
# ---------------------------------------------------------------------------

def validate_mode(command: str, mode: PermissionMode) -> ValidationResult:
    if mode == PermissionMode.READ_ONLY:
        return validate_read_only(command, mode)

    if mode == PermissionMode.WORKSPACE_WRITE:
        if _command_targets_outside_workspace(command):
            return ValidationResult.warn(
                "Command appears to target files outside the workspace — requires elevated permission"
            )
        return ValidationResult.allow()

    # DangerFullAccess, Allow, Prompt
    return ValidationResult.allow()


def _command_targets_outside_workspace(command: str) -> bool:
    first = extract_first_command(command)
    if first not in WRITE_COMMANDS and first not in STATE_MODIFYING_COMMANDS:
        return False
    return any(sys_path in command for sys_path in SYSTEM_PATHS)


# ---------------------------------------------------------------------------
# 4. sedValidation
# ---------------------------------------------------------------------------

def validate_sed(command: str, mode: PermissionMode) -> ValidationResult:
    first = extract_first_command(command)
    if first != "sed":
        return ValidationResult.allow()

    if mode == PermissionMode.READ_ONLY and " -i" in command:
        return ValidationResult.block(
            "sed -i (in-place editing) is not allowed in read-only mode"
        )

    return ValidationResult.allow()


# ---------------------------------------------------------------------------
# 5. pathValidation
# ---------------------------------------------------------------------------

def validate_paths(command: str, workspace: Path) -> ValidationResult:
    if "../" in command:
        workspace_str = str(workspace)
        if workspace_str not in command:
            return ValidationResult.warn(
                "Command contains directory traversal pattern '../' — "
                "verify the target path resolves within the workspace"
            )

    if "~/" in command or "$HOME" in command:
        return ValidationResult.warn(
            "Command references home directory — verify it stays within the workspace scope"
        )

    return ValidationResult.allow()


# ---------------------------------------------------------------------------
# 6. commandSemantics
# ---------------------------------------------------------------------------

def classify_command(command: str) -> CommandIntent:
    first = extract_first_command(command)
    return _classify_by_first_command(first, command)


def _classify_by_first_command(first: str, command: str) -> CommandIntent:
    if first in SEMANTIC_READ_ONLY_COMMANDS:
        if first == "sed" and " -i" in command:
            return CommandIntent.WRITE
        return CommandIntent.READ_ONLY

    if first in ALWAYS_DESTRUCTIVE_COMMANDS or first == "rm":
        return CommandIntent.DESTRUCTIVE

    if first in WRITE_COMMANDS:
        return CommandIntent.WRITE

    if first in NETWORK_COMMANDS:
        return CommandIntent.NETWORK

    if first in PROCESS_COMMANDS:
        return CommandIntent.PROCESS_MANAGEMENT

    if first in PACKAGE_COMMANDS:
        return CommandIntent.PACKAGE_MANAGEMENT

    if first in SYSTEM_ADMIN_COMMANDS:
        return CommandIntent.SYSTEM_ADMIN

    if first == "git":
        sub = _get_git_subcommand(command)
        if sub and sub not in GIT_READ_ONLY_SUBCOMMANDS:
            return CommandIntent.WRITE
        return CommandIntent.READ_ONLY

    return CommandIntent.UNKNOWN


# ---------------------------------------------------------------------------
# 7. validate_command — full pipeline
# ---------------------------------------------------------------------------

def validate_command(command: str, mode: PermissionMode, workspace: Path) -> ValidationResult:
    # 1. Mode-level validation (includes read-only checks)
    result = validate_mode(command, mode)
    if not result.is_allowed:
        return result

    # 2. Sed-specific validation
    result = validate_sed(command, mode)
    if not result.is_allowed:
        return result

    # 3. Destructive command warnings
    result = check_destructive(command)
    if not result.is_allowed:
        return result

    # 4. Path validation
    return validate_paths(command, workspace)


# ---------------------------------------------------------------------------
# is_read_only_command — conservative heuristic for permission_enforcer
# ---------------------------------------------------------------------------

def is_read_only_command(command: str) -> bool:
    """Conservative heuristic: is this bash command safe in read-only mode?

    Any shell metacharacter that could chain, substitute, pipe, or redirect
    into a state-changing command rejects the whole line.
    """
    if not command.strip():
        return False

    # Shell metacharacters block the whole command
    for ch in command:
        if ch in SHELL_METACHARS:
            return False

    tokens = command.split()
    first_token = tokens[0].rsplit("/", 1)[-1] if "/" in tokens[0] else tokens[0]

    # git: only known read-only subcommands
    if first_token == "git":
        subcommand = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else ""
        return subcommand in GIT_READ_ONLY_SUBCOMMANDS

    # find: reject actions
    if first_token == "find" and any(
        flag in command for flag in ("-exec", "-execdir", "-delete", "-ok", "-fprintf")
    ):
        return False

    if first_token not in SEMANTIC_READ_ONLY_COMMANDS:
        return False

    if "-i " in command or "--in-place" in command:
        return False

    return True
