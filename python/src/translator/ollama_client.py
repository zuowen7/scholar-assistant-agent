"""Ollama 翻译客户端 - 调用本地 Qwen3 模型"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


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

    def translate(self, text: str) -> TranslationResult:
        """翻译单段文本

        Args:
            text: 待翻译的英文文本

        Returns:
            TranslationResult

        Raises:
            ConnectionError: Ollama 服务不可达
            ValueError: 翻译失败
        """
        payload = {
            "model": self.model,
            "prompt": text,
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

        data = resp.json()
        translated = data.get("response", "").strip()

        # 清理 Qwen3 的思考标签 <think >...</think > (如果出现)
        translated = _strip_think_tags(translated)

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
    import re

    return re.sub(r"<think\b[^>]*>.*?</think\s*>", "", text, flags=re.DOTALL).strip()
