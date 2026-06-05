"""WorkflowStore — SQLite-backed persistence for WorkflowSession with auto-cleanup."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.agent.models import Message
from src.agent.workflow_session import WorkflowSession, WorkflowState

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflows (
    id            TEXT PRIMARY KEY,
    state         TEXT NOT NULL DEFAULT 'active',
    title         TEXT NOT NULL DEFAULT '',
    state_json    TEXT NOT NULL DEFAULT '{}',
    messages      TEXT NOT NULL DEFAULT '[]',
    workspace_root TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    archived_at   TEXT,
    message_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_workflows_state ON workflows(state);
CREATE INDEX IF NOT EXISTS idx_workflows_updated ON workflows(updated_at);
"""

_ARCHIVE_COMPLETED_DAYS = 30
_DELETE_ARCHIVED_DAYS = 90
_MAX_DB_BYTES = 500 * 1024 * 1024  # 500MB


class WorkflowStore:
    def __init__(self, db_path: str | Path = "data/agent/workflows.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(_SCHEMA)
        self._conn.row_factory = sqlite3.Row
        self._write_lock = threading.RLock()
        logger.info("WorkflowStore initialized at %s", self.db_path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def save(self, workflow: WorkflowSession) -> None:
        """Upsert a workflow session."""
        now = datetime.now().isoformat(timespec="seconds")
        data = workflow.to_dict()
        row = {
            "id": workflow.id,
            "state": workflow.state.value,
            "title": workflow.title,
            "state_json": json.dumps({
                "stages": data.get("stages", []),
                "current_stage": data.get("current_stage", ""),
            }, ensure_ascii=False),
            "messages": json.dumps(data.get("messages", []), ensure_ascii=False),
            "workspace_root": workflow.workspace_root or "",
            "created_at": workflow.created_at or now,
            "updated_at": workflow.updated_at or now,
            "archived_at": workflow.archived_at,
            "message_count": len(workflow.messages),
        }
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO workflows (id, state, title, state_json, messages,
                   workspace_root, created_at, updated_at, archived_at, message_count)
                   VALUES (:id, :state, :title, :state_json, :messages,
                   :workspace_root, :created_at, :updated_at, :archived_at, :message_count)
                   ON CONFLICT(id) DO UPDATE SET
                     state=excluded.state, title=excluded.title,
                     state_json=excluded.state_json, messages=excluded.messages,
                     workspace_root=excluded.workspace_root,
                     updated_at=excluded.updated_at,
                     archived_at=excluded.archived_at,
                     message_count=excluded.message_count
                """, row)
            self._conn.commit()

    def load(self, workflow_id: str) -> WorkflowSession | None:
        """Load a workflow by ID."""
        cur = self._conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_workflow(row)

    def load_messages(self, workflow_id: str) -> list[Message]:
        """Load only the messages for a workflow (lightweight)."""
        cur = self._conn.execute("SELECT messages FROM workflows WHERE id = ?", (workflow_id,))
        row = cur.fetchone()
        if row is None:
            return []
        raw = json.loads(row["messages"])
        messages = []
        for m in raw:
            tool_calls = None
            tc_list = m.get("tool_calls")
            if tc_list:
                from src.agent.models import ToolCall
                tool_calls = [ToolCall(**tc) for tc in tc_list]
            messages.append(Message(
                role=m["role"],
                content=m.get("content", ""),
                tool_calls=tool_calls,
                tool_call_id=m.get("tool_call_id"),
            ))
        return messages

    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent workflows (metadata only, no messages)."""
        cur = self._conn.execute(
            "SELECT id, state, title, state_json, workspace_root, created_at, updated_at,"
            " message_count FROM workflows WHERE state != 'deleted' AND state != ''"
            " ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        results = []
        for row in cur.fetchall():
            state_json = json.loads(row["state_json"]) if row["state_json"] else {}
            results.append({
                "id": row["id"],
                "state": row["state"],
                "title": row["title"],
                "current_stage": state_json.get("current_stage", ""),
                "workspace_root": row["workspace_root"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "message_count": row["message_count"],
            })
        return results

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow. Returns True if something was deleted."""
        with self._write_lock:
            cur = self._conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> dict[str, int]:
        """Archive old completed workflows, delete old archived ones."""
        now = datetime.now()
        archived = self._archive_old(now)
        deleted = self._delete_old(now)
        evicted = self._enforce_quota()
        return {"archived": archived, "deleted": deleted, "evicted": evicted}

    def _archive_old(self, now: datetime) -> int:
        """Archive completed workflows older than ARCHIVE_COMPLETED_DAYS."""
        cutoff = (now - timedelta(days=_ARCHIVE_COMPLETED_DAYS)).isoformat()
        with self._write_lock:
            cur = self._conn.execute(
                "UPDATE workflows SET state = ?, archived_at = ?"
                " WHERE state = 'completed' AND updated_at < ?",
                (WorkflowState.ARCHIVED.value, now.isoformat(), cutoff),
            )
            self._conn.commit()
            return cur.rowcount

    def _delete_old(self, now: datetime) -> int:
        """Delete archived workflows older than DELETE_ARCHIVED_DAYS."""
        cutoff = (now - timedelta(days=_DELETE_ARCHIVED_DAYS)).isoformat()
        with self._write_lock:
            cur = self._conn.execute(
                "DELETE FROM workflows WHERE state = 'archived' AND archived_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            return cur.rowcount

    def _enforce_quota(self) -> int:
        """If total storage exceeds quota, LRU evict oldest archived workflows."""
        # Simple approach: check file size, if over quota delete oldest archived
        try:
            file_size = self.db_path.stat().st_size
        except OSError:
            return 0
        if file_size <= _MAX_DB_BYTES:
            return 0

        excess_bytes = file_size - _MAX_DB_BYTES
        evicted = 0
        # Delete oldest archived first
        with self._write_lock:
            while excess_bytes > 0 and evicted < 100:
                cur = self._conn.execute(
                    "SELECT id FROM workflows WHERE state = 'archived'"
                    " ORDER BY updated_at ASC LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    break
                self._conn.execute("DELETE FROM workflows WHERE id = ?", (row["id"],))
                self._conn.commit()
                evicted += 1
                try:
                    excess_bytes -= self.db_path.stat().st_size - file_size
                    file_size = self.db_path.stat().st_size
                except OSError:
                    break
        return evicted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_workflow(self, row: sqlite3.Row) -> WorkflowSession:
        """Convert a DB row to a WorkflowSession."""
        state_json = json.loads(row["state_json"]) if row["state_json"] else {}
        raw_messages = json.loads(row["messages"]) if row["messages"] else []

        messages = []
        for m in raw_messages:
            tool_calls = None
            tc_list = m.get("tool_calls")
            if tc_list:
                from src.agent.models import ToolCall
                tool_calls = [ToolCall(**tc) for tc in tc_list]
            messages.append(Message(
                role=m["role"],
                content=m.get("content", ""),
                tool_calls=tool_calls,
                tool_call_id=m.get("tool_call_id"),
            ))

        ws = WorkflowSession(
            workflow_id=row["id"],
            workspace_root=row["workspace_root"] or None,
        )
        ws.state = WorkflowState(row["state"])
        ws.title = row["title"]
        ws.stages = state_json.get("stages", [])
        ws.current_stage = state_json.get("current_stage", "")
        ws.messages = messages
        ws.created_at = row["created_at"]
        ws.updated_at = row["updated_at"]
        ws.archived_at = row["archived_at"]
        return ws

    def close(self) -> None:
        with self._write_lock:
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
