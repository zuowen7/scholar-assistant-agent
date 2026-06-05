"""Sub-agent — 参考 claw-code agents.rs。

主 Agent 可调用 run_sub_agent 委派子任务（审查/解释/实施/翻译），
子 Agent 使用相同 Provider 但不同 system prompt，结果返回主 Agent。
"""
from __future__ import annotations

import json
from typing import Any

from src.agent_v2.tools.registry import ToolRegistry, ToolResult

# 预设模式 → system prompt（参考 claw-code Preset）
_PRESETS: dict[str, str] = {
    "audit": (
        "You are a precise academic auditor. Review the following content for:\n"
        "1. Logical flaws and unsupported claims\n"
        "2. Missing citations or references\n"
        "3. Clarity issues and ambiguity\n"
        "4. Structural problems\n"
        "Provide a numbered list of findings. Be specific. Suggest concrete fixes."
    ),
    "explain": (
        "You are an academic writing coach. Explain the following content clearly:\n"
        "1. Break down complex concepts into simple terms\n"
        "2. Provide examples where helpful\n"
        "3. Highlight connections between ideas\n"
        "4. Summarize key points\n"
        "Use a pedagogical tone. Structure with headings."
    ),
    "implement": (
        "You are an academic editor. Implement the requested changes to the following content:\n"
        "1. Follow the instructions precisely\n"
        "2. Maintain the original academic tone and citations\n"
        "3. Make minimal but effective changes\n"
        "4. Output the complete modified text\n"
        "Do NOT just describe changes — output the actual modified content."
    ),
    "translate": (
        "You are a professional academic translator. Translate the following content:\n"
        "1. Preserve all technical terms, formulas, and citations exactly as-is\n"
        "2. Maintain the original paragraph structure\n"
        "3. Use natural, fluent academic language\n"
        "4. Translate everything — do not skip or summarize\n"
        "Output the complete translation."
    ),
}


def register_sub_agent(registry: ToolRegistry) -> None:
    """注册 run_sub_agent 工具。"""

    async def run_sub_agent(args: dict) -> ToolResult:
        preset = str(args.get("preset", "explain"))
        content = str(args.get("content", ""))
        instruction = str(args.get("instruction", ""))

        if not content:
            return ToolResult("error: content is required", is_error=True)

        preset_key = preset.lower()
        system_prompt = _PRESETS.get(preset_key)
        if system_prompt is None:
            available = ", ".join(_PRESETS.keys())
            return ToolResult(f"error: unknown preset '{preset}'. Available: {available}", is_error=True)

        # Build messages for sub-agent
        user_msg = content
        if instruction:
            user_msg = f"Instruction: {instruction}\n\nContent:\n{content}"

        from src.agent_v2.types import Message, MessageRole, TextBlock

        messages = [Message(role=MessageRole.USER, blocks=[TextBlock(text=user_msg)])]

        # Use the provider from the parent runtime (stored in registry context)
        provider = getattr(registry, '_provider', None)
        if provider is None:
            return ToolResult("error: sub-agent requires provider (set registry._provider)", is_error=True)

        try:
            resp = await provider.chat(
                messages=messages,
                tools=None,  # sub-agents don't use tools
                system_prompt=system_prompt,
                max_tokens=4096,
                temperature=0.3,
            )
            text = resp.text_content()
            if not text.strip():
                return ToolResult(f"[{preset}] (no output)", is_error=True)
            return ToolResult(f"[{preset}]\n{text}")
        except Exception as e:
            return ToolResult(f"sub-agent [{preset}] error: {e}", is_error=True)

    registry.register("run_sub_agent", (
        "Run a specialized sub-agent to audit, explain, implement, or translate content. "
        "Use this for complex multi-step tasks. Available presets: audit, explain, implement, translate."
    ), {
        "type": "object",
        "properties": {
            "preset": {"type": "string", "description": "Sub-agent preset: audit, explain, implement, translate"},
            "content": {"type": "string", "description": "Content for the sub-agent to process"},
            "instruction": {"type": "string", "description": "Optional specific instruction for the sub-agent"},
        },
        "required": ["preset", "content"],
    }, run_sub_agent, permission="read-only")
