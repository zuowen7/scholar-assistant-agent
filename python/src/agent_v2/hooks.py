"""Hooks system — lifecycle interceptors with abort signal, progress, JSON parsing.

Port of claw-code rust/crates/runtime/src/hooks.rs.

Advanced features over original:
  - HookAbortSignal: async cancellation of running hooks
  - HookProgressReporter: progress events during hook execution
  - HookRunResult.updated_input: hook can modify tool parameters
  - HookRunResult.permission_override/reason: hook provides permission context
  - Shell hook JSON stdout parsing (decision, reason, updatedInput, permissionDecision)
  - Shell hook exit code conventions: 0=allow, 2=deny, 3=ask
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class HookDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class HookPoint(Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    INIT = "Init"
    SHUTDOWN = "Shutdown"


@dataclass
class HookEvent:
    hook: HookPoint
    tool_name: str = ""
    tool_input: str = ""
    tool_result: str = ""
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook.value,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_result": self.tool_result,
            "is_error": self.is_error,
            **self.metadata,
        }


@dataclass
class HookResult:
    decision: HookDecision = HookDecision.ALLOW
    reason: str = ""
    updated_input: str | None = None
    permission_override: str | None = None
    permission_reason: str | None = None
    messages: list[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.decision == HookDecision.ALLOW

    @property
    def is_denied(self) -> bool:
        return self.decision == HookDecision.DENY


# ---------------------------------------------------------------------------
# HookAbortSignal
# ---------------------------------------------------------------------------

class HookAbortSignal:
    """Thread-safe abort signal for cancelling hook execution.

    Reference: claw-code HookAbortSignal (Arc<AtomicBool>).
    """

    def __init__(self) -> None:
        self._aborted = threading.Event()

    def abort(self) -> None:
        self._aborted.set()

    def is_aborted(self) -> bool:
        return self._aborted.is_set()


# ---------------------------------------------------------------------------
# HookRunResult — enriched result with updated_input + permission_override
# ---------------------------------------------------------------------------

@dataclass
class HookRunResult:
    decision: HookDecision = HookDecision.ALLOW
    reason: str = ""
    updated_input: str | None = None
    permission_override: str | None = None
    permission_reason: str | None = None
    cancelled: bool = False
    messages: list[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.decision == HookDecision.ALLOW

    @property
    def is_denied(self) -> bool:
        return self.decision == HookDecision.DENY


# ---------------------------------------------------------------------------
# HookDefinition
# ---------------------------------------------------------------------------

class HookDefinition:
    def __init__(self, name: str, hook_point: HookPoint, command: str, priority: int = 50):
        self.name = name
        self.hook_point = hook_point
        self.command = command
        self.priority = priority

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hook_point": self.hook_point.value,
            "command": self.command,
            "priority": self.priority,
        }


# ---------------------------------------------------------------------------
# Progress reporter protocol
# ---------------------------------------------------------------------------

class HookProgressReporter(Protocol):
    def on_event(self, event: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# HookRunner
# ---------------------------------------------------------------------------

class HookRunner:
    """Hook executor with abort signal, progress reporting, and JSON parsing.

    Reference: claw-code HookRunner.
    """

    def __init__(self):
        self._hooks: list[HookDefinition] = []
        self._callables: dict[str, Any] = {}

    def register(self, hook: HookDefinition) -> None:
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: h.priority)

    def register_callable(self, name: str, hook_point: HookPoint,
                          func, priority: int = 50) -> None:
        self._callables[f"{hook_point.value}:{name}"] = func
        self.register(HookDefinition(name=name, hook_point=hook_point,
                                      command=f"callable:{name}", priority=priority))

    def add_builtin_hooks(self) -> None:
        def _log_tool_call(event: HookEvent) -> HookResult:
            logger.info("tool_call: %s input_len=%d", event.tool_name, len(event.tool_input))
            return HookResult(decision=HookDecision.ALLOW)

        def _log_tool_failure(event: HookEvent) -> HookResult:
            logger.warning("tool_failure: %s error=%s", event.tool_name, event.tool_result[:200])
            return HookResult(decision=HookDecision.ALLOW)

        self.register_callable("builtin:log_tool", HookPoint.POST_TOOL_USE,
                               _log_tool_call, priority=100)
        self.register_callable("builtin:log_failure", HookPoint.POST_TOOL_USE_FAILURE,
                               _log_tool_failure, priority=100)

    def create_abort_signal(self) -> HookAbortSignal:
        return HookAbortSignal()

    async def run(
        self,
        hook_point: HookPoint,
        event: HookEvent,
        *,
        abort_signal: HookAbortSignal | None = None,
        reporter: HookProgressReporter | None = None,
    ) -> HookRunResult:
        """Execute all hooks matching hook_point.

        Short-circuit logic:
        - PreToolUse: first DENY or ASK returns immediately
        - Other hook types: all hooks execute, return ALLOW
        """
        # Check abort before starting
        if abort_signal and abort_signal.is_aborted():
            if reporter:
                reporter.on_event({"type": "cancelled", "hook": hook_point.value,
                                    "tool_name": event.tool_name})
            return HookRunResult(cancelled=True, messages=["hook cancelled before execution"])

        event.hook = hook_point
        final = HookRunResult(decision=HookDecision.ALLOW)

        for hook in self._hooks:
            if hook.hook_point != hook_point:
                continue

            # Check abort between hooks
            if abort_signal and abort_signal.is_aborted():
                if reporter:
                    reporter.on_event({"type": "cancelled", "hook": hook_point.value,
                                        "tool_name": event.tool_name, "command": hook.command})
                final.cancelled = True
                final.messages.append(f"{hook_point.value} hook cancelled")
                return final

            if reporter:
                reporter.on_event({"type": "started", "hook": hook_point.value,
                                    "tool_name": event.tool_name, "command": hook.command})

            result = await self._execute_hook(hook, event)

            if reporter:
                evt_type = "completed" if not (abort_signal and abort_signal.is_aborted()) else "cancelled"
                reporter.on_event({"type": evt_type, "hook": hook_point.value,
                                    "tool_name": event.tool_name, "command": hook.command})

            # Merge result fields
            final.messages.extend(result.messages)
            if result.updated_input is not None:
                final.updated_input = result.updated_input
            if result.permission_override is not None:
                final.permission_override = result.permission_override
            if result.permission_reason is not None:
                final.permission_reason = result.permission_reason

            if hook_point == HookPoint.PRE_TOOL_USE:
                if result.decision == HookDecision.DENY:
                    final.decision = HookDecision.DENY
                    final.reason = result.reason
                    return final
                if result.decision == HookDecision.ASK:
                    final.decision = HookDecision.ASK
                    final.reason = result.reason
                    return final

        return final

    async def _execute_hook(self, hook: HookDefinition, event: HookEvent) -> HookResult:
        # Check for callable
        key = f"{hook.hook_point.value}:{hook.name}"
        func = self._callables.get(key)
        if func is not None:
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(event)
                else:
                    result = func(event)
                if isinstance(result, HookResult):
                    return result
                return HookResult(decision=HookDecision.ALLOW)
            except Exception as e:
                logger.warning("hook '%s' failed: %s", hook.name, e)
                return HookResult(decision=HookDecision.ALLOW)

        # Shell command hook
        if hook.command and not hook.command.startswith("callable:"):
            try:
                proc = await _create_subprocess(hook.command)
                input_json = json.dumps(event.to_dict(), ensure_ascii=False)
                stdout, _ = await asyncio.wait_for(proc.communicate(input_json.encode()), timeout=10.0)
                stdout_text = stdout.decode("utf-8", errors="replace").strip()

                return _parse_shell_hook_output(proc.returncode, stdout_text)
            except Exception as e:
                logger.warning("shell hook '%s' failed: %s", hook.name, e)

        return HookResult(decision=HookDecision.ALLOW)


# ---------------------------------------------------------------------------
# Shell hook JSON output parsing (claw-code convention)
# ---------------------------------------------------------------------------

def _parse_shell_hook_output(return_code: int | None, stdout: str) -> HookResult:
    """Parse shell hook stdout following claw-code conventions.

    Exit codes: 0=allow (check JSON), 2=deny, 3=ask, other=fail.
    JSON fields: decision, reason, systemMessage, continue,
                 hookSpecificOutput.{updatedInput, permissionDecision, permissionDecisionReason}
    """
    messages: list[str] = []
    updated_input: str | None = None
    permission_override: str | None = None
    permission_reason: str | None = None
    deny = False

    # Try JSON parsing
    if stdout:
        try:
            root = json.loads(stdout)
            if isinstance(root, dict):
                # Extract messages
                for key in ("systemMessage", "reason"):
                    if key in root and isinstance(root[key], str):
                        messages.append(root[key])

                # Decision
                if root.get("continue") is False or root.get("decision") == "block":
                    deny = True

                # Hook-specific output
                specific = root.get("hookSpecificOutput")
                if isinstance(specific, dict):
                    if "additionalContext" in specific:
                        messages.append(str(specific["additionalContext"]))
                    pd = specific.get("permissionDecision")
                    if isinstance(pd, str) and pd in ("allow", "deny", "ask"):
                        permission_override = pd
                    pr = specific.get("permissionDecisionReason")
                    if isinstance(pr, str):
                        permission_reason = pr
                    ui = specific.get("updatedInput")
                    if ui is not None:
                        updated_input = json.dumps(ui) if not isinstance(ui, str) else ui

                if not messages:
                    messages.append(stdout)
        except (json.JSONDecodeError, TypeError):
            # Non-JSON stdout → plain message
            if stdout:
                messages.append(stdout)

    # Exit code takes precedence for deny/ask
    if return_code == 2:
        return HookResult(decision=HookDecision.DENY, reason=messages[0] if messages else "hook denied",
                          messages=messages)
    if return_code == 3:
        return HookResult(decision=HookDecision.ASK, reason=messages[0] if messages else "hook asks for approval",
                          messages=messages)
    if deny:
        return HookResult(decision=HookDecision.DENY, reason=messages[0] if messages else "hook denied",
                          updated_input=updated_input, permission_override=permission_override,
                          permission_reason=permission_reason, messages=messages)

    return HookResult(decision=HookDecision.ALLOW, updated_input=updated_input,
                      permission_override=permission_override, permission_reason=permission_reason,
                      messages=messages)


async def _create_subprocess(command: str):
    import asyncio
    return await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
