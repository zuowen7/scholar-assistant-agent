"""Argument Mapping — 共享 LLM 调用工具"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

from src.constants import ANTHROPIC_API_VERSION
from src.llm_request_policy import (
    apply_reasoning_effort_policy,
    apply_thinking_policy,
    resolve_thinking_mode,
)

logger = logging.getLogger(__name__)

_REASONING_MODEL_MARKERS = (
    "reasoner",
    "reasoning",
    "deepseek-r1",
    "deepseek-v4",
    "qwq",
    "qwen3-thinking",
)
_MIN_REASONING_TOKENS = 8192
_MAX_INITIAL_REASONING_TOKENS = 32768
_MAX_RETRY_TOKENS = 32768


def _emit_request_audit(client: Any, event: dict[str, Any]) -> None:
    """Emit a header-free request event when an explicit audit hook is attached."""
    hook = getattr(client, "request_audit_hook", None)
    if hook is not None:
        hook(copy.deepcopy(event))


def _is_reasoning_model(model: str) -> bool:
    normalized = model.strip().lower()
    return any(marker in normalized for marker in _REASONING_MODEL_MARKERS)


def _initial_token_budget(client: Any, model: str, requested: int) -> int:
    """Avoid a predictably empty first request for reasoning-heavy models."""
    if not _is_reasoning_model(model):
        return requested
    configured = getattr(client, "max_tokens", _MIN_REASONING_TOKENS)
    try:
        configured_tokens = int(configured or _MIN_REASONING_TOKENS)
    except (TypeError, ValueError):
        configured_tokens = _MIN_REASONING_TOKENS
    return min(
        max(requested, configured_tokens, _MIN_REASONING_TOKENS),
        _MAX_INITIAL_REASONING_TOKENS,
    )


async def call_llm_chat(
    prompt: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    json_mode: bool = False,
) -> str:
    """调用 LLM，三层降级：Cloud HTTP → Ollama → 空字符串。

    Args:
        prompt: 用户提示词。
        cloud_client: CloudClient 实例（通过 getattr 访问属性）。
        ollama_client: OllamaClient 实例。
        max_tokens: 最大生成 token 数。
        temperature: 采样温度。
        json_mode: 要求云端按 JSON 输出（response_format=json_object，提示词须含 "json"）。
    """
    cloud_error: Exception | None = None
    if cloud_client is not None:
        try:
            return await _direct_cloud_chat(
                prompt, cloud_client, max_tokens, temperature, json_mode=json_mode
            )
        except Exception as e:
            logger.warning("Cloud chat failed: %s", e)
            cloud_error = e

    if ollama_client is not None:
        try:
            result = ollama_client.translate(prompt)
            if hasattr(result, "translated"):
                return result.translated
            if hasattr(result, "text"):
                return result.text
            return str(result)
        except Exception as e:
            logger.warning("Ollama fallback failed: %s", e)

    if cloud_error is not None:
        raise cloud_error
    return ""


async def _direct_cloud_chat(
    prompt: str,
    client: Any,
    max_tokens: int,
    temperature: float,
    *,
    json_mode: bool = False,
) -> str:
    import httpx

    messages = [{"role": "user", "content": prompt}]
    api_format = getattr(client, "api_format", "openai")
    api_key = getattr(client, "api_key", "")
    model = getattr(client, "model", "gpt-4o")
    base_url = getattr(client, "base_url", "")
    timeout = getattr(client, "timeout", 60.0)
    try:
        timeout = min(float(timeout), 90.0)
    except (TypeError, ValueError):
        timeout = 60.0
    thinking_mode = getattr(client, "thinking_mode", "auto")

    if api_format == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        url = f"{base_url}/v1/messages"
    else:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # DeepSeek/OpenAI JSON Output：保证返回合法 JSON（提示词须含 "json" 字样）
            payload["response_format"] = {"type": "json_object"}
        resolved_thinking = apply_thinking_policy(
            payload,
            base_url=base_url,
            model=model,
            configured=thinking_mode,
        )
        if resolved_thinking != "disabled":
            apply_reasoning_effort_policy(
                payload,
                base_url=base_url,
                model=model,
                configured=getattr(client, "reasoning_effort", None),
            )
        url = f"{base_url}/chat/completions"

    request_sequence = 0

    async def _do_request(http: Any, tokens: int) -> tuple[str, str, str]:
        nonlocal request_sequence
        request_sequence += 1
        p = {**payload, "max_tokens": tokens}
        started_monotonic = time.monotonic()
        started_at = time.time()
        _emit_request_audit(
            client,
            {
                "event": "request_started",
                "sequence": request_sequence,
                "started_at": started_at,
                "payload": p,
            },
        )
        resp = None
        try:
            resp = await http.post(url, headers=headers, json=p)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            _emit_request_audit(
                client,
                {
                    "event": "request_failed",
                    "sequence": request_sequence,
                    "started_at": started_at,
                    "ended_at": time.time(),
                    "http_status": getattr(resp, "status_code", None),
                    "error_type": type(exc).__name__,
                },
            )
            raise
        logger.info(
            "argument LLM completed model=%s max_tokens=%d elapsed_ms=%d",
            model,
            tokens,
            round((time.monotonic() - started_monotonic) * 1000),
        )
        if api_format == "anthropic":
            text = "".join(
                b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
            )
            _emit_request_audit(
                client,
                {
                    "event": "response_received",
                    "sequence": request_sequence,
                    "started_at": started_at,
                    "ended_at": time.time(),
                    "http_status": getattr(resp, "status_code", None),
                    "finish_reason": None,
                    "response_model": data.get("model"),
                    "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
                },
            )
            return text, "", ""
        msg = data.get("choices", [{}])[0].get("message", {})
        finish = data.get("choices", [{}])[0].get("finish_reason", "")
        _emit_request_audit(
            client,
            {
                "event": "response_received",
                "sequence": request_sequence,
                "started_at": started_at,
                "ended_at": time.time(),
                "http_status": getattr(resp, "status_code", None),
                "finish_reason": finish,
                "response_model": data.get("model"),
                "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
            },
        )
        return msg.get("content", ""), msg.get("reasoning_content", ""), finish

    resolved_thinking = resolve_thinking_mode(base_url, model, thinking_mode)
    initial_tokens = (
        _initial_token_budget(client, model, max_tokens)
        if resolved_thinking != "disabled"
        else max_tokens
    )
    async with httpx.AsyncClient(timeout=timeout) as http:
        content, reasoning, finish = await _do_request(http, initial_tokens)

        # A reasoning model may still consume its entire budget before emitting
        # final content. Retry once on the same connection with bounded headroom.
        if not content and reasoning and finish == "length":
            retry_tokens = min(
                max(initial_tokens * 2, _MAX_RETRY_TOKENS),
                _MAX_RETRY_TOKENS,
            )
            logger.warning(
                "Model %s exhausted %d tokens on reasoning, retrying with %d",
                model,
                initial_tokens,
                retry_tokens,
            )
            content, _, _ = await _do_request(http, retry_tokens)

    if not content and reasoning:
        content = reasoning
    return content
