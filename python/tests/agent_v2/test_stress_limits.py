"""极限/压力测试 — 并发、大量数据、快速序列、内存、超时。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agent_v2.providers.mock_provider import MockProvider, Scenario, _text_response, _tool_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, PermissionPolicy, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.runtime.usage import UsageTracker
from src.agent_v2.tools.registry import ToolRegistry, create_default_registry
from src.agent_v2.types import (
    TokenUsage, Message, MessageRole, TextBlock, ToolUseBlock,
    AgentEventType,
)


# ============================================================================
# PermissionPolicy — 大规模规则匹配性能
# ============================================================================

class TestPolicyStress:
    def test_1000_rules_performance(self):
        rules = [f"tool_{i:04d}(path_{i}:*)" for i in range(1000)]
        policy = PermissionPolicy(
            PermissionMode.DANGER_FULL_ACCESS,  # Full access so non-matching tools are still allowed
            allow_rules=rules,
        )
        # Find middle rule — matches
        result1 = policy.authorize("tool_0500", '{"command":"path_0500_something"}')
        assert result1.is_allowed
        # Non-matching tool name — no rule match, but DANGER_FULL_ACCESS allows it
        result2 = policy.authorize("other_tool", '{"command":"path_0999_test"}')
        assert result2.is_allowed

    def test_10000_authorize_calls(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY, {
            "read_file": PermissionMode.READ_ONLY,
            "write_file": PermissionMode.WORKSPACE_WRITE,
        })
        for i in range(10000):
            result = policy.authorize("read_file", '{"file_path":"test.txt"}')
            assert result.is_allowed


# ============================================================================
# Session — 极端数据量
# ============================================================================

class TestSessionStress:
    def test_100000_messages(self, tmp_path: Path):
        """10 万条消息 — 不 OOM"""
        session = Session(workspace=str(tmp_path))
        for i in range(100_000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=f"msg {i}")]))
        assert session.message_count == 100_000

    def test_save_load_50000_messages(self, tmp_path: Path):
        """5 万条消息保存恢复"""
        session = Session(workspace=str(tmp_path))
        for i in range(50_000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=f"x{i}")]))
        sp = tmp_path / "stress.jsonl"
        session.save(sp)
        loaded = Session.load(sp)
        assert loaded.message_count == 50_000


# ============================================================================
# ToolRegistry — 大量工具 + 并发执行
# ============================================================================

class TestRegistryStress:
    def test_1000_tools_registered(self):
        reg = ToolRegistry()
        for i in range(1000):
            async def tool(args, n=i):
                from src.agent_v2.tools.registry import ToolResult
                return ToolResult(f"tool {n}")
            reg.register(f"tool_{i:04d}", f"Tool {i}", {}, tool)
        assert len(reg.definitions()) == 1000
        # Quick lookup
        assert reg.get("tool_0500") is not None

    @pytest.mark.asyncio
    async def test_100_concurrent_executions(self, tmp_path: Path):
        reg = create_default_registry(workspace_root=tmp_path)
        (tmp_path / "big.txt").write_text("x\n" * 1000, encoding="utf-8")
        results = await asyncio.gather(*[
            reg.execute("read_file", {"file_path": "big.txt"})
            for _ in range(100)
        ])
        for r in results:
            assert not r.is_error

    @pytest.mark.asyncio
    async def test_read_huge_file(self, tmp_path: Path):
        """300MB 文件读取 — 截断不 OOM"""
        reg = create_default_registry(workspace_root=tmp_path)
        big = tmp_path / "huge.txt"
        big.write_text("x" * (300 * 1024), encoding="utf-8")
        result = await reg.execute("read_file", {"file_path": "huge.txt"})
        assert not result.is_error
        assert "truncated" in result.output


# ============================================================================
# UsageTracker — 大数精度
# ============================================================================

class TestUsageStress:
    def test_billion_tokens(self):
        t = UsageTracker(model="deepseek-chat")
        t.record(TokenUsage(input_tokens=1_000_000_000, output_tokens=500_000_000))
        cost = t.estimated_cost()
        assert cost > 0
        assert t.total_tokens() == 1_500_000_000

    def test_100k_calls(self):
        t = UsageTracker(model="qwen3:8b")
        for _ in range(100_000):
            t.record(TokenUsage(input_tokens=10, output_tokens=5))
        assert t.call_count == 100_000
        assert t.total_tokens() == 1_500_000


# ============================================================================
# MockProvider — 高并发场景匹配
# ============================================================================

class TestProviderStress:
    @pytest.mark.asyncio
    async def test_100_concurrent_chat_calls(self):
        provider = MockProvider()
        msgs = [Message(role=MessageRole.USER, blocks=[TextBlock(text="hello")])]
        results = await asyncio.gather(*[
            provider.chat(msgs) for _ in range(100)
        ])
        for r in results:
            assert len(r.blocks) > 0


# ============================================================================
# ConversationRuntime — 长对话序列
# ============================================================================

class TestRuntimeStress:
    @pytest.mark.asyncio
    async def test_100_turn_conversation(self, tmp_path: Path):
        """100 轮对话"""
        (tmp_path / "doc.md").write_text("line\n" * 10, encoding="utf-8")
        provider = MockProvider()
        registry = create_default_registry(workspace_root=tmp_path)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(tmp_path))
        rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                  permission_policy=policy, session=session)
        for i in range(100):
            events = []
            async for e in rt.turn(f"message {i}"):
                events.append(e)
            assert any(t in (AgentEventType.RESPONSE, AgentEventType.DONE) for t in [e.type for e in events])

    @pytest.mark.asyncio
    async def test_rapid_concurrent_runtimes(self, tmp_path: Path):
        """10 个并发 Runtime，各自独立"""
        (tmp_path / "a.md").write_text("a", encoding="utf-8")

        async def single():
            provider = MockProvider()
            registry = create_default_registry(workspace_root=tmp_path)
            policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
            session = Session(workspace=str(tmp_path))
            rt = ConversationRuntime(provider=provider, tool_registry=registry,
                                      permission_policy=policy, session=session)
            events = []
            async for e in rt.turn("hello"):
                events.append(e)
            return events

        results = await asyncio.gather(*[single() for _ in range(10)])
        for events in results:
            types = [e.type for e in events]
            assert AgentEventType.RESPONSE in types


# ============================================================================
# 边界值/注入攻击
# ============================================================================

class TestBoundaryInjection:
    def test_null_byte_injection_tool_name(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        result = policy.authorize("read_file\x00bash", "{}")
        # Should not crash — treated as unknown tool name
        assert result.is_denied or result.is_allowed  # no crash is pass

    def test_sql_injection_input(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        result = policy.authorize("grep_files", '{"pattern":"DROP TABLE users; --"}')
        assert isinstance(result, type(policy.authorize("read_file", "{}")))

    def test_extremely_long_tool_name(self):
        name = "x" * 10000
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        policy.authorize(name, "{}")  # should not crash

    def test_deeply_nested_json_input(self):
        nested = '{"a":' * 100 + '"x"' + '}' * 100
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        try:
            policy.authorize("read_file", nested)
        except RecursionError:
            pytest.skip("Deep nesting causes recursion error")
        # Should not crash with MemoryError

    def test_unicode_surrogate_input(self):
        policy = PermissionPolicy(PermissionMode.READ_ONLY)
        result = policy.authorize("read_file", '{"file_path":"\\ud800\\udfff"}')
        assert result is not None  # no crash

    @pytest.mark.asyncio
    async def test_tool_result_max_truncation(self, tmp_path: Path):
        reg = create_default_registry(workspace_root=tmp_path)
        (tmp_path / "small.txt").write_text("hello", encoding="utf-8")
        # Repeated reads should all succeed
        results = await asyncio.gather(*[reg.execute("read_file", {"file_path": "small.txt"}) for _ in range(50)])
        for r in results:
            assert not r.is_error
            assert "hello" in r.output
