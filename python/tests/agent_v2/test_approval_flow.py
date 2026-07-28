"""审批流测试 — 暂停/恢复/拒绝/超时/并发审批。"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path

import pytest

from src.agent_v2.hooks import HookDecision, HookPoint, HookResult, HookRunner
from src.agent_v2.providers.mock_provider import (
    MockProvider,
    Scenario,
    _text_response,
    _tool_response,
)
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import ToolRegistry, ToolResult, create_default_registry
from src.agent_v2.types import AgentEventType


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "test.md").write_text("original content\n", encoding="utf-8")
    return tmp_path


async def _collect(runtime, msg, timeout=30):
    """收集事件，支持审批"""
    events = []

    async def _run():
        async for e in runtime.turn(msg):
            events.append(e)

    with suppress(TimeoutError):
        await asyncio.wait_for(_run(), timeout=timeout)
    return events


class TestApprovalAutoApprove:
    """auto_approve=True 时直接执行，不等待"""

    @pytest.mark.asyncio
    async def test_write_executes_immediately(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {
                            "file_path": "new.txt",
                            "content": "data",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=True,
        )
        events = await _collect(rt, "write new file", timeout=5)
        types = [e.type for e in events]
        # No approval event since auto_approve=True
        assert AgentEventType.AWAIT_APPROVAL not in types
        assert AgentEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_str_replace_executes_immediately(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "r",
                    trigger_patterns=["replace"],
                    response_factory=lambda m, t: _tool_response(
                        "str_replace",
                        {
                            "file_path": "test.md",
                            "old_string": "original",
                            "new_string": "modified",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=True,
        )
        events = await _collect(rt, "replace text", timeout=5)
        types = [e.type for e in events]
        assert AgentEventType.AWAIT_APPROVAL not in types
        assert AgentEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_selection_scope_rejects_a_stale_paragraph_before_edit(self, workspace: Path):
        target = workspace / "test.md"
        target.write_text(
            "older selected paragraph\ncurrent selected paragraph\n",
            encoding="utf-8",
        )
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=True,
            edit_scope={
                "file_path": "test.md",
                "start_line": 2,
                "start_column": 1,
                "end_line": 2,
                "end_column": 27,
                "text": "current selected paragraph",
            },
        )
        stale_call = _tool_response(
            "str_replace",
            {
                "file_path": "test.md",
                "old_string": "older selected paragraph",
                "new_string": "incorrect replacement",
            },
        ).blocks[0]

        events = [event async for event in rt._execute_tool(stale_call)]

        assert target.read_text(encoding="utf-8") == (
            "older selected paragraph\ncurrent selected paragraph\n"
        )
        result_events = [event for event in events if event.type == AgentEventType.TOOL_RESULT]
        assert len(result_events) == 1
        assert "current active selection" in result_events[0].data["output"]
        assert result_events[0].data["is_error"] is True

    def test_selection_scope_accepts_equivalent_line_endings_and_preserves_boundary(
        self, workspace: Path
    ):
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        rt = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            edit_scope={
                "file_path": "test.md",
                "start_line": 1,
                "start_column": 1,
                "end_line": 3,
                "end_column": 1,
                "text": "first\r\nsecond\r\n",
            },
        )
        args = {
            "file_path": "test.md",
            "old_string": "first\nsecond",
            "new_string": "polished\nparagraph",
        }
        tool_call = _tool_response("str_replace", args).blocks[0]

        error = rt._apply_edit_scope(tool_call, args)

        assert error is None
        assert args["old_string"] == "first\r\nsecond\r\n"
        assert args["new_string"] == "polished\r\nparagraph\r\n"


class TestApprovalPause:
    """auto_approve=False 时暂停等审批"""

    @pytest.mark.asyncio
    async def test_write_triggers_approval(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {
                            "file_path": "new.txt",
                            "content": "data",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        # Start collecting events in background
        events = []

        async def _bg_collect():
            async for e in rt.turn("write new file"):
                events.append(e)

        task = asyncio.create_task(_bg_collect())
        # Wait for approval event
        await asyncio.sleep(0.3)
        # Approve it
        found = False
        for e in events:
            if e.type == AgentEventType.AWAIT_APPROVAL:
                ok = rt.approve(e.data.get("id", ""), "allow_once")
                assert ok
                found = True
                break
        assert found, "Expected AWAIT_APPROVAL event"
        # Wait for completion
        with suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in events]
        assert AgentEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_arbitrary_process_tool_requires_approval(self, workspace: Path):
        """SEC-02: approval is derived from effects, not a hard-coded tool name."""
        registry = ToolRegistry(workspace_root=workspace)
        executed = False

        async def custom_process(_args):
            nonlocal executed
            executed = True
            return ToolResult("ok")

        registry.register(
            "custom_process",
            "custom plugin-like process",
            {"type": "object", "properties": {}},
            custom_process,
            permission="workspace-write",
            effects={"process"},
        )
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=False,
        )
        call = _tool_response("custom_process", {}).blocks[0]
        events = []

        async def collect():
            async for event in runtime._execute_tool(call):
                events.append(event)

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.05)
        approval = next(event for event in events if event.type == AgentEventType.AWAIT_APPROVAL)
        assert executed is False
        assert runtime.approve(approval.data["id"], "deny")
        await task
        assert executed is False

    @pytest.mark.asyncio
    async def test_allow_session_is_scoped_to_exact_tool_arguments(self, workspace: Path):
        """SEC-01: approving one command must not approve a different command."""
        registry = ToolRegistry(workspace_root=workspace)

        async def custom_process(args):
            return ToolResult(str(args["command"]))

        registry.register(
            "custom_process",
            "custom plugin-like process",
            {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            custom_process,
            permission="workspace-write",
            effects={"process"},
        )
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=False,
        )

        async def execute_and_decide(command: str, decision: str):
            call = _tool_response("custom_process", {"command": command}).blocks[0]
            events = []

            async def collect():
                async for event in runtime._execute_tool(call):
                    events.append(event)

            task = asyncio.create_task(collect())
            await asyncio.sleep(0.05)
            approval = next(
                event for event in events if event.type == AgentEventType.AWAIT_APPROVAL
            )
            assert runtime.approve(approval.data["id"], decision)
            await task
            return events

        await execute_and_decide("first", "allow_session")
        second_events = await execute_and_decide("second", "allow_once")
        assert any(event.type == AgentEventType.AWAIT_APPROVAL for event in second_events)

    @pytest.mark.asyncio
    async def test_pre_tool_hook_deny_blocks_execution(self, workspace: Path):
        """SEC-02: production Runtime must enforce PreToolUse DENY."""
        registry = ToolRegistry(workspace_root=workspace)
        executed = False

        async def custom_tool(_args):
            nonlocal executed
            executed = True
            return ToolResult("ok")

        registry.register(
            "custom_tool",
            "custom tool",
            {"type": "object", "properties": {}},
            custom_tool,
            effects={"process"},
        )
        hooks = HookRunner()
        hooks.register_callable(
            "deny-custom",
            HookPoint.PRE_TOOL_USE,
            lambda _event: HookResult(decision=HookDecision.DENY, reason="blocked by test"),
        )
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=True,
            hook_runner=hooks,
        )
        call = _tool_response("custom_tool", {}).blocks[0]
        events = [event async for event in runtime._execute_tool(call)]
        assert executed is False
        denied = next(event for event in events if event.type == AgentEventType.TOOL_DENIED)
        assert "blocked by test" in denied.data["reason"]

    @pytest.mark.asyncio
    async def test_no_change_does_not_emit_checkpoint(self, workspace: Path):
        """RUN-02: a no-op remains a tool attempt but is not a mutation."""
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=True,
        )
        call = _tool_response(
            "str_replace",
            {
                "file_path": "test.md",
                "old_string": "original content",
                "new_string": "original content",
            },
        ).blocks[0]
        events = [event async for event in runtime._execute_tool(call)]
        result = next(event for event in events if event.type == AgentEventType.TOOL_RESULT)
        assert result.data["status"] == "no_change"
        assert all(event.type != AgentEventType.CHECKPOINT for event in events)

    @pytest.mark.asyncio
    async def test_long_tool_result_keeps_truncation_marker_and_metadata(self, workspace: Path):
        """IO-01: Runtime and Session must not silently remove truncation evidence."""
        (workspace / "long.txt").write_text("x" * 12000, encoding="utf-8")
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        runtime = ConversationRuntime(
            provider=MockProvider(),
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=True,
        )
        call = _tool_response("read_file", {"file_path": "long.txt"}).blocks[0]
        events = [event async for event in runtime._execute_tool(call)]
        result = next(event for event in events if event.type == AgentEventType.TOOL_RESULT)
        assert result.data["truncated"] is True
        assert result.data["original_chars"] == 12000
        assert "[truncated;" in result.data["output"]
        assert "continue with offset=3500" in result.data["output"]
        persisted = session.messages[-1].blocks[0]
        assert "[truncated;" in persisted.output
        assert persisted.truncated is True

    @pytest.mark.asyncio
    async def test_approval_is_registered_before_event_is_emitted(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file", {"file_path": "new.txt", "content": "data"}
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=Session(workspace=str(workspace)),
            auto_approve=False,
        )

        stream = rt.turn("write new file")
        try:
            approved = False
            async for event in stream:
                if event.type == AgentEventType.AWAIT_APPROVAL:
                    assert rt.approve(event.data["id"], "allow_once") is True
                    approved = True
                if approved and event.type == AgentEventType.TOOL_RESULT:
                    break
        finally:
            await stream.aclose()

        assert (workspace / "new.txt").read_text(encoding="utf-8") == "data"

    @pytest.mark.asyncio
    async def test_deny_blocks_execution(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {
                            "file_path": "new.txt",
                            "content": "data",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        events = []

        async def _bg_collect():
            async for e in rt.turn("write new file"):
                events.append(e)

        task = asyncio.create_task(_bg_collect())
        await asyncio.sleep(0.3)
        # Deny it
        for e in events:
            if e.type == AgentEventType.AWAIT_APPROVAL:
                rt.approve(e.data.get("id", ""), "deny")
                break
        with suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in events]
        # Denial produces TOOL_ERROR with the deny message
        denied = [
            e
            for e in events
            if e.type in (AgentEventType.TOOL_RESULT, AgentEventType.TOOL_ERROR)
            and "denied" in str(e.data).lower()
        ]
        assert len(denied) >= 1 or AgentEventType.APPROVAL_RECEIVED in types, (
            f"Expected denial evidence, got types: {types}"
        )
        assert types.count(AgentEventType.AWAIT_APPROVAL) == 1
        assert AgentEventType.ABORTED in types
        assert AgentEventType.DONE in types
        assert not (workspace / "new.txt").exists()

    @pytest.mark.asyncio
    async def test_allow_session_skips_later_approval_for_same_tool(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "first",
                    trigger_patterns=["edit twice"],
                    turn_index=0,
                    response_factory=lambda m, t: _tool_response(
                        "str_replace",
                        {
                            "file_path": "test.md",
                            "old_string": "original",
                            "new_string": "first",
                        },
                    ),
                ),
                Scenario(
                    "second",
                    trigger_patterns=["edit twice"],
                    turn_index=1,
                    response_factory=lambda m, t: _tool_response(
                        "str_replace",
                        {
                            "file_path": "test.md",
                            "old_string": "first",
                            "new_string": "second",
                        },
                    ),
                ),
                Scenario(
                    "done",
                    trigger_patterns=["edit twice"],
                    turn_index=2,
                    response_factory=lambda m, t: _text_response("Both edits completed."),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        events = []

        async def _bg_collect():
            async for event in rt.turn("edit twice"):
                events.append(event)

        task = asyncio.create_task(_bg_collect())
        for _ in range(30):
            approval = next(
                (event for event in events if event.type == AgentEventType.AWAIT_APPROVAL), None
            )
            if approval:
                assert rt.approve(approval.data.get("id", ""), "allow_session")
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("Expected first edit approval")

        await asyncio.wait_for(task, timeout=5)
        types = [event.type for event in events]
        assert types.count(AgentEventType.AWAIT_APPROVAL) == 1
        assert types.count(AgentEventType.CHECKPOINT) == 2
        assert (workspace / "test.md").read_text(encoding="utf-8") == "second content\n"

    @pytest.mark.asyncio
    async def test_approval_timeout_expires_without_impersonating_user_denial(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("src.agent_v2.runtime.conversation._APPROVAL_TIMEOUT", 0.05)
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {
                            "file_path": "timed-out.txt",
                            "content": "must not be written",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        events = await _collect(rt, "write after approval", timeout=2)
        types = [event.type for event in events]
        decisions = [
            event.data.get("decision")
            for event in events
            if event.type == AgentEventType.APPROVAL_RECEIVED
        ]
        assert types.count(AgentEventType.AWAIT_APPROVAL) == 1
        assert decisions == ["timeout"]
        assert AgentEventType.ABORTED in types
        assert AgentEventType.DONE in types
        serialized_events = " ".join(str(event.data) for event in events).lower()
        assert "approval timed out" in serialized_events
        assert "user denied" not in serialized_events
        assert not (workspace / "timed-out.txt").exists()


class TestApprovalRecovery:
    @pytest.mark.asyncio
    async def test_approve_nonexistent_event(self, workspace: Path):
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider, tool_registry=registry, permission_policy=policy, session=session
        )
        assert not rt.approve("nonexistent_id", "allow_once")

    @pytest.mark.asyncio
    async def test_abort_unblocks_approval(self, workspace: Path):
        provider = MockProvider(
            scenarios=[
                Scenario(
                    "w",
                    trigger_patterns=["write"],
                    response_factory=lambda m, t: _tool_response(
                        "write_file",
                        {
                            "file_path": "new.txt",
                            "content": "data",
                        },
                    ),
                ),
            ]
        )
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(
            provider=provider,
            tool_registry=registry,
            permission_policy=policy,
            session=session,
            auto_approve=False,
        )

        events = []

        async def _bg_collect():
            async for e in rt.turn("write new file"):
                events.append(e)

        task = asyncio.create_task(_bg_collect())
        await asyncio.sleep(0.3)
        rt.abort()
        with suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=5)
        types = [e.type for e in events]
        # Should have aborted or completed without hanging
        assert AgentEventType.ABORTED in types or AgentEventType.DONE in types
        serialized_events = " ".join(str(event.data) for event in events).lower()
        assert "user denied" not in serialized_events
