"""Ollama 翻译客户端 - 调用本地 Qwen3 模型"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 3.0  # 秒


@dataclass
class TranslationResult:
    """翻译结果"""

    original: str
    translated: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class OllamaClient:
    """Ollama REST API 客户端"""

    _CONTEXT_SNIPPET_LEN = 300

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        temperature: float = 0.3,
        num_predict: int = 16384,
        system_prompt: str = "",
        timeout: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.num_predict = num_predict
        self.system_prompt = system_prompt
        self.timeout = timeout
        self._prev_translation = ""

    def translate(self, text: str, prev_translation: str = "") -> TranslationResult:
        """翻译单段文本，失败自动重试

        Args:
            text: 待翻译的英文文本
            prev_translation: 前一个 chunk 的翻译结果，用于保持术语一致性

        Returns:
            TranslationResult

        Raises:
            ConnectionError: Ollama 服务不可达
            ValueError: 翻译失败
        """
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = self._call_api(text, ctx)
                if not _validate_translation(result):
                    logger.warning(
                        "翻译结果过短 (attempt %d): original=%d chars, translated=%d chars",
                        attempt + 1, len(result.original), len(result.translated),
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)
                        continue
                self._prev_translation = result.translated
                return result
            except (ConnectionError, ValueError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    logger.warning("翻译失败，%d 秒后重试 (attempt %d): %s", RETRY_DELAY, attempt + 1, e)
                    time.sleep(RETRY_DELAY)

        raise last_error or ValueError("翻译失败")

    def _call_api(self, text: str, prev_translation: str = "") -> TranslationResult:
        """实际调用 Ollama API"""
        prompt = text
        if prev_translation:
            snippet = prev_translation[-self._CONTEXT_SNIPPET_LEN:]
            prompt = (
                f"[前文翻译参考（仅用于保持术语和风格一致，不要翻译此部分）]\n"
                f"{snippet}\n\n"
                f"[请翻译以下内容]\n{text}"
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        if self.system_prompt:
            payload["system"] = self.system_prompt

        try:
            resp = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.base_url})，请确认 Ollama 已启动"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(f"翻译请求失败: HTTP {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Ollama 请求超时 ({self.timeout}s)，模型可能过载或 num_predict 过大"
            ) from e

        data = resp.json()
        translated = (data.get("response") or "").strip()

        translated = _strip_think_tags(translated)
        translated = _strip_preamble(translated)
        translated = _strip_context_leak(translated)
        translated = _repair_truncation(translated)

        return TranslationResult(
            original=text,
            translated=translated,
            model=data.get("model", self.model),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    def health_check(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


def translate(
    text: str,
    base_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    system_prompt: str = "",
) -> TranslationResult:
    """翻译文本（快捷函数）

    Args:
        text: 待翻译文本
        base_url: Ollama 地址
        model: 模型名称
        system_prompt: 系统提示词

    Returns:
        TranslationResult
    """
    client = OllamaClient(base_url=base_url, model=model, system_prompt=system_prompt)
    return client.translate(text)


def _strip_think_tags(text: str) -> str:
    """移除 Qwen3 的 <think >...</think > 标签"""
    return re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _strip_preamble(text: str) -> str:
    """移除模型可能输出的前言（如 "Here is the translation:", "以下是翻译："等）"""
    preamble_pattern = re.compile(
        r"^(?:"
        r"(?:Here|Below|Following)\s+(?:is|are)\s+(?:the\s+)?(?:translation|result|translated\s+text)[：:]*\s*"
        r"|以下是翻译[：:]*\s*"
        r"|翻译如下[：:]*\s*"
        r"|(?:Sure|Certainly|Of\s+course)[，,\s]*(?:here|below)\s+(?:is|are)[^。\n]*[。.\n]\s*"
        r"|(?:好的|没问题)[，,]?\s*(?:以下是|翻译如下)[：:]*\s*"
        r")",
        re.IGNORECASE,
    )
    return preamble_pattern.sub("", text).strip()


def _strip_context_leak(text: str) -> str:
    """移除模型误翻译了上下文参考部分的内容"""
    ctx_markers = [
        "[前文翻译参考",
        "（仅用于保持术语",
        "[请翻译以下内容]",
    ]
    for marker in ctx_markers:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx].rstrip()
    return text.strip()


def _validate_translation(result: TranslationResult) -> bool:
    """校验翻译结果质量"""
    if not result.translated:
        return False
    orig_len = len(result.original)
    trans_len = len(result.translated)
    # 译文不到原文 10% 且原文较长 → 疑似截断
    if orig_len > 100 and trans_len < orig_len * 0.1:
        return False
    # 译文极短但原文有一定长度 → 翻译失败 (放宽中文阈值: 英50字→中可能15字)
    if trans_len < max(10, orig_len * 0.2) and orig_len > 30:
        return False
    return True


def _repair_truncation(text: str) -> str:
    """尝试修复被截断的翻译（如句子在中间被截断）"""
    if not text:
        return text
    last_sentence_end = max(
        text.rfind("。"),
        text.rfind("！"),
        text.rfind("？"),
        text.rfind("；"),
        text.rfind("."),
        text.rfind("!"),
        text.rfind("?"),
    )
    if last_sentence_end >= 0 and last_sentence_end < len(text) - 1:
        tail = text[last_sentence_end + 1:].strip()
        if len(tail) < len(text) * 0.15 and len(tail) > 0:
            logger.info("截断修复: 移除末尾 %d 字符不完整片段", len(tail))
            return text[: last_sentence_end + 1].rstrip()
    return text
