"""Agent V2 核心类型定义。

参考 claw-code:
  - api/types.rs: StreamEvent, ContentBlock, ToolDefinition, MessageRequest/Response
  - runtime/session.rs: ContentBlock, ConversationMessage, MessageRole
  - runtime/conversation.rs: AssistantEvent
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ---------------------------------------------------------------------------
# Message roles
# ---------------------------------------------------------------------------

class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ---------------------------------------------------------------------------
# Content blocks (unified across providers)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class ThinkingBlock:
    thinking: str
    signature: str | None = None


@dataclass(frozen=True)
class ToolUseBlock:
    id: str
    name: str
    input: str  # JSON string


@dataclass(frozen=True)
class ToolResultBlock:
    tool_use_id: str
    tool_name: str
    output: str
    is_error: bool = False


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@dataclass
class Message:
    role: MessageRole
    blocks: list[ContentBlock] = field(default_factory=list)
    usage: TokenUsage | None = None

    def text_content(self) -> str:
        return "".join(b.text for b in self.blocks if isinstance(b, TextBlock))

    def tool_calls(self) -> list[ToolUseBlock]:
        return [b for b in self.blocks if isinstance(b, ToolUseBlock)]


@dataclass
class InputMessage:
    role: MessageRole
    content: str

    @staticmethod
    def user_text(text: str) -> InputMessage:
        return InputMessage(role=MessageRole.USER, content=text)


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
        )


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent events (SSE stream output)
# ---------------------------------------------------------------------------

class AgentEventType(Enum):
    SESSION_STARTED = "session_started"
    TASK_STARTED = "task_started"
    TOKEN = "token"
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_DENIED = "tool_denied"
    TOOL_ERROR = "tool_error"
    AWAIT_APPROVAL = "await_approval"
    APPROVAL_RECEIVED = "approval_received"
    USAGE = "usage"
    RESPONSE = "response"
    ERROR = "error"
    DONE = "done"
    ABORTED = "aborted"
    PIPELINE_STAGE = "pipeline_stage"
    CHECKPOINT = "checkpoint"


@dataclass
class AgentEvent:
    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    # ---- Factory helpers ----

    @staticmethod
    def session_started(session_id: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.SESSION_STARTED, data={"session_id": session_id})

    @staticmethod
    def token(text: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.TOKEN, data={"text": text})

    @staticmethod
    def thought(text: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.THOUGHT, data={"text": text})

    @staticmethod
    def tool_call(id: str, name: str, input_str: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.TOOL_CALL, data={"id": id, "tool_name": name, "input": input_str})

    @staticmethod
    def tool_result(id: str, name: str, output: str, is_error: bool = False) -> AgentEvent:
        evt_type = AgentEventType.TOOL_ERROR if is_error else AgentEventType.TOOL_RESULT
        return AgentEvent(type=evt_type, data={"id": id, "tool_name": name, "output": output})

    @staticmethod
    def tool_denied(id: str, name: str, reason: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.TOOL_DENIED, data={"id": id, "tool_name": name, "reason": reason})

    @staticmethod
    def await_approval(id: str, name: str, reason: str, preview: dict[str, Any] | None = None) -> AgentEvent:
        data: dict[str, Any] = {"id": id, "tool_name": name, "reason": reason}
        if preview:
            data["preview"] = preview
        return AgentEvent(type=AgentEventType.AWAIT_APPROVAL, data=data)

    @staticmethod
    def usage(usage: TokenUsage) -> AgentEvent:
        return AgentEvent(type=AgentEventType.USAGE, data=usage.__dict__)

    @staticmethod
    def response(text: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.RESPONSE, data={"text": text})

    @staticmethod
    def error(message: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.ERROR, data={"message": message})

    @staticmethod
    def approval_received(id: str, decision: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.APPROVAL_RECEIVED, data={"id": id, "decision": decision})

    @staticmethod
    def done() -> AgentEvent:
        return AgentEvent(type=AgentEventType.DONE)

    @staticmethod
    def aborted(reason: str = "Session aborted") -> AgentEvent:
        return AgentEvent(type=AgentEventType.ABORTED, data={"reason": reason})

    @staticmethod
    def pipeline_stage(stage: str) -> AgentEvent:
        return AgentEvent(type=AgentEventType.PIPELINE_STAGE, data={"content": stage})

    @staticmethod
    def checkpoint(data: dict[str, Any] | None = None) -> AgentEvent:
        return AgentEvent(type=AgentEventType.CHECKPOINT, data=data or {})


# ---------------------------------------------------------------------------
# Provider response
# ---------------------------------------------------------------------------

@dataclass
class ProviderResponse:
    blocks: list[ContentBlock] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    stop_reason: str = "end_turn"

    def has_tool_calls(self) -> bool:
        return any(isinstance(b, ToolUseBlock) for b in self.blocks)

    def text_content(self) -> str:
        return "".join(b.text for b in self.blocks if isinstance(b, TextBlock))

    def tool_calls(self) -> list[ToolUseBlock]:
        return [b for b in self.blocks if isinstance(b, ToolUseBlock)]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AgentError(Exception):
    pass


class ApiError(AgentError):
    def __init__(self, message: str, status_code: int = 0, retry_after: float | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class ToolError(AgentError):
    pass
