"""Placeholder dynamic tool generator.

The full product can grow dynamic tools later; this minimal implementation
keeps the Agent importable and safely declines generation requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolGenerator:
    registry: Any

    def generate_from_llm_request(self, llm_request: str, task_description: str = "") -> None:
        return None

    def generate_tool(self, tool_spec: Any) -> bool:
        return False


def create_tool_generator(registry: Any) -> ToolGenerator:
    return ToolGenerator(registry=registry)
