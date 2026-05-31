"""OpenAI-compatible cloud backend for LLMClient."""

from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

import httpx

from src.agent._llm_helpers import (
    _normalize_cloud_response,
    _safe_response_text,
    messages_to_openai,
)


class OpenAIMixin:
    """Provides _call_cloud and _stream_cloud for LLMClient."""

    async def _call_cloud(
        self, messages, tools: list[dict] | None,
    ) -> dict:
        client = await self._get_http_client()  # type: ignore[attr-defined]
        openai_messages = messages_to_openai(messages)
        payload: dict = {
            "model": self.effective_model,  # type: ignore[attr-defined]
            "messages": openai_messages,
            "temperature": self.temperature,  # type: ignore[attr-defined]
            "max_tokens": self.num_predict,  # type: ignore[attr-defined]
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",  # type: ignore[attr-defined]
        }

        try:
            resp = await client.post(
                f"{self.cloud_base_url}/chat/completions",  # type: ignore[attr-defined]
                json=payload, headers=headers,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接云端 API ({self.cloud_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"云端 API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"云端 API 请求超时 ({self.timeout}s)"  # type: ignore[attr-defined]
            ) from e

        return _normalize_cloud_response(resp.json())

    async def _stream_cloud(
        self, messages, tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()  # type: ignore[attr-defined]
        openai_messages = messages_to_openai(messages)
        endpoint = f"{self.cloud_base_url}/chat/completions"  # type: ignore[attr-defined]
        payload: dict = {
            "model": self.effective_model,  # type: ignore[attr-defined]
            "messages": openai_messages,
            "temperature": self.temperature,  # type: ignore[attr-defined]
            "max_tokens": self.num_predict,  # type: ignore[attr-defined]
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",  # type: ignore[attr-defined]
        }

        full_content = ""
        reasoning_content = ""
        tc_accumulator: dict[str, dict] = {}

        try:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    error_text = body.decode(errors="replace")[:500]
                    raise ValueError(f"云端 API 错误 (HTTP {resp.status_code}): {error_text}")

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    err_obj = chunk.get("error")
                    if err_obj:
                        err_msg = err_obj if isinstance(err_obj, str) else err_obj.get("message", str(err_obj))
                        raise ValueError(f"云端 API 流式错误: {err_msg}")

                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    rc = delta.get("reasoning_content", "")
                    if rc:
                        reasoning_content += rc
                    token = delta.get("content", "")
                    if isinstance(token, list):
                        token = "".join(
                            p.get("text", "") if isinstance(p, dict) else str(p)
                            for p in token
                        )
                    if token:
                        full_content += token
                        yield {"type": "token", "content": token}, None

                    tc_deltas = delta.get("tool_calls")
                    if tc_deltas:
                        for tc_d in tc_deltas:
                            idx = str(tc_d.get("index", 0))
                            if idx not in tc_accumulator:
                                tc_accumulator[idx] = {"id": "", "name": "", "arguments_str": ""}
                            acc = tc_accumulator[idx]
                            if tc_d.get("id"):
                                acc["id"] = tc_d["id"]
                            func = tc_d.get("function", {})
                            if func.get("name"):
                                acc["name"] = func["name"]
                            if func.get("arguments"):
                                acc["arguments_str"] += func["arguments"]

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接云端 API ({self.cloud_base_url})"  # type: ignore[attr-defined]
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"云端 API 请求超时 ({self.timeout}s)"  # type: ignore[attr-defined]
            ) from e

        normalized_tool_calls = []
        for acc in tc_accumulator.values():
            raw_args = acc["arguments_str"] or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"raw_input": raw_args}
            normalized_tool_calls.append({
                "id": acc["id"] or str(uuid.uuid4())[:8],
                "function": {"name": acc["name"], "arguments": args},
            })

        result: dict = {"message": {"role": "assistant", "content": full_content}}
        if reasoning_content:
            result["message"]["reasoning_content"] = reasoning_content
        if normalized_tool_calls:
            result["message"]["tool_calls"] = normalized_tool_calls
        yield None, result
