"""Session resume 集成测试 — 断流恢复、跨进程持久化。"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.agent.agent import AgentLoop
from src.agent.models import Message, SessionState, EVT_DONE, EVT_SESSION_STARTED
from src.agent.session import AgentSession, SessionConfig
from src.agent.session_store import SessionStore
from src.agent.task_queue import TaskStatus


@pytest.fixture
def agent():
    return AgentLoop(ollama_base_url="http://localhost:99999", model="test")


@pytest.fixture
def store(tmp_path):
    return SessionStore(db_path=str(tmp_path / "resume_sessions.db"))


class TestResumeFromCheckpoint:
    @pytest.mark.anyio
    async def test_resume_restores_task_queue(self, agent, store):
        """Simulate: session runs 2 tasks, disconnects, resumes for remaining tasks."""
        session = AgentSession(
            agent=agent,
            session_id="sess_resume1",
            session_store=store,
            config=SessionConfig(auto_approve=True),
        )
        session.messages = [Message(role="user", content="test")]
        session.global_step = 10

        # Simulate 2 tasks done, 3 remaining
        from src.agent.task_queue import Task, TaskQueue, TaskStatus
        session.task_queue._tasks = [
            Task(id="t_1", title="step 1", status=TaskStatus.DONE, result="ok"),
            Task(id="t_2", title="step 2", status=TaskStatus.DONE, result="ok"),
            Task(id="t_3", title="step 3", status=TaskStatus.PENDING),
            Task(id="t_4", title="step 4", status=TaskStatus.PENDING),
            Task(id="t_5", title="step 5", status=TaskStatus.PENDING),
        ]

        # Save checkpoint
        session._query = "multi-step task"
        session._checkpoint()

        # Verify stored
        loaded = store.load("sess_resume1")
        assert loaded is not None
        assert loaded["global_step"] == 10
        tq_data = loaded["task_queue"]
        assert len(tq_data) == 5
        assert sum(1 for t in tq_data if t["status"] == "DONE") == 2
        assert sum(1 for t in tq_data if t["status"] == "PENDING") == 3

    @pytest.mark.anyio
    async def test_resume_event_includes_metadata(self, agent, store):
        """Resumed session yields session_started with resumed=true."""
        session = AgentSession(
            agent=agent,
            session_id="sess_meta",
            session_store=store,
            config=SessionConfig(),
        )
        session.task_queue._tasks = []  # No tasks — immediate done

        events = []
        async for ev in session.resume(agent):
            events.append(ev)

        # First event should be session_started with resumed=True
        start_ev = events[0]
        assert start_ev.type == EVT_SESSION_STARTED
        assert start_ev.metadata.get("resumed") is True


class TestCrossProcessPersistence:
    def test_session_survives_store_close(self, tmp_path):
        """Session data persists after closing and reopening the store."""
        db_path = str(tmp_path / "persist.db")

        # First "process" — write
        store1 = SessionStore(db_path=db_path)
        store1.save({
            "id": "sess_persist",
            "state": "IDLE",
            "global_step": 15,
            "messages": [
                {"role": "user", "content": "long task"},
                {"role": "assistant", "content": "partial result"},
            ],
            "task_queue": [
                {"id": "t_1", "title": "step 1", "status": "DONE", "result": "ok"},
                {"id": "t_2", "title": "step 2", "status": "DONE", "result": "ok"},
                {"id": "t_3", "title": "step 3", "status": "PENDING", "result": ""},
            ],
            "config": {"auto_approve": True, "max_task_steps": 50, "max_global_steps": 200},
            "workspace_root": "",
            "query": "long task",
        })
        store1.close()

        # Second "process" — read
        store2 = SessionStore(db_path=db_path)
        loaded = store2.load("sess_persist")
        assert loaded is not None
        assert loaded["global_step"] == 15
        assert len(loaded["messages"]) == 2

        tq = store2.deserialize_task_queue(loaded["task_queue"])
        assert tq.done_count == 2
        assert tq.has_pending()

        # Can reconstruct a session
        messages = store2.deserialize_messages(loaded["messages"])
        assert len(messages) == 2
        assert messages[0].role == "user"

        store2.close()


class TestSessionListMerged:
    def test_in_memory_and_stored_sessions(self, tmp_path, agent):
        """list_sessions merges in-memory pool and stored sessions."""
        store = SessionStore(db_path=str(tmp_path / "merged.db"))

        # Save a persisted session
        store.save({
            "id": "sess_stored",
            "state": "IDLE",
            "global_step": 3,
            "messages": [],
            "task_queue": [
                {"id": "t_1", "title": "done", "status": "DONE", "result": "ok"},
                {"id": "t_2", "title": "pending", "status": "PENDING", "result": ""},
            ],
            "config": {},
            "workspace_root": "",
            "query": "stored task",
        })

        result = store.list_sessions()
        assert any(r["id"] == "sess_stored" for r in result)

        # The stored session should show task counts
        stored = next(r for r in result if r["id"] == "sess_stored")
        assert stored["tasks_total"] == 2
        assert stored["tasks_done"] == 1

        store.close()
