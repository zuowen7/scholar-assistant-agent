"""ConversationRuntime — 统一 Agent 对话循环（真流式）。

参考 claw-code:
  - runtime/conversation.rs: ConversationRuntime + stream_message
  - claw-analog/src/lib.rs: dispatch_tool + turn loop + session persist
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator

from src.agent_v2.runtime.permissions import (
    PermissionMode,
    PermissionPolicy,
    PermissionResult,
    policy_from_registry,
)
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import ToolRegistry, ToolResult
from src.agent_v2.types import (
    AgentEvent,
    AgentEventType,
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)

_DEFAULT_MAX_STEPS = 20
_TOOL_RESULT_MAX_CHARS = 4000


class ConversationRuntime:
    """统一 Agent 对话循环（真流式）。

    参考 claw-code:
      - provider 支持 chat_stream (SSE) 或 chat (降级)
      - 每轮结束后自动保存 session
      - 工具执行前通过 enforcer 检查权限
    """

    def __init__(
        self,
        provider: Any,
        tool_registry: ToolRegistry,
        permission_policy: PermissionPolicy,
        session: Session,
        max_steps: int = _DEFAULT_MAX_STEPS,
        system_prompt: str | None = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.permission_policy = permission_policy
        self.session = session
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    # ---- Public API ----

    async def turn(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        """单轮对话。yield AgentEvent 序列（实时流式）。含重试恢复。"""
        if not user_message.strip():
            yield AgentEvent.error("empty message")
            yield AgentEvent.done()
            return

        yield AgentEvent.session_started(self.session.session_id)

        self.session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=user_message)]))
        self._auto_save()

        for step in range(self.max_steps):
            for retry in range(3):
                try:
                    async for event in self._llm_turn():
                        yield event
                        if event.type in (AgentEventType.ERROR, AgentEventType.RESPONSE):
                            self._auto_save()
                            yield AgentEvent.done()
                            return
                        if event.type == AgentEventType.DONE:
                            return
                    break  # _llm_turn succeeded without exception
                except ApiError as e:
                    if e.status_code == 429 and retry < 2:
                        wait = e.retry_after or (2 ** retry)
                        import asyncio
                        yield AgentEvent.token(f"\n[Rate limited, retrying in {wait:.0f}s...]\n")
                        await asyncio.sleep(wait)
                        continue
                    yield AgentEvent.error(f"API error: {e}")
                    yield AgentEvent.done()
                    return
                except Exception as e:
                    if retry < 2:
                        import asyncio
                        yield AgentEvent.token(f"\n[Error, retrying ({retry+1}/3)...]\n")
                        await asyncio.sleep(1.0)
                        continue
                    logger.exception("unexpected error in turn")
                    yield AgentEvent.error(f"unexpected error: {e}")
                    yield AgentEvent.done()
                    return
        else:
            yield AgentEvent.error(f"max steps ({self.max_steps}) reached")
            yield AgentEvent.done()

    # ---- Internal ----

    async def _llm_turn(self) -> AsyncGenerator[AgentEvent, None]:
        """单次 LLM 往返：非流式调用 → parse → tool_calls → execute → loop。

        默认非流式以确保所有 provider 兼容。设置 SCHOLAR_AGENT_STREAM=1 启用流式。
        """
        import os
        messages = self.session.messages

        use_stream = os.environ.get("SCHOLAR_AGENT_STREAM", "").strip() == "1"
        provider_stream = None

        if use_stream and hasattr(self.provider, "chat_stream"):
            provider_stream = self.provider.chat_stream(
                messages=messages,
                tools=self.tool_registry.definitions(),
                system_prompt=self.system_prompt,
            )
        else:
            # 默认非流式 — 可靠兼容所有 provider
            resp = await self.provider.chat(
                messages=messages,
                tools=self.tool_registry.definitions(),
                system_prompt=self.system_prompt,
            )
            provider_stream = _fallback_stream(resp)

        tool_blocks = []
        text_blocks = []
        thinking_seen = False

        async for chunk in provider_stream:
            if isinstance(chunk, TextBlock):
                text_blocks.append(chunk)
                yield AgentEvent.token(chunk.text)
            elif isinstance(chunk, ThinkingBlock):
                thinking_seen = True
                yield AgentEvent.thought(chunk.thinking)
            elif isinstance(chunk, ToolUseBlock):
                tool_blocks.append(chunk)
                yield AgentEvent.tool_call(chunk.id, chunk.name, chunk.input)
            elif isinstance(chunk, TokenUsage):
                if chunk.total() > 0:
                    yield AgentEvent.usage(chunk)
            elif isinstance(chunk, ProviderResponse):
                # Final assembled response — emit usage and check tool calls
                if chunk.usage.total() > 0:
                    yield AgentEvent.usage(chunk.usage)

                # Fallback: if individual stream tracking produced nothing,
                # use the blocks from the ProviderResponse directly.
                if not tool_blocks and not text_blocks:
                    for b in chunk.blocks:
                        if isinstance(b, TextBlock):
                            text_blocks.append(b)
                        elif isinstance(b, ToolUseBlock):
                            tool_blocks.append(b)

                # Assemble assistant message
                assistant_blocks = []
                full_text = ""
                for tb in tool_blocks:
                    assistant_blocks.append(tb)
                if text_blocks:
                    full_text = "".join(b.text for b in text_blocks)
                    assistant_blocks.append(TextBlock(text=full_text))

                if assistant_blocks:
                    self.session.append(Message(role=MessageRole.ASSISTANT, blocks=assistant_blocks, usage=chunk.usage))

                # 2. 没有 tool_call → 最终回复
                if not tool_blocks:
                    if full_text.strip():
                        yield AgentEvent.response(full_text)
                    else:
                        yield AgentEvent.error("empty response from LLM")
                    return

                # 3. 执行工具调用
                for tb in tool_blocks:
                    async for evt in self._execute_tool(tb):
                        yield evt

                return

    async def _execute_tool(self, tb: ToolUseBlock) -> AsyncGenerator[AgentEvent, None]:
        """执行单个 tool_call，含权限检查 + diff 预览。"""
        # Parse args
        args = {}
        try:
            if tb.input:
                args = json.loads(tb.input)
        except json.JSONDecodeError:
            args = {}

        # Permission check
        perm_result = self.permission_policy.authorize(tb.name, tb.input)

        # Capture old content for diff preview
        old_text = ""
        new_text = ""
        file_path = args.get("file_path", "") or args.get("path", "")
        if tb.name == "str_replace":
            old_text = args.get("old_string", "")
            new_text = args.get("new_string", "")
        elif tb.name == "write_file":
            new_text = args.get("content", "")
            if file_path:
                try:
                    ws = self.tool_registry._resolve_path(file_path) if hasattr(self.tool_registry, '_resolve_path') else None
                    if ws is None and hasattr(self.tool_registry, '_workspace_root') and self.tool_registry._workspace_root:
                        from pathlib import Path
                        ws = Path(file_path) if Path(file_path).is_absolute() else (self.tool_registry._workspace_root / file_path)
                    if ws and ws.is_file():
                        old_text = ws.read_text(encoding="utf-8", errors="replace")[:4000]
                except Exception:
                    pass

        # For file-modifying tools, always emit approval event for frontend diff UI
        if tb.name in ("write_file", "str_replace"):
            yield AgentEvent.await_approval(
                tb.id, tb.name, f"Editing {file_path}",
                preview={"old_text": old_text, "new_text": new_text, "file_path": file_path},
            )

        if perm_result.is_denied:
            yield AgentEvent.tool_denied(tb.id, tb.name, perm_result.reason)
            tool_output = f"Permission denied: {perm_result.reason}"
            is_error = True
        elif perm_result.needs_approval:
            # Non-interactive: auto-deny
            tool_output = f"Requires approval: {perm_result.reason}"
            is_error = True
        else:
            # Execute
            result = await self.tool_registry.execute(tb.name, args)
            tool_output = result.output
            is_error = result.is_error

        yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=is_error)

        # 文件修改后发送 checkpoint，通知前端刷新文件树和编辑器
        if tb.name in ("write_file", "str_replace") and not is_error:
            try:
                fp = args.get("file_path", "") or args.get("path", "")
            except Exception:
                fp = ""
            yield AgentEvent.checkpoint({
                "action": tb.name,
                "file": fp,
                "workspace": self.session.meta.workspace,
            })

        self.session.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id=tb.id, tool_name=tb.name,
                            output=tool_output[:_TOOL_RESULT_MAX_CHARS], is_error=is_error),
        ]))

    def _auto_save(self) -> None:
        """Save session after each turn if a save path is configured."""
        sp = getattr(self.session, '_save_path', '')
        if sp and sp.strip():
            try:
                self.session.save_with_rotate(sp)
            except Exception as e:
                logger.warning("auto-save session failed: %s", e)


async def _fallback_stream(resp: ProviderResponse) -> AsyncGenerator:
    """将非流式响应模拟为流式。"""
    for block in resp.blocks:
        yield block
    if resp.usage.total() > 0:
        yield resp.usage
    yield resp
