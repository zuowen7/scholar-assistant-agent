"""SSE 适配层 — 将 AgentEvent 转换为前端可见的 SSE 格式。

前端 useAgentChat.ts 只对 `response` 事件更新 msg.content:
  case 'response':
    msg.content = msg.content + data.content

所以把 token/tool_call/tool_result/thought 都映射为 `response` 类型，
让用户能实时看到 Agent 在做什么。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from src.agent_v2.types import AgentEvent, AgentEventType


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:8]}"


def agent_event_to_sse(event: AgentEvent) -> dict[str, Any]:
    """转换为前端 SSE dict: {"type": str, "content": str, "event_id": str}。"""
    t = event.type
    data = event.data
    content = ""

    # ---- 以下事件映射为 `response` 类型，前端会实时更新 msg.content ----
    if t == AgentEventType.TOKEN:
        content = data.get("text", "")
        evt_type = "response"
    elif t == AgentEventType.THOUGHT:
        content = f"\n> {data.get('text', '')}\n"
        evt_type = "response"
    elif t == AgentEventType.TOOL_CALL:
        tool_name = data.get("tool_name", "unknown")
        inp = data.get("input", "")
        # 截断长 input 防止刷屏
        inp_short = inp[:120] + "..." if len(inp) > 120 else inp
        content = f"\n🔧 调用 {tool_name}: {inp_short}\n"
        evt_type = "response"
    elif t == AgentEventType.TOOL_RESULT:
        out = data.get("output", "")
        out_short = out[:200] + "..." if len(out) > 200 else out
        content = f"\n✅ {data.get('tool_name', '')} 完成\n"
        evt_type = "response"
    elif t == AgentEventType.TOOL_DENIED:
        content = f"\n⛔ {data.get('tool_name', '')} 被拒绝: {data.get('reason', '')}\n"
        evt_type = "response"
    elif t == AgentEventType.TOOL_ERROR:
        content = f"\n❌ {data.get('tool_name', '')} 出错: {data.get('output', '')[:200]}\n"
        evt_type = "response"
    elif t == AgentEventType.APPROVAL_RECEIVED:
        content = data.get("decision", "")
        evt_type = "approval_received"
    elif t == AgentEventType.AWAIT_APPROVAL:
        tool_name = data.get("tool_name", "")
        content = f"Agent wants to modify {tool_name}"
        evt_type = "await_approval"
        preview = data.get("preview") or {}
        metadata = {
            "tool_name": tool_name,
            "reason": data.get("reason", ""),
            "risk": "MODERATE",
            "file_path": preview.get("file_path", ""),
            "old_text": preview.get("old_text", ""),
            "new_text": preview.get("new_text", ""),
            "force_approval": True,
        }
        # Use tool_use ID as event_id so frontend can match approval back
        return {"type": evt_type, "content": content, "event_id": data.get("id", _event_id()), "metadata": metadata}

    # ---- 以下保留原始类型 ----
    elif t == AgentEventType.CHECKPOINT:
        content = data.get("content", f"文件 {data.get('file', '')} 已更新")
        evt_type = "checkpoint"
        metadata = {
            "stage": "editing",
            "checkpoint_type": "SLIM",
            "action": data.get("action", ""),
            "file": data.get("file", ""),
            "content": data.get("content", ""),
        }
        return {"type": evt_type, "content": content, "event_id": _event_id(), "metadata": metadata}
    elif t == AgentEventType.SESSION_STARTED:
        content = data.get("session_id", "")
        evt_type = t.value
    elif t == AgentEventType.RESPONSE:
        content = data.get("text", "")
        evt_type = "response"
    elif t == AgentEventType.ERROR:
        content = data.get("message", "")
        evt_type = "error"
    elif t == AgentEventType.DONE:
        content = ""
        evt_type = "done"
    elif t == AgentEventType.ABORTED:
        content = data.get("reason", "")
        evt_type = "aborted"
    else:
        content = json.dumps(data) if data else ""
        evt_type = t.value

    return {
        "type": evt_type,
        "content": content,
        "event_id": _event_id(),
    }


def agent_event_to_sse_stream(event: AgentEvent) -> dict[str, str]:
    """转为 SSE stream dict: {"event": event_type, "data": json_str}。"""
    payload = agent_event_to_sse(event)
    return {
        "event": payload["type"],
        "data": json.dumps(payload, ensure_ascii=False),
    }
