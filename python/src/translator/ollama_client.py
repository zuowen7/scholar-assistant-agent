"""Ollama 翻译客户端 - 调用本地 Qwen3 模型

核心优化:
1. 三级上下文: 文档摘要 + 术语表 + 滑动窗口
2. 自动术语提取与记忆
3. 翻译自检 + 质量验证
4. httpx 连接复用
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Sequence

import httpx

logger = logging.getLogger(__name__)

from src.translator._helpers import (
    TranslationResult,
    _extract_term_pairs,
    _strip_think_tags,
    _strip_code_block_wrapping,
    _strip_preamble,
    _strip_context_leak,
    _validate_translation,
    _repair_truncation,
    _strip_empty_parentheses,
    _strip_trailing_summary,
    _deduplicate_repetition,
)

MAX_RETRIES = 3
RETRY_DELAY_BASE = 3.0  # 基础重试延迟（秒），指数退避倍增
RETRY_DELAY_MAX = 30.0  # 最大重试延迟

_CONTEXT_WINDOW_LEN = 800
_GLOSSARY_MAX_TERMS = 30
_GLOSSARY_EXTRACTION_THRESHOLD = 0.3
# Prompt 总长度安全上限（字符数），防止超出模型 context window
_PROMPT_MAX_CHARS = 28_000


def _backoff_delay(attempt: int) -> float:
    """指数退避: base * 2^attempt, 上限 RETRY_DELAY_MAX"""
    delay = RETRY_DELAY_BASE * (2 ** attempt)
    return min(delay, RETRY_DELAY_MAX)



@dataclass
class GlossaryEntry:
    english: str
    chinese: str
    count: int = 1


class Glossary:
    """自动构建的术语表，跨 chunk 保持术语一致"""

    def __init__(self) -> None:
        self._entries: dict[str, GlossaryEntry] = {}

    def update(self, original: str, translated: str) -> None:
        pairs = _extract_term_pairs(original, translated)
        for en, zh in pairs:
            key = en.lower()
            if key in self._entries:
                entry = self._entries[key]
                if zh != entry.chinese:
                    entry.count += 1
                    if entry.count <= 5:
                        entry.chinese = zh
                else:
                    entry.count += 1
            else:
                self._entries[key] = GlossaryEntry(english=en, chinese=zh)

    def to_prompt_text(self) -> str:
        if not self._entries:
            return ""
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.count,
            reverse=True,
        )[:_GLOSSARY_MAX_TERMS]
        lines = [f"- {e.english} → {e.chinese}" for e in sorted_entries]
        return "\n".join(lines)


class OllamaClient:

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        temperature: float = 0.3,
        num_predict: int = 16384,
        system_prompt: str = "",
        timeout: float = 300.0,
    ) -> None:
        """初始化 Ollama 翻译客户端

        Args:
            base_url: Ollama 服务地址
            model: 模型名称（如 ``qwen3:8b``）
            temperature: 生成温度
            num_predict: 最大生成 token 数
            system_prompt: 自定义系统提示词
            timeout: HTTP 请求超时秒数
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.num_predict = num_predict
        self.system_prompt = system_prompt
        self.timeout = timeout

        self._prev_translation = ""
        self._document_context = ""
        self._glossary = Glossary()
        self._chunk_index = 0
        self._http_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._lock: asyncio.Lock | None = None  # 延迟初始化，避免在无事件循环的上下文中创建

    def _ensure_lock(self) -> asyncio.Lock:
        """延迟创建 Lock，确保在有事件循环的上下文中调用"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def set_document_context(self, context: str) -> None:
        """设置文档级上下文（标题+摘要），用于跨 chunk 保持一致性"""
        self._document_context = context.strip()

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                timeout=self.timeout,
                proxy=None,  # Ollama 在本地，不走系统代理
            )
        return self._http_client

    def close(self) -> None:
        """关闭底层 httpx 连接池，释放资源"""
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def translate(self, text: str, prev_translation: str = "") -> TranslationResult:
        """翻译单段文本，失败自动重试（指数退避）

        Args:
            text: 待翻译文本
            prev_translation: 前一段译文（用于上下文衔接）

        Returns:
            TranslationResult 含原文、译文、模型信息、token 统计

        Raises:
            ConnectionError: 无法连接 Ollama 服务
            ValueError: 重试耗尽后仍翻译失败
        """
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                # 最后一次尝试：丢掉 prev_translation 上下文，缩小 prompt 体积
                effective_ctx = "" if attempt == MAX_RETRIES else ctx
                result = self._call_api(text, effective_ctx)
                if not _validate_translation(result):
                    logger.warning(
                        "翻译结果过短 (attempt %d): original=%d chars, translated=%d chars",
                        attempt + 1,
                        len(result.original),
                        len(result.translated),
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
                    logger.warning(
                        "翻译失败，%.1f 秒后重试 (attempt %d): %s",
                        delay,
                        attempt + 1,
                        e,
                    )
                    time.sleep(delay)

        raise last_error if last_error else ValueError("翻译失败")

    def _build_system_prompt(self) -> str:
        """构建系统提示词，整合术语表和块索引

        三级上下文组装策略:
        - Level 1 (system prompt): 基础翻译指令 + 术语表
        - Level 2 (user prompt): 文档背景（标题+摘要）
        - Level 3 (user prompt): 前文翻译滑动窗口
        """
        parts = []

        # 默认翻译指令（如果用户未提供自定义system prompt）
        if not self.system_prompt:
            parts.append("You are a professional academic translator. Translate the given text from English to Chinese.")
        else:
            parts.append(self.system_prompt)

        # 段落结构保持指令（P1-2：降低段落对齐失败率）
        parts.append("""
CRITICAL: Preserve paragraph structure exactly.
- Input has N paragraphs separated by blank lines (\\n\\n).
- Output MUST have exactly N paragraphs separated by blank lines.
- Do NOT merge paragraphs. Do NOT split paragraphs.
- Do NOT add explanations, headers, or numbering.
- Do NOT include the original text in your output.
- Output ONLY the translation.

严格保持段落结构：输入有 N 段（用空行分隔），输出必须也是 N 段。不要合并、不要拆分、不要加序号、不要返回原文。""")

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

    def _build_prompt(self, text: str, prev_translation: str = "") -> str:
        prompt_parts = []

        if self._document_context:
            prompt_parts.append(
                f"[文档背景（不要翻译此部分）]\n{self._document_context}\n\n"
            )

        if prev_translation:
            snippet = prev_translation[-_CONTEXT_WINDOW_LEN:]
            prompt_parts.append(
                f"[前文翻译参考（不要翻译此部分，仅用于保持术语和风格一致）]\n"
                f"{snippet}\n\n"
            )

        # 计算段数并显式注明（P1-2：增强段落对齐）
        paragraph_count = len([p for p in text.split("\n\n") if p.strip()])
        prompt_parts.append(f"[请翻译以下内容（共 {paragraph_count} 段）]\n{text}")
        prompt = "".join(prompt_parts)

        if len(prompt) > _PROMPT_MAX_CHARS:
            ctx_budget = _PROMPT_MAX_CHARS - len(text) - 200
            if ctx_budget > 0 and prev_translation:
                snippet = prev_translation[-min(ctx_budget, _CONTEXT_WINDOW_LEN):]
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

    def _build_api_payloads(self, prompt: str) -> tuple[dict, dict]:
        system = self._build_system_prompt()
        options = {
            "temperature": self.temperature,
            "num_predict": self.num_predict,
            "repeat_penalty": 1.2,
        }
        chat_payload = {
            "model": self.model,
            "messages": (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": prompt}]
            ),
            "stream": False,
            "options": options,
        }
        generate_payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if system:
            generate_payload["system"] = system
        return chat_payload, generate_payload

    def _parse_response(self, data: dict, text: str) -> TranslationResult:
        if "message" in data:
            translated = (data.get("message") or {}).get("content") or ""
        else:
            translated = data.get("response") or ""
        translated = self._post_process(translated.strip())
        return TranslationResult(
            original=text,
            translated=translated,
            model=data.get("model", self.model),
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
        )

    def _call_api(self, text: str, prev_translation: str = "") -> TranslationResult:
        prompt = self._build_prompt(text, prev_translation)
        chat_payload, generate_payload = self._build_api_payloads(prompt)

        try:
            client = self._get_http_client()
            resp = client.post(f"{self.base_url}/api/chat", json=chat_payload)
            if resp.status_code >= 400:
                chat_error = f"Chat API HTTP {resp.status_code}"
                try:
                    resp = client.post(f"{self.base_url}/api/generate", json=generate_payload)
                except Exception:
                    raise ValueError(f"Chat API 和 Generate API 均失败（{chat_error}）")
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.base_url})，请确认 Ollama 已启动"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"翻译请求失败: HTTP {e.response.status_code}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Ollama 请求超时 ({self.timeout}s)，模型可能过载或 num_predict 过大"
            ) from e

        return self._parse_response(resp.json(), text)

    def health_check(self) -> bool:
        """检查 Ollama 服务是否在线（GET /api/tags）"""
        try:
            client = self._get_http_client()
            resp = client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


    # ── 异步并行翻译 ─────────────────────────────────────────────────────────

    async def _get_async_http_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    async def close_async(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    async def _call_api_async(
        self, text: str, prev_translation: str = "",
    ) -> dict:
        """异步调用 Ollama Chat API（不走重试，重试由外层 handle）"""
        prompt = self._build_prompt(text, prev_translation)
        chat_payload, generate_payload = self._build_api_payloads(prompt)

        try:
            client = await self._get_async_http_client()
            resp = await client.post(f"{self.base_url}/api/chat", json=chat_payload)
            if resp.status_code >= 400:
                chat_error = f"Chat API HTTP {resp.status_code}"
                try:
                    resp = await client.post(f"{self.base_url}/api/generate", json=generate_payload)
                except Exception:
                    raise ValueError(f"Chat API 和 Generate API 均失败（{chat_error}）")
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

        return resp.json()

    def _post_process(self, translated: str) -> str:
        """翻译后处理流水线"""
        translated = _strip_think_tags(translated)
        translated = _strip_code_block_wrapping(translated)
        translated = _strip_preamble(translated)
        translated = _strip_context_leak(translated)
        translated = _deduplicate_repetition(translated)
        translated = _strip_trailing_summary(translated)
        translated = _strip_empty_parentheses(translated)
        translated = _repair_truncation(translated)
        return translated

    async def translate_async(
        self, text: str, prev_translation: str = "",
    ) -> TranslationResult:
        """异步翻译单段，自动重试 + 状态更新（线程安全）

        Args:
            text: 待翻译文本
            prev_translation: 前一段译文（用于上下文衔接）

        Returns:
            TranslationResult
        """
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                effective_ctx = "" if attempt == MAX_RETRIES else ctx
                data = await self._call_api_async(text, effective_ctx)
                result = self._parse_response(data, text)

                if not _validate_translation(result):
                    logger.warning(
                        "翻译结果过短 (attempt %d): original=%d chars, translated=%d chars",
                        attempt + 1, len(text), len(result.translated),
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(_backoff_delay(attempt))
                        continue

                # 锁内顺序更新状态，保证 glossary 顺序正确
                async with self._ensure_lock():
                    self._prev_translation = result.translated
                    self._glossary.update(text, result.translated)
                    self._chunk_index += 1

                return result

            except (ConnectionError, ValueError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = _backoff_delay(attempt)
                    logger.warning(
                        "翻译失败，%.1f 秒后重试 (attempt %d): %s",
                        delay, attempt + 1, e,
                    )
                    await asyncio.sleep(delay)

        raise last_error if last_error else ValueError("翻译失败")

    async def translate_batch(
        self,
        chunks: Sequence[str],
        prev_translations: Sequence[str] | None = None,
        *,
        max_concurrency: int = 4,
    ) -> list[TranslationResult]:
        """并发翻译多个 chunk（保持顺序）

        使用 asyncio.Semaphore 控制并发数，避免 Ollama 过载。
        结果顺序与输入 chunks 顺序一致。

        Args:
            chunks: 待翻译文本块列表
            prev_translations: 每个 chunk 对应的前一段译文（可选，默认用滑动窗口）
            max_concurrency: 最大并发数（默认 4，建议 Ollama 2-4）
            on_progress: 进度回调 (completed: int, total: int)

        Returns:
            TranslationResult 列表（顺序与 chunks 一致）
        """
        if not chunks:
            return []

        n = len(chunks)
        prevs = prev_translations if prev_translations is not None else [self._prev_translation] * n
        sem = asyncio.Semaphore(max_concurrency)

        async def _translate_one(index: int, text: str, prev_t: str) -> tuple[int, TranslationResult]:
            async with sem:
                try:
                    result = await self.translate_async(text, prev_t)
                    return index, result
                except Exception as e:
                    logger.error("块 %d 翻译失败: %s", index + 1, e)
                    raise

        tasks = [
            _translate_one(i, chunks[i], prevs[i] if i < len(prevs) else "")
            for i in range(n)
        ]

        results: list[TranslationResult | None] = [None] * n
        completed = 0

        for coro in asyncio.as_completed(tasks):
            index, result = await coro
            results[index] = result
            completed += 1
            logger.debug("  并行翻译进度 %d/%d (块 %d)", completed, n, index + 1)

        # 验证所有结果都成功
        failed = [i for i, r in enumerate(results) if r is None]
        if failed:
            raise RuntimeError(f"以下块翻译失败: {failed}")

        return results  # type: ignore[return-value]



def translate(
    text: str,
    base_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    system_prompt: str = "",
) -> TranslationResult:
    """一次性翻译便捷函数（自动创建并关闭客户端）

    Args:
        text: 待翻译文本
        base_url: Ollama 服务地址
        model: 模型名称
        system_prompt: 自定义系统提示词

    Returns:
        TranslationResult
    """
    client = OllamaClient(base_url=base_url, model=model, system_prompt=system_prompt)
    try:
        return client.translate(text)
    finally:
        client.close()
