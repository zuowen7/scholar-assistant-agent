"""Shared helpers for LLM client backends.

Message conversion, response normalization, token usage tracking.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

import httpx

from src.agent.models import Message, ToolCall

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _safe_response_text(response: httpx.Response) -> str:
    try:
        await response.aread()
        return response.text[:500]
    except Exception:
        return "<response body not available>"


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------

def messages_to_openai(messages: list[Message]) -> list[dict]:
    """Convert Message list to OpenAI-compatible dict list."""
    out: list[dict] = []
    for m in messages:
        content_val: str | None = m.content if m.content else (None if m.tool_calls else m.content)
        d: dict = {"role": m.role, "content": content_val}
        if m.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
        if m.tool_call_id is not None:
            d["tool_call_id"] = m.tool_call_id
        out.append(d)
    return out


def messages_to_anthropic(
    messages: list[Message], system_prompt: str = "",
) -> tuple[str, list[dict]]:
    """Convert Message list to Anthropic Messages API format.

    Returns (system_text, anthropic_messages).
    """
    system_text = system_prompt
    anthropic_msgs: list[dict] = []
    for msg in messages:
        if msg.role == "system":
            if msg.content:
                system_text = (system_text + "\n\n" + msg.content).strip() if system_text else msg.content
            continue
        if msg.role == "tool" and msg.tool_call_id:
            anthropic_msgs.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content,
                }],
            })
            continue
        if msg.role == "assistant" and msg.tool_calls:
            blocks: list[dict] = []
            if msg.content:
                blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            anthropic_msgs.append({"role": "assistant", "content": blocks})
            continue
        if msg.content:
            anthropic_msgs.append({"role": msg.role, "content": msg.content})
    return system_text, anthropic_msgs


def _ollama_tools_to_anthropic(ollama_tools: list[dict]) -> list[dict]:
    return [
        {
            "name": t.get("function", {}).get("name", ""),
            "description": t.get("function", {}).get("description", ""),
            "input_schema": t.get("function", {}).get("parameters", {"type": "object", "properties": {}}),
        }
        for t in ollama_tools
    ]


# ---------------------------------------------------------------------------
# Response normalization
# ---------------------------------------------------------------------------

def _normalize_cloud_response(data: dict) -> dict:
    """Normalize OpenAI response -> Ollama format."""
    choice = data.get("choices", [{}])[0]
    openai_msg = choice.get("message", {})
    normalized_tool_calls = []
    for tc in (openai_msg.get("tool_calls") or []):
        func = tc.get("function", {})
        raw_args = func.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"raw_input": raw_args}
        else:
            args = raw_args if isinstance(raw_args, dict) else {}
        normalized_tool_calls.append({
            "id": tc.get("id", str(uuid.uuid4())[:8]),
            "function": {"name": func.get("name", ""), "arguments": args},
        })
    result = {
        "message": {
            "role": openai_msg.get("role", "assistant"),
            "content": openai_msg.get("content", ""),
        }
    }
    rc = openai_msg.get("reasoning_content")
    if rc:
        result["message"]["reasoning_content"] = rc
    if normalized_tool_calls:
        result["message"]["tool_calls"] = normalized_tool_calls
    return result


def _normalize_anthropic_response(data: dict) -> dict:
    """Normalize Anthropic response -> Ollama format."""
    text_parts: list[str] = []
    normalized_tool_calls = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            normalized_tool_calls.append({
                "id": block.get("id", str(uuid.uuid4())[:8]),
                "function": {
                    "name": block.get("name", ""),
                    "arguments": block.get("input", {}),
                },
            })
    return {
        "message": {
            "role": "assistant",
            "content": "".join(text_parts),
            **({"tool_calls": normalized_tool_calls} if normalized_tool_calls else {}),
        }
    }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_text_content(response: dict) -> str:
    return (response.get("message") or {}).get("content", "").strip()


def extract_tool_calls(response: dict) -> list[ToolCall]:
    """Extract tool calls from normalized (Ollama-format) response.

    Three strategies:
    1. Native tool_calls in message
    2. Text ReAct parsing (Action/Action Input)
    3. Anthropic tool_use field
    """
    tool_calls: list[ToolCall] = []
    message = response.get("message", {})

    for call in message.get("tool_calls", []):
        func = call.get("function", {})
        name = func.get("name", "")
        arguments = func.get("arguments", {})
        if not name:
            continue
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"raw_input": arguments}
        tool_calls.append(ToolCall(
            id=call.get("id") or str(uuid.uuid4())[:8],
            name=name,
            arguments=arguments if isinstance(arguments, dict) else {},
        ))

    if not tool_calls:
        tool_use = message.get("tool_use")
        if tool_use and isinstance(tool_use, dict):
            name = tool_use.get("name", "")
            raw_input = tool_use.get("input", {})
            if isinstance(raw_input, str):
                try:
                    raw_input = json.loads(raw_input)
                except json.JSONDecodeError:
                    raw_input = {"raw_input": raw_input}
            if name:
                tool_calls.append(ToolCall(
                    id=tool_use.get("id") or str(uuid.uuid4())[:8],
                    name=name,
                    arguments=raw_input if isinstance(raw_input, dict) else {},
                ))

    return tool_calls


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------

@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0

    def accumulate(self, response: dict) -> None:
        eval_count = response.get("eval_count") or 0
        prompt_eval = response.get("prompt_eval_count")
        if eval_count:
            self.completion_tokens += eval_count
        if prompt_eval:
            self.prompt_tokens += prompt_eval
        usage = response.get("usage")
        if isinstance(usage, dict) and "prompt_tokens" in usage:
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
        elif isinstance(usage, dict) and "input_tokens" in usage:
            self.prompt_tokens += usage.get("input_tokens", 0)
            self.completion_tokens += usage.get("output_tokens", 0)
        self.total_tokens = self.prompt_tokens + self.completion_tokens
        self.llm_calls += 1

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
        }
