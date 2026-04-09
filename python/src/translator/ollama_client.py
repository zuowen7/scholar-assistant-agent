"""Ollama 翻译客户端 - 调用本地 Qwen3 模型

核心优化:
1. 三级上下文: 文档摘要 + 术语表 + 滑动窗口
2. 自动术语提取与记忆
3. 翻译自检 + 质量验证
4. httpx 连接复用
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
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
class TranslationResult:
    original: str
    translated: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


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
                    if entry.count <= 2:
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

    def set_document_context(self, context: str) -> None:
        self._document_context = context.strip()

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self.timeout)
        return self._http_client

    def close(self) -> None:
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None

    def translate(self, text: str, prev_translation: str = "") -> TranslationResult:
        last_error: Exception | None = None
        ctx = prev_translation or self._prev_translation

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = self._call_api(text, ctx)
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

        raise last_error or ValueError("翻译失败")

    def _build_system_prompt(self) -> str:
        """构建系统提示词，整合术语表和块索引

        三级上下文组装策略:
        - Level 1 (system prompt): 基础翻译指令 + 术语表
        - Level 2 (user prompt): 文档背景（标题+摘要）
        - Level 3 (user prompt): 前文翻译滑动窗口
        """
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

    def _call_api(self, text: str, prev_translation: str = "") -> TranslationResult:
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

        prompt_parts.append(f"[请翻译以下内容]\n{text}")
        prompt = "".join(prompt_parts)

        # Token 安全保护：如果 prompt 总长度超出上限，裁剪上下文
        if len(prompt) > _PROMPT_MAX_CHARS:
            # 优先保留当前 chunk 文本，缩减上下文窗口
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

        system = self._build_system_prompt()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        if system:
            payload["system"] = system

        try:
            client = self._get_http_client()
            # 优先走 Chat API：与 Qwen3 等模型的对话模板对齐，指令遵循通常优于裸 generate
            chat_payload = {
                "model": self.model,
                "messages": (
                    ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": prompt}]
                ),
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.num_predict,
                },
            }
            resp = client.post(f"{self.base_url}/api/chat", json=chat_payload)
            if resp.status_code >= 400:
                # Chat API 失败，fallback 到 Generate API，保留原始错误信息
                chat_error = f"Chat API HTTP {resp.status_code}"
                try:
                    resp = client.post(f"{self.base_url}/api/generate", json=payload)
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

        data = resp.json()
        if "message" in data:
            translated = (data.get("message") or {}).get("content") or ""
        else:
            translated = data.get("response") or ""
        translated = translated.strip()

        translated = _strip_think_tags(translated)
        translated = _strip_code_block_wrapping(translated)
        translated = _strip_preamble(translated)
        translated = _strip_context_leak(translated)
        translated = _repair_truncation(translated)

        return TranslationResult(
            original=text,
            translated=translated,
            model=data.get("model", self.model),
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
        )

    def health_check(self) -> bool:
        try:
            client = self._get_http_client()
            resp = client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False


def translate(
    text: str,
    base_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    system_prompt: str = "",
) -> TranslationResult:
    client = OllamaClient(base_url=base_url, model=model, system_prompt=system_prompt)
    try:
        return client.translate(text)
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 术语提取
# ---------------------------------------------------------------------------

def _extract_term_pairs(original: str, translated: str) -> list[tuple[str, str]]:
    """从原文-译文对中提取可能的术语翻译对

    策略: 找译文中「中文（英文）」模式的括号注解，
    这些通常是模型按 system_prompt 要求标注的术语。
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    pattern = re.compile(
        r"([\u4e00-\u9fff][\u4e00-\u9fff\w\s]{1,20})"
        r"[（(]"
        r"([A-Za-z][A-Za-z\s\-/]+[A-Za-z])"
        r"[）)]"
    )
    for m in pattern.finditer(translated):
        zh_term = m.group(1).strip()
        en_term = m.group(2).strip()
        key = en_term.lower()
        if key not in seen and len(en_term) > 2:
            pairs.append((en_term, zh_term))
            seen.add(key)

    return pairs


# ---------------------------------------------------------------------------
# 后处理
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """移除推理模型常见思考段，避免进入正文。"""
    for tag in ("think", "redacted_thinking", "redacted_reasoning"):
        pat = rf"<{tag}\b[^>]*>.*?</{tag}\s*>"
        text = re.sub(pat, "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()


def _strip_code_block_wrapping(text: str) -> str:
    """移除 LLM 用 markdown 代码块包裹翻译结果的格式幻觉

    常见模式:
    ```markdown
    翻译内容...
    ```
    或
    ```
    翻译内容...
    ```
    """
    stripped = text.strip()
    # 匹配 ```lang\n...\n``` 或 ```\n...\n``` 模式
    m = re.match(r"^```(?:\w+)?\s*\n(.*?)\n```\s*$", stripped, re.DOTALL)
    if m:
        inner = m.group(1).strip()
        # 安全检查: 内部不应还有代码块（避免误剥嵌套的公式代码块）
        if inner.count("```") == 0:
            return inner
    return text


def _strip_preamble(text: str) -> str:
    preamble_pattern = re.compile(
        r"^(?:"
        r"(?:Here|Below|Following)\s+(?:is|are)\s+(?:the\s+)?(?:translation|result|translated\s+text)[：:]*\s*"
        r"|以下是翻译[：:]*\s*"
        r"|翻译如下[：:]*\s*"
        # 避免把正文「这是翻译结果」整句误删：要求冒号或换行后再接正文
        r"|这是翻译结果(?:[：:]+\s*|\n+\s*)"
        r"|下面是(?:翻译|译文)[：:]*\s*"
        r"|这是(?:翻译|译文)(?:[：:]+\s*|\n+\s*)"
        r"|(?:Sure|Certainly|Of\s+course)[，,\s]*(?:here|below)\s+(?:is|are)[^。\n]*[。.\n]\s*"
        r"|(?:好的|没问题|收到)[，,]?\s*(?:以下是翻译|以下是译文|翻译如下|下面是翻译|下面是译文)[：:]*\s*"
        r")",
        re.IGNORECASE,
    )
    return preamble_pattern.sub("", text).strip()


def _strip_context_leak(text: str) -> str:
    """去掉开头附近的指令回声；仅在扫描窗口内匹配，避免误伤正文。"""
    scan_len = 500
    head = text[:scan_len]
    ctx_markers = [
        "[文档背景",
        "[前文翻译参考",
        "（不要翻译此部分",
        "（仅用于保持术语",
        "[请翻译以下内容]",
    ]
    for marker in ctx_markers:
        idx = head.find(marker)
        if idx < 0:
            continue
        rest = text[idx:]
        if "\n\n" in rest[:2500]:
            _, sep, tail = rest.partition("\n\n")
            if sep:
                return tail.lstrip()
        return text[idx + len(marker) :].lstrip()
    return text.strip()


def _validate_translation(result: TranslationResult) -> bool:
    """校验翻译结果质量

    多层校验:
    1. 空值/极短检测
    2. 截断检测（译文过短）
    3. 未翻译检测（原文=译文）
    4. 语言检测（无中文字符）
    5. 格式幻觉检测（markdown 代码块包裹、多份重复翻译）
    """
    if not result.translated:
        return False
    orig = result.original
    trans = result.translated
    orig_len = len(orig)
    trans_len = len(trans)

    # 短块: 标题、图注等, 只要有输出就通过
    if orig_len < 100:
        return trans_len >= 1

    # 原文公式/LaTeX/代码占比高时不做强校验
    latexish = sum(1 for c in orig if c in "\\{}$[]_^") / max(orig_len, 1)
    if latexish > 0.04:
        return trans_len >= max(3, int(orig_len * 0.03))

    # 译文太短 (原文 > 100 字符但译文不到 3%) — 明显截断
    if orig_len > 100 and trans_len < orig_len * 0.03:
        return False

    # 译文与原文完全相同（去掉空白后） — 明显未翻译
    orig_no_space = re.sub(r"\s+", "", orig)
    trans_no_space = re.sub(r"\s+", "", trans)
    if orig_no_space and orig_no_space == trans_no_space:
        logger.warning("译文与原文完全相同，疑似未翻译")
        return False

    # CJK 占比检查: 如果完全没有中文字符且 ASCII 占比极高，判定未翻译
    cjk_n = sum(1 for c in trans if "\u4e00" <= c <= "\u9fff")
    cjk_ratio = cjk_n / max(trans_len, 1)
    if cjk_ratio < 0.05 and orig_len > 100:
        ascii_ratio = sum(1 for c in trans if c.isascii() and c.isalpha()) / max(trans_len, 1)
        if ascii_ratio > 0.95:
            logger.warning("译文 ASCII 占比 %.0f%% 且无中文，疑似未翻译: %.50s...", ascii_ratio * 100, trans)
            return False

    # 格式幻觉检测: LLM 用 markdown 代码块包裹翻译结果
    stripped = trans.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        logger.warning("译文被 markdown 代码块包裹，疑似格式幻觉")
        return False

    # 重复翻译检测: 译文前半段和后半段高度重复（>80% 相同）
    if trans_len > 400:
        half = trans_len // 2
        first_half = stripped[:half]
        second_half = stripped[half:half * 2]
        if first_half and second_half and len(first_half) > 50:
            # 计算两半的前 100 字符重复率
            shorter_len = min(len(first_half), len(second_half), 100)
            overlap = sum(1 for a, b in zip(first_half[:shorter_len], second_half[:shorter_len]) if a == b)
            if overlap / shorter_len > 0.8:
                logger.warning("译文前后半段高度重复 (%.0f%%)，疑似重复翻译", overlap / shorter_len * 100)
                return False

    return True


def _repair_truncation(text: str) -> str:
    if not text:
        return text

    n = len(text)
    # 短文本（< 100 字符）不进行截断修复，避免误删标题或图注
    if n < 100:
        return text

    zh_endings = ["。", "！", "？", "；", "…"]
    en_endings = ["!", "?"]

    last_zh = max((text.rfind(c) for c in zh_endings), default=-1)
    last_en = max((text.rfind(c) for c in en_endings), default=-1)

    # 对 "." 单独处理：排除小数点 (3.14)、缩写 (Fig. Dr.)、省略号 (...) 等误匹配
    last_dot = text.rfind(".")
    if last_dot >= 0:
        before = text[:last_dot].rstrip()
        # 排除小数点: 前面紧跟数字
        if before and before[-1].isdigit():
            last_dot = -1
        # 排除省略号: 前面紧跟 .
        elif before and before[-1] == ".":
            last_dot = -1
        # 排除常见缩写
        elif before and re.search(
            r"(?:Fig|Eq|Ref|Vol|No|Dr|Mr|Mrs|Prof|Sr|Jr|St|vs|etc|al|ed|e\.g|i\.e)$",
            before, re.IGNORECASE
        ):
            last_dot = -1

    last_en = max(last_en, last_dot)

    last_sentence_end = max(last_zh, last_en)

    # 仅当「最后一句边界」落在文末附近时尝试修剪，避免误删未打句号的整段译文
    if last_sentence_end >= 0 and last_sentence_end < n - 1 and last_sentence_end >= int(n * 0.75):
        tail = text[last_sentence_end + 1 :].strip()
        tail_cjk = sum(1 for c in tail if "\u4e00" <= c <= "\u9fff")
        if (
            0 < len(tail) < min(120, int(n * 0.12))
            and tail_cjk == 0
            and not re.search(r"[\w\u4e00-\u9fff]{6,}", tail)
        ):
            logger.info("截断修复: 移除末尾疑似残缺片段 (%d 字符)", len(tail))
            return text[: last_sentence_end + 1].rstrip()
    return text


def _restore_paragraphs(original: str, translated: str) -> str:
    """译文缺少段落分隔时，按原文段落比例恢复 \n\n 分段。

    模型常把多段译文合并为一段，此函数按原文各段的字符占比，
    在中文句号/问号/感叹号处切割译文，恢复与原文对应的段落结构。
    """
    orig_paras = [p.strip() for p in original.split("\n\n") if p.strip()]
    if len(orig_paras) <= 1:
        return translated

    # 译文已经有足够的段落分隔 → 无需修复
    trans_paras = [p.strip() for p in translated.split("\n\n") if p.strip()]
    if len(trans_paras) >= len(orig_paras):
        return translated

    # 找出译文中所有中文句末位置
    sentence_ends = []
    for i, c in enumerate(translated):
        if c in "。！？；":
            sentence_ends.append(i + 1)
    if len(sentence_ends) < len(orig_paras) - 1:
        return translated  # 句末太少，无法安全分割

    # 按原文各段长度占比，在最近的句号处切分
    total_orig = sum(len(p) for p in orig_paras)
    cumulative = 0
    split_positions: list[int] = []
    used = set()
    for para in orig_paras[:-1]:
        cumulative += len(para)
        ratio = cumulative / total_orig
        target_char = int(len(translated) * ratio)
        # 找距离目标位置最近的句末（且未被用过）
        best = min(
            (p for p in sentence_ends if p not in used),
            key=lambda pos: abs(pos - target_char),
            default=None,
        )
        if best is not None:
            split_positions.append(best)
            used.add(best)

    if not split_positions:
        return translated

    # 按位置排序后拼接
    result = []
    prev = 0
    for pos in sorted(split_positions):
        result.append(translated[prev:pos].strip())
        prev = pos
    result.append(translated[prev:].strip())

    return "\n\n".join(result)
