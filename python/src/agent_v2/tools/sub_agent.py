"""Sub-agent — 参考 claw-code agents.rs。

主 Agent 可调用 run_sub_agent 委派子任务（审查/解释/实施/翻译），
子 Agent 使用相同 Provider 但不同 system prompt，结果返回主 Agent。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from src.agent_v2.runtime.session import Session, SessionFork
from src.agent_v2.tools.registry import ToolRegistry, ToolResult
from src.agent_v2.types import Message, MessageRole, TextBlock

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
        timeout_seconds = max(1, min(int(args.get("timeout_seconds", 60)), 120))
        max_tokens = max(256, min(int(args.get("max_tokens", 4096)), 4096))

        if not content:
            return ToolResult("error: content is required", is_error=True)

        preset_key = preset.lower()
        system_prompt = _PRESETS.get(preset_key)
        if system_prompt is None:
            available = ", ".join(_PRESETS.keys())
            return ToolResult(
                f"error: unknown preset '{preset}'. Available: {available}", is_error=True
            )

        # Build messages for sub-agent
        user_msg = content
        if instruction:
            user_msg = f"Instruction: {instruction}\n\nContent:\n{content}"

        messages = [Message(role=MessageRole.USER, blocks=[TextBlock(text=user_msg)])]

        # Use the provider from the parent runtime (stored in registry context)
        provider = (
            registry.get_provider()
            if hasattr(registry, "get_provider")
            else getattr(registry, "_provider", None)
        )
        if provider is None:
            return ToolResult(
                "error: sub-agent requires provider (call registry.set_provider() first)",
                is_error=True,
            )

        context = registry.get_runtime_context()
        parent_session_id = str(context.get("parent_session_id", ""))
        sub_session = Session(
            workspace=str(context.get("workspace", "")),
            model=str(getattr(provider, "model", "")),
            session_id=f"sub_{uuid.uuid4().hex[:12]}",
        )
        if parent_session_id:
            sub_session.fork_meta = SessionFork(
                parent_session_id=parent_session_id,
                branch_name=f"sub-agent:{preset_key}",
            )
        sub_session.append(messages[0])
        sub_session.set_outcome(
            "RUNNING",
            {
                "preset": preset_key,
                "parent_session_id": parent_session_id,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
            },
        )
        parent_session_path = str(context.get("parent_session_path", ""))
        sub_session_path: Path | None = None
        if parent_session_path:
            parent_path = Path(parent_session_path)
            sub_session_path = (
                parent_path.parent
                / "subagents"
                / (parent_session_id or "detached")
                / f"{sub_session.session_id}.jsonl"
            )
            sub_session.save(sub_session_path)

        def persist_sub_session() -> None:
            if sub_session_path is not None:
                sub_session.save(sub_session_path)

        try:
            resp = await asyncio.wait_for(
                provider.chat(
                    messages=messages,
                    tools=[],  # Sub-agent budget does not admit nested tools.
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=0.3,
                ),
                timeout=timeout_seconds,
            )
            text = resp.text_content()
            if not text.strip():
                sub_session.set_outcome(
                    "FAILED",
                    {"stop_code": "empty_response", "parent_session_id": parent_session_id},
                )
                persist_sub_session()
                return ToolResult(f"[{preset}] (no output)", is_error=True)
            sub_session.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    blocks=[TextBlock(text=text)],
                    usage=resp.usage,
                )
            )
            sub_session.set_outcome(
                "COMPLETE",
                {
                    "preset": preset_key,
                    "parent_session_id": parent_session_id,
                    "usage": {
                        "input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens,
                    },
                },
            )
            persist_sub_session()
            return ToolResult(
                f"[{preset}]\n{text}",
                metadata={
                    "sub_agent_run_id": sub_session.session_id,
                    "parent_session_id": parent_session_id,
                    "sub_agent_state": "COMPLETE",
                    "sub_agent_usage": {
                        "input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens,
                    },
                    "sub_agent_session_path": str(sub_session_path or ""),
                },
            )
        except TimeoutError:
            sub_session.set_outcome(
                "FAILED",
                {
                    "stop_code": "timeout",
                    "parent_session_id": parent_session_id,
                    "timeout_seconds": timeout_seconds,
                },
            )
            persist_sub_session()
            return ToolResult(
                f"sub-agent [{preset}] timed out after {timeout_seconds}s",
                is_error=True,
                metadata={
                    "sub_agent_run_id": sub_session.session_id,
                    "parent_session_id": parent_session_id,
                    "sub_agent_state": "FAILED",
                },
            )
        except asyncio.CancelledError:
            sub_session.set_outcome(
                "ABORTED",
                {"stop_code": "cancelled", "parent_session_id": parent_session_id},
            )
            persist_sub_session()
            raise
        except Exception as e:
            sub_session.set_outcome(
                "FAILED",
                {
                    "stop_code": "provider_error",
                    "parent_session_id": parent_session_id,
                    "message": str(e),
                },
            )
            persist_sub_session()
            return ToolResult(
                f"sub-agent [{preset}] error: {e}",
                is_error=True,
                metadata={
                    "sub_agent_run_id": sub_session.session_id,
                    "parent_session_id": parent_session_id,
                    "sub_agent_state": "FAILED",
                },
            )

    registry.register(
        "run_sub_agent",
        (
            "Run a one-shot specialist model call to audit, explain, implement, or translate "
            "provided content. It has no tools and cannot delegate or perform multi-step "
            "workspace work. Available presets: audit, explain, implement, translate."
        ),
        {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "description": "Sub-agent preset: audit, explain, implement, translate",
                },
                "content": {
                    "type": "string",
                    "description": "Content for the sub-agent to process",
                },
                "instruction": {
                    "type": "string",
                    "description": "Optional specific instruction for the sub-agent",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 120,
                    "default": 60,
                },
                "max_tokens": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 4096,
                    "default": 4096,
                },
            },
            "required": ["preset", "content"],
        },
        run_sub_agent,
        permission="read-only",
        effects={"cost"},
        approval_scope="exact-input",
    )
