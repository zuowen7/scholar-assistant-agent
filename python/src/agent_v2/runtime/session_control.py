"""Session Control — pause/resume/abort + workspace-namespaced session store.

Port of claw-code session_control.rs.

SessionControl: in-memory state machine for session lifecycle (Active/Paused/Aborted).
SessionStore: per-workspace session persistence with namespace isolation.
"""
from __future__ import annotations

import hashlib
import json
import logging
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SessionControl — in-memory state machine
# ---------------------------------------------------------------------------

class SessionState(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ABORTED = "aborted"


class SessionControl:
    """In-memory session lifecycle control (pause/resume/abort)."""

    def __init__(self) -> None:
        self.state = SessionState.ACTIVE

    def pause(self) -> None:
        if self.state == SessionState.ACTIVE:
            self.state = SessionState.PAUSED

    def resume(self) -> None:
        if self.state == SessionState.PAUSED:
            self.state = SessionState.ACTIVE

    def abort(self) -> None:
        self.state = SessionState.ABORTED

    def is_active(self) -> bool:
        return self.state == SessionState.ACTIVE


# ---------------------------------------------------------------------------
# SessionStore — workspace-namespaced session persistence
# ---------------------------------------------------------------------------

def _workspace_fingerprint(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]


class SessionStore:
    """Per-worktree session store with namespace isolation.

    Layout: <sessions_root>/<workspace_hash>/<session_id>.jsonl
    """

    def __init__(self, workspace_root: Path, sessions_root: Path | None = None):
        self.workspace_root = workspace_root
        fingerprint = _workspace_fingerprint(workspace_root)
        self._sessions_dir = (sessions_root or workspace_root / ".scholar" / "sessions") / fingerprint

    @staticmethod
    def from_cwd(cwd: Path) -> SessionStore:
        return SessionStore(cwd)

    def sessions_dir(self) -> Path:
        return self._sessions_dir

    def save(self, session) -> None:
        from src.agent_v2.runtime.session import Session
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._sessions_dir / f"{session.session_id}.jsonl"
        session.save(path)

    def load(self, session_id: str):
        from src.agent_v2.runtime.session import Session
        path = self._sessions_dir / f"{session_id}.jsonl"
        if not path.is_file():
            return None
        return Session.load(path)

    def delete(self, session_id: str) -> bool:
        path = self._sessions_dir / f"{session_id}.jsonl"
        if path.is_file():
            path.unlink()
            return True
        return False

    def list_sessions(self):
        from src.agent_v2.runtime.session import Session
        if not self._sessions_dir.is_dir():
            return []
        sessions = []
        for p in self._sessions_dir.glob("*.jsonl"):
            try:
                sessions.append((p.stat().st_mtime, Session.load(p)))
            except Exception:
                pass
        sessions.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in sessions]

    def latest(self):
        sessions = self.list_sessions()
        return sessions[0] if sessions else None
