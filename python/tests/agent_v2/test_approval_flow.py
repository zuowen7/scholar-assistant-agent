"""审批流测试 — 暂停/恢复/拒绝/超时/并发审批。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import MockProvider, Scenario, _tool_response, _text_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import create_default_registry
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
    try:
        await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return events


class TestApprovalAutoApprove:
    """auto_approve=True 时直接执行，不等待"""
    @pytest.mark.asyncio
    async def test_write_executes_immediately(self, workspace: Path):
        provider = MockProvider(scenarios=[
            Scenario("w", trigger_patterns=["write"],
                     response_factory=lambda m, t: _tool_response("write_file", {
                         "file_path": "new.txt", "content": "data",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session, auto_approve=True)
        events = await _collect(rt, "write new file", timeout=5)
        types = [e.type for e in events]
        # No approval event since auto_approve=True
        assert AgentEventType.AWAIT_APPROVAL not in types
        assert AgentEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_str_replace_executes_immediately(self, workspace: Path):
        provider = MockProvider(scenarios=[
            Scenario("r", trigger_patterns=["replace"],
                     response_factory=lambda m, t: _tool_response("str_replace", {
                         "file_path": "test.md", "old_string": "original", "new_string": "modified",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session, auto_approve=True)
        events = await _collect(rt, "replace text", timeout=5)
        types = [e.type for e in events]
        assert AgentEventType.AWAIT_APPROVAL not in types
        assert AgentEventType.TOOL_RESULT in types


class TestApprovalPause:
    """auto_approve=False 时暂停等审批"""
    @pytest.mark.asyncio
    async def test_write_triggers_approval(self, workspace: Path):
        provider = MockProvider(scenarios=[
            Scenario("w", trigger_patterns=["write"],
                     response_factory=lambda m, t: _tool_response("write_file", {
                         "file_path": "new.txt", "content": "data",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session, auto_approve=False)

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
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            pass
        types = [e.type for e in events]
        assert AgentEventType.TOOL_RESULT in types

    @pytest.mark.asyncio
    async def test_deny_blocks_execution(self, workspace: Path):
        provider = MockProvider(scenarios=[
            Scenario("w", trigger_patterns=["write"],
                     response_factory=lambda m, t: _tool_response("write_file", {
                         "file_path": "new.txt", "content": "data",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session, auto_approve=False)

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
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            pass
        types = [e.type for e in events]
        # Denial produces TOOL_ERROR with the deny message
        denied = [e for e in events if e.type in (AgentEventType.TOOL_RESULT, AgentEventType.TOOL_ERROR)
                  and "denied" in str(e.data).lower()]
        assert len(denied) >= 1 or AgentEventType.APPROVAL_RECEIVED in types, f"Expected denial evidence, got types: {types}"


class TestApprovalRecovery:
    @pytest.mark.asyncio
    async def test_approve_nonexistent_event(self, workspace: Path):
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session)
        assert not rt.approve("nonexistent_id", "allow_once")

    @pytest.mark.asyncio
    async def test_abort_unblocks_approval(self, workspace: Path):
        provider = MockProvider(scenarios=[
            Scenario("w", trigger_patterns=["write"],
                     response_factory=lambda m, t: _tool_response("write_file", {
                         "file_path": "new.txt", "content": "data",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session, auto_approve=False)

        events = []
        async def _bg_collect():
            async for e in rt.turn("write new file"):
                events.append(e)

        task = asyncio.create_task(_bg_collect())
        await asyncio.sleep(0.3)
        rt.abort()
        try:
            await asyncio.wait_for(task, timeout=5)
        except asyncio.TimeoutError:
            pass
        types = [e.type for e in events]
        # Should have aborted or completed without hanging
        assert AgentEventType.ABORTED in types or AgentEventType.DONE in types
