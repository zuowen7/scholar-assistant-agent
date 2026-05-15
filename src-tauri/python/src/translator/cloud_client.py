"""云端大模型翻译客户端 - 支持 OpenAI 兼容和 Anthropic API 格式"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

from src.translator.ollama_client import (
    TranslationResult,
    Glossary,
)
from src.translator._helpers import (
    _extract_term_pairs,
    _strip_think_tags,
    _strip_code_block_wrapping,
    _strip_preamble,
    _strip_context_leak,
    _repair_truncation,
    _validate_translation,
    _deduplicate_repetition,
    _strip_trailing_summary,
    _strip_empty_parentheses,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY_BASE = 3.0
RETRY_DELAY_MAX = 30.0
_PROMPT_MAX_CHARS = 28_000
# 云端 API 两个请求之间的最小间隔（秒），防止触发 rate limit
_RATE_LIMIT_INTERVAL = 1.0


def _backoff_delay(attempt: int) -> float:
    """指数退避: base * 2^attempt, 上限 RETRY_DELAY_MAX"""
    delay = RETRY_DELAY_BASE * (2 ** attempt)
    return min(delay, RETRY_DELAY_MAX)

# ── 供应商预设（从 YAML 懒加载） ──

_PROVIDERS_YAML = Path(__file__).resolve().parents[4] / "config" / "providers.yaml"


def _load_provider_presets() -> dict[str, dict]:
    """从 config/providers.yaml 加载供应商预设，找不到则返回空字典。"""
    try:
        with open(_PROVIDERS_YAML, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("providers.yaml not found at %s, using empty presets", _PROVIDERS_YAML)
        return {}


PROVIDER_PRESETS: dict[str, dict] = _load_provider_presets()


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
        """初始化云端翻译客户端

        Args:
            provider: 供应商标识（对应 PROVIDER_PRESETS 的 key）
            base_url: API Base URL
            api_key: API 密钥
            model: 模型名称
            temperature: 生成温度
            max_tokens: 最大生成 token 数
            system_prompt: 自定义系统提示词
            timeout: HTTP 请求超时秒数
        """
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
        self._last_request_time: float = 0.0  # 速率限制追踪

    def _get_http_client(self) -> httpx.Client:
        """懒加载复用 httpx 连接（走系统代理，需安装 socksio 支持 SOCKS）"""
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.timeout)
        return self._http_client

    def close(self) -> None:
        """关闭底层 httpx 连接池，释放资源"""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def _rate_limit_wait(self) -> None:
        """确保两个 API 请求之间至少间隔 _RATE_LIMIT_INTERVAL 秒"""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _RATE_LIMIT_INTERVAL:
            wait = _RATE_LIMIT_INTERVAL - elapsed
            time.sleep(wait)
        self._last_request_time = time.monotonic()

    def translate(self, text: str, prev_translation: str = "") -> TranslationResult:
        """翻译单段文本，失败自动重试（指数退避）+ 速率限制"""
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                self._rate_limit_wait()
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
                        time.sleep(_backoff_delay(attempt))
                        continue
                self._prev_translation = result.translated
                self._glossary.update(text, result.translated)
                self._chunk_index += 1
                return result
            except (ConnectionError, ValueError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = _backoff_delay(attempt)
                    logger.warning("翻译失败，%.1f 秒后重试 (attempt %d): %s", delay, attempt + 1, e)
                    time.sleep(delay)

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
        """设置文档级上下文（标题+摘要），用于跨 chunk 保持一致性"""
        self._document_context = context.strip()

    def _post_process(self, translated: str) -> str:
        """后处理翻译结果"""
        translated = _strip_think_tags(translated)
        translated = _strip_code_block_wrapping(translated)
        translated = _strip_preamble(translated)
        translated = _strip_context_leak(translated)
        translated = _deduplicate_repetition(translated)
        translated = _strip_trailing_summary(translated)
        translated = _strip_empty_parentheses(translated)
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
                logger.debug("Failed to parse API error response body", exc_info=True)
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
                logger.debug("Failed to parse Anthropic error response body", exc_info=True)
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
        result, _ = self.health_check_detail()
        return result

    def health_check_detail(self) -> tuple[bool, str]:
        """检查云端 API 是否可用，返回 (是否成功, 错误原因)"""
        try:
            if self.api_format == "anthropic":
                return self._anthropic_health_check_detail()
            else:
                return self._openai_health_check_detail()
        except Exception as e:
            logger.debug("Cloud health check failed", exc_info=True)
            return False, f"连接异常: {e}"

    def _openai_health_check(self) -> bool:
        result, _ = self._openai_health_check_detail()
        return result

    def _openai_health_check_detail(self) -> tuple[bool, str]:
        """OpenAI 兼容 API 健康检查 — 尝试 /models 端点（不消耗 token）"""
        for path in ("/models", "/v1/models"):
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                client = self._get_http_client()
                resp = client.get(f"{self.base_url}{path}", headers=headers, timeout=10.0)
                if resp.status_code == 200:
                    return True, ""
                if resp.status_code == 401:
                    return False, "API Key 无效 (401 Unauthorized)"
                if resp.status_code == 403:
                    return False, "访问被拒绝 (403 Forbidden)，检查代理或网络设置"
                return False, f"HTTP {resp.status_code}"
            except httpx.TimeoutException:
                return False, f"连接 {self.base_url} 超时，请检查网络或代理设置"
            except httpx.HTTPError:
                continue

        # fallback: 发最小 chat 请求
        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                return True, ""
            if resp.status_code == 401:
                return False, "API Key 无效 (401 Unauthorized)"
            if resp.status_code == 403:
                return False, "访问被拒绝 (403 Forbidden)，检查代理或网络设置"
            return False, f"HTTP {resp.status_code}"
        except httpx.TimeoutException:
            return False, f"连接 {self.base_url} 超时，请检查网络或代理设置"
        except httpx.HTTPError as e:
            return False, f"连接错误: {e}"

    def _anthropic_health_check(self) -> bool:
        result, _ = self._anthropic_health_check_detail()
        return result

    def _anthropic_health_check_detail(self) -> tuple[bool, str]:
        """Anthropic API 健康检查 — 发送最小请求"""
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {"model": self.model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        try:
            client = self._get_http_client()
            resp = client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 200:
                return True, ""
            if resp.status_code == 401:
                return False, "API Key 无效 (401 Unauthorized)"
            if resp.status_code == 403:
                return False, "访问被拒绝 (403 Forbidden)，检查代理或网络设置"
            return False, f"HTTP {resp.status_code}"
        except httpx.TimeoutException:
            return False, f"连接 {self.base_url} 超时，请检查网络或代理设置"
        except httpx.HTTPError as e:
            return False, f"连接错误: {e}"
