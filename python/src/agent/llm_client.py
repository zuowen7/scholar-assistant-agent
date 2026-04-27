"""Unified LLM client — encapsulates all LLM communication for the Agent subsystem.

Supports three backends:
1. Ollama (local, /api/chat)
2. OpenAI-compatible cloud APIs (18 providers via PROVIDER_PRESETS)
3. Anthropic Messages API

Each backend supports streaming and non-streaming modes. All responses are
normalized to a common Ollama-compatible dict format so downstream code
(AgentLoop) stays backend-agnostic.

Message conversion helpers:
- messages_to_openai(messages) -> list[dict]
- messages_to_anthropic(messages) -> (system_text, list[dict])
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator

import httpx

from src.agent.models import Message, ToolCall, message_to_ollama_dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _safe_response_text(response: httpx.Response) -> str:
    try:
        await response.aread()
        return response.text[:500]
    except Exception:
        return "<response body not available>"


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
        if m.reasoning_content:
            d["reasoning_content"] = m.reasoning_content
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

    # Strategy 1: native
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

    # Strategy 2: Anthropic tool_use
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
        # Ollama
        eval_count = response.get("eval_count") or 0
        prompt_eval = response.get("prompt_eval_count")
        if eval_count:
            self.completion_tokens += eval_count
        if prompt_eval:
            self.prompt_tokens += prompt_eval
        # OpenAI
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


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class LLMClient:
    """Unified LLM client for Ollama, OpenAI-compatible, and Anthropic APIs.

    All responses are normalized to Ollama format:
    {"message": {"role", "content", "tool_calls"?, "reasoning_content"?}}
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        temperature: float = 0.3,
        num_predict: int = 4096,
        timeout: float = 300.0,
        cloud_base_url: str = "",
        cloud_api_key: str = "",
        cloud_model: str = "",
        api_format: str = "openai",
        system_prompt: str = "",
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout = timeout
        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format
        self.system_prompt = system_prompt
        self.token_usage = TokenUsage()
        self._http_client: httpx.AsyncClient | None = None

    @property
    def use_cloud(self) -> bool:
        return bool(self.cloud_api_key and self.cloud_base_url)

    @property
    def effective_model(self) -> str:
        return self.cloud_model or self.model

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> dict:
        """Non-streaming LLM call. Returns normalized Ollama-format response."""
        if not self.use_cloud:
            return await self._call_ollama(messages, tools)
        if self.api_format == "anthropic":
            return await self._call_anthropic(messages, tools)
        return await self._call_cloud(messages, tools)

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        """Streaming LLM call.

        Yields:
            (token_event_dict, None)  — each token
            (None, full_response)     — final complete response
        """
        if not self.use_cloud:
            async for item in self._stream_ollama(messages, tools):
                yield item
        elif self.api_format == "anthropic":
            async for item in self._stream_anthropic(messages, tools):
                yield item
        else:
            async for item in self._stream_cloud(messages, tools):
                yield item

    async def call_simple(self, messages: list[Message]) -> str | None:
        """Lightweight non-streaming call (no tools). Used for planning etc."""
        client = await self._get_http_client()
        ollama_dicts = [message_to_ollama_dict(m) for m in messages]

        try:
            if self.use_cloud:
                if self.api_format == "anthropic":
                    system_text = ""
                    anthropic_msgs = []
                    for d in ollama_dicts:
                        if d["role"] == "system":
                            system_text += d.get("content", "")
                            continue
                        anthropic_msgs.append({"role": d["role"], "content": d.get("content", "")})
                    payload: dict = {
                        "model": self.effective_model,
                        "max_tokens": 1024,
                        "messages": anthropic_msgs,
                    }
                    if system_text:
                        payload["system"] = system_text
                    headers = {
                        "Content-Type": "application/json",
                        "x-api-key": self.cloud_api_key,
                        "anthropic-version": "2023-06-01",
                    }
                    resp = await client.post(
                        f"{self.cloud_base_url}/v1/messages",
                        json=payload, headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return "".join(
                        b.get("text", "") for b in data.get("content", [])
                        if b.get("type") == "text"
                    ).strip() or None
                else:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.cloud_api_key}",
                    }
                    resp = await client.post(
                        f"{self.cloud_base_url}/chat/completions",
                        json={
                            "model": self.effective_model,
                            "messages": ollama_dicts,
                            "temperature": 0.1,
                            "max_tokens": 1024,
                            "stream": False,
                        },
                        headers=headers,
                    )
                    resp.raise_for_status()
                    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip() or None
            else:
                resp = await client.post(
                    f"{self.ollama_base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": ollama_dicts,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 1024},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "").strip() or None
        except Exception as e:
            logger.warning("LLM 辅助调用失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    async def _call_ollama(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> dict:
        client = await self._get_http_client()
        ollama_messages = [message_to_ollama_dict(m) for m in messages]
        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {"temperature": self.temperature, "num_predict": self.num_predict},
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = await client.post(f"{self.ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接 Ollama 服务 ({self.ollama_base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"Ollama API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"无法连接 Ollama 服务 ({self.ollama_base_url})") from e

        return resp.json()

    async def _stream_ollama(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()
        ollama_messages = [message_to_ollama_dict(m) for m in messages]
        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {"temperature": self.temperature, "num_predict": self.num_predict},
        }
        if tools:
            payload["tools"] = tools

        full_content = ""
        tool_calls_acc: list[dict] = []

        try:
            async with client.stream("POST", f"{self.ollama_base_url}/api/chat", json=payload) as resp:
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
            raise ConnectionError(f"无法连接 Ollama 服务 ({self.ollama_base_url})") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Ollama 请求超时 ({self.timeout}s)") from e

        result = {"message": {"role": "assistant", "content": full_content}}
        if tool_calls_acc:
            result["message"]["tool_calls"] = tool_calls_acc
        yield None, result

    # ------------------------------------------------------------------
    # OpenAI-compatible cloud
    # ------------------------------------------------------------------

    async def _call_cloud(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> dict:
        client = await self._get_http_client()
        openai_messages = messages_to_openai(messages)
        payload: dict = {
            "model": self.effective_model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.num_predict,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",
        }

        try:
            resp = await client.post(
                f"{self.cloud_base_url}/chat/completions",
                json=payload, headers=headers,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接云端 API ({self.cloud_base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"云端 API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"云端 API 请求超时 ({self.timeout}s)") from e

        return _normalize_cloud_response(resp.json())

    async def _stream_cloud(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()
        openai_messages = messages_to_openai(messages)
        endpoint = f"{self.cloud_base_url}/chat/completions"
        payload: dict = {
            "model": self.effective_model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.num_predict,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",
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
            raise ConnectionError(f"无法连接云端 API ({self.cloud_base_url})") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"云端 API 请求超时 ({self.timeout}s)") from e

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

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    async def _call_anthropic(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> dict:
        client = await self._get_http_client()
        system_text, anthropic_msgs = messages_to_anthropic(messages, self.system_prompt)
        payload: dict = {
            "model": self.effective_model,
            "max_tokens": self.num_predict,
            "messages": anthropic_msgs,
        }
        if system_text:
            payload["system"] = system_text
        if tools:
            payload["tools"] = _ollama_tools_to_anthropic(tools)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            resp = await client.post(
                f"{self.cloud_base_url}/v1/messages",
                json=payload, headers=headers,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接 Anthropic API ({self.cloud_base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = await _safe_response_text(e.response)
            raise ValueError(f"Anthropic API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Anthropic API 请求超时 ({self.timeout}s)") from e

        return _normalize_anthropic_response(resp.json())

    async def _stream_anthropic(
        self, messages: list[Message], tools: list[dict] | None,
    ) -> AsyncGenerator[tuple[dict | None, dict | None], None]:
        client = await self._get_http_client()
        system_text, anthropic_msgs = messages_to_anthropic(messages, self.system_prompt)
        payload: dict = {
            "model": self.effective_model,
            "max_tokens": self.num_predict,
            "messages": anthropic_msgs,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text
        if tools:
            payload["tools"] = _ollama_tools_to_anthropic(tools)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,
            "anthropic-version": "2023-06-01",
        }

        full_content = ""
        tool_use_blocks: dict[int, dict] = {}

        try:
            async with client.stream("POST", f"{self.cloud_base_url}/v1/messages", json=payload, headers=headers) as resp:
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
            raise ConnectionError(f"无法连接 Anthropic API ({self.cloud_base_url})") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Anthropic API 请求超时 ({self.timeout}s)") from e

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
