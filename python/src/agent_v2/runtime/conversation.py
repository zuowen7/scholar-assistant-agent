"""ConversationRuntime — 统一 Agent 对话循环（真流式 + 审批暂停）。

参考 claw-code:
  - runtime/conversation.rs: ConversationRuntime + stream_message
  - claw-analog/src/lib.rs: dispatch_tool + turn loop + session persist
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from src.agent_v2.runtime.permissions import (
    PermissionMode,
    PermissionPolicy,
    policy_from_registry,
)
from src.agent_v2.runtime.session import Session
from src.agent_v2.runtime.usage import UsageTracker, pricing_for_model
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
_APPROVAL_TIMEOUT = 120.0  # 2 分钟等用户审批
_TOOL_RESULT_MAX_CHARS = 4000


class ConversationRuntime:
    """统一 Agent 对话循环（真流式 + 审批暂停）。"""

    def __init__(
        self,
        provider: Any,
        tool_registry: ToolRegistry,
        permission_policy: PermissionPolicy,
        session: Session,
        max_steps: int = _DEFAULT_MAX_STEPS,
        system_prompt: str | None = None,
        auto_approve: bool = True,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.permission_policy = permission_policy
        self.session = session
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.auto_approve = auto_approve
        self.usage = UsageTracker(model=session.meta.model)
        # Approval state
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._aborted = False
        self._planning_retried = False

    # ---- Public API ----

    async def turn(self, user_message: str) -> AsyncGenerator[AgentEvent, None]:
        if not user_message.strip():
            yield AgentEvent.error("empty message")
            yield AgentEvent.done()
            return

        yield AgentEvent.session_started(self.session.session_id)
        self.session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=user_message)]))
        self._auto_save()

        for step in range(self.max_steps):
            if self._aborted:
                yield AgentEvent.aborted("Session aborted by user")
                yield AgentEvent.done()
                return

            for retry in range(3):
                try:
                    async for event in self._llm_turn():
                        yield event
                        if event.type in (AgentEventType.RESPONSE, AgentEventType.ERROR):
                            self._auto_save()
                            yield AgentEvent.usage(TokenUsage(
                                input_tokens=self.usage.total_input,
                                output_tokens=self.usage.total_output,
                            ))
                            yield AgentEvent.done()
                            return
                        if event.type == AgentEventType.DONE:
                            return
                    break
                except ApiError as e:
                    if e.status_code == 429 and retry < 2:
                        wait = e.retry_after or (2 ** retry)
                        yield AgentEvent.token(f"\n[Rate limited, retrying in {wait:.0f}s...]\n")
                        await asyncio.sleep(wait)
                        continue
                    yield AgentEvent.error(f"API error: {e}")
                    yield AgentEvent.done()
                    return
                except Exception as e:
                    if retry < 2:
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

    def approve(self, event_id: str, decision: str) -> bool:
        """Handle approval decision from frontend. Returns True if event was found."""
        evt = self._approval_events.get(event_id)
        if evt is None:
            return False
        self._approval_decisions[event_id] = decision
        evt.set()
        return True

    def abort(self) -> None:
        self._aborted = True
        # Signal all pending approvals to unblock
        for evt in self._approval_events.values():
            evt.set()

    # ---- Internal ----

    async def _llm_turn(self) -> AsyncGenerator[AgentEvent, None]:
        import os
        messages = self.session.messages

        use_stream = os.environ.get("SCHOLAR_AGENT_STREAM", "1").strip() == "1"
        provider_stream = None

        if use_stream and hasattr(self.provider, "chat_stream"):
            provider_stream = self.provider.chat_stream(
                messages=messages, tools=self.tool_registry.definitions(),
                system_prompt=self.system_prompt,
            )
        if provider_stream is None:
            resp = await self.provider.chat(
                messages=messages, tools=self.tool_registry.definitions(),
                system_prompt=self.system_prompt,
            )
            provider_stream = _fallback_stream(resp)

        tool_blocks = []
        text_blocks = []

        async for chunk in provider_stream:
            if isinstance(chunk, TextBlock):
                text_blocks.append(chunk)
                yield AgentEvent.token(chunk.text)
            elif isinstance(chunk, ThinkingBlock):
                yield AgentEvent.thought(chunk.thinking)
            elif isinstance(chunk, ToolUseBlock):
                tool_blocks.append(chunk)
                yield AgentEvent.tool_call(chunk.id, chunk.name, chunk.input)
            elif isinstance(chunk, TokenUsage):
                if chunk.total() > 0:
                    self.usage.record(chunk)
                    yield AgentEvent.usage(chunk)
            elif isinstance(chunk, ProviderResponse):
                if chunk.usage.total() > 0:
                    self.usage.record(chunk.usage)
                    yield AgentEvent.usage(chunk.usage)

                # Fallback: use ProviderResponse blocks if stream produced nothing
                if not tool_blocks and not text_blocks:
                    for b in chunk.blocks:
                        if isinstance(b, TextBlock):
                            text_blocks.append(b)
                        elif isinstance(b, ToolUseBlock):
                            tool_blocks.append(b)

                full_text = "".join(b.text for b in text_blocks)
                assistant_blocks = list(tool_blocks)
                if text_blocks:
                    assistant_blocks.append(TextBlock(text=full_text))
                if assistant_blocks:
                    self.session.append(Message(role=MessageRole.ASSISTANT, blocks=assistant_blocks, usage=chunk.usage))

                if not tool_blocks:
                    if full_text.strip():
                        # Detect "planning-only" responses
                        planning_keywords = ("let me", "i will", "i'll", "first", "接下来", "让我", "我先",
                                            "首先", "我需要", "i need to", "here's what", "我会",
                                            "第一步", "step 1", "plan:", "计划")
                        last_user = ""
                        for m in reversed(self.session.messages):
                            if m.role == MessageRole.USER:
                                last_user = m.text_content().lower()
                                break
                        action_keywords = ("write", "edit", "modify", "save", "create", "translate",
                                          "写", "改", "编辑", "修改", "保存", "创建", "翻译", "扩写",
                                          "run", "运行", "执行", "replace", "替换", "update", "更新")
                        text_lower = full_text.lower()
                        is_planning = any(k in text_lower for k in planning_keywords)
                        wants_action = any(k in last_user for k in action_keywords)
                        has_tools = bool(self.tool_registry.definitions())

                        if is_planning and wants_action and has_tools and not self._planning_retried:
                            self._planning_retried = True
                            yield AgentEvent.token(full_text)
                            # Retry once with a clear demand — but don't use tool_choice=required
                            # as some providers (DeepSeek) don't support it reliably
                            self.session.append(Message(role=MessageRole.USER, blocks=[
                                TextBlock(text="STOP describing. Call a tool NOW: read_file, write_file, str_replace, or grep_files. No more text — EXECUTE.")
                            ]))
                            # Yield the text so user sees what happened, but DON'T end the turn
                            # The outer loop will call _llm_turn again with the retry message
                            return
                        yield AgentEvent.response(full_text)
                    else:
                        yield AgentEvent.error("empty response from LLM")
                    return

                # Execute tool calls
                for tb in tool_blocks:
                    async for evt in self._execute_tool(tb):
                        yield evt
                return

    async def _execute_tool(self, tb: ToolUseBlock) -> AsyncGenerator[AgentEvent, None]:
        args = {}
        try:
            if tb.input:
                args = json.loads(tb.input)
        except json.JSONDecodeError:
            args = {}

        perm_result = self.permission_policy.authorize(tb.name, tb.input)

        # Capture old content for diff
        old_text = ""
        new_text = ""
        file_path = args.get("file_path", "") or args.get("path", "")
        if tb.name == "str_replace":
            old_text = args.get("old_string", "")
            new_text = args.get("new_string", "")
        elif tb.name == "write_file":
            new_text = args.get("content", "")
            if file_path and self.tool_registry._workspace_root:
                try:
                    full = file_path if Path(file_path).is_absolute() else (self.tool_registry._workspace_root / file_path)
                    if full.is_file():
                        old_text = full.read_text(encoding="utf-8", errors="replace")[:4000]
                except Exception:
                    pass

        if perm_result.is_denied:
            yield AgentEvent.tool_denied(tb.id, tb.name, perm_result.reason)
            tool_output = f"Permission denied: {perm_result.reason}"
            is_error = True
        else:
            # ── 文件修改工具：暂停等用户审批 ──
            if tb.name in ("write_file", "str_replace") and not self.auto_approve:
                yield AgentEvent.await_approval(
                    tb.id, tb.name, f"Agent wants to edit {file_path}",
                    preview={"old_text": old_text, "new_text": new_text, "file_path": file_path},
                )
                # Wait for approval
                evt = asyncio.Event()
                self._approval_events[tb.id] = evt
                try:
                    await asyncio.wait_for(evt.wait(), timeout=_APPROVAL_TIMEOUT)
                except asyncio.TimeoutError:
                    self._approval_decisions[tb.id] = "deny"
                finally:
                    self._approval_events.pop(tb.id, None)

                decision = self._approval_decisions.pop(tb.id, "deny")
                yield AgentEvent.approval_received(tb.id, decision)

                if decision != "allow_once" and decision != "allow_session":
                    tool_output = f"User denied the change to {file_path}"
                    is_error = True
                    yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=True)
                    self.session.append(Message(role=MessageRole.TOOL, blocks=[
                        ToolResultBlock(tool_use_id=tb.id, tool_name=tb.name, output=tool_output, is_error=True),
                    ]))
                    return

            # Execute
            result = await self.tool_registry.execute(tb.name, args)
            tool_output = result.output
            is_error = result.is_error

        yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=is_error)
        self.session.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id=tb.id, tool_name=tb.name, output=tool_output[:_TOOL_RESULT_MAX_CHARS], is_error=is_error),
        ]))

        # Checkpoint after file modifications
        if tb.name in ("write_file", "str_replace") and not is_error:
            yield AgentEvent.checkpoint({
                "action": tb.name, "file": file_path,
                "workspace": self.session.meta.workspace,
            })

    def _auto_save(self) -> None:
        sp = getattr(self.session, '_save_path', '')
        if sp and sp.strip():
            try:
                self.session.save_with_rotate(sp)
            except Exception as e:
                logger.warning("auto-save session failed: %s", e)


async def _fallback_stream(resp: ProviderResponse) -> AsyncGenerator:
    for block in resp.blocks:
        yield block
    if resp.usage.total() > 0:
        yield resp.usage
    yield resp
