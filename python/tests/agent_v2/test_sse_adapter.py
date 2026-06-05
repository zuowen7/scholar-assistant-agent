"""SSE adapter tests — verify frontend-compatible event format."""
from __future__ import annotations

import json

from src.agent_v2.sse_adapter import agent_event_to_sse, agent_event_to_sse_stream
from src.agent_v2.types import AgentEvent, AgentEventType


class TestAdapter:

    def test_token_maps_to_response(self):
        """token → response 类型，前端实时显示流式文本"""
        event = AgentEvent(type=AgentEventType.TOKEN, data={"text": "hello"})
        result = agent_event_to_sse(event)
        assert result["type"] == "response"
        assert result["content"] == "hello"

    def test_tool_call_maps_to_response(self):
        """tool_call → response 类型，前端看到调用状态"""
        event = AgentEvent(type=AgentEventType.TOOL_CALL, data={
            "id": "t1", "tool_name": "read_file", "input": '{"file_path":"a.md"}',
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "response"
        assert "read_file" in result["content"]

    def test_tool_result_maps_to_response(self):
        event = AgentEvent(type=AgentEventType.TOOL_RESULT, data={
            "id": "t1", "tool_name": "read_file", "output": "file content",
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "response"
        assert "read_file" in result["content"]

    def test_tool_error_maps_to_response(self):
        event = AgentEvent(type=AgentEventType.TOOL_ERROR, data={
            "id": "t1", "tool_name": "read_file", "output": "not found",
        })
        result = agent_event_to_sse(event)
        assert result["type"] == "response"

    def test_thought_maps_to_response(self):
        event = AgentEvent(type=AgentEventType.THOUGHT, data={"text": "thinking..."})
        result = agent_event_to_sse(event)
        assert result["type"] == "response"

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
        assert result["event"] == "response"
        parsed = json.loads(result["data"])
        assert parsed["type"] == "response"
        assert parsed["content"] == "hi"

    def test_unique_event_ids(self):
        e1 = AgentEvent(type=AgentEventType.TOKEN, data={"text": "a"})
        e2 = AgentEvent(type=AgentEventType.TOKEN, data={"text": "b"})
        r1 = agent_event_to_sse(e1)
        r2 = agent_event_to_sse(e2)
        assert r1["event_id"] != r2["event_id"]
