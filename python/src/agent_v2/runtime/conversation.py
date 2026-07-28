"""ConversationRuntime — 统一 Agent 对话循环（真流式 + 审批暂停）。

参考 claw-code:
  - runtime/conversation.rs: ConversationRuntime + stream_message
  - claw-analog/src/lib.rs: dispatch_tool + turn loop + session persist
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.agent_v2.hooks import HookDecision, HookEvent, HookPoint, HookRunner
from src.agent_v2.runtime.file_mutations import read_text_exact
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
_APPROVAL_TIMEOUT = 600.0  # 10 分钟等用户审批；超时必须与用户拒绝分开
_TOOL_RESULT_MAX_CHARS = 4000
_DEFAULT_MAX_TOOL_CALLS = 32
_DEFAULT_SOFT_TOOL_CALLS = 28
_SELECTION_MAX_TOOL_CALLS = 4
_DEFAULT_MAX_TOOL_ERRORS = 5
_SELECTION_MAX_TOOL_ERRORS = 2
_MAX_IDENTICAL_TOOL_CALLS = 2
_SELECTION_SAFE_TOOLS = frozenset(
    {
        "str_replace",
        "rag_search",
        "arxiv_search",
        "web_search",
        "web_fetch",
        "read_argument_graph",
        "read_argument_ledger",
        "read_reviewer_state",
    }
)


class _EmptyModelResponse(RuntimeError):
    """Provider completed without a user-visible answer or tool call."""


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _preferred_line_ending(text: str) -> str:
    for index, char in enumerate(text):
        if char == "\r":
            return "\r\n" if index + 1 < len(text) and text[index + 1] == "\n" else "\r"
        if char == "\n":
            return "\n"
    return "\n"


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
        hook_runner: HookRunner | None = None,
        max_tool_calls: int = _DEFAULT_MAX_TOOL_CALLS,
        soft_tool_calls: int | None = None,
    ):
        self.provider = provider
        self.tool_registry = tool_registry
        self.permission_policy = permission_policy
        self.session = session
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.auto_approve = auto_approve
        self.edit_scope = dict(edit_scope) if edit_scope else None
        self.hook_runner = hook_runner
        self.max_tool_calls = max(1, int(max_tool_calls))
        configured_soft_limit = (
            int(soft_tool_calls)
            if soft_tool_calls is not None
            else min(_DEFAULT_SOFT_TOOL_CALLS, self.max_tool_calls - 1)
        )
        self.soft_tool_calls = max(0, min(configured_soft_limit, self.max_tool_calls - 1))
        self.usage = UsageTracker(model=session.meta.model)
        self.tool_registry.set_runtime_context(
            parent_session_id=session.session_id,
            parent_session_path=getattr(session, "_save_path", ""),
            workspace=session.meta.workspace,
        )
        # Approval state
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_decisions: dict[str, str] = {}
        self._session_approved_actions: set[str] = set()
        self._approval_denied = False
        self._approval_stop_reason: str | None = None
        self._aborted = False
        self._tool_calls_this_turn = 0
        self._tool_errors_this_turn = 0
        self._tool_call_counts: dict[str, int] = {}
        self._readonly_tool_names = frozenset(
            name for name, perm in tool_registry.permission_specs() if perm == "read-only"
        )
        self._tool_stop_reason: str | None = None
        self._tool_stop_code: str | None = None
        self._selection_edit_completed = False
        self._changed_files_this_turn: set[str] = set()
        self._turn_message_start = 0
        self._turn_id = ""
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
        self._approval_stop_reason = None
        self._tool_calls_this_turn = 0
        self._tool_errors_this_turn = 0
        self._tool_call_counts.clear()
        self._tool_stop_reason = None
        self._tool_stop_code = None
        self._selection_edit_completed = False
        self._changed_files_this_turn.clear()
        self._turn_message_start = len(self.session.messages)
        self._turn_id = uuid.uuid4().hex
        self.session.set_outcome("RUNNING", {})
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
                    self._persist_turn_outcome("ABORTED", "user_aborted", "Session aborted by user")
                    yield AgentEvent.aborted("Session aborted by user")
                    yield AgentEvent.done()
                    return

                recovery_instruction = self._step_instruction()
                for retry in range(3):
                    try:
                        async for event in self._llm_turn(
                            recovery_instruction=recovery_instruction
                        ):
                            yield event
                            if event.type in (AgentEventType.RESPONSE, AgentEventType.ERROR):
                                if event.type == AgentEventType.RESPONSE:
                                    self._persist_turn_outcome("COMPLETE", "", "")
                                else:
                                    self._persist_turn_outcome(
                                        "FAILED",
                                        str(event.data.get("code", "runtime_error")),
                                        str(event.data.get("message", "")),
                                    )
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
                            self._persist_turn_outcome(
                                "ABORTED", "user_aborted", "Session aborted by user"
                            )
                            yield AgentEvent.aborted("Session aborted by user")
                            yield AgentEvent.done()
                            return
                        if self._approval_denied:
                            state = "PARTIAL" if self._changed_files_this_turn else "ABORTED"
                            self._persist_turn_outcome(
                                state,
                                "approval_denied",
                                self._approval_stop_reason or "Tool approval denied",
                            )
                            self._auto_save()
                            yield AgentEvent.aborted(
                                self._approval_stop_reason
                                or "File edit rejected; no changes were applied"
                            )
                            yield AgentEvent.done()
                            return
                        if self._tool_stop_reason:
                            async for final_event in self._finalize_stopped_turn():
                                yield final_event
                            self._auto_save()
                            yield AgentEvent.usage(
                                TokenUsage(
                                    input_tokens=self.usage.total_input,
                                    output_tokens=self.usage.total_output,
                                )
                            )
                            yield AgentEvent.done()
                            return
                        break
                    except _EmptyModelResponse:
                        if retry < 2:
                            yield AgentEvent.warning(
                                f"模型未返回最终答复，正在继续生成（{retry + 1}/3）",
                                code="empty_model_response",
                                attempt=retry + 1,
                                max_attempts=3,
                                reset_stream=True,
                            )
                            recovery_instruction = "\n\n".join(
                                part
                                for part in (
                                    self._step_instruction(),
                                    "The previous completion contained reasoning but no final "
                                    "answer or tool call. Continue the same task now. Return a "
                                    "user-facing final answer or invoke the required tool(s). "
                                    "Do not return reasoning alone.",
                                )
                                if part
                            )
                            continue
                        yield AgentEvent.error(
                            "模型连续 3 次未返回最终答复或工具调用。请重试，或切换模型后继续。"
                        )
                        self._persist_turn_outcome(
                            "FAILED", "empty_model_response", "Model returned no final response"
                        )
                        yield AgentEvent.done()
                        return
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
                        self._persist_turn_outcome("FAILED", "api_error", str(e))
                        yield AgentEvent.done()
                        return
                    except Exception as e:
                        logger.exception("unexpected error in turn")
                        yield AgentEvent.error(f"unexpected error: {e}")
                        self._persist_turn_outcome("FAILED", "unexpected_error", str(e))
                        yield AgentEvent.done()
                        return
                self.last_active_monotonic = time.monotonic()
            else:
                self._tool_stop_reason = f"max steps ({self.max_steps}) reached before completion"
                self._tool_stop_code = "max_steps_exhausted"
                async for final_event in self._finalize_stopped_turn():
                    yield final_event
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

    def _build_turn_outcome(
        self,
        *,
        stop_code: str,
        stop_reason: str,
    ) -> dict[str, Any]:
        counts = {
            "success": 0,
            "error": 0,
            "denied": 0,
            "skipped": 0,
            "no_change": 0,
        }
        unexecuted: list[dict[str, str]] = []
        for message in self.session.messages[self._turn_message_start :]:
            for block in message.blocks:
                if not isinstance(block, ToolResultBlock):
                    continue
                status = (
                    block.status
                    if block.status in counts
                    else ("error" if block.is_error else "success")
                )
                counts[status] += 1
                if status in {"skipped", "denied"}:
                    unexecuted.append(
                        {
                            "tool_use_id": block.tool_use_id,
                            "tool_name": block.tool_name,
                            "status": status,
                        }
                    )
        return {
            "stop_code": stop_code,
            "stop_reason": stop_reason,
            "tool_counts": counts,
            "changed_files": sorted(self._changed_files_this_turn),
            "unexecuted": unexecuted,
        }

    def _persist_turn_outcome(self, state: str, stop_code: str, stop_reason: str) -> None:
        self.session.set_outcome(
            state,
            self._build_turn_outcome(stop_code=stop_code, stop_reason=stop_reason),
        )
        self._auto_save()

    async def _finalize_stopped_turn(self) -> AsyncGenerator[AgentEvent, None]:
        stop_code = self._tool_stop_code or "tool_loop_stopped"
        stop_reason = self._tool_stop_reason or "Tool execution stopped before completion"
        outcome = self._build_turn_outcome(
            stop_code=stop_code,
            stop_reason=stop_reason,
        )
        self.session.set_outcome("FINALIZING", outcome)
        self._auto_save()
        instruction = (
            "Tool execution has stopped and no more tools are available. "
            "Return a concise user-facing PARTIAL completion report. State what succeeded, "
            "what failed or was skipped, which files changed, and what remains unverified. "
            "Do not claim rollback or full completion.\n\n"
            f"Execution outcome:\n{json.dumps(outcome, ensure_ascii=False, sort_keys=True)}"
        )
        emitted_response = False
        try:
            try:
                async for event in self._llm_turn(
                    recovery_instruction=instruction,
                    force_no_tools=True,
                ):
                    if event.type == AgentEventType.RESPONSE:
                        emitted_response = True
                    yield event
            except Exception as exc:
                logger.warning("Agent finalization failed: %s", exc)
            if not emitted_response:
                counts = outcome["tool_counts"]
                changed = outcome["changed_files"]
                changed_text = ", ".join(changed) if changed else "none"
                yield AgentEvent.response(
                    "Task partially completed. "
                    f"Successful tools: {counts['success']}; errors: {counts['error']}; "
                    f"skipped: {counts['skipped']}; no change: {counts['no_change']}. "
                    f"Changed files: {changed_text}. "
                    f"Stop reason: {stop_reason}"
                )
        finally:
            self.session.set_outcome("PARTIAL", outcome)
            self._auto_save()

    async def _llm_turn(
        self,
        *,
        recovery_instruction: str | None = None,
        force_no_tools: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        import os

        messages = self.session.messages
        system_prompt = "\n\n".join(
            part for part in (self.system_prompt, self._selection_instruction()) if part
        )
        if recovery_instruction:
            system_prompt = "\n\n".join(
                part for part in (system_prompt, recovery_instruction) if part
            )
        tool_definitions = [] if force_no_tools else self._tool_definitions_for_turn()

        use_stream = os.environ.get("SCHOLAR_AGENT_STREAM", "1").strip() == "1"
        provider_stream = None

        if use_stream and hasattr(self.provider, "chat_stream"):
            provider_stream = self.provider.chat_stream(
                messages=messages,
                tools=tool_definitions,
                system_prompt=system_prompt,
            )
        if provider_stream is None:
            resp = await self.provider.chat(
                messages=messages,
                tools=tool_definitions,
                system_prompt=system_prompt,
            )
            provider_stream = _fallback_stream(resp)

        tool_blocks = []
        text_blocks = []
        recorded_usage: set[tuple[int, int, int, int]] = set()

        def record_usage_once(usage: TokenUsage) -> bool:
            signature = (
                usage.input_tokens,
                usage.output_tokens,
                usage.cache_read_tokens,
                usage.cache_creation_tokens,
            )
            if usage.total() <= 0 or signature in recorded_usage:
                return False
            recorded_usage.add(signature)
            self.usage.record(usage)
            return True

        async for chunk in provider_stream:
            if isinstance(chunk, TextBlock):
                text_blocks.append(chunk)
                yield AgentEvent.token(chunk.text)
            elif isinstance(chunk, ThinkingBlock):
                yield AgentEvent.thought(chunk.thinking)
            elif isinstance(chunk, ToolUseBlock):
                if not force_no_tools:
                    tool_blocks.append(chunk)
                    yield AgentEvent.tool_call(chunk.id, chunk.name, chunk.input)
            elif isinstance(chunk, TokenUsage):
                if record_usage_once(chunk):
                    yield AgentEvent.usage(chunk)
            elif isinstance(chunk, ProviderResponse):
                if record_usage_once(chunk.usage):
                    yield AgentEvent.usage(chunk.usage)

                # A provider may stream only some tool blocks and return the rest
                # in the final response. Merge by id and reject conflicting reuse.
                tool_blocks_by_id = {block.id: block for block in tool_blocks}
                if not force_no_tools:
                    for b in chunk.blocks:
                        if not isinstance(b, ToolUseBlock):
                            continue
                        streamed = tool_blocks_by_id.get(b.id)
                        if streamed is None:
                            tool_blocks.append(b)
                            tool_blocks_by_id[b.id] = b
                            yield AgentEvent.tool_call(b.id, b.name, b.input)
                        elif streamed.name != b.name or streamed.input != b.input:
                            raise RuntimeError(
                                f"Provider reused tool-use id {b.id!r} with conflicting payload"
                            )
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

                if tool_blocks and full_text:
                    # Text emitted in a tool-use turn is provisional. Clear it
                    # from the live answer so "completed" claims and recovery
                    # narration are not presented as the final response.
                    yield AgentEvent.warning("", code="tool_turn", reset_stream=True)

                if not tool_blocks:
                    if full_text.strip():
                        yield AgentEvent.response(full_text)
                    else:
                        raise _EmptyModelResponse
                    return

                # Execute tool calls
                for idx, tb in enumerate(tool_blocks):
                    async for evt in self._execute_tool(tb):
                        yield evt
                    if self._approval_denied or self._aborted or self._tool_stop_reason:
                        # Supplement synthetic ToolResultBlocks for remaining
                        # unexecuted tool calls so the persisted session history
                        # stays protocol-valid (every ToolUseBlock needs a
                        # matching ToolResultBlock).
                        for remaining in tool_blocks[idx + 1 :]:
                            skip_output = (
                                "Tool execution skipped because the turn was "
                                "stopped by a safety limit or user action."
                            )
                            self.session.append(
                                Message(
                                    role=MessageRole.TOOL,
                                    blocks=[
                                        ToolResultBlock(
                                            tool_use_id=remaining.id,
                                            tool_name=remaining.name,
                                            output=skip_output,
                                            is_error=False,
                                            status="skipped",
                                        ),
                                    ],
                                )
                            )
                            yield AgentEvent.tool_result(
                                remaining.id,
                                remaining.name,
                                skip_output,
                                status="skipped",
                            )
                        self._auto_save()
                        return
                return

    async def _execute_tool(self, tb: ToolUseBlock) -> AsyncGenerator[AgentEvent, None]:
        args = {}
        try:
            if tb.input:
                args = json.loads(tb.input)
        except json.JSONDecodeError:
            args = {}

        loop_error = self._check_tool_loop(tb, args)
        if loop_error:
            self._append_tool_error(tb, loop_error)
            self._tool_stop_reason = loop_error
            yield AgentEvent.tool_result(tb.id, tb.name, loop_error, is_error=True)
            return
        if self._should_skip_in_draining(tb):
            output = (
                "Tool execution skipped because the soft budget is exhausted; "
                "only read-only verification is allowed while draining."
            )
            self.session.append(
                Message(
                    role=MessageRole.TOOL,
                    blocks=[
                        ToolResultBlock(
                            tool_use_id=tb.id,
                            tool_name=tb.name,
                            output=output,
                            status="skipped",
                        )
                    ],
                )
            )
            self.session.set_outcome(
                "DRAINING",
                {
                    "tool_calls": self._tool_calls_this_turn,
                    "tool_calls_remaining": max(
                        0, self.max_tool_calls - self._tool_calls_this_turn
                    ),
                },
            )
            self._auto_save()
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                output,
                status="skipped",
            )
            return

        hook_asks_for_approval = False
        if self.hook_runner is not None:
            hook_result = await self.hook_runner.run(
                HookPoint.PRE_TOOL_USE,
                HookEvent(
                    hook=HookPoint.PRE_TOOL_USE,
                    tool_name=tb.name,
                    tool_input=json.dumps(args, ensure_ascii=False, sort_keys=True),
                ),
            )
            if hook_result.updated_input is not None:
                try:
                    updated_args = json.loads(hook_result.updated_input)
                except (json.JSONDecodeError, TypeError):
                    updated_args = None
                if not isinstance(updated_args, dict):
                    reason = "PreToolUse hook returned invalid updated input"
                    self._append_tool_error(tb, reason)
                    yield AgentEvent.tool_result(tb.id, tb.name, reason, is_error=True)
                    return
                args = updated_args
            if hook_result.decision == HookDecision.DENY:
                reason = hook_result.reason or "Tool denied by PreToolUse hook"
                self.session.append(
                    Message(
                        role=MessageRole.TOOL,
                        blocks=[
                            ToolResultBlock(
                                tool_use_id=tb.id,
                                tool_name=tb.name,
                                output=reason,
                                is_error=True,
                                status="denied",
                            )
                        ],
                    )
                )
                self._auto_save()
                yield AgentEvent.tool_denied(tb.id, tb.name, reason)
                yield AgentEvent.tool_result(tb.id, tb.name, reason, is_error=True, status="denied")
                self._record_tool_error()
                return
            hook_asks_for_approval = hook_result.decision == HookDecision.ASK

        scope_error = self._apply_edit_scope(tb, args)
        if scope_error:
            self._append_tool_error(tb, scope_error)
            self._record_tool_error()
            yield AgentEvent.tool_result(tb.id, tb.name, scope_error, is_error=True)
            return

        # The scope guard may inject trusted line/column anchors. Use the
        # normalized arguments for authorization without mutating the provider's
        # immutable ToolUseBlock.
        normalized_input = json.dumps(args, ensure_ascii=False)
        operation_key = ""
        if tb.name in {"write_file", "str_replace"}:
            operation_key = hashlib.sha256(
                f"{tb.name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}".encode()
            ).hexdigest()
            applied = self.session.applied_mutation(operation_key)
            if applied is not None:
                output = (
                    f"no change: identical Agent mutation {applied.mutation_id} is already applied"
                )
                self.session.append(
                    Message(
                        role=MessageRole.TOOL,
                        blocks=[
                            ToolResultBlock(
                                tool_use_id=tb.id,
                                tool_name=tb.name,
                                output=output,
                                status="no_change",
                            )
                        ],
                    )
                )
                self._tool_errors_this_turn = 0
                self._auto_save()
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    output,
                    status="no_change",
                )
                return
        perm_result = self.permission_policy.authorize(tb.name, normalized_input)
        spec = self.tool_registry.get(tb.name)

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
        result_metadata: dict[str, Any] = {}

        if perm_result.is_denied:
            yield AgentEvent.tool_denied(tb.id, tb.name, perm_result.reason)
            tool_output = f"Permission denied: {perm_result.reason}"
            is_error = True
            result_status = "denied"
            result_truncated = False
            result_original_chars = len(tool_output)
            result_returned_chars = len(tool_output)
        else:
            approval_key = self._approval_key(tb.name, args, resolved_path)
            requires_approval = bool(spec and spec.requires_approval)
            # All side-effecting tools use the same capability-based approval path.
            if (
                hook_asks_for_approval or (requires_approval and not self.auto_approve)
            ) and approval_key not in self._session_approved_actions:
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
                    force_approval=hook_asks_for_approval,
                )
                # Wait for approval
                try:
                    await asyncio.wait_for(evt.wait(), timeout=_APPROVAL_TIMEOUT)
                except TimeoutError:
                    self._approval_decisions[tb.id] = "timeout"
                finally:
                    self._approval_events.pop(tb.id, None)

                decision = self._approval_decisions.pop(
                    tb.id, "aborted" if self._aborted else "cancelled"
                )
                yield AgentEvent.approval_received(tb.id, decision)

                if decision != "allow_once" and decision != "allow_session":
                    if decision == "timeout":
                        tool_output = f"Approval timed out for the change to {file_path}"
                        stop_reason = "File edit approval timed out; no changes were applied"
                    elif decision == "aborted":
                        tool_output = f"Approval cancelled for the change to {file_path}"
                        stop_reason = "Session aborted by user"
                    else:
                        tool_output = f"User denied the change to {file_path}"
                        stop_reason = "File edit rejected; no changes were applied"
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
                                    status="denied",
                                ),
                            ],
                        )
                    )
                    self._auto_save()
                    yield AgentEvent.tool_result(
                        tb.id, tb.name, tool_output, is_error=True, status="denied"
                    )
                    if not self._aborted:
                        self._approval_denied = True
                        self._approval_stop_reason = stop_reason
                    return
                if decision == "allow_session":
                    self._session_approved_actions.add(approval_key)

            # Capture an exact pre-image immediately before execution. Preview
            # text is intentionally truncated and cannot support reliable Undo.
            mutation_before_exists = False
            mutation_before_content = ""
            mutation_before_bytes = b""
            mutation_is_binary = tb.name == "export_document"
            mutation_target_path = resolved_path
            if tb.name == "export_document" and resolved_path:
                normalized_format = str(args.get("format", "latex")).lower()
                suffix = (
                    ".docx"
                    if normalized_format in {"word", "docx"}
                    else ".pdf"
                    if normalized_format == "pdf"
                    else ".tex"
                )
                mutation_target_path = str(Path(resolved_path).with_suffix(suffix))
            if tb.name in ("write_file", "str_replace", "export_document") and mutation_target_path:
                try:
                    mutation_path = Path(mutation_target_path)
                    mutation_before_exists = mutation_path.is_file()
                    if mutation_before_exists:
                        if mutation_is_binary:
                            mutation_before_bytes = mutation_path.read_bytes()
                        else:
                            mutation_before_content = read_text_exact(mutation_path)
                except Exception:
                    mutation_before_exists = False
                    mutation_before_content = ""
                    mutation_before_bytes = b""

            # Execute
            result = await self.tool_registry.execute(tb.name, args)
            tool_output = result.output
            is_error = result.is_error
            result_status = result.status
            result_truncated = result.truncated
            result_original_chars = result.original_chars
            result_returned_chars = result.returned_chars
            result_metadata = dict(result.metadata or {})
            sub_agent_usage = result_metadata.get("sub_agent_usage")
            if isinstance(sub_agent_usage, dict):
                self.usage.record(
                    TokenUsage(
                        input_tokens=int(sub_agent_usage.get("input_tokens", 0) or 0),
                        output_tokens=int(sub_agent_usage.get("output_tokens", 0) or 0),
                    )
                )

            if (
                tb.name in ("write_file", "str_replace", "export_document")
                and result_status == "success"
                and mutation_target_path
            ):
                try:
                    if mutation_is_binary:
                        after_bytes = Path(mutation_target_path).read_bytes()
                        self.session.record_binary_mutation(
                            turn_id=self._turn_id,
                            tool_use_id=tb.id,
                            path=mutation_target_path,
                            before_exists=mutation_before_exists,
                            before_content=mutation_before_bytes,
                            after_content=after_bytes,
                            operation_key=operation_key,
                        )
                    else:
                        after_content = read_text_exact(Path(mutation_target_path))
                        self.session.record_mutation(
                            turn_id=self._turn_id,
                            tool_use_id=tb.id,
                            path=mutation_target_path,
                            before_exists=mutation_before_exists,
                            before_content=mutation_before_content,
                            after_content=after_content,
                            operation_key=operation_key,
                        )
                except Exception as exc:
                    logger.error(
                        "File changed but its mutation journal could not be persisted: %s",
                        exc,
                    )
                    tool_output = (
                        f"{tool_output}\nwarning: mutation journal failed; Undo is unavailable "
                        "for this edit"
                    )

            if self.hook_runner is not None:
                post_point = (
                    HookPoint.POST_TOOL_USE_FAILURE if is_error else HookPoint.POST_TOOL_USE
                )
                await self.hook_runner.run(
                    post_point,
                    HookEvent(
                        hook=post_point,
                        tool_name=tb.name,
                        tool_input=json.dumps(args, ensure_ascii=False, sort_keys=True),
                        tool_result=tool_output,
                        is_error=is_error,
                    ),
                )

        self.session.append(
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(
                        tool_use_id=tb.id,
                        tool_name=tb.name,
                        output=tool_output,
                        is_error=is_error,
                        status=result_status,
                        truncated=result_truncated,
                        original_chars=result_original_chars,
                        returned_chars=result_returned_chars,
                        metadata=result_metadata,
                    ),
                ],
            )
        )
        self._auto_save()
        yield AgentEvent.tool_result(
            tb.id,
            tb.name,
            tool_output,
            is_error=is_error,
            status=result_status,
            truncated=result_truncated,
            original_chars=result_original_chars,
            returned_chars=result_returned_chars,
            metadata=result_metadata,
        )
        if is_error:
            self._record_tool_error()
        else:
            # The limit is deliberately consecutive: a successful or no-op
            # result proves the execution path recovered.
            self._tool_errors_this_turn = 0

        # Checkpoint after file modifications: include new content for frontend
        if (
            tb.name in ("write_file", "str_replace", "export_document")
            and result_status == "success"
        ):
            # A successful write changes file-system state, so earlier identical
            # reads are no longer "repeated" — reset only read-only fingerprints
            # to avoid false circuit-breaker trips on legitimate read-edit-read
            # cycles. Write-tool fingerprints are preserved so that repeated
            # identical writes still trip the breaker.
            readonly_prefixes = tuple(f"{rn}:" for rn in self._readonly_tool_names)
            if readonly_prefixes:
                self._tool_call_counts = {
                    k: v
                    for k, v in self._tool_call_counts.items()
                    if not k.startswith(readonly_prefixes)
                }
            if self.edit_scope is not None and tb.name == "str_replace":
                self._selection_edit_completed = True
            checkpoint_path = mutation_target_path or resolved_path
            if checkpoint_path:
                self._changed_files_this_turn.add(checkpoint_path)
            new_content = ""
            if checkpoint_path and not mutation_is_binary:
                try:
                    fp = Path(checkpoint_path)
                    if fp.is_file():
                        new_content = fp.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            yield AgentEvent.checkpoint(
                {
                    "action": tb.name,
                    "file": checkpoint_path,
                    "workspace": self.session.meta.workspace,
                    "content": new_content[:10000] if new_content else tool_output,
                    "content_truncated": len(new_content) > 10000,
                }
            )

    def _approval_key(self, tool_name: str, args: dict[str, Any], resolved_path: str) -> str:
        spec = self.tool_registry.get(tool_name)
        scope = spec.approval_scope if spec is not None else "exact-input"
        if scope == "path":
            subject: Any = resolved_path
        elif scope == "domain":
            url = str(args.get("url", ""))
            subject = urlsplit(url).hostname if url else tool_name
        else:
            subject = args
        return f"{tool_name}:{json.dumps(subject, ensure_ascii=False, sort_keys=True)}"

    def _tool_definitions_for_turn(self) -> list:
        definitions = self.tool_registry.definitions()
        if self.edit_scope is None:
            return definitions
        if self._selection_edit_completed:
            return []
        return [
            definition for definition in definitions if definition.name in _SELECTION_SAFE_TOOLS
        ]

    def _selection_instruction(self) -> str | None:
        if self.edit_scope is None:
            return None
        if self._selection_edit_completed:
            return (
                "# Active selection status\n"
                "The active selection has already been modified successfully. "
                "Do not call any more tools. Return a concise user-facing summary now."
            )
        return (
            "# Active selection rules\n"
            "The exact selected text in the current user message is authoritative and sufficient. "
            "Do not read, search, or rewrite the active file. If a modification is requested, make "
            "one anchored str_replace call using the complete selection as old_string. Never use "
            "write_file or run_command to edit selected text."
        )

    def _step_instruction(self) -> str | None:
        if self.edit_scope is not None and self._selection_edit_completed:
            return (
                "The selection edit is complete. Do not call any more tools; provide the final "
                "concise response."
            )
        if self.edit_scope is None and self._tool_calls_this_turn >= self.soft_tool_calls > 0:
            remaining = max(0, self.max_tool_calls - self._tool_calls_this_turn)
            self.session.set_outcome(
                "DRAINING",
                {
                    "tool_calls": self._tool_calls_this_turn,
                    "tool_calls_remaining": remaining,
                },
            )
            self._auto_save()
            return (
                f"Tool budget is low ({remaining} calls remain). Do not start new mutation, "
                "process, network, or costly work. Verify the current result with read-only "
                "tools if essential, then provide the final user-facing answer."
            )
        return None

    def _check_tool_loop(self, tb: ToolUseBlock, args: dict[str, Any]) -> str | None:
        self._tool_calls_this_turn += 1
        max_calls = (
            _SELECTION_MAX_TOOL_CALLS if self.edit_scope is not None else self.max_tool_calls
        )
        if self._tool_calls_this_turn > max_calls:
            self._tool_stop_code = "tool_budget_exhausted"
            return (
                f"Agent tool-call limit reached ({max_calls}) before completion. "
                "The task was stopped because it exhausted its tool budget."
            )

        fingerprint = f"{tb.name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}"
        count = self._tool_call_counts.get(fingerprint, 0) + 1
        self._tool_call_counts[fingerprint] = count
        if count > _MAX_IDENTICAL_TOOL_CALLS:
            self._tool_stop_code = "repeated_tool_call"
            return (
                f"Agent repeated the same tool call more than {_MAX_IDENTICAL_TOOL_CALLS} times. "
                "The task was stopped instead of retrying indefinitely."
            )
        return None

    def _should_skip_in_draining(self, tb: ToolUseBlock) -> bool:
        if (
            self.edit_scope is not None
            or self.soft_tool_calls <= 0
            or self._tool_calls_this_turn <= self.soft_tool_calls
        ):
            return False
        spec = self.tool_registry.get(tb.name)
        if spec is None:
            return False
        return bool(
            spec.effects
            & {
                "filesystem_write",
                "process",
                "network",
                "external_side_effect",
                "cost",
            }
        )

    def _record_tool_error(self) -> None:
        self._tool_errors_this_turn += 1
        max_errors = (
            _SELECTION_MAX_TOOL_ERRORS if self.edit_scope is not None else _DEFAULT_MAX_TOOL_ERRORS
        )
        if self._tool_errors_this_turn >= max_errors and self._tool_stop_reason is None:
            self._tool_stop_code = "tool_error_limit"
            self._tool_stop_reason = (
                f"Agent encountered {max_errors} tool errors in this turn. "
                "The task was stopped so the same failing strategy is not repeated."
            )

    def _append_tool_error(self, tb: ToolUseBlock, output: str) -> None:
        self.session.append(
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(
                        tool_use_id=tb.id,
                        tool_name=tb.name,
                        output=output,
                        is_error=True,
                    ),
                ],
            )
        )
        self._auto_save()

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
        requested_old_text = str(args.get("old_string", ""))
        normalized_selection = _normalize_line_endings(selected_text)
        normalized_requested = _normalize_line_endings(requested_old_text)
        if normalized_requested.rstrip("\n") != normalized_selection.rstrip("\n"):
            return (
                "Selection edit blocked: old_string does not equal the current active selection. "
                "Ignore selections from earlier turns and retry with the exact current text."
            )

        # Coordinates remain the authority. Canonicalize harmless CRLF/LF and
        # terminal-newline differences so the model does not fall back to a
        # whole-file write merely because Monaco selected the paragraph break.
        trailing_newlines = normalized_selection[len(normalized_selection.rstrip("\n")) :]
        normalized_new = _normalize_line_endings(str(args.get("new_string", ""))).rstrip("\n")
        normalized_new += trailing_newlines
        preferred_eol = _preferred_line_ending(selected_text)
        args["old_string"] = selected_text
        args["new_string"] = normalized_new.replace("\n", preferred_eol)

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
