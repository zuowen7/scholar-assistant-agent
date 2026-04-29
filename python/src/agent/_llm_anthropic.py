"""Anthropic Messages API backend for LLMClient."""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

import httpx

from src.agent._llm_helpers import (
    _normalize_anthropic_response,
    _ollama_tools_to_anthropic,
    _safe_response_text,
    messages_to_anthropic,
)


class AnthropicMixin:
    """Provides _call_anthropic and _stream_anthropic for LLMClient."""

    async def _call_anthropic(
        self, messages, tools: list[dict] | None,
    ) -> dict:
        client = await self._get_http_client()  # type: ignore[attr-defined]
        system_text, anthropic_msgs = messages_to_anthropic(
            messages, self.system_prompt,  # type: ignore[attr-defined]
        )
        payload: dict = {
            "model": self.effective_model,  # type: ignore[attr-defined]
            "max_tokens": self.num_predict,  # type: ignore[attr-defined]
            "messages": anthropic_msgs,
        }
        if system_text:
            payload["system"] = system_text
        if tools:
            payload["tools"] = _ollama_tools_to_anthropic(tools)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,  # type: ignore[attr-defined]
            "anthropic-version": "2023-06-01",
        }

        try:
            resp = await client.post(
                f"{self.cloud_base_url}/v1/messages",  # type: ignore[attr-defined]
                json=payload, headers=headers,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Anthropic API ({self.cloud_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"Anthropic API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Anthropic API 请求超时 ({self.timeout}s)"  # type: ignore[attr-defined]
            ) from e

        return _normalize_anthropic_response(resp.json())

    async def _stream_anthropic(
        self, messages, tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()  # type: ignore[attr-defined]
        system_text, anthropic_msgs = messages_to_anthropic(
            messages, self.system_prompt,  # type: ignore[attr-defined]
        )
        payload: dict = {
            "model": self.effective_model,  # type: ignore[attr-defined]
            "max_tokens": self.num_predict,  # type: ignore[attr-defined]
            "messages": anthropic_msgs,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text
        if tools:
            payload["tools"] = _ollama_tools_to_anthropic(tools)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,  # type: ignore[attr-defined]
            "anthropic-version": "2023-06-01",
        }

        full_content = ""
        tool_use_blocks: dict[int, dict] = {}

        try:
            async with client.stream(
                "POST",
                f"{self.cloud_base_url}/v1/messages",  # type: ignore[attr-defined]
                json=payload, headers=headers,
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    error_text = body.decode(errors="replace")[:500]
                    raise ValueError(f"Anthropic API 错误 (HTTP {resp.status_code}): {error_text}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = chunk.get("type", "")
                    if event_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                full_content += token
                                yield {"type": "token", "content": token}, None
                        elif delta.get("type") == "input_json_delta":
                            idx = chunk.get("index", 0)
                            if idx in tool_use_blocks:
                                tool_use_blocks[idx]["input_str"] += delta.get("partial_json", "")
                    elif event_type == "content_block_start":
                        block = chunk.get("content_block", {})
                        if block.get("type") == "tool_use":
                            idx = chunk.get("index", 0)
                            tool_use_blocks[idx] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input_str": "",
                            }
                    elif event_type == "message_stop":
                        break

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Anthropic API ({self.cloud_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Anthropic API 请求超时 ({self.timeout}s)"  # type: ignore[attr-defined]
            ) from e

        normalized_tool_calls = []
        for blk in tool_use_blocks.values():
            raw = blk.get("input_str") or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"raw_input": raw}
            normalized_tool_calls.append({
                "id": blk.get("id") or str(uuid.uuid4())[:8],
                "function": {"name": blk.get("name", ""), "arguments": args},
            })

        result: dict = {"message": {"role": "assistant", "content": full_content}}
        if normalized_tool_calls:
            result["message"]["tool_calls"] = normalized_tool_calls
        yield None, result
