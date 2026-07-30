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
import re
import time
import uuid
from collections import Counter
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import date
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

_DEFAULT_MAX_STEPS = 96
_APPROVAL_TIMEOUT = 600.0  # 10 分钟等用户审批；超时必须与用户拒绝分开
_TOOL_RESULT_MAX_CHARS = 4000
_DEFAULT_MAX_TOOL_CALLS = 64
_DEFAULT_SOFT_TOOL_CALLS = 56
_DEFAULT_MAX_MODEL_CALLS = 32
_DEFAULT_MAX_MUTATION_ATTEMPTS = 20
_DEFAULT_MAX_ACTIVE_SECONDS = 600.0
_DEFAULT_MAX_RESEARCH_CALLS = 24
_DEFAULT_SOFT_RESEARCH_CALLS = 20
_SELECTION_MAX_TOOL_CALLS = 4
_DEFAULT_MAX_TOOL_ERRORS = 5
_SELECTION_MAX_TOOL_ERRORS = 2
_MAX_IDENTICAL_TOOL_CALLS = 2
_APPROVAL_POLICY_VERSION = "1"
_ACADEMIC_FILE_SUFFIXES = frozenset({".md", ".markdown", ".tex", ".rst", ".adoc"})
_ACADEMIC_PATH_HINTS = frozenset(
    {
        "draft",
        "paper",
        "papers",
        "manuscript",
        "manuscripts",
        "thesis",
        "chapter",
        "chapters",
        "论文",
    }
)
_ACADEMIC_FILE_NAMES = frozenset(
    {
        "main.md",
        "main.tex",
        "paper.md",
        "paper.tex",
        "manuscript.md",
        "manuscript.tex",
        "thesis.tex",
    }
)
_FACT_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:\d+(?:\.\d+)?\s*%|\d{1,3}(?:,\d{3})+|\d+\.\d+|\d{2,})"
    r"(?![A-Za-z0-9_-])"
)
_ARXIV_ID_RE = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", re.IGNORECASE)
_CITATION_RE = re.compile(r"(?<!\!)\[(?:\d+(?:\s*[-,]\s*\d+)*)\]")
_CONTEXT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_CONTEXT_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "analysis",
        "article",
        "based",
        "before",
        "between",
        "from",
        "into",
        "model",
        "paper",
        "results",
        "study",
        "that",
        "their",
        "this",
        "using",
        "with",
    }
)
_VERIFICATION_CLAIMS = (
    "经核查",
    "经验证",
    "已验证",
    "完整读取",
    "全面核验",
    "verified",
    "validated",
    "complete dataset",
)
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
_RESEARCH_TOOLS = frozenset({"arxiv_search", "rag_search", "web_search", "web_fetch"})
_AUTO_EVIDENCE_TOOLS = frozenset(
    {"arxiv_search", "rag_search", "read_file", "run_command", "web_fetch"}
)
_PENDING_RESUME_MARKERS = (
    "继续",
    "未完成",
    "尚未完成",
    "接着",
    "continue",
    "resume",
    "unfinished",
)


class _EmptyModelResponse(RuntimeError):
    """Provider completed without a user-visible answer or tool call."""


class _OperationAborted(RuntimeError):
    """An active provider or tool operation was cancelled by the user."""


class _ResourceBudgetExceeded(RuntimeError):
    """A non-retryable per-turn execution budget was exhausted."""

    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


class _MalformedToolProtocol(RuntimeError):
    """Provider returned textual tool protocol instead of a user-facing response."""


def _contains_tool_protocol(text: str) -> bool:
    normalized = text.lower().replace("｜", "|")
    return any(
        marker in normalized
        for marker in (
            "dsml||tool_calls",
            "dsml|tool_calls",
            "<tool_calls>",
            "</tool_calls>",
            "<function=",
        )
    )


def _is_academic_target(path_value: str) -> bool:
    path = Path(path_value)
    if path.suffix.lower() not in _ACADEMIC_FILE_SUFFIXES:
        return False
    lowered_parts = {part.lower() for part in path.parts}
    return path.name.lower() in _ACADEMIC_FILE_NAMES or bool(lowered_parts & _ACADEMIC_PATH_HINTS)


def _fact_scan_text(text: str) -> str:
    # Markdown headings frequently contain section numbers rather than claims.
    without_current_date = text.replace(date.today().isoformat(), "")
    return "\n".join(
        line for line in without_current_date.splitlines() if not re.match(r"^\s*#{1,6}\s", line)
    )


def _fact_marker_counts(text: str) -> Counter[str]:
    scan = _fact_scan_text(text)
    arxiv_ids = _ARXIV_ID_RE.findall(scan)
    without_arxiv_ids = _ARXIV_ID_RE.sub(" ", scan)
    markers: Counter[str] = Counter(_FACT_NUMBER_RE.findall(without_arxiv_ids))
    markers.update(f"source_id:{value}" for value in arxiv_ids)
    markers.update(f"citation:{value}" for value in _CITATION_RE.findall(scan))
    for phrase in _VERIFICATION_CLAIMS:
        markers[f"claim:{phrase}"] = scan.lower().count(phrase.lower())
    return markers


def _new_fact_markers(old_text: str, new_text: str) -> list[str]:
    old_markers = _fact_marker_counts(old_text)
    new_markers = _fact_marker_counts(new_text)
    additions: list[str] = []
    for marker, count in new_markers.items():
        additions.extend([marker] * max(0, count - old_markers.get(marker, 0)))
    return additions


def _marker_value(marker: str) -> str:
    return marker.split(":", 1)[1] if marker.startswith("source_id:") else marker


def _context_line(text: str, marker: str) -> str:
    value = _marker_value(marker)
    for line in text.splitlines():
        if value in line:
            return line[:2000]
    index = text.find(value)
    if index < 0:
        return ""
    return text[max(0, index - 500) : index + len(value) + 500]


def _context_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _CONTEXT_TOKEN_RE.findall(text)
        if token.lower() not in _CONTEXT_STOPWORDS
    }


def _contextually_supports(source_text: str, new_text: str, marker: str) -> bool:
    """Require title/model overlap so an unrelated page sharing an ID cannot pass."""
    value = _marker_value(marker)
    if value not in source_text:
        return False
    claim_tokens = _context_tokens(_context_line(new_text, marker))
    shared = claim_tokens & _context_tokens(source_text)
    if len(shared) >= 2:
        return True
    return any(
        len(token) >= 8 or any(char.isdigit() for char in token) or "-" in token for token in shared
    )


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
        max_model_calls: int = _DEFAULT_MAX_MODEL_CALLS,
        max_mutation_attempts: int = _DEFAULT_MAX_MUTATION_ATTEMPTS,
        max_active_seconds: float = _DEFAULT_MAX_ACTIVE_SECONDS,
        max_research_calls: int = _DEFAULT_MAX_RESEARCH_CALLS,
        workspace_grant: str = "",
        editor_files: list[dict[str, Any]] | None = None,
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
        self.max_model_calls = max(1, int(max_model_calls))
        self.max_mutation_attempts = max(1, int(max_mutation_attempts))
        self.max_active_seconds = max(0.01, float(max_active_seconds))
        self.max_research_calls = max(1, int(max_research_calls))
        self.soft_research_calls = min(
            _DEFAULT_SOFT_RESEARCH_CALLS, max(0, self.max_research_calls - 1)
        )
        self.workspace_grant = workspace_grant
        self._editor_files: dict[str, dict[str, Any]] = {}
        workspace_path = tool_registry._workspace_root
        for state in editor_files or []:
            if not isinstance(state, dict):
                continue
            raw_path = str(state.get("file_path", "")).strip()
            if not raw_path:
                continue
            try:
                path = Path(raw_path)
                if not path.is_absolute() and workspace_path is not None:
                    path = workspace_path / path
                resolved = path.resolve()
                if workspace_path is not None:
                    resolved.relative_to(workspace_path.resolve())
            except (OSError, ValueError):
                continue
            self._editor_files[str(resolved).lower()] = dict(state)
        self.usage = UsageTracker(
            model=session.meta.model,
            total_input=session.meta.total_usage.input_tokens,
            total_output=session.meta.total_usage.output_tokens,
        )
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
        self._model_calls_this_turn = 0
        self._mutation_attempts_this_turn = 0
        self._research_tool_calls_this_turn = 0
        self._active_seconds_this_turn = 0.0
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
        self._resume_pending_actions = False
        self._pending_created_this_turn = False
        self._pending_response_retries_this_turn = 0
        # Lifecycle tracking — used by router._cleanup_pool to evict stale
        # sessions safely (never evict a streaming session).
        self.last_active_monotonic: float = time.monotonic()
        self._is_streaming: bool = False
        self._active_operation_task: asyncio.Future[Any] | None = None

    # ---- Public API ----

    async def turn(
        self,
        user_message: str,
        *,
        resume: bool = False,
        persisted_user_message: str | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        if not resume and not user_message.strip():
            yield AgentEvent.error("empty message")
            yield AgentEvent.done()
            return

        self._approval_denied = False
        self._approval_stop_reason = None
        self._tool_calls_this_turn = 0
        self._tool_errors_this_turn = 0
        self._model_calls_this_turn = 0
        self._mutation_attempts_this_turn = 0
        self._research_tool_calls_this_turn = 0
        self._active_seconds_this_turn = 0.0
        self._tool_call_counts.clear()
        self._tool_stop_reason = None
        self._tool_stop_code = None
        self._selection_edit_completed = False
        self._changed_files_this_turn.clear()
        self._turn_message_start = len(self.session.messages)
        self._turn_id = uuid.uuid4().hex
        lowered_message = user_message.lower()
        self._resume_pending_actions = resume or any(
            marker in lowered_message for marker in _PENDING_RESUME_MARKERS
        )
        self._pending_created_this_turn = False
        self._pending_response_retries_this_turn = 0
        self.session.start_turn(self._turn_id)
        self.session.set_outcome(
            "RUNNING",
            {
                "pending_actions": self._active_pending_actions(),
            },
        )
        self._is_streaming = True
        self.last_active_monotonic = time.monotonic()
        try:
            yield AgentEvent.session_started(self.session.session_id)
            if not resume:
                self.session.append(
                    Message(
                        role=MessageRole.USER,
                        blocks=[TextBlock(text=user_message)],
                        persisted_text=persisted_user_message,
                        context_externalized=persisted_user_message is not None
                        and persisted_user_message != user_message,
                    )
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
                    retry_pending_delivery = False
                    try:
                        async for event in self._llm_turn(
                            recovery_instruction=recovery_instruction
                        ):
                            if (
                                event.type == AgentEventType.RESPONSE
                                and self._active_pending_actions()
                            ):
                                if self._pending_response_retries_this_turn < 2:
                                    self._pending_response_retries_this_turn += 1
                                    retry_pending_delivery = True
                                    yield AgentEvent.warning(
                                        "交付文件仍未完成，已拒绝降级为聊天回复并继续恢复写入。",
                                        code="pending_actions_retry",
                                        attempt=self._pending_response_retries_this_turn,
                                        max_attempts=2,
                                        reset_stream=True,
                                        pending_actions=self._active_pending_actions(),
                                    )
                                    continue
                                pending = self._active_pending_actions()
                                event.data.update(
                                    {
                                        "partial": True,
                                        "stop_code": "pending_actions_remaining",
                                        "stop_reason": (
                                            "Required file mutation remains unresolved after "
                                            "automatic recovery attempts"
                                        ),
                                        "pending_actions": pending,
                                    }
                                )
                                yield event
                                self._persist_turn_outcome(
                                    "PARTIAL",
                                    "pending_actions_remaining",
                                    (
                                        "Required file mutation remains unresolved after "
                                        "automatic recovery attempts"
                                    ),
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
                        if retry_pending_delivery:
                            break
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
                    except _OperationAborted:
                        self._persist_turn_outcome(
                            "ABORTED", "user_aborted", "Session aborted by user"
                        )
                        yield AgentEvent.aborted("Session aborted by user")
                        yield AgentEvent.done()
                        return
                    except _ResourceBudgetExceeded as exc:
                        self._tool_stop_code = exc.code
                        self._tool_stop_reason = exc.reason
                        async for final_event in self._finalize_stopped_turn(allow_model=False):
                            yield final_event
                        yield AgentEvent.usage(
                            TokenUsage(
                                input_tokens=self.usage.total_input,
                                output_tokens=self.usage.total_output,
                            )
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
        if decision not in {"allow_once", "allow_session", "deny"}:
            return False
        evt = self._approval_events.get(event_id)
        if evt is None:
            return False
        self._approval_decisions[event_id] = decision
        evt.set()
        return True

    def abort(self) -> None:
        self._aborted = True
        if self._active_operation_task is not None:
            self._active_operation_task.cancel()
        # Signal all pending approvals to unblock
        for evt in self._approval_events.values():
            evt.set()

    # ---- Internal ----

    async def _await_active_operation(self, awaitable: Any) -> Any:
        """Make one provider/tool awaitable immediately cancellable through abort()."""
        task = asyncio.ensure_future(awaitable)
        self._active_operation_task = task
        started = time.monotonic()
        try:
            remaining = self.max_active_seconds - self._active_seconds_this_turn
            if remaining <= 0:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise _ResourceBudgetExceeded(
                    "active_time_exhausted",
                    (
                        "Agent active execution time limit reached "
                        f"({self.max_active_seconds:g}s) before completion."
                    ),
                )
            return await asyncio.wait_for(task, timeout=remaining)
        except TimeoutError as exc:
            if self._aborted:
                raise _OperationAborted from exc
            raise _ResourceBudgetExceeded(
                "active_time_exhausted",
                (
                    "Agent active execution time limit reached "
                    f"({self.max_active_seconds:g}s) before completion."
                ),
            ) from exc
        except asyncio.CancelledError as exc:
            if self._aborted:
                raise _OperationAborted from exc
            raise
        finally:
            self._active_seconds_this_turn += time.monotonic() - started
            if self._active_operation_task is task:
                self._active_operation_task = None

    async def _abortable_stream(self, stream: Any) -> AsyncGenerator[Any, None]:
        iterator = stream.__aiter__()
        while True:
            try:
                chunk = await self._await_active_operation(anext(iterator))
            except StopAsyncIteration:
                return
            yield chunk

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
            "pending_actions": self._active_pending_actions(),
        }

    def _active_pending_actions(self) -> list[dict[str, Any]]:
        if not (self._pending_created_this_turn or self._resume_pending_actions):
            return []
        return [dict(action) for action in self.session.meta.pending_actions]

    def _pending_target_path(self, tb: ToolUseBlock, path_value: str = "") -> str:
        raw_path = str(path_value or "").strip()
        if not raw_path and tb.input:
            match = re.search(r'"(?:file_path|path)"\s*:\s*"([^"]+)', tb.input)
            if match:
                raw_path = match.group(1)
        if not raw_path:
            return ""
        try:
            path = Path(raw_path)
            workspace = self.tool_registry._workspace_root
            if not path.is_absolute() and workspace is not None:
                path = workspace / path
            return str(path.resolve())
        except (OSError, ValueError):
            return raw_path

    def _record_pending_mutation(
        self,
        tb: ToolUseBlock,
        *,
        error_code: str,
        target_path: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        if tb.name not in {"write_file", "str_replace"}:
            return
        self.session.record_pending_action(
            tool_name=tb.name,
            target_path=self._pending_target_path(tb, target_path),
            error_code=error_code,
            turn_id=self._turn_id,
            details=details,
        )
        self._pending_created_this_turn = True
        self._auto_save()

    def _resolve_pending_mutation(
        self,
        tb: ToolUseBlock,
        *,
        target_path: str,
    ) -> None:
        if tb.name not in {"write_file", "str_replace"}:
            return
        self.session.resolve_pending_action(
            tool_name=tb.name,
            target_path=self._pending_target_path(tb, target_path),
        )

    def _persist_turn_outcome(self, state: str, stop_code: str, stop_reason: str) -> None:
        self.session.set_outcome(
            state,
            self._build_turn_outcome(stop_code=stop_code, stop_reason=stop_reason),
        )
        self._auto_save()

    async def _finalize_stopped_turn(
        self, *, allow_model: bool = True
    ) -> AsyncGenerator[AgentEvent, None]:
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
            if allow_model and self._model_calls_this_turn < self.max_model_calls:
                for attempt in range(2):
                    try:
                        repair_instruction = instruction
                        if attempt:
                            repair_instruction += (
                                "\n\nThe previous finalization contained provider tool protocol. "
                                "Return plain user-facing text only. Do not output XML-like tags, "
                                "DSML, JSON tool calls, or function syntax."
                            )
                        async for event in self._llm_turn(
                            recovery_instruction=repair_instruction,
                            force_no_tools=True,
                        ):
                            if event.type == AgentEventType.RESPONSE:
                                emitted_response = True
                                yield AgentEvent.response(
                                    str(event.data.get("text", "")),
                                    partial=True,
                                    stop_code=stop_code,
                                    stop_reason=stop_reason,
                                    tool_counts=outcome["tool_counts"],
                                    changed_count=len(outcome["changed_files"]),
                                )
                            else:
                                yield event
                        if emitted_response:
                            break
                    except _MalformedToolProtocol:
                        logger.warning(
                            "Agent finalization returned textual tool protocol (attempt %d/2)",
                            attempt + 1,
                        )
                        continue
                    except Exception as exc:
                        logger.warning("Agent finalization failed: %s", exc)
                        break
            if not emitted_response:
                counts = outcome["tool_counts"]
                yield AgentEvent.response(
                    self._deterministic_partial_summary(outcome),
                    partial=True,
                    stop_code=stop_code,
                    stop_reason=stop_reason,
                    tool_counts=counts,
                    changed_count=len(outcome["changed_files"]),
                )
        finally:
            self.session.set_outcome("PARTIAL", outcome)
            self._auto_save()

    @staticmethod
    def _deterministic_partial_summary(outcome: dict[str, Any]) -> str:
        counts = outcome.get("tool_counts", {})
        changed_files = list(outcome.get("changed_files", []) or [])
        parts = [
            "Task partially completed.",
            f"Stop code: {outcome.get('stop_code', 'tool_loop_stopped')}.",
            (
                "Tool results: "
                f"{int(counts.get('success', 0) or 0)} succeeded, "
                f"{int(counts.get('error', 0) or 0)} failed, "
                f"{int(counts.get('skipped', 0) or 0)} skipped, "
                f"{int(counts.get('denied', 0) or 0)} denied."
            ),
        ]
        if changed_files:
            parts.append("Changed files: " + ", ".join(changed_files) + ".")
        parts.append("Remaining or skipped work is unverified; continue only after reviewing it.")
        return " ".join(parts)

    async def _llm_turn(
        self,
        *,
        recovery_instruction: str | None = None,
        force_no_tools: bool = False,
    ) -> AsyncGenerator[AgentEvent, None]:
        import os

        self._model_calls_this_turn += 1
        if self._model_calls_this_turn > self.max_model_calls:
            raise _ResourceBudgetExceeded(
                "model_call_budget_exhausted",
                (f"Agent model-call limit reached ({self.max_model_calls}) before completion."),
            )

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
            resp = await self._await_active_operation(
                self.provider.chat(
                    messages=messages,
                    tools=tool_definitions,
                    system_prompt=system_prompt,
                )
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
            self.session.meta.total_usage = TokenUsage(
                input_tokens=self.usage.total_input,
                output_tokens=self.usage.total_output,
                cache_read_tokens=self.usage.total_cache_read,
                cache_creation_tokens=self.usage.total_cache_creation,
            )
            self.session.meta.usage_available = True
            return True

        async for chunk in self._abortable_stream(provider_stream):
            if isinstance(chunk, TextBlock):
                text_blocks.append(chunk)
                # A reserved no-tools finalizer is buffered until its entire
                # text is known safe. This prevents DSML/function protocol from
                # leaking through token events before validation.
                if not force_no_tools:
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
                if _contains_tool_protocol(full_text):
                    if not force_no_tools:
                        yield AgentEvent.warning(
                            "",
                            code="malformed_tool_call",
                            reset_stream=True,
                        )
                    raise _MalformedToolProtocol(
                        "Provider returned textual tool protocol instead of a response"
                    )
                assistant_blocks = list(tool_blocks)
                if text_blocks:
                    assistant_blocks.append(TextBlock(text=full_text))
                if assistant_blocks:
                    self.session.append(
                        Message(
                            role=MessageRole.ASSISTANT,
                            blocks=assistant_blocks,
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
                            self._log_tool_completion(remaining, "skipped")
                        self._auto_save()
                        return
                return

    async def _execute_tool(self, tb: ToolUseBlock) -> AsyncGenerator[AgentEvent, None]:
        tool_started = time.monotonic()
        args = {}
        try:
            if tb.input:
                args = json.loads(tb.input)
        except (json.JSONDecodeError, TypeError) as exc:
            detail = (
                "Tool input is invalid or truncated JSON; the tool was not executed. "
                f"Retry with a smaller payload or split the operation into compact steps "
                f"(input_chars={len(tb.input or '')}, error_position={getattr(exc, 'pos', 0)})."
            )
            self._record_pending_mutation(
                tb,
                error_code="invalid_tool_json",
                details={
                    "input_chars": len(tb.input or ""),
                    "error_position": getattr(exc, "pos", 0),
                },
            )
            self._append_tool_error(tb, detail)
            self._record_tool_error()
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                detail,
                is_error=True,
                status="error",
            )
            return
        if not isinstance(args, dict):
            detail = "Tool input must be a JSON object; the tool was not executed."
            self._append_tool_error(tb, detail)
            self._record_tool_error()
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                detail,
                is_error=True,
                status="error",
            )
            return

        loop_error = self._check_tool_loop(tb, args)
        if loop_error:
            self._append_tool_error(tb, loop_error)
            self._tool_stop_reason = loop_error
            yield AgentEvent.tool_result(tb.id, tb.name, loop_error, is_error=True)
            return
        mutation_budget_error = self._check_mutation_budget(tb.name)
        if mutation_budget_error:
            self._append_tool_error(tb, mutation_budget_error)
            self._tool_stop_reason = mutation_budget_error
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                mutation_budget_error,
                is_error=True,
            )
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
            self._log_tool_completion(tb, "skipped", duration_started=tool_started)
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                output,
                status="skipped",
            )
            return

        hook_asks_for_approval = False
        if self.hook_runner is not None:
            try:
                hook_result = await self._await_active_operation(
                    self.hook_runner.run(
                        HookPoint.PRE_TOOL_USE,
                        HookEvent(
                            hook=HookPoint.PRE_TOOL_USE,
                            tool_name=tb.name,
                            tool_input=json.dumps(args, ensure_ascii=False, sort_keys=True),
                        ),
                    )
                )
            except _OperationAborted:
                tool_output = "Tool execution aborted while running its safety hook."
                self._append_skipped_tool(tb, tool_output)
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    tool_output,
                    status="skipped",
                )
                return
            except _ResourceBudgetExceeded as exc:
                self._tool_stop_code = exc.code
                self._tool_stop_reason = exc.reason
                tool_output = f"Tool execution skipped: {exc.reason}"
                self._append_skipped_tool(tb, tool_output)
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    tool_output,
                    status="skipped",
                )
                return
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
                self._log_tool_completion(
                    tb,
                    "denied",
                    metadata={"code": "hook_denied"},
                    duration_started=tool_started,
                )
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
                if tb.name == "write_file" and not bool(args.get("final_chunk", True)):
                    self._record_pending_mutation(
                        tb,
                        error_code="chunked_write_incomplete",
                        target_path=str(args.get("file_path", "")),
                    )
                else:
                    self._resolve_pending_mutation(
                        tb,
                        target_path=str(args.get("file_path", "") or args.get("path", "")),
                    )
                self._auto_save()
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    output,
                    status="no_change",
                )
                self._log_tool_completion(tb, "no_change", duration_started=tool_started)
                return
        spec = self.tool_registry.get(tb.name)
        preflight_result = self.tool_registry.preflight(tb.name, args)
        if preflight_result is not None:
            self._record_pending_mutation(
                tb,
                error_code=str(
                    (preflight_result.metadata or {}).get("code", "tool_preflight_failed")
                ),
                target_path=str(args.get("file_path", "") or args.get("path", "")),
                details=dict(preflight_result.metadata or {}),
            )
            self._append_tool_error(
                tb,
                preflight_result.output,
                metadata=dict(preflight_result.metadata or {}),
            )
            self._record_tool_error()
            yield AgentEvent.tool_result(
                tb.id,
                tb.name,
                preflight_result.output,
                is_error=True,
                status=preflight_result.status,
                metadata=dict(preflight_result.metadata or {}),
            )
            return

        perm_result = self.permission_policy.authorize(tb.name, normalized_input)

        # Capture old content for diff
        old_text = ""
        new_text = ""
        evidence_old_text = ""
        verified_evidence_refs: list[dict[str, str]] = []
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
            evidence_old_text = old_text
        elif tb.name == "write_file":
            new_text = args.get("content", "")
            if resolved_path:
                try:
                    full = Path(resolved_path)
                    if full.is_file():
                        evidence_old_text = full.read_text(encoding="utf-8", errors="replace")
                        old_text = evidence_old_text[:4000]
                except Exception:
                    pass
            if str(args.get("mode", "overwrite")).lower() == "append":
                evidence_old_text = ""
        result_metadata: dict[str, Any] = {}

        if tb.name in {"write_file", "str_replace"}:
            conflict = self._editor_conflict(resolved_path)
            if conflict is not None:
                detail, metadata = conflict
                self._record_pending_mutation(
                    tb,
                    error_code=str(metadata.get("code", "editor_conflict")),
                    target_path=resolved_path,
                    details=metadata,
                )
                self._append_tool_error(tb, detail, metadata=metadata)
                self._record_tool_error()
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    detail,
                    is_error=True,
                    status="error",
                    metadata=metadata,
                )
                return

        if tb.name in {"write_file", "str_replace"} and _is_academic_target(resolved_path):
            missing_facts = _new_fact_markers(evidence_old_text, new_text)
            if missing_facts:
                verified_evidence_refs, unsupported_facts = self._verify_evidence_refs(
                    args.get("evidence_refs"),
                    missing_facts,
                    new_text,
                )
                if unsupported_facts:
                    display_facts = [
                        value.split(":", 1)[1] if ":" in value else value
                        for value in unsupported_facts
                    ]
                    metadata = {
                        "code": "academic_evidence_required",
                        "missing_facts": display_facts,
                        "evidence_candidates": self._evidence_candidates(),
                        "suggested_next_action": (
                            "Reuse an exact quote from one of evidence_candidates and retry. "
                            "The runtime will resolve a stale or fabricated tool_use_id to the "
                            "real successful result when the quote matches."
                        ),
                    }
                    detail = (
                        "Academic evidence gate blocked the mutation before approval. "
                        "Unsupported new facts: " + ", ".join(display_facts)
                    )
                    self._record_pending_mutation(
                        tb,
                        error_code="academic_evidence_required",
                        target_path=resolved_path,
                        details={
                            "missing_facts": display_facts,
                            "evidence_candidates": [
                                value.get("tool_use_id", "")
                                for value in metadata["evidence_candidates"]
                            ],
                        },
                    )
                    self._append_tool_error(tb, detail, metadata=metadata)
                    self._record_tool_error()
                    yield AgentEvent.tool_result(
                        tb.id,
                        tb.name,
                        detail,
                        is_error=True,
                        status="error",
                        metadata=metadata,
                    )
                    return

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
            session_scope_approved = (
                approval_key in self._session_approved_actions
                or self.session.has_session_approval(
                    approval_key,
                    workspace_grant=self.workspace_grant,
                    policy_version=_APPROVAL_POLICY_VERSION,
                )
            )
            if (
                hook_asks_for_approval or (requires_approval and not self.auto_approve)
            ) and not session_scope_approved:
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
                    self._log_tool_completion(
                        tb,
                        "denied",
                        metadata={"code": decision},
                        duration_started=tool_started,
                    )
                    if not self._aborted:
                        self._approval_denied = True
                        self._approval_stop_reason = stop_reason
                    return
                if decision == "allow_session":
                    self._session_approved_actions.add(approval_key)
                    self.session.grant_session_approval(
                        approval_key,
                        workspace_grant=self.workspace_grant,
                        policy_version=_APPROVAL_POLICY_VERSION,
                    )
                    self._auto_save()

            # Capture an exact pre-image immediately before execution. Preview
            # text is intentionally truncated and cannot support reliable Undo.
            mutation_before_exists = False
            mutation_before_content = ""
            mutation_before_bytes = b""
            mutation_before_hash = ""
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
                            mutation_before_hash = hashlib.sha256(mutation_before_bytes).hexdigest()
                        else:
                            mutation_before_content = read_text_exact(mutation_path)
                            mutation_before_hash = hashlib.sha256(
                                mutation_before_content.encode("utf-8")
                            ).hexdigest()
                except Exception:
                    mutation_before_exists = False
                    mutation_before_content = ""
                    mutation_before_bytes = b""

            # Execute
            try:
                result = await self._await_active_operation(
                    self.tool_registry.execute(tb.name, args)
                )
            except _OperationAborted:
                tool_output = "Tool execution aborted by user."
                self._append_skipped_tool(tb, tool_output)
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    tool_output,
                    status="skipped",
                )
                return
            except _ResourceBudgetExceeded as exc:
                self._tool_stop_code = exc.code
                self._tool_stop_reason = exc.reason
                tool_output = f"Tool execution skipped: {exc.reason}"
                self._append_skipped_tool(tb, tool_output)
                yield AgentEvent.tool_result(
                    tb.id,
                    tb.name,
                    tool_output,
                    status="skipped",
                )
                return
            tool_output = result.output
            is_error = result.is_error
            result_status = result.status
            result_truncated = result.truncated
            result_original_chars = result.original_chars
            result_returned_chars = result.returned_chars
            result_metadata = dict(result.metadata or {})
            if verified_evidence_refs:
                result_metadata["evidence_refs"] = verified_evidence_refs
            if tb.name in {"write_file", "str_replace"}:
                if is_error:
                    self._record_pending_mutation(
                        tb,
                        error_code=str(result_metadata.get("code", "tool_execution_failed")),
                        target_path=resolved_path,
                        details=result_metadata,
                    )
                elif (
                    tb.name == "write_file"
                    and result_status in {"success", "no_change"}
                    and not bool(args.get("final_chunk", True))
                ):
                    self._record_pending_mutation(
                        tb,
                        error_code="chunked_write_incomplete",
                        target_path=resolved_path,
                        details=result_metadata,
                    )
                elif result_status in {"success", "no_change"}:
                    self._resolve_pending_mutation(
                        tb,
                        target_path=resolved_path,
                    )
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
                try:
                    await self._await_active_operation(
                        self.hook_runner.run(
                            post_point,
                            HookEvent(
                                hook=post_point,
                                tool_name=tb.name,
                                tool_input=json.dumps(args, ensure_ascii=False, sort_keys=True),
                                tool_result=tool_output,
                                is_error=is_error,
                            ),
                        )
                    )
                except _OperationAborted:
                    logger.info("PostToolUse hook cancelled after tool %s completed", tb.name)
                except _ResourceBudgetExceeded as exc:
                    self._tool_stop_code = exc.code
                    self._tool_stop_reason = exc.reason

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
        self._log_tool_completion(
            tb,
            result_status,
            metadata=result_metadata,
            duration_started=tool_started,
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
            checkpoint_after_hash = ""
            if checkpoint_path and not mutation_is_binary:
                with suppress(Exception):
                    fp = Path(checkpoint_path)
                    if fp.is_file():
                        new_content = fp.read_text(encoding="utf-8", errors="replace")
                        checkpoint_after_hash = hashlib.sha256(
                            new_content.encode("utf-8")
                        ).hexdigest()
            elif checkpoint_path and mutation_is_binary:
                with suppress(Exception):
                    checkpoint_after_hash = hashlib.sha256(
                        Path(checkpoint_path).read_bytes()
                    ).hexdigest()
            yield AgentEvent.checkpoint(
                {
                    "action": tb.name,
                    "file": checkpoint_path,
                    "workspace": self.session.meta.workspace,
                    "content": new_content[:10000] if new_content else tool_output,
                    "content_truncated": len(new_content) > 10000,
                    "evidence_refs": verified_evidence_refs,
                    "before_hash": mutation_before_hash or None,
                    "after_hash": checkpoint_after_hash or None,
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
        pending = self._active_pending_actions()
        if pending:
            self.session.set_outcome(
                "RECOVERING",
                {
                    "pending_actions": pending,
                    "automatic_recovery_attempt": self._pending_response_retries_this_turn + 1,
                },
            )
            self._auto_save()
            return (
                "# Required delivery recovery\n"
                "A requested file mutation is still pending. A chat-only answer is not an "
                "acceptable substitute. Inspect the pending error and retry the mutation now. "
                "For academic_evidence_required, reuse exact quotes from successful tool results; "
                "never invent tool_use_id values. For a large write, use write_file with "
                "mode=overwrite and final_chunk=false for the first compact chunk, then "
                "mode=append for compact continuation chunks and final_chunk=true only on the "
                "last chunk. Do not return a final response until the pending action is resolved.\n\n"
                f"Pending actions:\n{json.dumps(pending, ensure_ascii=False, sort_keys=True)}"
            )
        if (
            self.edit_scope is None
            and self.soft_research_calls > 0
            and self._research_tool_calls_this_turn >= self.soft_research_calls
        ):
            remaining = max(0, self.max_research_calls - self._research_tool_calls_this_turn)
            return (
                f"Research budget is nearly exhausted ({remaining} research calls remain). "
                "Stop broad or duplicate searches. Select the strongest sources already fetched, "
                "synthesize the requested deliverable, write it, and verify the written file."
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
        if tb.name in _RESEARCH_TOOLS:
            self._research_tool_calls_this_turn += 1
            if self._research_tool_calls_this_turn > self.max_research_calls:
                self._tool_stop_code = "research_budget_exhausted"
                return (
                    "Research tool-call limit reached "
                    f"({self.max_research_calls}) before delivery. Stop expanding the search set "
                    "and complete the deliverable from the sources already collected."
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

    def _check_mutation_budget(self, tool_name: str) -> str | None:
        spec = self.tool_registry.get(tool_name)
        if spec is None or "filesystem_write" not in spec.effects:
            return None
        self._mutation_attempts_this_turn += 1
        if self._mutation_attempts_this_turn <= self.max_mutation_attempts:
            return None
        self._tool_stop_code = "mutation_budget_exhausted"
        return (
            "Agent file-mutation attempt limit reached "
            f"({self.max_mutation_attempts}) before completion."
        )

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

    def _successful_tool_results(self) -> list[ToolResultBlock]:
        results: list[ToolResultBlock] = []
        for message in self.session.messages:
            for block in message.blocks:
                if (
                    isinstance(block, ToolResultBlock)
                    and not block.is_error
                    and block.status not in {"error", "denied", "skipped"}
                ):
                    results.append(block)
        return results

    def _evidence_candidates(self) -> list[dict[str, str]]:
        return [
            {
                "tool_use_id": block.tool_use_id,
                "tool_name": block.tool_name,
            }
            for block in self._successful_tool_results()
            if block.tool_name in _AUTO_EVIDENCE_TOOLS
        ][-64:]

    @staticmethod
    def _verified_evidence(
        *,
        source_type: str,
        source_id: str,
        source_text: str,
        quote: str,
        anchor: str = "",
    ) -> dict[str, str]:
        return {
            "source": source_type,
            "tool_use_id": source_id if source_type == "tool_result" else "",
            "source_id": source_id,
            "source_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            "quote_hash": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            "anchor": anchor[:500],
        }

    def _verify_evidence_refs(
        self,
        raw_refs: Any,
        fact_markers: list[str],
        new_text: str,
    ) -> tuple[list[dict[str, str]], list[str]]:
        refs = raw_refs if isinstance(raw_refs, list) else []
        successful_results = self._successful_tool_results()
        tool_results = {block.tool_use_id: block for block in successful_results}
        user_text = ""
        for message in self.session.messages:
            if message.role == MessageRole.USER:
                user_text = message.text_content()

        verified: list[dict[str, str]] = []
        supported_text: list[str] = []
        support_records: list[tuple[str, str, str]] = []
        seen_refs: set[tuple[str, str]] = set()

        def add_verified(
            *,
            source_type: str,
            source_id: str,
            source_text: str,
            quote: str,
            anchor: str = "",
        ) -> None:
            key = (source_id, hashlib.sha256(quote.encode("utf-8")).hexdigest())
            if key in seen_refs:
                return
            seen_refs.add(key)
            supported_text.append(quote)
            support_records.append((source_type, source_text, quote))
            verified.append(
                self._verified_evidence(
                    source_type=source_type,
                    source_id=source_id,
                    source_text=source_text,
                    quote=quote,
                    anchor=anchor,
                )
            )

        for value in refs[:64]:
            if not isinstance(value, dict):
                continue
            quote = str(value.get("quote", "")).strip()
            if not quote:
                continue
            tool_use_id = str(value.get("tool_use_id", "")).strip()
            source = str(value.get("source", "")).strip()
            source_text = ""
            source_type = ""
            source_id = ""
            if tool_use_id:
                block = tool_results.get(tool_use_id)
                if block is not None and quote in block.output:
                    source_text = block.output
                    source_type = "tool_result"
                    source_id = block.tool_use_id
                else:
                    # Provider-generated IDs are often stale or fabricated.
                    # Recover provenance only when the exact quote is present
                    # in an actually successful persisted tool result.
                    matched = next(
                        (
                            candidate
                            for candidate in reversed(successful_results)
                            if quote in candidate.output
                        ),
                        None,
                    )
                    if matched is None:
                        continue
                    source_text = matched.output
                    source_type = "tool_result"
                    source_id = matched.tool_use_id
            elif source == "user_message":
                source_text = user_text
                source_type = "user_message"
                source_id = self._turn_id or "current_turn"
            else:
                matched = next(
                    (
                        candidate
                        for candidate in reversed(successful_results)
                        if quote in candidate.output
                    ),
                    None,
                )
                if matched is None:
                    continue
                source_text = matched.output
                source_type = "tool_result"
                source_id = matched.tool_use_id
            if quote not in source_text:
                continue
            add_verified(
                source_type=source_type,
                source_id=source_id,
                source_text=source_text,
                quote=quote,
                anchor=str(value.get("anchor", "")),
            )

        # Proactively recover facts from sources already collected in this
        # session. Context overlap prevents an unrelated arXiv page that merely
        # shares an identifier from grounding the claim.
        combined = "\n".join(supported_text)
        for marker in fact_markers:
            if marker.startswith(("citation:", "claim:")) or _marker_value(marker) in combined:
                continue
            marker_value = _marker_value(marker)
            if marker_value in user_text:
                quote = _context_line(user_text, marker) or marker_value
                add_verified(
                    source_type="user_message",
                    source_id=self._turn_id or "current_turn",
                    source_text=user_text,
                    quote=quote,
                )
                combined = "\n".join(supported_text)
                continue
            for block in reversed(successful_results):
                if block.tool_name not in _AUTO_EVIDENCE_TOOLS:
                    continue
                if not _contextually_supports(block.output, new_text, marker):
                    continue
                quote = _context_line(block.output, marker) or marker_value
                add_verified(
                    source_type="tool_result",
                    source_id=block.tool_use_id,
                    source_text=block.output,
                    quote=quote,
                    anchor=_context_line(new_text, marker),
                )
                combined = "\n".join(supported_text)
                break

        unsupported: list[str] = []
        for marker in fact_markers:
            # Citations and verification language require a real validated
            # source, while numeric facts must appear verbatim in the quote.
            if marker.startswith(("citation:", "claim:")):
                if not verified:
                    unsupported.append(marker)
            elif marker.startswith("source_id:"):
                marker_value = _marker_value(marker)
                if not any(
                    marker_value in quote
                    and (
                        source_type == "user_message"
                        or _contextually_supports(source_text, new_text, marker)
                    )
                    for source_type, source_text, quote in support_records
                ):
                    unsupported.append(marker)
            elif _marker_value(marker) not in combined:
                unsupported.append(marker)
        return verified, unsupported

    def _log_tool_completion(
        self,
        tb: ToolUseBlock,
        status: str,
        *,
        metadata: dict[str, Any] | None = None,
        duration_started: float | None = None,
    ) -> None:
        details = metadata or {}
        duration_ms = (
            max(0, int((time.monotonic() - duration_started) * 1000))
            if duration_started is not None
            else 0
        )
        log = logger.warning if status in {"error", "denied"} else logger.info
        log(
            "agent_tool_completed session_id=%s turn_id=%s tool_use_id=%s "
            "tool_name=%s status=%s error_code=%s duration_ms=%d",
            self.session.session_id,
            self._turn_id,
            tb.id,
            tb.name,
            status,
            str(details.get("code", "")),
            duration_ms,
        )

    def _editor_conflict(self, resolved_path: str) -> tuple[str, dict[str, Any]] | None:
        if not resolved_path:
            return None
        try:
            key = str(Path(resolved_path).resolve()).lower()
        except (OSError, ValueError):
            return None
        state = self._editor_files.get(key)
        if state is None:
            return None
        if bool(state.get("is_dirty", False)):
            return (
                "File mutation blocked because the same file has unsaved editor changes. "
                "Save or resolve the editor version before retrying.",
                {
                    "code": "dirty_editor_conflict",
                    "file_path": resolved_path,
                    "editor_version": int(state.get("editor_version", 0) or 0),
                    "suggested_next_action": "save_or_resolve_editor",
                },
            )
        expected_hash = str(state.get("content_hash", "") or "").lower()
        if not expected_hash:
            return None
        try:
            path = Path(resolved_path)
            if not path.is_file():
                return None
            disk_text = path.read_text(encoding="utf-8", errors="strict")
            disk_hash = hashlib.sha256(disk_text.encode("utf-8")).hexdigest()
        except (OSError, UnicodeError):
            return None
        if disk_hash == expected_hash:
            return None
        return (
            "File mutation blocked because the editor snapshot no longer matches the disk file.",
            {
                "code": "editor_version_conflict",
                "file_path": resolved_path,
                "expected_hash": expected_hash,
                "actual_hash": disk_hash,
                "editor_version": int(state.get("editor_version", 0) or 0),
                "suggested_next_action": "reload_or_resolve_editor",
            },
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

    def _append_tool_error(
        self,
        tb: ToolUseBlock,
        output: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.append(
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(
                        tool_use_id=tb.id,
                        tool_name=tb.name,
                        output=output,
                        is_error=True,
                        metadata=dict(metadata or {}),
                    ),
                ],
            )
        )
        self._log_tool_completion(tb, "error", metadata=metadata)
        self._auto_save()

    def _append_skipped_tool(self, tb: ToolUseBlock, output: str) -> None:
        self.session.append(
            Message(
                role=MessageRole.TOOL,
                blocks=[
                    ToolResultBlock(
                        tool_use_id=tb.id,
                        tool_name=tb.name,
                        output=output,
                        status="skipped",
                    ),
                ],
            )
        )
        self._log_tool_completion(tb, "skipped")
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
                # Live snapshots already use atomic replace. Rotating a complete
                # JSONL snapshot on every tool event causes large sessions to
                # churn .1/.2/.3 files and can collide with readers on Windows.
                self.session.save(sp)
            except Exception as e:
                logger.warning("auto-save session failed: %s", e)


async def _fallback_stream(resp: ProviderResponse) -> AsyncGenerator:
    for block in resp.blocks:
        yield block
    if resp.usage.total() > 0:
        yield resp.usage
    yield resp
