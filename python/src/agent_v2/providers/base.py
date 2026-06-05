"""Base Provider ABC。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.agent_v2.types import Message, ProviderResponse, ToolDefinition


class BaseProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ProviderResponse:
        ...
