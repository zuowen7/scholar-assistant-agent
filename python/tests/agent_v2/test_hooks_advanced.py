"""TDD tests for Hooks Advanced Features.

Reference: claw-code rust/crates/runtime/src/hooks.rs

New features under test:
  1. HookAbortSignal — async cancellation of running hooks
  2. HookProgressReporter — progress events during hook execution
  3. HookRunResult.updated_input — hook modifies tool input
  4. Shell hook JSON stdout parsing (decision, reason, updatedInput, permissionDecision)
  5. HookRunResult.permission_override — hook provides permission context
  6. Pre-tool-use deny short-circuits pipeline
  7. Hook payload structure matches claw-code format
"""
from __future__ import annotations

import asyncio
import json

import pytest

from src.agent_v2.hooks import (
    HookAbortSignal,
    HookDecision,
    HookDefinition,
    HookEvent,
    HookPoint,
    HookResult,
    HookRunResult,
    HookRunner,
)


# ============================================================================
# 1. HookAbortSignal
# ============================================================================

class TestHookAbortSignal:

    def test_initial_state_not_aborted(self):
        from src.agent_v2.hooks import HookAbortSignal
        signal = HookAbortSignal()
        assert not signal.is_aborted()

    def test_abort_sets_flag(self):
        from src.agent_v2.hooks import HookAbortSignal
        signal = HookAbortSignal()
        signal.abort()
        assert signal.is_aborted()

    def test_abort_is_idempotent(self):
        from src.agent_v2.hooks import HookAbortSignal
        signal = HookAbortSignal()
        signal.abort()
        signal.abort()
        assert signal.is_aborted()

    def test_multiple_signals_independent(self):
        from src.agent_v2.hooks import HookAbortSignal
        s1 = HookAbortSignal()
        s2 = HookAbortSignal()
        s1.abort()
        assert s1.is_aborted()
        assert not s2.is_aborted()

    @pytest.mark.asyncio
    async def test_abort_cancels_hook_run(self):
        runner = HookRunner()
        signal = runner.create_abort_signal()

        async def slow_hook(event: HookEvent) -> HookResult:
            await asyncio.sleep(10)  # would hang if not cancelled
            return HookResult(decision=HookDecision.ALLOW)

        runner.register_callable("slow", HookPoint.PRE_TOOL_USE, slow_hook, priority=10)

        # Abort before running
        signal.abort()
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event, abort_signal=signal)
        assert result.decision == HookDecision.ALLOW
        assert result.cancelled

    @pytest.mark.asyncio
    async def test_abort_signal_during_hook_run(self):
        runner = HookRunner()
        signal = runner.create_abort_signal()

        async def cancellable_hook(event: HookEvent) -> HookResult:
            await asyncio.sleep(0.05)
            return HookResult(decision=HookDecision.ALLOW)

        runner.register_callable("cancellable", HookPoint.PRE_TOOL_USE, cancellable_hook, priority=10)

        async def run_and_abort():
            await asyncio.sleep(0.01)
            signal.abort()

        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        run_task = asyncio.create_task(
            runner.run(HookPoint.PRE_TOOL_USE, event, abort_signal=signal)
        )
        abort_task = asyncio.create_task(run_and_abort())
        result = await run_task
        # Hook may or may not complete depending on timing,
        # but the system should not hang


# ============================================================================
# 2. HookProgressReporter
# ============================================================================

class TestHookProgressReporter:

    @pytest.mark.asyncio
    async def test_reports_started_and_completed(self):
        events_log = []

        class MyReporter:
            def on_event(self, event):
                events_log.append(event)

        runner = HookRunner()
        runner.register_callable("h1", HookPoint.PRE_TOOL_USE,
                                  lambda e: HookResult(decision=HookDecision.ALLOW),
                                  priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        reporter = MyReporter()
        result = await runner.run(HookPoint.PRE_TOOL_USE, event, reporter=reporter)
        assert len(events_log) >= 2
        assert events_log[0]["type"] == "started"
        assert events_log[-1]["type"] == "completed"

    @pytest.mark.asyncio
    async def test_reports_cancelled_on_abort(self):
        events_log = []

        class MyReporter:
            def on_event(self, event):
                events_log.append(event)

        runner = HookRunner()
        signal = runner.create_abort_signal()
        signal.abort()
        runner.register_callable("h1", HookPoint.PRE_TOOL_USE,
                                  lambda e: HookResult(decision=HookDecision.ALLOW),
                                  priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event,
                                   abort_signal=signal, reporter=MyReporter())
        # Cancelled event should be reported
        cancel_events = [e for e in events_log if e.get("type") == "cancelled"]
        assert len(cancel_events) >= 1


# ============================================================================
# 3. HookRunResult — updated_input, permission_override
# ============================================================================

class TestHookRunResult:

    def test_basic_result(self):
        result = HookRunResult(decision=HookDecision.ALLOW)
        assert result.is_allowed
        assert not result.is_denied
        assert not result.cancelled

    def test_result_with_updated_input(self):
        result = HookRunResult(
            decision=HookDecision.ALLOW,
            updated_input='{"file_path": "renamed.md"}',
        )
        assert result.updated_input == '{"file_path": "renamed.md"}'

    def test_result_with_permission_override(self):
        result = HookRunResult(
            decision=HookDecision.ALLOW,
            permission_override="deny",
            permission_reason="sensitive file",
        )
        assert result.permission_override == "deny"
        assert result.permission_reason == "sensitive file"

    def test_result_cancelled(self):
        result = HookRunResult(decision=HookDecision.ALLOW, cancelled=True)
        assert result.cancelled


# ============================================================================
# 4. Callable hook returns updated_input
# ============================================================================

class TestHookUpdatedInput:

    @pytest.mark.asyncio
    async def test_hook_can_modify_tool_input(self):
        runner = HookRunner()

        def rewrite_path(event: HookEvent) -> HookResult:
            if event.tool_name == "write_file":
                data = json.loads(event.tool_input) if event.tool_input else {}
                data["file_path"] = data.get("file_path", "").replace("../", "")
                return HookResult(
                    decision=HookDecision.ALLOW,
                    updated_input=json.dumps(data),
                )
            return HookResult(decision=HookDecision.ALLOW)

        runner.register_callable("rewrite", HookPoint.PRE_TOOL_USE, rewrite_path, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file",
                          tool_input='{"file_path": "../../../etc/passwd"}')
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.updated_input is not None
        modified = json.loads(result.updated_input)
        assert "../" not in modified["file_path"]

    @pytest.mark.asyncio
    async def test_deny_hook_does_not_modify_input(self):
        runner = HookRunner()

        def block(event: HookEvent) -> HookResult:
            return HookResult(decision=HookDecision.DENY, reason="blocked")

        runner.register_callable("block", HookPoint.PRE_TOOL_USE, block, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.is_denied
        assert result.updated_input is None


# ============================================================================
# 5. Callable hook returns permission_override
# ============================================================================

class TestHookPermissionOverride:

    @pytest.mark.asyncio
    async def test_hook_can_override_to_ask(self):
        runner = HookRunner()

        def ask_hook(event: HookEvent) -> HookResult:
            return HookResult(
                decision=HookDecision.ALLOW,
                permission_override="ask",
                permission_reason="requires user confirmation",
            )

        runner.register_callable("ask", HookPoint.PRE_TOOL_USE, ask_hook, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="run_command")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.permission_override == "ask"
        assert result.permission_reason == "requires user confirmation"

    @pytest.mark.asyncio
    async def test_hook_can_override_to_deny(self):
        runner = HookRunner()

        def deny_hook(event: HookEvent) -> HookResult:
            return HookResult(
                decision=HookDecision.DENY,
                permission_override="deny",
                permission_reason="forbidden by policy",
            )

        runner.register_callable("deny", HookPoint.PRE_TOOL_USE, deny_hook, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="bash")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.is_denied


# ============================================================================
# 6. Shell hook JSON stdout parsing
# ============================================================================

class TestShellHookJsonParsing:
    """Test that shell hooks can return JSON to control behavior."""

    @pytest.mark.asyncio
    async def test_shell_hook_json_deny(self):
        """Shell hook returns exit code 2 or JSON with decision=block → deny."""
        runner = HookRunner()
        script = f'echo {json.dumps({"decision": "block", "reason": "forbidden"})}'
        runner.register(HookDefinition(name="block", hook_point=HookPoint.PRE_TOOL_USE,
                                        command=script, priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        # Shell hook executed, parsed JSON
        assert result.decision == HookDecision.DENY or result.is_denied

    @pytest.mark.asyncio
    async def test_shell_hook_json_updated_input(self):
        runner = HookRunner()
        output = json.dumps({
            "hookSpecificOutput": {
                "updatedInput": {"file_path": "safe.md"},
            }
        })
        script = f'echo {json.dumps(output)}'
        runner.register(HookDefinition(name="rewrite", hook_point=HookPoint.PRE_TOOL_USE,
                                        command=f'echo {output}', priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file",
                          tool_input='{"file_path": "../evil.md"}')
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.updated_input is not None

    @pytest.mark.asyncio
    async def test_shell_hook_exit_code_2_denies(self):
        """Exit code 2 means deny (claw-code convention)."""
        runner = HookRunner()
        runner.register(HookDefinition(name="deny2", hook_point=HookPoint.PRE_TOOL_USE,
                                        command="exit 2", priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.DENY

    @pytest.mark.asyncio
    async def test_shell_hook_exit_code_3_ask(self):
        """Exit code 3 means ask (claw-code convention)."""
        runner = HookRunner()
        runner.register(HookDefinition(name="ask3", hook_point=HookPoint.PRE_TOOL_USE,
                                        command="exit 3", priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ASK

    @pytest.mark.asyncio
    async def test_shell_hook_json_permission_decision(self):
        runner = HookRunner()
        output = json.dumps({
            "hookSpecificOutput": {
                "permissionDecision": "ask",
                "permissionDecisionReason": "confirm before deletion",
            }
        })
        runner.register(HookDefinition(name="perm", hook_point=HookPoint.PRE_TOOL_USE,
                                        command=f'echo {output}', priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="run_command")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.permission_override == "ask"

    @pytest.mark.asyncio
    async def test_shell_hook_exit_code_0_with_json_block(self):
        """Exit code 0 + JSON with continue:false → deny."""
        runner = HookRunner()
        output = json.dumps({"continue": False, "reason": "policy violation"})
        runner.register(HookDefinition(name="block_json", hook_point=HookPoint.PRE_TOOL_USE,
                                        command=f'echo {output}', priority=10))
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.DENY

    @pytest.mark.asyncio
    async def test_shell_hook_non_json_stdout_just_message(self):
        """Non-JSON stdout is treated as a plain message."""
        runner = HookRunner()
        runner.register(HookDefinition(name="msg", hook_point=HookPoint.POST_TOOL_USE,
                                        command="echo 'operation logged'", priority=10))
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.POST_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW
        assert len(result.messages) > 0


# ============================================================================
# 7. Hook payload structure
# ============================================================================

class TestHookPayload:

    @pytest.mark.asyncio
    async def test_payload_contains_expected_fields(self):
        """Callable hook receives event with correct fields."""
        received = {}

        def capture(event: HookEvent) -> HookResult:
            received["tool_name"] = event.tool_name
            received["tool_input"] = event.tool_input
            received["tool_result"] = event.tool_result
            received["is_error"] = event.is_error
            received["hook"] = event.hook
            return HookResult(decision=HookDecision.ALLOW)

        runner = HookRunner()
        runner.register_callable("cap", HookPoint.POST_TOOL_USE, capture, priority=10)
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="read_file",
                          tool_input='{"file_path": "a.md"}', tool_result="content", is_error=False)
        await runner.run(HookPoint.POST_TOOL_USE, event)
        assert received["tool_name"] == "read_file"
        assert received["tool_input"] == '{"file_path": "a.md"}'
        assert received["tool_result"] == "content"
        assert received["is_error"] is False
