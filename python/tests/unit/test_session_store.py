"""SessionStore 单元测试 — SQLite 持久化、序列化/反序列化。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.agent.models import SessionState, Message
from src.agent.session import AgentSession, SessionConfig
from src.agent.agent import AgentLoop
from src.agent.session_store import SessionStore
from src.agent.task_queue import TaskQueue, Task, TaskStatus


@pytest.fixture
def store(tmp_path):
    return SessionStore(db_path=str(tmp_path / "test_sessions.db"))


@pytest.fixture
def agent():
    return AgentLoop(ollama_base_url="http://localhost:99999", model="test")


class TestSessionStoreCRUD:
    def test_save_and_load(self, store):
        data = {
            "id": "sess_abc123",
            "state": "EXECUTING",
            "config": {"auto_approve": True, "max_task_steps": 50},
            "messages": [{"role": "user", "content": "hello"}],
            "task_queue": [
                {"id": "t_001", "title": "step 1", "status": "DONE", "result": "ok"},
                {"id": "t_002", "title": "step 2", "status": "PENDING", "result": ""},
            ],
            "global_step": 5,
            "workspace_root": "/tmp/project",
            "query": "do something",
        }
        store.save(data)

        loaded = store.load("sess_abc123")
        assert loaded is not None
        assert loaded["id"] == "sess_abc123"
        assert loaded["state"] == "EXECUTING"
        assert loaded["global_step"] == 5
        assert len(loaded["messages"]) == 1
        assert len(loaded["task_queue"]) == 2

    def test_load_nonexistent(self, store):
        assert store.load("no_such_id") is None

    def test_upsert(self, store):
        data = {"id": "sess_1", "state": "INITIALIZING", "global_step": 0,
                "messages": [], "task_queue": [], "config": {}, "query": "q1"}
        store.save(data)

        data["state"] = "EXECUTING"
        data["global_step"] = 10
        store.save(data)

        loaded = store.load("sess_1")
        assert loaded["state"] == "EXECUTING"
        assert loaded["global_step"] == 10

    def test_delete(self, store):
        store.save({"id": "sess_del", "state": "DONE", "global_step": 1,
                     "messages": [], "task_queue": [], "config": {}, "query": ""})
        assert store.delete("sess_del") is True
        assert store.load("sess_del") is None
        assert store.delete("sess_del") is False


class TestSessionList:
    def test_list_excludes_done(self, store):
        for i, state in enumerate(["EXECUTING", "DONE", "IDLE", "ABORTED"]):
            store.save({"id": f"s{i}", "state": state, "global_step": 0,
                         "messages": [], "task_queue": [], "config": {}, "query": f"q{i}"})
        result = store.list_sessions()
        ids = [r["id"] for r in result]
        assert "s0" in ids  # EXECUTING
        assert "s1" not in ids  # DONE excluded
        assert "s2" in ids  # IDLE
        assert "s3" not in ids  # ABORTED excluded

    def test_list_all(self, store):
        for i, state in enumerate(["EXECUTING", "DONE"]):
            store.save({"id": f"s{i}", "state": state, "global_step": 0,
                         "messages": [], "task_queue": [], "config": {}, "query": ""})
        result = store.list_sessions(exclude_done=False)
        assert len(result) == 2

    def test_list_by_state(self, store):
        store.save({"id": "s1", "state": "EXECUTING", "global_step": 0,
                     "messages": [], "task_queue": [], "config": {}, "query": ""})
        store.save({"id": "s2", "state": "IDLE", "global_step": 0,
                     "messages": [], "task_queue": [], "config": {}, "query": ""})
        result = store.list_sessions(state="EXECUTING")
        assert len(result) == 1
        assert result[0]["id"] == "s1"


class TestSerializeSession:
    def test_serialize_roundtrip(self, store, agent):
        session = AgentSession(
            agent=agent,
            session_id="sess_rt",
            config=SessionConfig(),
        )
        session.global_step = 7
        session.task_queue.add("task 1")
        session.task_queue.add("task 2")
        session.task_queue.mark_done(session.task_queue.all_tasks[0].id)
        session.messages = [Message(role="user", content="test")]

        data = store.serialize_session(session, query="test query")
        assert data["id"] == "sess_rt"
        assert data["global_step"] == 7
        assert len(data["task_queue"]) == 2
        assert len(data["messages"]) == 1

        # Round-trip
        store.save(data)
        loaded = store.load("sess_rt")
        assert loaded is not None
        assert loaded["global_step"] == 7

    def test_deserialize_task_queue(self, store):
        raw = [
            {"id": "t_1", "title": "step a", "status": "DONE", "result": "ok"},
            {"id": "t_2", "title": "step b", "status": "PENDING", "result": ""},
            {"id": "t_3", "title": "step c", "status": "RUNNING", "result": ""},
        ]
        tq = store.deserialize_task_queue(raw)
        assert tq.total_count == 3
        assert tq.done_count == 1
        assert tq.has_pending()

    def test_deserialize_messages(self, store):
        raw = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello", "tool_call_id": None},
        ]
        msgs = store.deserialize_messages(raw)
        assert len(msgs) == 3
        assert msgs[0].role == "system"
        assert msgs[1].content == "hi"


class TestSessionCheckpoint:
    @pytest.mark.anyio
    async def test_checkpoint_persists(self, store, agent):
        session = AgentSession(
            agent=agent,
            session_id="sess_ckpt",
            session_store=store,
            config=SessionConfig(),
        )
        session.global_step = 42
        session.messages = [Message(role="user", content="checkpoint test")]

        session._checkpoint()

        loaded = store.load("sess_ckpt")
        assert loaded is not None
        assert loaded["global_step"] == 42

    def test_no_store_no_crash(self, agent):
        session = AgentSession(agent=agent, config=SessionConfig())
        session._checkpoint()  # Should not raise


class TestRestartRecovery:
    def test_survives_store_reopen(self, tmp_path):
        db_path = str(tmp_path / "sessions.db")

        store1 = SessionStore(db_path=db_path)
        store1.save({"id": "sess_r", "state": "EXECUTING", "global_step": 3,
                      "messages": [{"role": "user", "content": "resume me"}],
                      "task_queue": [
                          {"id": "t_1", "title": "done", "status": "DONE", "result": "ok"},
                          {"id": "t_2", "title": "pending", "status": "PENDING", "result": ""},
                      ],
                      "config": {}, "query": "resume me"})
        store1.close()

        # Reopen
        store2 = SessionStore(db_path=db_path)
        loaded = store2.load("sess_r")
        assert loaded is not None
        assert loaded["state"] == "EXECUTING"
        assert loaded["global_step"] == 3
        assert len(loaded["task_queue"]) == 2

        tq = store2.deserialize_task_queue(loaded["task_queue"])
        assert tq.has_pending()
        assert tq.done_count == 1
        store2.close()
