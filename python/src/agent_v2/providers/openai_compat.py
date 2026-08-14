"""OpenAI-compatible Provider（含真流式 SSE）。

Covers: OpenAI, Ollama, DeepSeek, Groq, and 17+ other providers.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

import httpx

from src.agent_v2.providers.base import BaseProvider
from src.agent_v2.types import (
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolDefinition,
    ToolUseBlock,
)
from src.llm_request_policy import apply_thinking_policy, normalize_thinking_mode

logger = logging.getLogger(__name__)


def _response_error_detail(response: httpx.Response) -> str:
    """Extract a concise provider error without leaking request headers."""
    raw = response.text.strip()
    if not raw:
        return response.reason_phrase or "unknown provider error"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500]
    error = payload.get("error", payload)
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("code")
        if message:
            return str(message)[:500]
    return raw[:500]


def _api_error_from_response(response: httpx.Response) -> ApiError:
    retry_after = None
    raw_retry_after = response.headers.get("retry-after")
    if raw_retry_after:
        with suppress(ValueError):
            retry_after = float(raw_retry_after)
    return ApiError(
        f"API error {response.status_code}: {_response_error_detail(response)}",
        status_code=response.status_code,
        retry_after=retry_after,
    )


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


def _usage_from_payload(usage_data: dict) -> TokenUsage:
    """Parse usage, mapping DeepSeek 磁盘缓存字段到统一的 cache_read/creation。"""
    return TokenUsage(
        input_tokens=usage_data.get("prompt_tokens", 0),
        output_tokens=usage_data.get("completion_tokens", 0),
        cache_read_tokens=usage_data.get("prompt_cache_hit_tokens", 0),
        cache_creation_tokens=usage_data.get("prompt_cache_miss_tokens", 0),
    )


class OpenAiCompatProvider(BaseProvider):
    """OpenAI-compatible Chat Completions provider with real streaming.

    Per-provider quirks auto-detected from model name / base URL.
    Connection strategy: system-proxy-aware → direct fallback.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        timeout: float = 300.0,
        proxy: str | None = None,
        thinking_mode: str = "auto",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.proxy = proxy
        self.thinking_mode = normalize_thinking_mode(thinking_mode)
        self._client: httpx.AsyncClient | None = None
        self._direct_client: httpx.AsyncClient | None = None
        from src.agent_v2.providers.quirks import detect_quirks

        self.quirks = detect_quirks(model, base_url)
        self.model_max_tokens = _max_tokens_for_model(model)

    def _make_kwargs(self, trust_env: bool) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        kwargs: dict[str, Any] = {"timeout": self.timeout, "headers": headers}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        elif not trust_env:
            kwargs["trust_env"] = False
        return kwargs

    async def _get_client(self) -> httpx.AsyncClient:
        """Primary client: uses explicit proxy or system proxy settings."""
        if self._client is None:
            self._client = httpx.AsyncClient(**self._make_kwargs(trust_env=True))
        return self._client

    async def _get_direct_client(self) -> httpx.AsyncClient:
        """Fallback client: direct connection, bypasses all proxy settings."""
        if self._direct_client is None:
            self._direct_client = httpx.AsyncClient(**self._make_kwargs(trust_env=False))
        return self._direct_client

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
                thinking = "".join(b.thinking for b in msg.blocks if isinstance(b, ThinkingBlock))
                if text or tool_calls:
                    entry: dict[str, Any] = {"role": "assistant"}
                    # Always include content key, even if null (matches claw-code)
                    entry["content"] = text if text else None
                    if tool_calls:
                        # 推理模型（DeepSeek/Qwen/GLM 等）要求工具调用回合回传
                        # reasoning_content；严格供应商（OpenAI/Groq 等）不识别该字段，
                        # 由 quirks.echo_reasoning_content 门控，避免 400。
                        # 非工具调用回合的 reasoning_content 会被忽略，不发送以省 token。
                        if thinking and self.quirks.echo_reasoning_content:
                            entry["reasoning_content"] = thinking
                        tc_list = []
                        for tc in tool_calls:
                            args = tc.input
                            try:
                                json.loads(args)
                            except (json.JSONDecodeError, TypeError):
                                args = json.dumps({"input": args})
                            tc_list.append(
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {"name": tc.name, "arguments": args},
                                }
                            )
                        entry["tool_calls"] = tc_list
                    result.append(entry)
            elif msg.role == MessageRole.TOOL:
                from src.agent_v2.types import ToolResultBlock

                for b in msg.blocks:
                    if isinstance(b, ToolResultBlock):
                        result.append(
                            {
                                "role": "tool",
                                "tool_call_id": b.tool_use_id,
                                "content": b.output,
                            }
                        )
        return result

    def _build_tools(self, tools: list[ToolDefinition] | None) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

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
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "max_tokens": min(max_tokens, self.model_max_tokens),
            "temperature": temperature,
            "stream": False,
        }
        built_tools = self._build_tools(tools)
        thinking_resolved = apply_thinking_policy(
            body,
            base_url=self.base_url,
            model=self.model,
            configured=self.thinking_mode,
        )
        if thinking_resolved == "enabled":
            # DeepSeek 思考模式下 temperature/top_p 等参数不生效（文档明示），
            # 显式省略以避免上游兼容性问题
            body.pop("temperature", None)
        if built_tools:
            body["tools"] = built_tools
            if tool_choice != "auto":
                body["tool_choice"] = tool_choice

        url = f"{self.base_url}/chat/completions"
        last_err: Exception | None = None

        for client_fn in (self._get_client, self._get_direct_client):
            client = await client_fn()
            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
            except httpx.ConnectError as e:
                last_err = e
                logger.debug("connect failed with %s, trying next client", client_fn.__name__)
                continue
            except httpx.HTTPStatusError as e:
                raise _api_error_from_response(e.response) from e
            data = resp.json()
            finish = data.get("choices", [{}])[0].get("finish_reason", "?")
            tc_count = len(data.get("choices", [{}])[0].get("message", {}).get("tool_calls") or [])
            text_len = len(data.get("choices", [{}])[0].get("message", {}).get("content") or "")
            logger.info(
                "chat response: finish=%s, tool_calls=%d, text_len=%d, model=%s, msgs=%d, tools=%d",
                finish,
                tc_count,
                text_len,
                data.get("model", "?"),
                len(messages),
                len(tools or []),
            )
            if tc_count == 0 and finish == "stop" and tools:
                logger.warning(
                    "DeepSeek text-only response with %d tools available. Last user msg: %s...",
                    len(tools),
                    (messages[-1].text_content() if messages else "")[:200],
                )
            return self._parse_response(data)

        raise ApiError(
            f"Cannot connect to {url}: {last_err}. Check network or firewall.",
            status_code=0,
        ) from last_err

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncGenerator[ProviderResponse | TokenUsage, None]:
        """真流式 — 每个 token 立即产出。先走系统代理，连不上直连回退。"""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "max_tokens": min(max_tokens, self.model_max_tokens),
            "temperature": temperature,
            "stream": True,
        }
        if self.quirks.supports_stream_options:
            body["stream_options"] = {"include_usage": True}
        thinking_resolved = apply_thinking_policy(
            body,
            base_url=self.base_url,
            model=self.model,
            configured=self.thinking_mode,
        )
        if thinking_resolved == "enabled":
            # DeepSeek 思考模式下 temperature/top_p 等参数不生效（文档明示）
            body.pop("temperature", None)
        built_tools = self._build_tools(tools)
        if built_tools:
            body["tools"] = built_tools

        url = f"{self.base_url}/chat/completions"
        last_err: Exception | None = None

        for client_fn in (self._get_client, self._get_direct_client):
            client = await client_fn()
            emitted = False
            try:
                async for chunk in self._stream_body(client, url, body):
                    emitted = True
                    yield chunk
                return
            except httpx.TransportError as e:
                last_err = e
                if emitted:
                    raise ApiError(
                        f"Streaming connection interrupted: {e}",
                        status_code=0,
                    ) from e
                logger.debug(
                    "stream connect failed with %s, trying next client", client_fn.__name__
                )
                continue
            except httpx.HTTPStatusError as e:
                raise _api_error_from_response(e.response) from e

        raise ApiError(
            f"Cannot connect to {url}: {last_err}. Check network or firewall.",
            status_code=0,
        ) from last_err

    async def _stream_body(
        self,
        client: httpx.AsyncClient,
        url: str,
        body: dict,
    ) -> AsyncGenerator[ProviderResponse | TokenUsage, None]:
        """Streaming SSE parser — single client, no retry logic."""
        blocks: list = []
        tc_map: dict[int, dict] = {}
        text_buf = ""
        reasoning_buf = ""
        stream_finished = False

        async with client.stream("POST", url, json=body) as resp:
            if resp.is_error:
                # Streaming responses are not buffered by httpx. Read the body
                # before raising so callers receive the provider's real error
                # instead of httpx.ResponseNotRead.
                await resp.aread()
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    stream_finished = True
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                upstream_error = chunk.get("error")
                if upstream_error:
                    if isinstance(upstream_error, dict):
                        detail = (
                            upstream_error.get("message")
                            or upstream_error.get("detail")
                            or upstream_error.get("code")
                        )
                    else:
                        detail = upstream_error
                    raise ApiError(
                        f"API stream error: {detail or 'unknown provider error'}",
                        status_code=502,
                    )

                choices = chunk.get("choices") or []
                if not choices:
                    usage_data = chunk.get("usage")
                    if usage_data:
                        yield _usage_from_payload(usage_data)
                    continue
                choice = choices[0]
                if choice.get("finish_reason") is not None:
                    stream_finished = True
                delta = choice.get("delta", {})

                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_buf += content
                    blocks.append(TextBlock(text=content))
                    yield TextBlock(text=content)

                reasoning = delta.get("reasoning_content")
                if isinstance(reasoning, str) and reasoning:
                    reasoning_buf += reasoning
                    yield ThinkingBlock(thinking=reasoning)

                for tc in delta.get("tool_calls") or []:
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

                usage_data = chunk.get("usage")
                if usage_data:
                    yield _usage_from_payload(usage_data)

        if not stream_finished:
            raise ApiError(
                "Streaming connection ended before the provider sent a completion marker",
                status_code=0,
            )

        for idx in sorted(tc_map.keys()):
            tc = tc_map[idx]
            if tc["name"]:
                blocks.append(
                    ToolUseBlock(
                        id=tc["id"] or f"tc_{uuid.uuid4().hex[:8]}",
                        name=tc["name"],
                        input=tc["args"] or "{}",
                    )
                )

        # 思考内容随最终响应一并返回：会话持久化需要它，
        # DeepSeek 工具调用回合在后续请求中必须回传 reasoning_content。
        if reasoning_buf:
            blocks.append(ThinkingBlock(thinking=reasoning_buf))

        yield ProviderResponse(
            blocks=blocks,
            usage=TokenUsage(),
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
            blocks.append(
                ToolUseBlock(
                    id=tc.get("id", f"tc_{uuid.uuid4().hex[:8]}"),
                    name=func.get("name", "unknown"),
                    input=func.get("arguments", "{}"),
                )
            )
        # 思考内容独立于正文捕获：纯工具调用回合 content 为空，
        # 若只按 text 非空才解析会丢失 reasoning，后续无法回传。
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            blocks.append(ThinkingBlock(thinking=reasoning))
        text = msg.get("content", "")
        if isinstance(text, str) and text:
            blocks.append(TextBlock(text=text))

        return ProviderResponse(
            blocks=blocks,
            usage=_usage_from_payload(usage_data),
            stop_reason="tool_use" if finish == "tool_calls" else "end_turn",
        )

    async def close(self) -> None:
        for c in (self._client, self._direct_client):
            if c:
                await c.aclose()
        self._client = None
        self._direct_client = None
