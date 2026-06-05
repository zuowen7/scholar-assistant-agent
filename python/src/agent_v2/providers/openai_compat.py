"""OpenAI-compatible Provider（含真流式 SSE）。

Covers: OpenAI, Ollama, DeepSeek, Groq, and 17+ other providers.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator

import logging

import httpx

from src.agent_v2.providers.base import BaseProvider

logger = logging.getLogger(__name__)
from src.agent_v2.types import (
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolDefinition,
    ToolUseBlock,
)


class OpenAiCompatProvider(BaseProvider):
    """OpenAI-compatible Chat Completions provider with real streaming."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    def _build_messages(self, messages: list[Message], system_prompt: str | None) -> list[dict]:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for msg in messages:
            if msg.role == MessageRole.USER:
                result.append({"role": "user", "content": msg.text_content()})
            elif msg.role == MessageRole.ASSISTANT:
                content: Any = msg.text_content() or None
                tool_calls = msg.tool_calls()
                if tool_calls:
                    content = None
                    tc_list = []
                    for tc in tool_calls:
                        args = tc.input
                        try:
                            json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = json.dumps({"input": args})
                        tc_list.append({
                            "id": tc.id, "type": "function",
                            "function": {"name": tc.name, "arguments": args},
                        })
                    result.append({"role": "assistant", "content": content, "tool_calls": tc_list})
                elif content:
                    result.append({"role": "assistant", "content": content})
            elif msg.role == MessageRole.TOOL:
                from src.agent_v2.types import ToolResultBlock
                for b in msg.blocks:
                    if isinstance(b, ToolResultBlock):
                        result.append({
                            "role": "tool",
                            "tool_call_id": b.tool_use_id,
                            "content": b.output,
                        })
        return result

    def _build_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        if not tools:
            return None
        return [{
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        } for t in tools]

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        """非流式调用（兼容旧接口）。"""
        client = await self._get_client()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        built_tools = self._build_tools(tools)
        if built_tools:
            body["tools"] = built_tools
            body["tool_choice"] = "auto"

        resp = await client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        logger.info("chat response: finish=%s, tool_calls=%d, text_len=%d",
                     data.get("choices", [{}])[0].get("finish_reason", "?"),
                     len(data.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []),
                     len(data.get("choices", [{}])[0].get("message", {}).get("content") or ""))
        return self._parse_response(data)

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncGenerator[ProviderResponse | TokenUsage, None]:
        """真流式 — 每个 token 立即产出，参考 claw-code stream_message。"""
        client = await self._get_client()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            # stream_options 是 OpenAI 扩展，部分 provider（DeepSeek 等）不支持
            # "stream_options": {"include_usage": True},
        }
        built_tools = self._build_tools(tools)
        if built_tools:
            body["tools"] = built_tools

        # --- Streaming state machine ---
        blocks: list = []  # accumulated blocks
        tc_map: dict[int, dict] = {}  # index → {id, name, args}
        finish_reason = "stop"
        text_buf = ""

        async with client.stream("POST", f"{self.base_url}/chat/completions", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    # Some providers send usage-only chunks with empty choices
                    usage_data = chunk.get("usage")
                    if usage_data:
                        yield TokenUsage(
                            input_tokens=usage_data.get("prompt_tokens", 0),
                            output_tokens=usage_data.get("completion_tokens", 0),
                        )
                    continue
                choice = choices[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")
                if finish:
                    finish_reason = finish

                # Text delta → yield immediately
                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_buf += content
                    blocks.append(TextBlock(text=content))
                    yield TextBlock(text=content)

                # Reasoning delta
                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    yield ThinkingBlock(thinking=reasoning)

                # Tool call accumulation (streamed incrementally)
                tc_deltas = delta.get("tool_calls") or []
                for tc in tc_deltas:
                    idx = tc.get("index", 0)
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "args": ""}
                    if "id" in tc and tc["id"]:
                        tc_map[idx]["id"] = tc["id"]
                    func = tc.get("function", {})
                    if "name" in func and func["name"]:
                        tc_map[idx]["name"] = func["name"]
                    if "arguments" in func:
                        tc_map[idx]["args"] += func["arguments"]

                # Final usage
                usage_data = chunk.get("usage")
                if usage_data:
                    yield TokenUsage(
                        input_tokens=usage_data.get("prompt_tokens", 0),
                        output_tokens=usage_data.get("completion_tokens", 0),
                    )

        # Build tool call blocks
        for idx in sorted(tc_map.keys()):
            tc = tc_map[idx]
            if tc["name"]:
                blocks.append(ToolUseBlock(id=tc["id"] or f"tc_{uuid.uuid4().hex[:8]}",
                                            name=tc["name"], input=tc["args"] or "{}"))

        # Yield final assembled response
        yield ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(),  # usage already yielded separately
            stop_reason="tool_use" if tc_map else "end_turn",
        )

    def _parse_response(self, data: dict) -> ProviderResponse:
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason", "stop")
        usage_data = data.get("usage", {})

        blocks = []
        tc_list = msg.get("tool_calls") or []
        for tc in tc_list:
            func = tc.get("function", {})
            blocks.append(ToolUseBlock(
                id=tc.get("id", f"tc_{uuid.uuid4().hex[:8]}"),
                name=func.get("name", "unknown"),
                input=func.get("arguments", "{}"),
            ))
        text = msg.get("content", "")
        if isinstance(text, str) and text:
            reasoning = msg.get("reasoning_content") or ""
            if reasoning:
                blocks.append(ThinkingBlock(thinking=reasoning))
            blocks.append(TextBlock(text=text))

        return ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
            ),
            stop_reason="tool_use" if finish == "tool_calls" else "end_turn",
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
