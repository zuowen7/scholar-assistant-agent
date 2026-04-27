"""AgentSession 单元测试 — 状态机、事件流、并发隔离。"""

from __future__ import annotations

import pytest

from src.agent.agent import AgentLoop
from src.agent.models import (
    AgentEvent,
    EVT_DONE,
    EVT_SESSION_STARTED,
    EVT_TASK_DONE,
    EVT_TASK_STARTED,
    EVT_TOOL_CALL,
    EVT_TOOL_RESULT,
    EVT_WARNING,
    Message,
    SessionState,
)
from src.agent.session import AgentSession, SessionConfig
from src.agent.task_queue import TaskStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent():
    """AgentLoop with no real LLM (tools won't actually be called)."""
    return AgentLoop(
        ollama_base_url="http://localhost:99999",
        model="test-model",
    )


@pytest.fixture
def session(agent):
    return AgentSession(agent=agent, config=SessionConfig())


# ---------------------------------------------------------------------------
# Session Lifecycle
# ---------------------------------------------------------------------------


class TestSessionInit:
    def test_auto_id(self, agent):
        s = AgentSession(agent=agent)
        assert s.id.startswith("sess_")
        assert s.state == SessionState.INITIALIZING

    def test_explicit_id(self, agent):
        s = AgentSession(agent=agent, session_id="my_session")
        assert s.id == "my_session"

    def test_default_config(self, agent):
        s = AgentSession(agent=agent)
        assert s.config.auto_approve is True
        assert s.global_step == 0
        assert len(s.pending_approvals) == 0
        assert len(s.approved_categories) == 0


# ---------------------------------------------------------------------------
# SessionState enum
# ---------------------------------------------------------------------------


class TestSessionState:
    def test_all_states(self):
        states = [s.value for s in SessionState]
        assert len(states) == 6
        assert SessionState.INITIALIZING.value == 1
        assert SessionState.DONE.value == 5

    def test_state_name(self):
        assert SessionState.INITIALIZING.name == "INITIALIZING"


# ---------------------------------------------------------------------------
# AgentEvent v2
# ---------------------------------------------------------------------------


class TestAgentEventV2:
    def test_event_id_auto_generated(self):
        ev = AgentEvent(type="test")
        assert ev.event_id.startswith("evt_")

    def test_event_id_explicit(self):
        ev = AgentEvent(type="test", event_id="custom_123")
        assert ev.event_id == "custom_123"

    def test_event_constants(self):
        assert EVT_SESSION_STARTED == "session_started"
        assert EVT_TASK_STARTED == "task_started"
        assert EVT_DONE == "done"
        assert EVT_TOOL_CALL == "tool_call"
        assert EVT_TOOL_RESULT == "tool_result"
        assert EVT_WARNING == "warning"


# ---------------------------------------------------------------------------
# Approve / Abort
# ---------------------------------------------------------------------------


class TestApproveAbort:
    @pytest.mark.anyio
    async def test_abort_sets_state(self, session):
        assert session.state == SessionState.INITIALIZING
        await session.abort()
        assert session.state == SessionState.ABORTED

    @pytest.mark.anyio
    async def test_approve_unknown_event(self, session):
        result = await session.approve("nonexistent", "allow_once")
        assert result is False

    @pytest.mark.anyio
    async def test_approve_with_future(self, session):
        import asyncio
        fut = asyncio.get_event_loop().create_future()
        session.pending_approvals["evt_123"] = fut

        result = await session.approve("evt_123", "allow_once")
        assert result is True
        assert fut.result() == "allow_once"
        assert "*" not in session.approved_categories

    @pytest.mark.anyio
    async def test_approve_session_adds_category(self, session):
        import asyncio
        fut = asyncio.get_event_loop().create_future()
        session.pending_approvals["evt_456"] = fut

        await session.approve("evt_456", "allow_session")
        assert "*" in session.approved_categories


# ---------------------------------------------------------------------------
# Concurrent Isolation
# ---------------------------------------------------------------------------


class TestConcurrentIsolation:
    def test_two_sessions_independent(self, agent):
        s1 = AgentSession(agent=agent, session_id="s1")
        s2 = AgentSession(agent=agent, session_id="s2")

        s1.global_step = 5
        s1.task_queue.add("task for s1")

        assert s2.global_step == 0
        assert s2.task_queue.total_count == 0
        assert s1.global_step == 5

    def test_approval_isolation(self, agent):
        s1 = AgentSession(agent=agent, session_id="s1")
        s2 = AgentSession(agent=agent, session_id="s2")

        s1.approved_categories.add("write_file")

        assert "write_file" not in s2.approved_categories
        assert "write_file" in s1.approved_categories
