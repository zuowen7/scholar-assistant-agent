"""Small no-op VRAM scheduler used when advanced scheduling is unavailable."""

from __future__ import annotations

from enum import Enum


class ContextRole(str, Enum):
    PLANNER = "planner"
    ACTOR = "actor"


class MultiplexingScheduler:
    def __init__(self, ollama_base_url: str = "http://localhost:11434", model: str = "qwen3:8b") -> None:
        self.ollama_base_url = ollama_base_url
        self.model = model
        self.role = ContextRole.PLANNER
        self._snapshot: list[dict] = []

    async def ensure_model(self) -> None:
        return None

    def enter_role(self, role: ContextRole) -> None:
        self.role = role

    async def switch_role(self, role: ContextRole) -> None:
        self.role = role

    def is_heavy_tool(self, name: str) -> bool:
        return name in {"translate_text", "parse_document"}

    def trim_to_budget(self, messages: list[dict]) -> list[dict]:
        return messages[-24:]

    def snapshot_context(self, messages: list[dict]) -> None:
        self._snapshot = list(messages)

    def restore_context(self, observation: str) -> list[dict]:
        restored = list(self._snapshot)
        if observation:
            restored.append({"role": "user", "content": f"Observation:\n{observation}"})
        return restored

    async def close(self) -> None:
        return None
