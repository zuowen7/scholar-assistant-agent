"""SSE adapter tests — verify frontend-compatible event format."""
from __future__ import annotations

import json

from src.agent_v2.sse_adapter import agent_event_to_sse, agent_event_to_sse_stream
from src.agent_v2.types import AgentEvent, AgentEventType


class TestAdapter:

    def test_token_uses_token_type(self):
        """token → token 类型，前端累加到 msg.content 实现流式显示"""
        event = AgentEvent(type=AgentEventType.TOKEN, data={"text": "hello"})
        result = agent_event_to_sse(event)
        assert result["type"] == "token"
        assert result["content"] == "hello"

    def test_tool_call_uses_tool_call_type(self):
        """tool_call → tool_call 类型，前端渲染为工具调用事件"""
        event = AgentEvent(type=AgentEventType.TOOL_CALL, data={
            "id": "t1", "tool_name": "read_file", "input": '{"file_path":"a.md"}',
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "tool_call"
        assert "read_file" in result["content"]

    def test_tool_result_uses_tool_result_type(self):
        event = AgentEvent(type=AgentEventType.TOOL_RESULT, data={
            "id": "t1", "tool_name": "read_file", "output": "file content",
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "tool_result"
        assert "file content" in result["content"]

    def test_tool_error_uses_tool_error_type(self):
        event = AgentEvent(type=AgentEventType.TOOL_ERROR, data={
            "id": "t1", "tool_name": "read_file", "output": "not found",
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "tool_error"

    def test_thought_uses_thought_type(self):
        event = AgentEvent(type=AgentEventType.THOUGHT, data={"text": "thinking..."})
        result = agent_event_to_sse(event)
        assert result["type"] == "thought"

    def test_response_stays_response(self):
        event = AgentEvent(type=AgentEventType.RESPONSE, data={"text": "final answer"})
        result = agent_event_to_sse(event)
        assert result["type"] == "response"
        assert result["content"] == "final answer"

    def test_error_stays_error(self):
        event = AgentEvent(type=AgentEventType.ERROR, data={"message": "fail"})
        result = agent_event_to_sse(event)
        assert result["type"] == "error"

    def test_done_stays_done(self):
        event = AgentEvent(type=AgentEventType.DONE)
        result = agent_event_to_sse(event)
        assert result["type"] == "done"

    def test_aborted_stays_aborted(self):
        event = AgentEvent(type=AgentEventType.ABORTED, data={"reason": "cancelled"})
        result = agent_event_to_sse(event)
        assert result["type"] == "aborted"

    def test_sse_stream_format(self):
        event = AgentEvent(type=AgentEventType.TOKEN, data={"text": "hi"})
        result = agent_event_to_sse_stream(event)
        assert result["event"] == "token"
        parsed = json.loads(result["data"])
        assert parsed["type"] == "token"
        assert parsed["content"] == "hi"

    def test_unique_event_ids(self):
        e1 = AgentEvent(type=AgentEventType.TOKEN, data={"text": "a"})
        e2 = AgentEvent(type=AgentEventType.TOKEN, data={"text": "b"})
        r1 = agent_event_to_sse(e1)
        r2 = agent_event_to_sse(e2)
        assert r1["event_id"] != r2["event_id"]

    def test_await_approval_preserves_metadata(self):
        event = AgentEvent(type=AgentEventType.AWAIT_APPROVAL, data={
            "id": "appr_1", "tool_name": "write_file", "reason": "modify draft",
            "preview": {"file_path": "test.md", "old_text": "a", "new_text": "b"},
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "await_approval"
        assert result["metadata"]["tool_name"] == "write_file"
        assert result["metadata"]["file_path"] == "test.md"

    def test_checkpoint_preserves_metadata(self):
        event = AgentEvent(type=AgentEventType.CHECKPOINT, data={
            "action": "write_file", "file": "test.md", "content": "updated",
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "checkpoint"
        assert result["metadata"]["file"] == "test.md"
