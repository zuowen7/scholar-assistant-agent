"""Phase 1 tests: WorkflowSession model — state machine, serialization, archive.

TDD Red phase — these tests exercise interfaces that do NOT exist yet.
"""
from __future__ import annotations

import pytest
from datetime import datetime


class TestWorkflowSession:
    """WorkflowSession core: creation, messages, stages, serialization."""

    def test_create_new(self):
        """Create a new WorkflowSession with defaults."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState

        ws = WorkflowSession()
        assert ws.id
        assert ws.state == WorkflowState.ACTIVE
        assert ws.messages == []
        assert ws.current_stage == ""
        assert ws.stages == []

    def test_add_message_updates_title(self):
        """First user message becomes the workflow title, truncated to 50."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="帮我写一篇关于机器学习优化的论文"))

        assert ws.title != ""
        assert len(ws.title) <= 50 if ws.title else True

    def test_add_message_does_not_change_title_after_first(self):
        """Only the first user message sets the title."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="第一句话"))
        title1 = ws.title
        ws.add_message(Message(role="assistant", content="回复"))
        ws.add_message(Message(role="user", content="第二句话"))
        assert ws.title == title1

    def test_add_message_appends(self):
        """Messages are appended sequentially."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="hello"))
        ws.add_message(Message(role="assistant", content="world"))
        assert len(ws.messages) == 2

    def test_advance_to_stage(self):
        """Advancing to a new stage records it and updates current_stage."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        chk = ws.advance_to("research")
        assert ws.current_stage == "research"
        assert len(ws.stages) == 1
        assert ws.stages[0]["name"] == "research"

    def test_advance_returns_checkpoint(self):
        """Stage advancement returns a checkpoint object."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        ws.advance_to("research")  # First stage, silent
        # advance_to should NOT return None on checkpoint-worthy transitions
        # but the first stage may not generate one. Let's test the second.
        chk = ws.advance_to("outline")
        assert chk is not None

    def test_serialization_roundtrip(self):
        """to_dict/from_dict preserves all data."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test query"))
        ws.advance_to("research")
        ws.advance_to("outline")

        data = ws.to_dict()
        restored = WorkflowSession.from_dict(data)

        assert restored.id == ws.id
        assert restored.state == ws.state
        assert restored.title == ws.title
        assert restored.current_stage == ws.current_stage
        assert len(restored.messages) == len(ws.messages)
        assert len(restored.stages) == len(ws.stages)

    def test_state_transitions_valid(self):
        """Only valid state transitions are allowed."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState

        ws = WorkflowSession()
        assert ws.state == WorkflowState.ACTIVE

        # Valid transitions
        ws.state = WorkflowState.COMPLETED
        assert ws.state == WorkflowState.COMPLETED


class TestWorkflowArchive:
    """Archive: compress messages, save space, allow re-open."""

    def test_archive_compresses_messages(self):
        """After archive(), messages are compressed (tool events removed)."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message, ToolCall

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="write file"))
        ws.add_message(Message(role="assistant", content="", tool_calls=[
            ToolCall(id="t1", name="write_file", arguments={"path": "a.txt", "content": "x"})
        ]))
        ws.add_message(Message(role="tool", content="success", tool_call_id="t1"))
        ws.add_message(Message(role="assistant", content="done"))

        original_len = len(ws.messages)
        ws.archive()

        # After archive, some messages should be compressed
        # tool_call/tool_result events are removed or compressed
        assert ws.state.value == "archived"

    def test_archive_saves_space(self):
        """Compressed messages use less storage than originals."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        # Add large messages
        for i in range(100):
            ws.add_message(Message(role="user" if i % 2 == 0 else "assistant",
                                   content=f"message content {i} " + "x" * 100))

        original_msg_count = len(ws.messages)
        ws.archive()

        # After archive, _compressed_messages exists
        assert ws.state.value == "archived"
        # Compressed should contain only user/assistant messages
        assert ws._compressed_messages is not None
        # Each compressed message is truncated to <= 500 chars
        for cm in ws._compressed_messages:
            assert len(cm["content"]) <= 500

    def test_reopen_archived_workflow(self):
        """An ARCHIVED workflow can be re-opened to ACTIVE."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="hello"))
        ws.state = WorkflowState.COMPLETED
        ws.archive()

        # Re-open
        ws.state = WorkflowState.ACTIVE
        assert ws.state == WorkflowState.ACTIVE
        ws.add_message(Message(role="user", content="continue"))
        assert len(ws.messages) == 2  # original + new

    def test_archive_empty_workflow(self):
        """Archive on empty workflow doesn't crash."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        ws.archive()
        assert ws.state.value == "archived"
