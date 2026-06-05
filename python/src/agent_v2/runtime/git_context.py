"""Git Context — detect workspace git state for system prompt injection.

Port of claw-code rust/crates/runtime/src/git_context.rs.

Detects: branch name, recent commits (max 5), staged files.
Returns None if workspace is not a git repo.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_RECENT_COMMITS = 5


@dataclass(frozen=True)
class GitCommitEntry:
    hash: str
    subject: str


@dataclass
class GitContext:
    branch: str | None
    recent_commits: list[GitCommitEntry]
    staged_files: list[str]

    @staticmethod
    def detect(cwd: Path) -> GitContext | None:
        if not _is_git_repo(cwd):
            return None
        return GitContext(
            branch=_read_branch(cwd),
            recent_commits=_read_recent_commits(cwd),
            staged_files=_read_staged_files(cwd),
        )

    def render(self) -> str:
        lines: list[str] = []
        if self.branch:
            lines.append(f"Git branch: {self.branch}")
        if self.recent_commits:
            lines.append("")
            lines.append("Recent commits:")
            for entry in self.recent_commits:
                lines.append(f"  {entry.hash} {entry.subject}")
        if self.staged_files:
            lines.append("")
            lines.append("Staged files:")
            for f in self.staged_files:
                lines.append(f"  {f}")
        return "\n".join(lines)


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, NotADirectoryError, OSError):
        return None


def _is_git_repo(cwd: Path) -> bool:
    result = _run_git(cwd, "rev-parse", "--is-inside-work-tree")
    return result is not None and result.returncode == 0


def _read_branch(cwd: Path) -> str | None:
    result = _run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    if result is None or result.returncode != 0:
        return None
    branch = result.stdout.strip()
    if not branch or branch == "HEAD":
        return None
    return branch


def _read_recent_commits(cwd: Path) -> list[GitCommitEntry]:
    result = _run_git(cwd, "--no-optional-locks", "log", "--oneline",
                      "-n", str(MAX_RECENT_COMMITS), "--no-decorate")
    if result is None or result.returncode != 0:
        return []
    entries: list[GitCommitEntry] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            entries.append(GitCommitEntry(hash=parts[0], subject=parts[1]))
    return entries


def _read_staged_files(cwd: Path) -> list[str]:
    result = _run_git(cwd, "--no-optional-locks", "diff", "--cached", "--name-only")
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
