"""Ollama backend for LLMClient."""

from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx

from src.agent._llm_helpers import _safe_response_text
from src.agent.models import message_to_ollama_dict


class OllamaMixin:
    """Provides _call_ollama and _stream_ollama for LLMClient."""

    async def _call_ollama(
        self, messages, tools: list[dict] | None,
    ) -> dict:
        from src.agent.models import Message

        client = await self._get_http_client()  # type: ignore[attr-defined]
        ollama_messages = [message_to_ollama_dict(m) for m in messages]
        payload: dict = {
            "model": self.model,  # type: ignore[attr-defined]
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,  # type: ignore[attr-defined]
                "num_predict": self.num_predict,  # type: ignore[attr-defined]
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await client.post(
                f"{self.ollama_base_url}/api/chat", json=payload,  # type: ignore[attr-defined]
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.ollama_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"Ollama API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.ollama_base_url})"  # type: ignore[attr-defined]
            ) from e

        return resp.json()

    async def _stream_ollama(
        self, messages, tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()  # type: ignore[attr-defined]
        ollama_messages = [message_to_ollama_dict(m) for m in messages]
        payload: dict = {
            "model": self.model,  # type: ignore[attr-defined]
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,  # type: ignore[attr-defined]
                "num_predict": self.num_predict,  # type: ignore[attr-defined]
            },
        }
        if tools:
            payload["tools"] = tools

        full_content = ""
        tool_calls_acc: list[dict] = []

        try:
            async with client.stream(
                "POST",
                f"{self.ollama_base_url}/api/chat", json=payload,  # type: ignore[attr-defined]
            ) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    error_text = body.decode(errors="replace")[:500]
                    raise ValueError(f"Ollama API 错误 (HTTP {resp.status_code}): {error_text}")

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})
                    token = msg.get("content", "")
                    tc_chunk = msg.get("tool_calls")
                    if tc_chunk:
                        tool_calls_acc.extend(tc_chunk)
                    if token:
                        full_content += token
                        yield {"type": "token", "content": token}, None

                    if chunk.get("done"):
                        ollama_err = chunk.get("error")
                        if ollama_err and not full_content:
                            raise ValueError(f"Ollama 流式错误: {ollama_err}")
                        result: dict = {"message": {"role": "assistant", "content": full_content}}
                        if tool_calls_acc:
                            result["message"]["tool_calls"] = tool_calls_acc
                        yield None, result
                        return

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.ollama_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Ollama 请求超时 ({self.timeout}s)"  # type: ignore[attr-defined]
            ) from e

        result = {"message": {"role": "assistant", "content": full_content}}
        if tool_calls_acc:
            result["message"]["tool_calls"] = tool_calls_acc
        yield None, result
