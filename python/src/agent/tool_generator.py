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
        """暂未实现，调用时显式提示未就绪。"""
        raise NotImplementedError(
            "Tool generation is not yet implemented. "
            "Set generate=True in agent config to enable dynamic generation.",
        )

    def generate_tool(self, tool_spec: Any) -> bool:
        raise NotImplementedError(
            "Tool generation is not yet implemented. "
            "Set generate=True in agent config to enable dynamic generation.",
        )


def create_tool_generator(registry: Any) -> ToolGenerator:
    return ToolGenerator(registry=registry)
