"""云端大模型翻译客户端 - 支持 OpenAI 兼容和 Anthropic API 格式"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from src.translator.ollama_client import (
    TranslationResult,
    Glossary,
    _extract_term_pairs,
    _strip_think_tags,
    _strip_preamble,
    _strip_context_leak,
    _repair_truncation,
    _validate_translation,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 3.0
_PROMPT_MAX_CHARS = 28_000

# ── 供应商预设 ──

PROVIDER_PRESETS: dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o3-mini"],
        "api_format": "openai",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-4-20250414"],
        "api_format": "anthropic",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "api_format": "openai",
    },
    "moonshot": {
        "name": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "api_format": "openai",
    },
    "zhipu": {
        "name": "智谱 ChatGLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-long"],
        "api_format": "openai",
    },
    "qwen": {
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "api_format": "openai",
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.0-flash", "gemini-2.5-pro-preview-06-05"],
        "api_format": "openai",
    },
    "siliconflow": {
        "name": "SiliconFlow 硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen3-235B-A22B", "deepseek-ai/DeepSeek-V3"],
        "api_format": "openai",
    },
    # ── 更多 OpenAI-Compatible 聚合 / 云厂商 ──
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001"],
        "api_format": "openai",
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        "api_format": "openai",
    },
    "together": {
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"],
        "api_format": "openai",
    },
    "mistral": {
        "name": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "models": ["mistral-large-latest", "mistral-small-latest"],
        "api_format": "openai",
    },
    "xai": {
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-2-latest", "grok-2-vision-latest"],
        "api_format": "openai",
    },
    "fireworks": {
        "name": "Fireworks AI",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "models": ["accounts/fireworks/models/llama-v3p3-70b-instruct"],
        "api_format": "openai",
    },
    "deepinfra": {
        "name": "DeepInfra",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct"],
        "api_format": "openai",
    },
    "perplexity": {
        "name": "Perplexity",
        "base_url": "https://api.perplexity.ai",
        "models": ["sonar", "sonar-pro"],
        "api_format": "openai",
    },
    "novita": {
        "name": "Novita AI",
        "base_url": "https://api.novita.ai/v3/openai",
        "models": ["meta-llama/llama-3.1-70b-instruct"],
        "api_format": "openai",
    },
    "volcengine_ark": {
        "name": "火山方舟 (豆包)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k"],
        "api_format": "openai",
    },
    "baidu_qianfan": {
        "name": "百度千帆 (兼容 OpenAI)",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.0-8k"],
        "api_format": "openai",
    },
    "azure_openai": {
        "name": "Azure OpenAI (需填资源专属 endpoint)",
        "base_url": "",
        "models": ["gpt-4o"],
        "api_format": "openai",
    },
    "custom": {
        "name": "自定义 (任意 OpenAI 兼容网关)",
        "base_url": "",
        "models": [],
        "api_format": "openai",
    },
}


class CloudClient:
    """云端大模型翻译客户端，支持 OpenAI 兼容和 Anthropic 两种 API 格式"""

    _CONTEXT_SNIPPET_LEN = 800

    def __init__(
        self,
        provider: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        temperature: float = 0.3,
        max_tokens: int = 16384,
        system_prompt: str = "",
        timeout: float = 300.0,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.timeout = timeout

        preset = PROVIDER_PRESETS.get(provider, {})
        self.api_format = preset.get("api_format", "openai")

        self._prev_translation = ""
        self._document_context = ""
        self._glossary = Glossary()  # 与 OllamaClient 使用相同的 Glossary 类
        self._chunk_index = 0
        self._http_client: httpx.Client | None = None

    def _get_http_client(self) -> httpx.Client:
        """懒加载复用 httpx 连接"""
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.timeout)
        return self._http_client

    def close(self) -> None:
        """关闭持久连接"""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def translate(self, text: str, prev_translation: str = "") -> TranslationResult:
        """翻译单段文本，失败自动重试"""
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                if self.api_format == "anthropic":
                    result = self._call_anthropic(text, ctx)
                else:
                    result = self._call_openai_compatible(text, ctx)

                if not _validate_translation(result):
                    logger.warning(
                        "翻译结果过短 (attempt %d): original=%d chars, translated=%d chars",
                        attempt + 1, len(result.original), len(result.translated),
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)
                        continue
                self._prev_translation = result.translated
                self._glossary.update(text, result.translated)
                self._chunk_index += 1
                return result
            except (ConnectionError, ValueError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning("翻译失败，%d 秒后重试 (attempt %d): %s", RETRY_DELAY, attempt + 1, e)
                    time.sleep(RETRY_DELAY)

        raise last_error or ValueError("翻译失败")

    def _build_prompt(self, text: str, prev_translation: str) -> str:
        """构建翻译提示词"""
        prompt_parts = []

        if self._document_context:
            prompt_parts.append(
                f"[文档背景（不要翻译此部分）]\n{self._document_context}\n\n"
            )

        if prev_translation:
            snippet = prev_translation[-self._CONTEXT_SNIPPET_LEN:]
            prompt_parts.append(
                f"[前文翻译参考（仅用于保持术语和风格一致，不要翻译此部分）]\n"
                f"{snippet}\n\n"
            )

        prompt_parts.append(f"[请翻译以下内容]\n{text}")
        prompt = "".join(prompt_parts)

        # Token 安全保护：如果 prompt 总长度超出上限，裁剪上下文
        if len(prompt) > _PROMPT_MAX_CHARS:
            ctx_budget = _PROMPT_MAX_CHARS - len(text) - 200
            if ctx_budget > 0 and prev_translation:
                snippet = prev_translation[-min(ctx_budget, self._CONTEXT_SNIPPET_LEN):]
                prompt = (
                    f"[前文翻译参考（不要翻译此部分）]\n{snippet}\n\n"
                    f"[请翻译以下内容]\n{text}"
                )
            elif self._document_context and ctx_budget > 0:
                prompt = (
                    f"[文档背景（不要翻译此部分）]\n{self._document_context[:ctx_budget]}\n\n"
                    f"[请翻译以下内容]\n{text}"
                )
            else:
                prompt = f"[请翻译以下内容]\n{text}"

        return prompt

    def _build_system_prompt(self) -> str:
        """构建系统提示词，包含术语表和块索引（与 OllamaClient 对齐）"""
        parts = []
        if self.system_prompt:
            parts.append(self.system_prompt)

        glossary_text = self._glossary.to_prompt_text()
        if glossary_text:
            parts.append(
                "\n\n## 已确定的术语翻译（请严格沿用以下译法）\n" + glossary_text
            )

        if self._chunk_index > 0:
            parts.append(
                f"\n\n（这是文档的第 {self._chunk_index + 1} 块，请保持与前文的术语和风格一致）"
            )

        return "\n".join(parts)

    def set_document_context(self, context: str) -> None:
        self._document_context = context.strip()

    def _post_process(self, translated: str) -> str:
        """后处理翻译结果"""
        translated = _strip_think_tags(translated)
        translated = _strip_preamble(translated)
        translated = _strip_context_leak(translated)
        translated = _repair_truncation(translated)
        return translated

    # ── OpenAI 兼容 API ──

    def _call_openai_compatible(self, text: str, prev_translation: str = "") -> TranslationResult:
        """调用 OpenAI 兼容的 chat completions API"""
        prompt = self._build_prompt(text, prev_translation)
        system = self._build_system_prompt()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接云端 API ({self.base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                body = e.response.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                detail = e.response.text[:200]
            raise ValueError(f"API 请求失败 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"API 请求超时 ({self.timeout}s)") from e

        data = resp.json()
        translated = ""
        choices = data.get("choices") or []
        if choices:
            translated = (choices[0].get("message", {}).get("content") or "").strip()

        translated = self._post_process(translated)

        usage = data.get("usage") or {}
        return TranslationResult(
            original=text,
            translated=translated,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    # ── Anthropic API ──

    def _call_anthropic(self, text: str, prev_translation: str = "") -> TranslationResult:
        """调用 Anthropic Messages API"""
        prompt = self._build_prompt(text, prev_translation)
        system = self._build_system_prompt()

        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        url = f"{self.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接 Anthropic API ({self.base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                body = e.response.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                detail = e.response.text[:200]
            raise ValueError(f"Anthropic API 请求失败 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Anthropic API 请求超时 ({self.timeout}s)") from e

        data = resp.json()
        translated = ""
        content_blocks = data.get("content") or []
        for block in content_blocks:
            if block.get("type") == "text":
                translated += block.get("text", "")
        translated = translated.strip()

        translated = self._post_process(translated)

        usage = data.get("usage") or {}
        return TranslationResult(
            original=text,
            translated=translated,
            model=data.get("model", self.model),
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
        )

    # ── 健康检查 ──

    def health_check(self) -> bool:
        """检查云端 API 是否可用（用 models 列表接口验证连通性，不消耗 token）"""
        try:
            if self.api_format == "anthropic":
                return self._anthropic_health_check()
            else:
                return self._openai_health_check()
        except Exception:
            return False

    def _openai_health_check(self) -> bool:
        """OpenAI 兼容 API 健康检查 — 尝试 /models 端点（不消耗 token）"""
        # 优先尝试 models 端点
        for path in ("/models", "/v1/models"):
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                }
                client = self._get_http_client()
                resp = client.get(f"{self.base_url}{path}", headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    return True
                if resp.status_code == 401:
                    return False
            except httpx.HTTPError:
                continue

        # fallback: 发最小 chat 请求（兼容不支持 /models 的网关）
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }
        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers, timeout=15.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def _anthropic_health_check(self) -> bool:
        """Anthropic API 健康检查 — 发送最小请求"""
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }
        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers, timeout=15.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
