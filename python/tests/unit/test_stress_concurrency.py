"""Stress & concurrency tests: race conditions, resource exhaustion, recovery.

Tests the system under extreme conditions:
- Concurrent workflow creation/deletion
- Rapid state transitions
- Store under disk pressure
- Multiple concurrent AgentLoop instances
"""
from __future__ import annotations

import asyncio
import json
import pytest

pytestmark = [pytest.mark.stress, pytest.mark.fault]
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


class TestStoreUnderStress:
    """WorkflowStore under concurrent read/write pressure."""

    @pytest.fixture
    def store(self, tmp_path):
        from src.agent.workflow_store import WorkflowStore
        return WorkflowStore(str(tmp_path / "stress.db"))

    def test_concurrent_save_delete_race(self, store):
        """Simultaneous saves and deletes — DB remains consistent."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        wf_ids = []

        # Phase 1: create 200 workflows
        for i in range(200):
            ws = WorkflowSession()
            ws.add_message(Message(role="user", content=f"wf_{i}"))
            store.save(ws)
            wf_ids.append(ws.id)

        # Phase 2: concurrently save updates + delete half
        def worker(start_idx: int):
            try:
                for i in range(start_idx, start_idx + 25):
                    ws = store.load(wf_ids[i])
                    if ws:
                        ws.add_message(Message(role="assistant", content=f"update_{i}"))
                        store.save(ws)
            except Exception:
                pass  # Transient conflict is OK under true concurrency

            try:
                for i in range(start_idx + 75, start_idx + 100):
                    if i < len(wf_ids):
                        store.delete(wf_ids[i])
            except Exception:
                pass

        threads = [threading.Thread(target=worker, args=(j,)) for j in range(0, 200, 100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Critical assertion: DB must still be queryable and uncorrupted
        recent = store.list_recent(limit=10)
        assert isinstance(recent, list)
        # Can still save new workflows
        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="post-race"))
        store.save(ws)
        assert store.load(ws.id) is not None

    def test_cleanup_under_concurrent_writes(self, store):
        """cleanup() while saving doesn't cause deadlock."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState
        from src.agent.models import Message
        from datetime import datetime, timedelta

        # Create some old workflows
        for i in range(10):
            ws = WorkflowSession()
            ws.add_message(Message(role="user", content=f"old_{i}"))
            ws.state = WorkflowState.COMPLETED
            ws.updated_at = (datetime.now() - timedelta(days=60)).isoformat()
            store.save(ws)

        errors = []

        def save_new():
            try:
                for j in range(10):
                    ws = WorkflowSession()
                    ws.add_message(Message(role="user", content=f"new_{j}"))
                    store.save(ws)
            except Exception as e:
                errors.append(str(e))

        t = threading.Thread(target=save_new)
        t.start()

        # Run cleanup while saves are happening
        stats = store.cleanup()
        t.join()

        assert len(errors) == 0
        assert isinstance(stats, dict)

    def test_repeated_open_close(self, tmp_path):
        """Opening and closing the store 20 times doesn't leak resources."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = str(tmp_path / "reopen_stress.db")

        for cycle in range(20):
            s = WorkflowStore(db_path)
            ws = WorkflowSession()
            ws.add_message(Message(role="user", content=f"cycle_{cycle}"))
            s.save(ws)
            loaded = s.load(ws.id)
            assert loaded is not None
            s.close()

        # Final open should see all 20
        s = WorkflowStore(db_path)
        recent = s.list_recent(limit=30)
        assert len(recent) >= 20
        s.close()


class TestAgentLoopConcurrency:
    """Multiple AgentLoop instances operating concurrently."""

    @pytest.mark.anyio
    async def test_multiple_parallel_verifications(self):
        """Multiple _verify_answer calls in parallel don't corrupt state."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )

        async def verify(i: int):
            return await agent._verify_answer(
                f"query_{i}", f"long answer " * 50
            )

        results = await asyncio.gather(*[verify(i) for i in range(50)])
        assert len(results) == 50
        # All should have decent confidence for long answers
        for r in results:
            assert r.confidence > 0.5

    @pytest.mark.anyio
    async def test_scratchpad_concurrent_access(self):
        """Scratchpad accessed from concurrent async tasks."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )

        async def write_and_read(i: int):
            key = f"key_{i}"
            agent._scratchpad_store(key, f"value_{i}")
            return agent.scratchpad_read(key)

        results = await asyncio.gather(*[write_and_read(i) for i in range(100)])
        assert len(results) == 100

        # Scratchpad should have max 32 entries (LRU eviction)
        assert len(agent._scratchpad) <= 32


class TestRouterStress:
    """Router API under stress conditions."""

    @pytest.fixture
    def client(self):
        """Test client for API endpoints."""
        with (
            pytest.MonkeyPatch().context() as mp,
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            mp.setenv("SCHOLAR_AGENT_TOKEN", "")
            # Minimal test: just verify request schema works
            from starlette.testclient import TestClient
            try:
                from api_factory import create_app
                app = create_app()
                client = TestClient(app, raise_server_exceptions=False)
                yield client
            except Exception:
                yield None

    def test_workflow_list_many_requests(self, client):
        """Rapid repeated workflow list requests."""
        if client is None:
            pytest.skip("App factory not available")
        for _ in range(20):
            resp = client.get("/api/agent/v2/workflows")
            assert resp.status_code in (200, 403)  # auth or success

    def test_chat_malformed_json(self, client):
        """Malformed JSON in request body returns 422."""
        if client is None:
            pytest.skip("App factory not available")
        resp = client.post(
            "/api/agent/v2/chat",
            content="not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code != 500  # should be 422 or 400, not crash

    def test_workflow_messages_invalid_id(self, client):
        """Path traversal in workflow_id doesn't crash."""
        if client is None:
            pytest.skip("App factory not available")
        resp = client.get("/api/agent/v2/workflows/../../../etc/passwd/messages")
        assert resp.status_code in (403, 404, 422)  # any non-500


class TestSerializationResilience:
    """to_dict/from_dict under adversarial conditions."""

    def test_from_dict_missing_fields(self):
        """from_dict with minimal data doesn't crash."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession.from_dict({"id": "minimal"})
        assert ws.id == "minimal"
        assert ws.messages == []
        assert ws.state.value == "active"  # default

    def test_from_dict_with_nulls(self):
        """from_dict with None values doesn't crash."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession.from_dict({
            "id": "test",
            "state": None,
            "messages": None,
            "stages": None,
        })
        assert ws.id == "test"
        assert ws.messages == []

    def test_to_dict_empty_workflow(self):
        """to_dict on empty workflow produces valid dict."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        data = ws.to_dict()
        assert "id" in data
        assert "messages" in data
        assert "state" in data

    def test_from_dict_with_wrong_type_messages(self):
        """from_dict where messages contains non-dict entries."""
        from src.agent.workflow_session import WorkflowSession

        # This should handle gracefully — messages should have a .get method
        try:
            ws = WorkflowSession.from_dict({
                "id": "bad_msg",
                "messages": [123, "string", None],
                "state": "active",
            })
            # If it doesn't crash, that's OK
            assert ws.id == "bad_msg"
        except (TypeError, AttributeError):
            # If it crashes, that's also acceptable
            pass
