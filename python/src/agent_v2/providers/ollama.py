"""Native Ollama provider with configurable context and tool streaming."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from src.agent_v2.providers.base import BaseProvider
from src.agent_v2.providers.openai_compat import _api_error_from_response
from src.agent_v2.types import (
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
)
from src.llm_request_policy import normalize_thinking_mode


class OllamaProvider(BaseProvider):
    """Use Ollama's native API so ``num_ctx`` is honored.

    Ollama's OpenAI-compatible endpoint fixes the runtime context at the server
    default (normally 4096 tokens). The native endpoint accepts ``num_ctx`` per
    request and keeps native function calling available for long manuscripts.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        timeout: float = 300.0,
        context_length: int = 32_768,
        thinking_mode: str = "auto",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.model = model
        self.timeout = timeout
        self.context_length = max(4_096, int(context_length))
        self.thinking_mode = normalize_thinking_mode(thinking_mode)
        self.model_max_tokens = 4_096
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        return self._client

    @staticmethod
    def _tool_arguments(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return "{}"

    @staticmethod
    def _tool_argument_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except (json.JSONDecodeError, TypeError):
            return {"input": value}
        return parsed if isinstance(parsed, dict) else {"input": parsed}

    def _build_messages(self, messages: list[Message], system_prompt: str | None) -> list[dict]:
        result: list[dict] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        for message in messages:
            if message.role == MessageRole.USER:
                result.append({"role": "user", "content": message.text_content()})
                continue
            if message.role == MessageRole.ASSISTANT:
                text = message.text_content()
                calls = message.tool_calls()
                if not text and not calls:
                    continue
                entry: dict[str, Any] = {"role": "assistant", "content": text}
                if calls:
                    entry["tool_calls"] = [
                        {
                            "function": {
                                "name": call.name,
                                "arguments": self._tool_argument_object(call.input),
                            }
                        }
                        for call in calls
                    ]
                result.append(entry)
                continue
            if message.role == MessageRole.TOOL:
                for block in message.blocks:
                    if isinstance(block, ToolResultBlock):
                        result.append(
                            {
                                "role": "tool",
                                "content": block.output,
                                "tool_name": block.tool_name,
                            }
                        )
        return result

    @staticmethod
    def _build_tools(tools: list[ToolDefinition] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    def _body(
        self,
        *,
        messages: list[Message],
        tools: list[ToolDefinition] | None,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
        stream: bool,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "stream": stream,
            "options": {
                "num_ctx": self.context_length,
                "num_predict": min(max_tokens, self.model_max_tokens),
                "temperature": temperature,
            },
        }
        built_tools = self._build_tools(tools)
        if built_tools and tool_choice != "none":
            body["tools"] = built_tools
        if self.thinking_mode == "enabled":
            body["think"] = True
        elif self.thinking_mode == "disabled":
            body["think"] = False
        return body

    @classmethod
    def _blocks_from_message(cls, message: dict[str, Any]) -> list:
        blocks: list = []
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking:
            blocks.append(ThinkingBlock(thinking=thinking))
        content = message.get("content")
        if isinstance(content, str) and content:
            blocks.append(TextBlock(text=content))
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            name = str(function.get("name") or "unknown")
            blocks.append(
                ToolUseBlock(
                    id=str(call.get("id") or f"tc_{uuid.uuid4().hex[:8]}"),
                    name=name,
                    input=cls._tool_arguments(function.get("arguments")),
                )
            )
        return blocks

    @classmethod
    def _parse_response(cls, data: dict[str, Any]) -> ProviderResponse:
        blocks = cls._blocks_from_message(data.get("message") or {})
        has_tools = any(isinstance(block, ToolUseBlock) for block in blocks)
        return ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(
                input_tokens=int(data.get("prompt_eval_count") or 0),
                output_tokens=int(data.get("eval_count") or 0),
            ),
            stop_reason="tool_use" if has_tools else "end_turn",
        )

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        tool_choice: str = "auto",
    ) -> ProviderResponse:
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/api/chat",
            json=self._body(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
                tool_choice=tool_choice,
            ),
        )
        if response.is_error:
            raise _api_error_from_response(response)
        return self._parse_response(response.json())

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncGenerator[ProviderResponse | TokenUsage, None]:
        client = await self._get_client()
        body = self._body(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        blocks: list = []
        finished = False
        usage = TokenUsage()
        async with client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
            if response.is_error:
                await response.aread()
                raise _api_error_from_response(response)
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise ApiError(str(chunk["error"]), status_code=502)
                message = chunk.get("message") or {}
                for block in self._blocks_from_message(message):
                    blocks.append(block)
                    yield block
                if chunk.get("done"):
                    finished = True
                    usage = TokenUsage(
                        input_tokens=int(chunk.get("prompt_eval_count") or 0),
                        output_tokens=int(chunk.get("eval_count") or 0),
                    )
                    if usage.total() > 0:
                        yield usage
                    break
        if not finished:
            raise ApiError(
                "Ollama stream ended before the completion marker",
                status_code=0,
            )
        has_tools = any(isinstance(block, ToolUseBlock) for block in blocks)
        yield ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(),
            stop_reason="tool_use" if has_tools else "end_turn",
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
