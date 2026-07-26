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
_APPROVAL_TIMEOUT = 600.0  # 10 分钟等用户审批；超时必须与用户拒绝分开
_TOOL_RESULT_MAX_CHARS = 4000
_DEFAULT_MAX_TOOL_CALLS = 32
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

                recovery_instruction = self._step_instruction()
                for retry in range(3):
                    try:
                        async for event in self._llm_turn(
                            recovery_instruction=recovery_instruction
                        ):
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
                            yield AgentEvent.aborted(
                                self._approval_stop_reason
                                or "File edit rejected; no changes were applied"
                            )
                            yield AgentEvent.done()
                            return
                        if self._tool_stop_reason:
                            self._auto_save()
                            yield AgentEvent.error(
                                self._tool_stop_reason,
                                code=self._tool_stop_code or "tool_loop_stopped",
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

    async def _llm_turn(
        self, *, recovery_instruction: str | None = None
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
        tool_definitions = self._tool_definitions_for_turn()

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
                                            is_error=True,
                                        ),
                                    ],
                                )
                            )
                            yield AgentEvent.tool_result(
                                remaining.id, remaining.name, skip_output, is_error=True
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
                                ),
                            ],
                        )
                    )
                    self._auto_save()
                    yield AgentEvent.tool_result(tb.id, tb.name, tool_output, is_error=True)
                    if not self._aborted:
                        self._approval_denied = True
                        self._approval_stop_reason = stop_reason
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
        if is_error:
            self._record_tool_error()

        # Checkpoint after file modifications: include new content for frontend
        if tb.name in ("write_file", "str_replace") and not is_error:
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
        return None

    def _check_tool_loop(self, tb: ToolUseBlock, args: dict[str, Any]) -> str | None:
        self._tool_calls_this_turn += 1
        max_calls = (
            _SELECTION_MAX_TOOL_CALLS if self.edit_scope is not None else _DEFAULT_MAX_TOOL_CALLS
        )
        if self._tool_calls_this_turn > max_calls:
            self._tool_stop_code = "tool_call_limit"
            return (
                f"Agent tool-call limit reached ({max_calls}) before completion. "
                "The task was stopped to prevent an uncontrolled tool loop."
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
