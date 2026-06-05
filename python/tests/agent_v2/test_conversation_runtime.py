"""ConversationRuntime 测试 — CR-001 ~ CR-054。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import MockProvider, Scenario, _text_response, _tool_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, PermissionPolicy, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import ToolRegistry, ToolResult, create_default_registry
from src.agent_v2.types import (
    AgentEvent,
    AgentEventType,
    ApiError,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)


async def _collect_events(runtime: ConversationRuntime, msg: str) -> list[AgentEvent]:
    events = []
    async for event in runtime.turn(msg):
        events.append(event)
    return events


def _event_types(events: list[AgentEvent]) -> list[AgentEventType]:
    return [e.type for e in events]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "main.md").write_text("# Hello World", encoding="utf-8")
    return tmp_path


@pytest.fixture
def runtime(workspace: Path) -> ConversationRuntime:
    provider = MockProvider()
    registry = create_default_registry(workspace_root=workspace)
    policy = policy_from_registry(
        PermissionMode.WORKSPACE_WRITE,
        registry.permission_specs(),
    )
    session = Session(workspace=str(workspace), model="mock")
    return ConversationRuntime(provider=provider, tool_registry=registry,
                                permission_policy=policy, session=session)


# ============================================================================
# 6.1 基础对话流
# ============================================================================

class TestBasicFlow:

    @pytest.mark.asyncio
    async def test_cr001_single_text_reply(self, runtime: ConversationRuntime):
        """CR-001: user → LLM(text) → response"""
        events = await _collect_events(runtime, "hello")
        types = _event_types(events)
        assert AgentEventType.SESSION_STARTED in types
        assert AgentEventType.TOKEN in types
        assert AgentEventType.RESPONSE in types
        assert AgentEventType.DONE in types

    @pytest.mark.asyncio
    async def test_cr002_tool_call_then_reply(self, workspace: Path):
        """CR-002: user → tool_call → execute → tool_result → reply"""
        provider = MockProvider(scenarios=[
            Scenario("r0", trigger_patterns=["read it"], turn_index=0,
                     response_factory=lambda m, t: _tool_response("read_file", {"file_path": "main.md"})),
            Scenario("r1", trigger_patterns=["read it"], turn_index=1,
                     response_factory=lambda m, t: _text_response("The file contains 'Hello World'.")),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "read it")
        types = _event_types(events)
        assert AgentEventType.TOOL_CALL in types
        assert AgentEventType.TOOL_RESULT in types
        assert AgentEventType.RESPONSE in types
        # Verify tool result contains file content
        tool_results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        assert any("Hello" in e.data.get("output", "") for e in tool_results)

    @pytest.mark.asyncio
    async def test_cr004_event_sequence(self, runtime: ConversationRuntime):
        """CR-004: 事件序列正确"""
        events = await _collect_events(runtime, "hello")
        types = _event_types(events)
        # SESSION_STARTED first, DONE last
        assert types[0] == AgentEventType.SESSION_STARTED
        assert types[-1] == AgentEventType.DONE
        # RESPONSE before DONE
        if AgentEventType.RESPONSE in types:
            assert types.index(AgentEventType.RESPONSE) < types.index(AgentEventType.DONE)

    @pytest.mark.asyncio
    async def test_cr005_empty_tool_calls(self, workspace: Path):
        """CR-005: LLM 返回无 tool_call（纯文本），直接结束"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "explain this concept")
        types = _event_types(events)
        assert AgentEventType.RESPONSE in types


# ============================================================================
# 6.2 权限集成
# ============================================================================

class TestPermissionIntegration:

    @pytest.mark.asyncio
    async def test_cr010_tool_denied(self, workspace: Path):
        """CR-010: 工具被 Deny"""
        provider = MockProvider(scenarios=[
            Scenario("write", trigger_patterns=["write"],
                     response_factory=lambda m, t: _tool_response("write_file", {"file_path": "out.txt", "content": "x"})),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.READ_ONLY, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "write something")
        types = _event_types(events)
        assert AgentEventType.TOOL_DENIED in types

    @pytest.mark.asyncio
    async def test_cr013_partial_deny(self, workspace: Path):
        """CR-013: 多工具部分拒绝"""
        provider = MockProvider(scenarios=[
            Scenario("multi", trigger_patterns=["multi"],
                     response_factory=lambda m, t: ProviderResponse(
                         blocks=[
                             ToolUseBlock(id="tu_1", name="read_file", input=json.dumps({"file_path": "main.md"})),
                             ToolUseBlock(id="tu_2", name="write_file", input=json.dumps({"file_path": "out.txt", "content": "x"})),
                         ],
                         stop_reason="tool_use",
                     )),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.READ_ONLY, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "multi operation")
        denied = [e for e in events if e.type == AgentEventType.TOOL_DENIED]
        results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        # read_file allowed, write_file denied
        assert len(results) >= 1  # read_file succeeded
        assert len(denied) >= 1  # write_file denied


# ============================================================================
# 6.3 会话管理
# ============================================================================

class TestSessionIntegration:

    @pytest.mark.asyncio
    async def test_cr020_session_auto_save(self, workspace: Path):
        """CR-020: 会话自动追加消息"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        await _collect_events(rt, "hello")
        # Session should have user + assistant messages
        assert session.message_count >= 2
        assert session.messages[0].role == MessageRole.USER
        assert session.messages[1].role == MessageRole.ASSISTANT


# ============================================================================
# 6.4 边缘测试
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_cr030_empty_user_message(self, runtime: ConversationRuntime):
        """CR-030: 空用户消息"""
        events = await _collect_events(runtime, "")
        types = _event_types(events)
        assert AgentEventType.ERROR in types

    @pytest.mark.asyncio
    async def test_cr031_whitespace_message(self, runtime: ConversationRuntime):
        """CR-031: 纯空白消息"""
        events = await _collect_events(runtime, "   \t\n  ")
        types = _event_types(events)
        assert AgentEventType.ERROR in types

    @pytest.mark.asyncio
    async def test_cr032_repeated_messages(self, workspace: Path):
        """CR-032: 重复消息独立处理"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events1 = await _collect_events(rt, "hello")
        events2 = await _collect_events(rt, "hello")
        # Both produce valid events
        assert any(e.type == AgentEventType.RESPONSE for e in events1)
        assert any(e.type == AgentEventType.RESPONSE for e in events2)


# ============================================================================
# 6.5 故障注入
# ============================================================================

class TestFaultInjection:

    @pytest.mark.asyncio
    async def test_cr040_llm_call_fails(self, workspace: Path):
        """CR-040: LLM 调用失败"""
        provider = MockProvider(error_on_turn={0: ApiError("LLM down", status_code=500)})
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "hello")
        types = _event_types(events)
        assert AgentEventType.ERROR in types
        assert any("API error" in e.data.get("message", "") for e in events if e.type == AgentEventType.ERROR)

    @pytest.mark.asyncio
    async def test_cr041_tool_execution_exception(self, workspace: Path):
        """CR-041: 工具执行中途异常"""
        provider = MockProvider(scenarios=[
            Scenario("boom", trigger_patterns=["boom"],
                     response_factory=lambda m, t: _tool_response("read_file", {"file_path": "nonexistent.txt"})),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect_events(rt, "boom boom")
        # Tool returns error result (is_error=True), runtime continues
        tool_results = [e for e in events if e.type == AgentEventType.TOOL_ERROR]
        assert len(tool_results) >= 1

    @pytest.mark.asyncio
    async def test_cr044_concurrent_requests(self, workspace: Path):
        """CR-044: 并发对话请求"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

        async def single_turn(msg_id: int):
            session = Session(workspace=str(workspace))
            rt = ConversationRuntime(provider=MockProvider(), tool_registry=registry,
                                      permission_policy=policy, session=session)
            events = await _collect_events(rt, "hello")
            return msg_id, events

        results = await asyncio.gather(*[single_turn(i) for i in range(5)])
        for msg_id, events in results:
            assert any(e.type == AgentEventType.RESPONSE for e in events)


# ============================================================================
# 6.6 极限测试
# ============================================================================

class TestStress:

    @pytest.mark.asyncio
    async def test_cr050_max_steps_boundary(self, workspace: Path):
        """CR-050: 恰好 max_steps 时正确终止"""
        provider = MockProvider(scenarios=[
            Scenario("loop", trigger_patterns=[],
                     response_factory=lambda m, t: _tool_response("read_file", {"file_path": "main.md"})),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy,
                                  session=session, max_steps=3)

        events = await _collect_events(rt, "keep going")
        types = _event_types(events)
        assert AgentEventType.ERROR in types
        assert any("max steps" in e.data.get("message", "") for e in events if e.type == AgentEventType.ERROR)

    @pytest.mark.asyncio
    async def test_cr054_fast_sequential(self, workspace: Path):
        """CR-054: 快速连续对话"""
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        for i in range(10):
            events = await _collect_events(rt, f"message {i}")
            assert any(e.type in (AgentEventType.RESPONSE, AgentEventType.ERROR) for e in events)
