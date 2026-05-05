"""SessionStore — SQLite-backed persistence for AgentSession.

Enables session resume after client disconnect or server restart.
Uses a simple SQLite table (one row per session) with JSON-serialized state.

WAL mode is required to avoid "database is locked" under concurrent writes
(the same pattern used throughout the project for ChromaDB / config stores).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.models import Message, SessionState

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    messages    TEXT NOT NULL DEFAULT '[]',
    task_queue  TEXT NOT NULL DEFAULT '[]',
    global_step INTEGER NOT NULL DEFAULT 0,
    workspace_root TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    query       TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
"""


class SessionStore:
    """SQLite-backed session store.

    Each session is serialized as a JSON row. The store supports:
    - save(): upsert a session snapshot
    - load(): restore a session by id
    - list_sessions(): filter by state
    - delete(): remove a session
    """

    def __init__(self, db_path: str | Path = "data/agent/sessions.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.row_factory = sqlite3.Row
        logger.info("SessionStore initialized at %s", self.db_path)

    def save(self, session_data: dict[str, Any]) -> None:
        """Upsert a session snapshot.

        Args:
            session_data: Serialized session dict with keys:
                id, state, config, messages, task_queue, global_step,
                workspace_root, query
        """
        sid = session_data["id"]
        now = datetime.now().isoformat(timespec="seconds")

        row = {
            "id": sid,
            "state": session_data.get("state", "INITIALIZING"),
            "config_json": json.dumps(session_data.get("config", {}), ensure_ascii=False),
            "messages": json.dumps(session_data.get("messages", []), ensure_ascii=False),
            "task_queue": json.dumps(session_data.get("task_queue", []), ensure_ascii=False),
            "global_step": session_data.get("global_step", 0),
            "workspace_root": session_data.get("workspace_root", ""),
            "created_at": session_data.get("created_at", now),
            "updated_at": now,
            "query": session_data.get("query", ""),
        }

        self._conn.execute(
            """INSERT INTO sessions (id, state, config_json, messages, task_queue,
               global_step, workspace_root, created_at, updated_at, query)
               VALUES (:id, :state, :config_json, :messages, :task_queue,
               :global_step, :workspace_root, :created_at, :updated_at, :query)
               ON CONFLICT(id) DO UPDATE SET
                 state=excluded.state,
                 config_json=excluded.config_json,
                 messages=excluded.messages,
                 task_queue=excluded.task_queue,
                 global_step=excluded.global_step,
                 workspace_root=excluded.workspace_root,
                 updated_at=excluded.updated_at,
                 query=excluded.query
            """,
            row,
        )
        self._conn.commit()

    def load(self, session_id: str) -> dict[str, Any] | None:
        """Load a session by id.

        Returns:
            Deserialized session dict, or None if not found.
        """
        cur = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None

        return {
            "id": row["id"],
            "state": row["state"],
            "config": json.loads(row["config_json"]),
            "messages": json.loads(row["messages"]),
            "task_queue": json.loads(row["task_queue"]),
            "global_step": row["global_step"],
            "workspace_root": row["workspace_root"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "query": row["query"],
        }

    def list_sessions(
        self,
        *,
        state: str | None = None,
        exclude_done: bool = True,
    ) -> list[dict[str, Any]]:
        """List sessions, optionally filtered.

        Args:
            state: Filter by session state name.
            exclude_done: Exclude DONE/ABORTED sessions by default.

        Returns:
            List of session summary dicts.
        """
        if state:
            cur = self._conn.execute(
                "SELECT id, state, global_step, workspace_root, created_at, updated_at, query FROM sessions WHERE state = ? ORDER BY updated_at DESC",
                (state,),
            )
        elif exclude_done:
            cur = self._conn.execute(
                "SELECT id, state, global_step, workspace_root, created_at, updated_at, query FROM sessions WHERE state NOT IN ('DONE', 'ABORTED') ORDER BY updated_at DESC"
            )
        else:
            cur = self._conn.execute(
                "SELECT id, state, global_step, workspace_root, created_at, updated_at, query FROM sessions ORDER BY updated_at DESC"
            )

        results = []
        for row in cur.fetchall():
            tq = self._load_task_queue(row["id"])
            results.append({
                "id": row["id"],
                "state": row["state"],
                "global_step": row["global_step"],
                "workspace_root": row["workspace_root"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "query": row["query"],
                "tasks_total": len(tq),
                "tasks_done": sum(1 for t in tq if t.get("status") == "DONE"),
            })
        return results

    def delete(self, session_id: str) -> bool:
        """Delete a session.

        Returns:
            True if a row was deleted.
        """
        cur = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def _load_task_queue(self, session_id: str) -> list[dict]:
        """Load task queue for a session from the main row."""
        cur = self._conn.execute(
            "SELECT task_queue FROM sessions WHERE id = ?", (session_id,)
        )
        row = cur.fetchone()
        if row is None:
            return []
        return json.loads(row["task_queue"])

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _serialize_message(m) -> dict:
        d: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_call_id is not None:
            d["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in m.tool_calls
            ]
        if m.reasoning_content:
            d["reasoning_content"] = m.reasoning_content
        return d

    @staticmethod
    def _deserialize_message(raw: dict):
        from src.agent.models import Message, ToolCall

        tool_calls = None
        tc_list = raw.get("tool_calls")
        if tc_list:
            tool_calls = [ToolCall(**tc) for tc in tc_list]
        return Message(
            role=raw["role"],
            content=raw.get("content", ""),
            tool_calls=tool_calls,
            tool_call_id=raw.get("tool_call_id"),
            reasoning_content=raw.get("reasoning_content"),
        )

    def serialize_session(self, session, *, query: str = "") -> dict[str, Any]:
        """Serialize an AgentSession to a storable dict.

        Args:
            session: AgentSession instance.
            query: The original user query.

        Returns:
            Serializable dict.
        """
        return {
            "id": session.id,
            "state": session.state.name,
            "config": {
                "max_task_steps": session.config.max_task_steps,
                "max_global_steps": session.config.max_global_steps,
                "auto_approve": session.config.auto_approve,
                "approval_timeout": session.config.approval_timeout,
            },
            "messages": [
                self._serialize_message(m)
                for m in session.messages
            ],
            "task_queue": [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status.name,
                    "result": t.result,
                }
                for t in session.task_queue.all_tasks
            ],
            "global_step": session.global_step,
            "workspace_root": str(session.workspace.root) if session.workspace else "",
            "query": query,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def deserialize_messages(self, raw: list[dict]) -> list[Message]:
        """Convert stored message dicts back to Message objects."""
        return [self._deserialize_message(m) for m in raw]

    def deserialize_task_queue(self, raw: list[dict]):
        """Rebuild a TaskQueue from stored task data."""
        from src.agent.task_queue import Task, TaskQueue, TaskStatus

        tq = TaskQueue()
        for t_data in raw:
            status = TaskStatus[t_data["status"]]
            task = Task(
                id=t_data["id"],
                title=t_data["title"],
                status=status,
                result=t_data.get("result", ""),
            )
            # Bypass add() to preserve IDs and status
            tq._tasks.append(task)
        return tq
