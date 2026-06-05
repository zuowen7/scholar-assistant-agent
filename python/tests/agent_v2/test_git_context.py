"""TDD tests for Git Context Injection.

Reference: claw-code rust/crates/runtime/src/git_context.rs

Tests cover:
  1. GitContext.detect() — detect git state from workspace
  2. GitContext.render() — format for system prompt injection
  3. Edge cases: non-git dir, empty repo, detached HEAD, many commits
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest


def _run_git(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with one commit."""
    _run_git(tmp_path, "init", "--quiet")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "init.txt").write_text("init\n", encoding="utf-8")
    _run_git(tmp_path, "add", "init.txt")
    _run_git(tmp_path, "commit", "-m", "initial commit", "--quiet")
    return tmp_path


@pytest.fixture
def non_git_dir(tmp_path: Path) -> Path:
    d = tmp_path / "plain"
    d.mkdir()
    return d


# ============================================================================
# 1. detect() — basic detection
# ============================================================================

class TestGitContextDetect:

    def test_returns_none_for_non_git_directory(self, non_git_dir: Path):
        from src.agent_v2.runtime.git_context import GitContext
        assert GitContext.detect(non_git_dir) is None

    def test_detects_branch_name(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        # Default branch name varies (main/master); just check it exists
        assert ctx.branch is not None
        assert ctx.branch != "HEAD"

    def test_detects_recent_commits(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert len(ctx.recent_commits) >= 1
        assert ctx.recent_commits[0].subject == "initial commit"

    def test_staged_files_empty_after_commit(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert ctx.staged_files == []

    def test_detects_staged_files(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        (git_repo / "new.txt").write_text("new content\n", encoding="utf-8")
        _run_git(git_repo, "add", "new.txt")
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert "new.txt" in ctx.staged_files

    def test_multiple_commits_ordered_newest_first(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        (git_repo / "second.txt").write_text("second\n", encoding="utf-8")
        _run_git(git_repo, "add", "second.txt")
        _run_git(git_repo, "commit", "-m", "second commit", "--quiet")
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert len(ctx.recent_commits) == 2
        assert ctx.recent_commits[0].subject == "second commit"
        assert ctx.recent_commits[1].subject == "initial commit"

    def test_limits_to_five_recent_commits(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        for i in range(2, 9):  # commits 2..8, total 8
            (git_repo / f"f{i}.txt").write_text(f"{i}\n", encoding="utf-8")
            _run_git(git_repo, "add", f"f{i}.txt")
            _run_git(git_repo, "commit", "-m", f"commit {i}", "--quiet")
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert len(ctx.recent_commits) == 5
        assert ctx.recent_commits[0].subject == "commit 8"

    def test_detached_head_returns_none_branch(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        first_hash = ctx.recent_commits[-1].hash
        _run_git(git_repo, "checkout", "--quiet", first_hash)
        ctx2 = GitContext.detect(git_repo)
        assert ctx2 is not None
        assert ctx2.branch is None

    def test_detects_branch_after_create(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        _run_git(git_repo, "checkout", "--quiet", "-b", "feature/test")
        (git_repo / "feat.txt").write_text("feat\n", encoding="utf-8")
        _run_git(git_repo, "add", "feat.txt")
        _run_git(git_repo, "commit", "-m", "feature work", "--quiet")
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        assert ctx.branch == "feature/test"


# ============================================================================
# 2. render() — format for system prompt
# ============================================================================

class TestGitContextRender:

    def test_render_includes_branch(self):
        from src.agent_v2.runtime.git_context import GitContext, GitCommitEntry
        ctx = GitContext(
            branch="main",
            recent_commits=[GitCommitEntry(hash="abc1234", subject="add feature")],
            staged_files=[],
        )
        rendered = ctx.render()
        assert "Git branch: main" in rendered
        assert "abc1234 add feature" in rendered

    def test_render_omits_empty_sections(self):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch="main", recent_commits=[], staged_files=[])
        rendered = ctx.render()
        assert "Git branch: main" in rendered
        assert "Recent commits:" not in rendered
        assert "Staged files:" not in rendered

    def test_render_includes_staged_files(self):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch="main", recent_commits=[], staged_files=["src/main.py", "README.md"])
        rendered = ctx.render()
        assert "Staged files:" in rendered
        assert "src/main.py" in rendered
        assert "README.md" in rendered

    def test_render_no_branch(self):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext(branch=None, recent_commits=[], staged_files=[])
        rendered = ctx.render()
        assert "Git branch:" not in rendered

    def test_real_repo_render(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        rendered = ctx.render()
        assert "Git branch:" in rendered
        assert "initial commit" in rendered


# ============================================================================
# 3. GitCommitEntry dataclass
# ============================================================================

class TestGitCommitEntry:

    def test_fields(self):
        from src.agent_v2.runtime.git_context import GitCommitEntry
        entry = GitCommitEntry(hash="abc123", subject="test commit")
        assert entry.hash == "abc123"
        assert entry.subject == "test commit"

    def test_equality(self):
        from src.agent_v2.runtime.git_context import GitCommitEntry
        a = GitCommitEntry(hash="abc", subject="s")
        b = GitCommitEntry(hash="abc", subject="s")
        assert a == b


# ============================================================================
# 4. Integration: inject into system prompt
# ============================================================================

class TestSystemPromptInjection:

    def test_inject_context_into_prompt(self, git_repo: Path):
        from src.agent_v2.runtime.git_context import GitContext
        ctx = GitContext.detect(git_repo)
        assert ctx is not None
        prompt_section = ctx.render()
        system_prompt = f"You are a helpful assistant.\n\n--- Git Context ---\n{prompt_section}\n--- End Git Context ---"
        assert "Git branch:" in system_prompt
        assert "initial commit" in system_prompt
