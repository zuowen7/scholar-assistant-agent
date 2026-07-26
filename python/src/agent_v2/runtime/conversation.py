"""ConversationRuntime — 统一 Agent 对话循环（真流式 + 审批暂停）。

参考 claw-code:
  - runtime/conversation.rs: ConversationRuntime + stream_message
  - claw-analog/src/lib.rs: dispatch_tool + turn loop + session persist
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from src.agent_v2.runtime.permissions import PermissionPolicy
from src.agent_v2.runtime.session import Session
from src.agent_v2.runtime.usage import UsageTracker
from src.agent_v2.tools.registry import ToolRegistry
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

_DEFAULT_MAX_STEPS = 48
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
        edit_scope: dict[str, Any] | None = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.permission_policy = permission_policy
        self.session = session
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.auto_approve = auto_approve
        self.edit_scope = dict(edit_scope) if edit_scope else None
        self.usage = UsageTracker(model=session.meta.model)
        # Approval state
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._session_approved_tools: set[str] = set()
        self._approval_denied = False
        self._aborted = False
        # Lifecycle tracking — used by router._cleanup_pool to evict stale
        # sessions safely (never evict a streaming session).
        self.last_active_monotonic: float = time.monotonic()
        self._is_streaming: bool = False

    # ---- Public API ----

    async def turn(
        self, user_message: str, *, resume: bool = False
    ) -> AsyncGenerator[AgentEvent, None]:
        if not resume and not user_message.strip():
            yield AgentEvent.error("empty message")
            yield AgentEvent.done()
            return

        self._approval_denied = False
        self._is_streaming = True
        self.last_active_monotonic = time.monotonic()
        try:
            yield AgentEvent.session_started(self.session.session_id)
            if not resume:
                self.session.append(
                    Message(role=MessageRole.USER, blocks=[TextBlock(text=user_message)])
                )
                self._auto_save()

            for _step in range(self.max_steps):
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
                                yield AgentEvent.usage(
                                    TokenUsage(
                                        input_tokens=self.usage.total_input,
                                        output_tokens=self.usage.total_output,
                                    )
                                )
                                yield AgentEvent.done()
                                return
                            if event.type == AgentEventType.DONE:
                                return
                        if self._aborted:
                            yield AgentEvent.aborted("Session aborted by user")
                            yield AgentEvent.done()
                            return
                        if self._approval_denied:
                            self._auto_save()
                            yield AgentEvent.aborted("File edit rejected; no changes were applied")
                            yield AgentEvent.done()
                            return
                        break
                    except ApiError as e:
                        if e.status_code == 429 and retry < 2:
                            wait = e.retry_after or (2**retry)
                            yield AgentEvent.warning(
                                f"Rate limited; retrying in {wait:.0f}s",
                                code="rate_limited",
                                attempt=retry + 1,
                                max_attempts=3,
                                reset_stream=True,
                            )
                            await asyncio.sleep(wait)
                            continue
                        if e.status_code == 0 and retry < 2:
                            yield AgentEvent.warning(
                                f"Connection interrupted; retrying ({retry + 1}/3)",
                                code="stream_interrupted",
                                attempt=retry + 1,
                                max_attempts=3,
                                reset_stream=True,
                            )
                            await asyncio.sleep(2.0)
                            continue
                        yield AgentEvent.error(f"API error: {e}")
                        yield AgentEvent.done()
                        return
                    except Exception as e:
                        logger.exception("unexpected error in turn")
                        yield AgentEvent.error(f"unexpected error: {e}")
                        yield AgentEvent.done()
                        return
                self.last_active_monotonic = time.monotonic()
            else:
                yield AgentEvent.error(f"max steps ({self.max_steps}) reached")
                yield AgentEvent.done()
        finally:
            # Guaranteed cleanup on any exit path (normal return, exception,
            # generator close, client disconnect). Prevents _approval_events
            # from leaking if the generator is abandoned mid-approval.
            self._is_streaming = False
            if self._approval_events:
                self._approval_events.clear()

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
                messages=messages,
                tools=self.tool_registry.definitions(),
                system_prompt=self.system_prompt,
            )
        if provider_stream is None:
            resp = await self.provider.chat(
                messages=messages,
                tools=self.tool_registry.definitions(),
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

                # Merge ProviderResponse blocks: streaming doesn't yield ToolUseBlock
                # individually, so we must extract them from the final response
                if not tool_blocks:
                    for b in chunk.blocks:
                        if isinstance(b, ToolUseBlock):
                            tool_blocks.append(b)
                            yield AgentEvent.tool_call(b.id, b.name, b.input)
                if not text_blocks:
                    for b in chunk.blocks:
                        if isinstance(b, TextBlock):
                            text_blocks.append(b)

                full_text = "".join(b.text for b in text_blocks)
                assistant_blocks = list(tool_blocks)
                if text_blocks:
                    assistant_blocks.append(TextBlock(text=full_text))
                if assistant_blocks:
                    self.session.append(
                        Message(
                            role=MessageRole.ASSISTANT, blocks=assistant_blocks, usage=chunk.usage
                        )
                    )
                    self._auto_save()

                if not tool_blocks:
                    if full_text.strip():
                        yield AgentEvent.response(full_text)
                    else:
                        yield AgentEvent.error("empty response from LLM")
                    return

                # Execute tool calls
                for tb in tool_blocks:
                    async for evt in self._execute_tool(tb):
                        yield evt
                    if self._approval_denied or self._aborted:
                        return
                return

    async def _execute_tool(self, tb: ToolUseBlock) -> AsyncGenerator[AgentEvent, None]:
        args = {}
        try:
            if tb.input:
                args = json.loads(tb.input)
        except json.JSONDecodeError:
            args = {}

        scope_error = self._apply_edit_scope(tb, args)
        if scope_error:
            self.session.append(
                Message(
                    role=MessageRole.TOOL,
                    blocks=[
                        ToolResultBlock(
                            tool_use_id=tb.id,
                            tool_name=tb.name,
                            output=scope_error,
                            is_error=True,
                        ),
                    ],
                )
            )
            self._auto_save()
            yield AgentEvent.tool_result(tb.id, tb.name, scope_error, is_error=True)
            return

        # The scope guard may inject trusted line/column anchors. Use the
        # normalized arguments for authorization without mutating the provider's
        # immutable ToolUseBlock.
        normalized_input = json.dumps(args, ensure_ascii=False)
        perm_result = self.permission_policy.authorize(tb.name, normalized_input)

        # Capture old content for diff
        old_text = ""
        new_text = ""
        file_path = args.get("file_path", "") or args.get("path", "")
        # Resolve to absolute path so frontend can match against editor tabs
        resolved_path = file_path
        if file_path and self.tool_registry._workspace_root:
            try:
                p = Path(file_path)
                candidate = self.tool_registry._workspace_root / p if not p.is_absolute() else p
                resolved_path = str(candidate.resolve())
            except Exception:
                pass
        if tb.name == "str_replace":
            old_text = args.get("old_string", "")
            new_text = args.get("new_string", "")
        elif tb.name == "write_file":
            new_text = args.get("content", "")
            if resolved_path:
                try:
                    full = Path(resolved_path)
                    if full.is_file():
                        old_text = full.read_text(encoding="utf-8", errors="replace")[:4000]
                except Exception:
                    pass

        if perm_result.is_denied:
            yield AgentEvent.tool_denied(tb.id, tb.name, perm_result.reason)
            tool_output = f"Permission denied: {perm_result.reason}"
            is_error = True
        else:
            # ── 有副作用的工具：暂停等用户审批 ──
            if (
                tb.name in ("write_file", "str_replace", "run_command", "export_document")
                and not self.auto_approve
                and tb.name not in self._session_approved_tools
            ):
                if tb.name == "run_command":
                    approval_reason = (
                        f"Agent wants to run a command in {args.get('cwd', '.')}: "
                        f"{args.get('command', '')}"
                    )
                elif tb.name == "export_document":
                    approval_reason = (
                        f"Agent wants to export {file_path} as {args.get('format', 'latex')}"
                    )
                else:
                    approval_reason = f"Agent wants to edit {file_path}"
                # Register before yielding. The frontend may POST its decision as
                # soon as it receives the SSE event.
                evt = asyncio.Event()
                self._approval_events[tb.id] = evt
                yield AgentEvent.await_approval(
                    tb.id,
                    tb.name,
                    approval_reason,
                    preview={
                        "old_text": old_text,
                        "new_text": new_text,
                        "file_path": resolved_path,
                        "command": args.get("command", ""),
                        "cwd": args.get("cwd", "."),
                    },
                )
                # Wait for approval
                try:
                    await asyncio.wait_for(evt.wait(), timeout=_APPROVAL_TIMEOUT)
                except TimeoutError:
                    self._approval_decisions[tb.id] = "deny"
                finally:
                    self._approval_events.pop(tb.id, None)

                decision = self._approval_decisions.pop(tb.id, "deny")
                yield AgentEvent.approval_received(tb.id, decision)

                if decision != "allow_once" and decision != "allow_session":
                    tool_output = f"User denied the change to {file_path}"
                    is_error = True
                    self.session.append(
                        Message(
                            role=MessageRole.TOOL,
                            blocks=[
                                ToolResultBlock(
                                    tool_use_id=tb.id,
                                    tool_name=tb.name,
                                    output=tool_output,
                                    is_error=True,
                                ),
                            ],
                        )
                    )
                    self._auto_save()
                    yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=True)
                    if not self._aborted:
                        self._approval_denied = True
                    return
                if decision == "allow_session":
                    self._session_approved_tools.add(tb.name)

            # Execute
            result = await self.tool_registry.execute(tb.name, args)
            tool_output = result.output
            is_error = result.is_error

        self.session.append(
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(
                        tool_use_id=tb.id,
                        tool_name=tb.name,
                        output=tool_output[:_TOOL_RESULT_MAX_CHARS],
                        is_error=is_error,
                    ),
                ],
            )
        )
        self._auto_save()
        yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=is_error)

        # Checkpoint after file modifications: include new content for frontend
        if tb.name in ("write_file", "str_replace") and not is_error:
            new_content = ""
            if resolved_path:
                try:
                    fp = Path(resolved_path)
                    if fp.is_file():
                        new_content = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            yield AgentEvent.checkpoint(
                {
                    "action": tb.name,
                    "file": resolved_path,
                    "workspace": self.session.meta.workspace,
                    "content": new_content[:10000] if new_content else tool_output,
                    "content_truncated": len(new_content) > 10000,
                }
            )

    def _apply_edit_scope(self, tb: ToolUseBlock, args: dict[str, Any]) -> str | None:
        """Restrict a selection turn to the exact active Monaco range.

        Read-only tools remain available for reasoning. Any side-effecting tool
        other than anchored str_replace is rejected before approval or execution.
        """
        scope = self.edit_scope
        if scope is None:
            return None

        spec = self.tool_registry.get(tb.name)
        if spec is None or spec.permission == "read-only":
            return None
        if tb.name != "str_replace":
            return (
                f"Selection edit blocked: {tb.name} cannot modify files during an active "
                "selection turn; use str_replace on the current active selection."
            )

        selected_text = str(scope.get("text", ""))
        if str(args.get("old_string", "")) != selected_text:
            return (
                "Selection edit blocked: old_string does not equal the current active selection. "
                "Ignore selections from earlier turns and retry with the exact current text."
            )

        requested_file = str(args.get("file_path", ""))
        selected_file = str(scope.get("file_path", ""))
        if not requested_file or not selected_file:
            return "Selection edit blocked: the current active selection has no valid file anchor."

        workspace = self.tool_registry._workspace_root

        def _resolve(path_value: str) -> Path:
            path = Path(path_value)
            if not path.is_absolute() and workspace is not None:
                path = workspace / path
            return path.resolve()

        try:
            if _resolve(requested_file) != _resolve(selected_file):
                return (
                    "Selection edit blocked: the requested file is not the file containing "
                    "the current active selection."
                )
        except (OSError, ValueError):
            return "Selection edit blocked: the current active selection file is invalid."

        args.update(
            {
                "start_line": int(scope["start_line"]),
                "start_column": int(scope["start_column"]),
                "end_line": int(scope["end_line"]),
                "end_column": int(scope["end_column"]),
            }
        )
        return None

    def _auto_save(self) -> None:
        sp = getattr(self.session, "_save_path", "")
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
