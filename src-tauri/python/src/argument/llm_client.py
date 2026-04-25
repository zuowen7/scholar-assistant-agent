"""Argument Mapping — 共享 LLM 调用工具"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def call_llm_chat(
    prompt: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """调用 LLM，三层降级：Cloud HTTP → Ollama → 空字符串。

    Args:
        prompt: 用户提示词。
        cloud_client: CloudClient 实例（通过 getattr 访问属性）。
        ollama_client: OllamaClient 实例。
        max_tokens: 最大生成 token 数。
        temperature: 采样温度。
    """
    if cloud_client is not None:
        try:
            return await _direct_cloud_chat(prompt, cloud_client, max_tokens, temperature)
        except Exception as e:
            logger.warning("Cloud chat failed: %s", e)

    if ollama_client is not None:
        try:
            result = ollama_client.translate(prompt)
            return result.text if hasattr(result, "text") else str(result)
        except Exception as e:
            logger.warning("Ollama fallback failed: %s", e)

    return ""


async def _direct_cloud_chat(
    prompt: str,
    client: Any,
    max_tokens: int,
    temperature: float,
) -> str:
    import httpx

    messages = [{"role": "user", "content": prompt}]
    api_format = getattr(client, "api_format", "openai")
    api_key = getattr(client, "api_key", "")
    model = getattr(client, "model", "gpt-4o")
    base_url = getattr(client, "base_url", "")
    timeout = getattr(client, "timeout", 60.0)

    if api_format == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {"model": model, "max_tokens": max_tokens, "messages": messages}
        url = f"{base_url}/v1/messages"
    else:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        url = f"{base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=timeout) as http:
        resp = await http.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if api_format == "anthropic":
        return data.get("content", [{}])[0].get("text", "")
    else:
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")
