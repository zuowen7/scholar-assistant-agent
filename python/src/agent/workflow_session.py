"""WorkflowSession — multi-turn workflow session with pipeline stage tracking.

A WorkflowSession spans multiple user messages, maintaining conversation
history server-side and tracking which pipeline stage the user is in.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.agent.models import Message


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------

class WorkflowState(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    ARCHIVED = "archived"


PIPELINE_STAGES = ("research", "outline", "draft", "review", "revise", "finalize")


@dataclass
class WorkflowCheckpoint:
    """Checkpoint emitted at stage boundaries."""
    stage: str
    title: str = ""
    deliverables: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    requires_confirmation: bool = True  # MANDATORY vs SLIM


# ---------------------------------------------------------------------------
# WorkflowSession
# ---------------------------------------------------------------------------

class WorkflowSession:
    def __init__(
        self,
        workflow_id: str | None = None,
        workspace_root: str | None = None,
    ) -> None:
        self.id = workflow_id or f"wf_{uuid.uuid4().hex[:8]}"
        self.state = WorkflowState.ACTIVE
        self.title = ""
        self.stages: list[dict[str, Any]] = []
        self.current_stage = ""
        self.messages: list[Message] = []
        self.workspace_root = workspace_root
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.updated_at = self.created_at
        self.archived_at: str | None = None
        self._compressed_messages: list[dict[str, str]] | None = None

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, message: Message) -> None:
        """Append a message to the workflow history."""
        self.messages.append(message)
        self.updated_at = datetime.now().isoformat(timespec="seconds")

        # Set title from first user message
        if not self.title and message.role == "user" and message.content:
            self.title = message.content.strip()[:50]

    # ------------------------------------------------------------------
    # Stage tracking
    # ------------------------------------------------------------------

    def advance_to(self, stage: str) -> WorkflowCheckpoint | None:
        """Advance to a new pipeline stage. Returns checkpoint if valid transition."""
        if stage not in PIPELINE_STAGES:
            return None

        old_stage = self.current_stage

        # Record completion of previous stage
        if old_stage and old_stage not in (s["name"] for s in self.stages):
            self.stages.append({
                "name": old_stage,
                "entered_at": self.updated_at,
                "status": "completed",
            })

        # Enter new stage
        self.current_stage = stage
        self.stages.append({
            "name": stage,
            "entered_at": datetime.now().isoformat(timespec="seconds"),
            "status": "active",
        })
        self.updated_at = datetime.now().isoformat(timespec="seconds")

        # Generate checkpoint
        checkpoint_number = len([s for s in self.stages if s["status"] == "completed"])
        return WorkflowCheckpoint(
            stage=stage,
            title=f"Stage {checkpoint_number + 1}: {stage.upper()}",
            deliverables=[],
            metrics={"messages": len(self.messages)},
            requires_confirmation=True,
        )

    # ------------------------------------------------------------------
    # Archive
    # ------------------------------------------------------------------

    def archive(self) -> None:
        """Compress messages and mark as ARCHIVED."""
        self.state = WorkflowState.ARCHIVED
        self.archived_at = datetime.now().isoformat(timespec="seconds")

        # Compress: keep user/assistant, discard tool messages, truncate long content
        self._compressed_messages = []
        for msg in self.messages:
            if msg.role in ("user", "assistant"):
                content = msg.content[:500] if msg.content else ""
                self._compressed_messages.append({
                    "role": msg.role,
                    "content": content,
                })

        self.updated_at = datetime.now().isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a storable dict.

        When archived, uses compressed messages to save space.
        """
        if self._compressed_messages is not None:
            messages_data = self._compressed_messages
        else:
            messages_data = []
            for m in self.messages:
                md: dict = {"role": m.role, "content": m.content}
                if m.tool_calls:
                    md["tool_calls"] = [
                        {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                        for tc in m.tool_calls
                    ]
                if m.tool_call_id:
                    md["tool_call_id"] = m.tool_call_id
                messages_data.append(md)

        result: dict[str, Any] = {
            "id": self.id,
            "state": self.state.value,
            "title": self.title,
            "stages": self.stages,
            "current_stage": self.current_stage,
            "messages": messages_data,
            "workspace_root": self.workspace_root,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived_at": self.archived_at,
        }
        # Only include _compressed_messages if NOT already represented in messages
        if self._compressed_messages is None:
            result["_compressed_messages"] = None
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowSession":
        """Restore from a serialized dict."""
        from src.agent.models import ToolCall

        ws = cls(
            workflow_id=data["id"],
            workspace_root=data.get("workspace_root"),
        )
        state_val = data.get("state") or "active"
        ws.state = WorkflowState(state_val)
        ws.title = data.get("title", "")
        ws.stages = data.get("stages", [])
        ws.current_stage = data.get("current_stage", "")

        messages = []
        for m in (data.get("messages") or []):
            tool_calls = None
            tc_list = m.get("tool_calls")
            if tc_list:
                tool_calls = [ToolCall(**tc) for tc in tc_list]
            messages.append(Message(
                role=m["role"],
                content=m.get("content", ""),
                tool_calls=tool_calls,
                tool_call_id=m.get("tool_call_id"),
            ))
        ws.messages = messages
        ws.created_at = data.get("created_at", ws.created_at)
        ws.updated_at = data.get("updated_at", ws.updated_at)
        ws.archived_at = data.get("archived_at")
        ws._compressed_messages = data.get("_compressed_messages") if "_compressed_messages" in data else None

        return ws
