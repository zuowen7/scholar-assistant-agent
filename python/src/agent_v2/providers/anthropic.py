"""Anthropic Messages API Provider。

通过 Anthropic 格式发请求给兼容的 provider（如 DeepSeek）。
参考 claw-code api/providers/anthropic.rs + cc-switch anthropic_to_openai 转换。

Anthropic 格式与 OpenAI 的关键差异:
  - system: 顶层字段（不在 messages 里）
  - messages: content 是数组 [{type, text/tool_use/tool_result}]
  - tools: 不带 "type": "function" 包装
  - tool_use: name + input (input 是 JSON object，不是 JSON string)
  - tool_result: role="user", content=[{type:"tool_result", tool_use_id, content}]
  - stop_reason: "end_turn" | "tool_use"
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from src.agent_v2.providers.base import BaseProvider
from src.agent_v2.types import (
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    TokenUsage,
    ToolDefinition,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Anthropic Messages API provider。

    用于发送 Anthropic 格式请求到兼容的 provider（DeepSeek 等）。
    在 Anthropic 格式下，DeepSeek 的工具调用比 OpenAI 格式更可靠。
    """

    def __init__(
        self,
        base_url: str = "https://api.anthropic.com",
        api_key: str = "",
        model: str = "claude-sonnet-4-6",
        timeout: float = 300.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self.model_max_tokens = 8192  # Anthropic models support 8K

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    # ---- Message conversion ----

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        """转换为 Anthropic Messages 格式。"""
        result = []
        for msg in messages:
            if msg.role == MessageRole.USER:
                text = msg.text_content()
                result.append({"role": "user", "content": [{"type": "text", "text": text}]})
            elif msg.role == MessageRole.ASSISTANT:
                blocks = []
                for b in msg.blocks:
                    if isinstance(b, TextBlock) and b.text.strip():
                        blocks.append({"type": "text", "text": b.text})
                    elif isinstance(b, ToolUseBlock):
                        try:
                            inp = json.loads(b.input)
                        except (json.JSONDecodeError, TypeError):
                            inp = {"input": b.input}
                        blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": inp})
                if blocks:
                    result.append({"role": "assistant", "content": blocks})
            elif msg.role == MessageRole.TOOL:
                from src.agent_v2.types import ToolResultBlock
                for b in msg.blocks:
                    if isinstance(b, ToolResultBlock):
                        result.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": b.tool_use_id,
                                "content": b.output,
                            }],
                        })
        return result

    def _build_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        """转换为 Anthropic 工具格式（无 type:function 包装）。"""
        if not tools:
            return None
        return [{
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        } for t in tools]

    # ---- API call ----

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        tool_choice: str = "auto",
    ) -> ProviderResponse:
        """非流式 Anthropic Messages API 调用。"""
        client = await self._get_client()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": min(max_tokens, self.model_max_tokens),
        }
        if system_prompt:
            body["system"] = system_prompt
        built_tools = self._build_tools(tools)
        if built_tools:
            body["tools"] = built_tools

        url = f"{self.base_url}/messages"
        if not url.startswith("http"):
            url = f"https://{url}" if "api" in url else f"https://api.anthropic.com/v1/messages"

        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        return self._parse_response(data)

    def _parse_response(self, data: dict) -> ProviderResponse:
        """解析 Anthropic Messages 响应。"""
        blocks = []
        stop_reason = data.get("stop_reason", "end_turn")
        usage_data = data.get("usage", {})

        for block in data.get("content", []):
            t = block.get("type", "")
            if t == "text":
                blocks.append(TextBlock(text=block.get("text", "")))
            elif t == "tool_use":
                inp = block.get("input", {})
                inp_str = json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else str(inp)
                blocks.append(ToolUseBlock(
                    id=block.get("id", f"tu_{uuid.uuid4().hex[:8]}"),
                    name=block.get("name", "unknown"),
                    input=inp_str,
                ))
            elif t == "thinking":
                pass  # thinking is metadata, not content

        return ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
            ),
            stop_reason="tool_use" if stop_reason == "tool_use" else "end_turn",
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
