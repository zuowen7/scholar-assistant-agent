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


def _max_tokens_for_model(model: str) -> int:
    """参考 claw-code max_tokens_for_model: 每个模型不同上限。"""
    m = model.lower()
    if "claude" in m:
        return 8192
    if "gpt-4" in m or "gpt-4o" in m:
        return 16384
    if "deepseek" in m:
        return 8192
    if "qwen" in m or "llama" in m:
        return 4096
    return 4096
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
    """OpenAI-compatible Chat Completions provider with real streaming.

    Per-provider quirks auto-detected from model name / base URL.
    """

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
        from src.agent_v2.providers.quirks import detect_quirks
        self.quirks = detect_quirks(model, base_url)
        self.model_max_tokens = _max_tokens_for_model(model)

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
                text = msg.text_content()
                tool_calls = msg.tool_calls()
                if text or tool_calls:
                    entry: dict[str, Any] = {"role": "assistant"}
                    # Always include content key, even if null (matches claw-code)
                    entry["content"] = text if text else None
                    if tool_calls:
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
                        entry["tool_calls"] = tc_list
                    result.append(entry)
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
        tool_choice: str = "auto",
    ) -> ProviderResponse:
        """非流式调用。tool_choice: 'auto' | 'required' | 'none'"""
        client = await self._get_client()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "max_tokens": min(max_tokens, self.model_max_tokens),
            "temperature": temperature,
            "stream": False,
        }
        built_tools = self._build_tools(tools)
        if built_tools:
            body["tools"] = built_tools
            # Only set tool_choice if explicitly requested (not "auto" default)
            if tool_choice != "auto":
                body["tool_choice"] = tool_choice

        resp = await client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        finish = data.get("choices", [{}])[0].get("finish_reason", "?")
        tc_count = len(data.get("choices", [{}])[0].get("message", {}).get("tool_calls") or [])
        text_len = len(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
        logger.info("chat response: finish=%s, tool_calls=%d, text_len=%d, model=%s, msgs=%d, tools=%d",
                     finish, tc_count, text_len, data.get("model", "?"), len(messages), len(tools or []))
        if tc_count == 0 and finish == "stop" and tools:
            logger.warning("DeepSeek text-only response with %d tools available. "
                           "Last user msg: %s...",
                           len(tools),
                           (messages[-1].text_content() if messages else "")[:200])
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
            "max_tokens": min(max_tokens, self.model_max_tokens),
            "temperature": temperature,
            "stream": True,
        }
        if self.quirks.supports_stream_options:
            body["stream_options"] = {"include_usage": True}
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
