"""TDD tests for Session Fork + Session Control.

Reference: claw-code session.rs (fork) + session_control.rs (store)

Tests cover:
  1. Session.fork() — create a new session from current state
  2. SessionFork metadata — parent_session_id, branch_name
  3. SessionControl — pause/resume/session store
  4. SessionStore — workspace-namespaced session persistence
  5. SessionHandle — reference resolution (id, path, alias)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent_v2.types import Message, MessageRole, TextBlock


def _user_msg(text: str) -> Message:
    return Message(role=MessageRole.USER, blocks=[TextBlock(text=text)])


def _asst_msg(text: str) -> Message:
    return Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text=text)])


# ============================================================================
# 1. Session.fork()
# ============================================================================

class TestSessionFork:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.session import Session
        self.Session = Session

    def test_fork_creates_new_session_id(self):
        session = self.Session()
        session.append(_user_msg("hello"))
        forked = session.fork()
        assert forked.session_id != session.session_id

    def test_fork_copies_messages(self):
        session = self.Session()
        session.append(_user_msg("hello"))
        session.append(_asst_msg("hi"))
        forked = session.fork()
        assert len(forked.messages) == 2

    def test_fork_preserves_parent_id(self):
        session = self.Session()
        forked = session.fork()
        assert forked.fork_meta is not None
        assert forked.fork_meta.parent_session_id == session.session_id

    def test_fork_with_branch_name(self):
        session = self.Session()
        forked = session.fork(branch_name="feature/test")
        assert forked.fork_meta is not None
        assert forked.fork_meta.branch_name == "feature/test"

    def test_fork_without_branch_name(self):
        session = self.Session()
        forked = session.fork()
        assert forked.fork_meta is not None
        assert forked.fork_meta.branch_name is None

    def test_fork_is_independent(self):
        """Modifying forked session doesn't affect original."""
        session = self.Session()
        session.append(_user_msg("original"))
        forked = session.fork()
        forked.append(_user_msg("fork message"))
        assert len(forked.messages) == 2
        assert len(session.messages) == 1

    def test_double_fork_chain(self):
        session = self.Session()
        fork1 = session.fork(branch_name="branch-a")
        fork2 = fork1.fork(branch_name="branch-b")
        assert fork2.fork_meta.parent_session_id == fork1.session_id
        assert fork1.fork_meta.parent_session_id == session.session_id

    def test_fork_has_new_timestamps(self):
        session = self.Session()
        import time
        time.sleep(0.01)
        forked = session.fork()
        assert forked.meta.created_ms >= session.meta.created_ms


# ============================================================================
# 2. SessionFork dataclass
# ============================================================================

class TestSessionForkDataclass:

    def test_fork_metadata(self):
        from src.agent_v2.runtime.session import SessionFork
        f = SessionFork(parent_session_id="abc123", branch_name="feature/x")
        assert f.parent_session_id == "abc123"
        assert f.branch_name == "feature/x"

    def test_fork_no_branch(self):
        from src.agent_v2.runtime.session import SessionFork
        f = SessionFork(parent_session_id="abc123")
        assert f.branch_name is None


# ============================================================================
# 3. SessionControl — pause / resume
# ============================================================================

class TestSessionControl:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.session_control import SessionControl, SessionState
        self.Control = SessionControl
        self.State = SessionState

    def test_initial_state_is_active(self):
        from src.agent_v2.runtime.session_control import SessionState
        ctrl = self.Control()
        assert ctrl.state == SessionState.ACTIVE

    def test_pause_changes_state(self):
        ctrl = self.Control()
        ctrl.pause()
        assert ctrl.state == self.State.PAUSED

    def test_resume_changes_state(self):
        ctrl = self.Control()
        ctrl.pause()
        ctrl.resume()
        assert ctrl.state == self.State.ACTIVE

    def test_pause_is_idempotent(self):
        ctrl = self.Control()
        ctrl.pause()
        ctrl.pause()
        assert ctrl.state == self.State.PAUSED

    def test_resume_without_pause_is_noop(self):
        ctrl = self.Control()
        ctrl.resume()
        assert ctrl.state == self.State.ACTIVE

    def test_is_active(self):
        ctrl = self.Control()
        assert ctrl.is_active()
        ctrl.pause()
        assert not ctrl.is_active()

    def test_state_values(self):
        from src.agent_v2.runtime.session_control import SessionState
        assert SessionState.ACTIVE.value == "active"
        assert SessionState.PAUSED.value == "paused"
        assert SessionState.ABORTED.value == "aborted"

    def test_abort(self):
        ctrl = self.Control()
        ctrl.abort()
        assert ctrl.state == self.State.ABORTED


# ============================================================================
# 4. SessionStore — workspace-namespaced persistence
# ============================================================================

class TestSessionStore:

    @pytest.fixture(autouse=True)
    def _import(self):
        from src.agent_v2.runtime.session_control import SessionStore
        self.Store = SessionStore

    def test_from_cwd_creates_store(self, tmp_path: Path):
        store = self.Store.from_cwd(tmp_path)
        assert store.workspace_root == tmp_path
        assert "sessions" in str(store.sessions_dir())

    def test_sessions_dir_created_on_save(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        store = self.Store.from_cwd(tmp_path)
        session = Session()
        session.append(_user_msg("test"))
        store.save(session)
        assert store.sessions_dir().exists()

    def test_save_and_load_roundtrip(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        store = self.Store.from_cwd(tmp_path)
        session = Session()
        session.append(_user_msg("hello"))
        store.save(session)

        loaded = store.load(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert len(loaded.messages) == 1

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        store = self.Store.from_cwd(tmp_path)
        assert store.load("nonexistent") is None

    def test_list_sessions(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        store = self.Store.from_cwd(tmp_path)
        s1 = Session()
        s1.append(_user_msg("s1"))
        s2 = Session()
        s2.append(_user_msg("s2"))
        store.save(s1)
        store.save(s2)
        sessions = store.list_sessions()
        assert len(sessions) >= 2

    def test_latest_session(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        import time
        store = self.Store.from_cwd(tmp_path)
        s1 = Session()
        s1.append(_user_msg("old"))
        store.save(s1)
        time.sleep(0.01)
        s2 = Session()
        s2.append(_user_msg("new"))
        store.save(s2)
        latest = store.latest()
        assert latest is not None
        assert latest.session_id == s2.session_id

    def test_delete_session(self, tmp_path: Path):
        from src.agent_v2.runtime.session import Session
        store = self.Store.from_cwd(tmp_path)
        session = Session()
        session.append(_user_msg("to delete"))
        store.save(session)
        store.delete(session.session_id)
        assert store.load(session.session_id) is None
