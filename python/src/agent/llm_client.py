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

import logging
from typing import AsyncGenerator

import httpx

from src.agent._llm_anthropic import AnthropicMixin
from src.agent._llm_helpers import (
    TokenUsage,
    extract_text_content,
    extract_tool_calls,
    messages_to_anthropic,
    messages_to_openai,
)
from src.agent._llm_ollama import OllamaMixin
from src.agent._llm_openai import OpenAIMixin
from src.agent.models import Message, message_to_ollama_dict

logger = logging.getLogger(__name__)

# Re-export helpers for backward compatibility (external importers).
# These are now defined in _llm_helpers.py but re-exported here so
# existing `from src.agent.llm_client import ...` calls keep working.
__all__ = [
    "LLMClient",
    "TokenUsage",
    "extract_text_content",
    "extract_tool_calls",
    "messages_to_anthropic",
    "messages_to_openai",
]


class LLMClient(OllamaMixin, OpenAIMixin, AnthropicMixin):
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

    def call_simple_sync(self, prompt: str) -> str:
        """Synchronous counterpart of call_simple for sync tool callers.

        Creates a short-lived httpx.Client per call (no persistent connection).
        Strips <think/> tags from the response.
        """
        import re as _re

        use_cloud = self.use_cloud
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                if use_cloud:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.cloud_api_key}",
                    }
                    resp = client.post(
                        f"{self.cloud_base_url}/chat/completions",
                        json={
                            "model": self.effective_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3,
                            "max_tokens": self.num_predict,
                            "stream": False,
                        },
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data.get("choices", [{}])[0].get("message", {})
                    content = msg.get("content", "").strip()
                    if not content:
                        content = msg.get("reasoning_content", "").strip()
                else:
                    resp = client.post(
                        f"{self.ollama_base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "options": {"temperature": 0.3, "num_predict": self.num_predict},
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data.get("message", {}).get("content", "").strip()

                stripped = _re.sub(r"<think.*?>.*?</think.*?>", "", content, flags=_re.DOTALL).strip()
                if stripped:
                    return stripped
                m = _re.search(r"<think[^>]*>(.*?)</think[^>]*>", content, flags=_re.DOTALL | _re.IGNORECASE)
                if m:
                    return m.group(1).strip() or "（LLM 返回为空）"
                return content.strip() or "（LLM 返回为空）"
        except Exception as e:
            return f"LLM 调用失败: {e}"
