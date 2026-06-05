"""Hooks 测试 — 注册/执行/拦截/故障/并发。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent_v2.hooks import (
    HookDecision,
    HookDefinition,
    HookEvent,
    HookPoint,
    HookResult,
    HookRunner,
)


class TestHookDefinition:
    def test_create_hook(self):
        h = HookDefinition(name="test", hook_point=HookPoint.PRE_TOOL_USE, command="echo ok", priority=30)
        assert h.name == "test"
        assert h.hook_point == HookPoint.PRE_TOOL_USE
        assert h.priority == 30

    def test_to_dict(self):
        h = HookDefinition(name="h1", hook_point=HookPoint.POST_TOOL_USE, command="echo x", priority=50)
        d = h.to_dict()
        assert d["name"] == "h1"
        assert d["hook_point"] == "PostToolUse"
        assert d["priority"] == 50


class TestHookEvent:
    def test_create_event(self):
        e = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file", tool_input="{}")
        assert e.tool_name == "write_file"
        assert not e.is_error

    def test_to_dict(self):
        e = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="read_file",
                      tool_input='{"file_path":"a.md"}', tool_result="file content")
        d = e.to_dict()
        assert d["tool_name"] == "read_file"
        assert "a.md" in d["tool_input"]
        assert d["tool_result"] == "file content"
        assert "POST_TOOL_USE" in d["hook"] or "PostToolUse" in str(d)


class TestHookRunner:
    @pytest.mark.asyncio
    async def test_run_empty_runner(self):
        runner = HookRunner()
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_callable_hook_allow(self):
        runner = HookRunner()
        def my_hook(event: HookEvent) -> HookResult:
            return HookResult(decision=HookDecision.ALLOW, reason="looks fine")
        runner.register_callable("my", HookPoint.PRE_TOOL_USE, my_hook, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_callable_hook_deny(self):
        runner = HookRunner()
        def block_rm(event: HookEvent) -> HookResult:
            if "rm" in event.tool_input:
                return HookResult(decision=HookDecision.DENY, reason="rm blocked")
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("block_rm", HookPoint.PRE_TOOL_USE, block_rm, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="run_command",
                          tool_input='{"command":"rm -rf /"}')
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.DENY
        assert "rm" in result.reason

    @pytest.mark.asyncio
    async def test_callable_hook_ask(self):
        runner = HookRunner()
        def ask_write(event: HookEvent) -> HookResult:
            return HookResult(decision=HookDecision.ASK, reason="confirm write?")
        runner.register_callable("ask", HookPoint.PRE_TOOL_USE, ask_write, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="write_file")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ASK

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """优先级小的 hook 先执行。PreToolUse 时第一个 DENY 短路。"""
        runner = HookRunner()
        calls = []
        def high_prio(event):
            calls.append("high")
            return HookResult(decision=HookDecision.DENY, reason="blocked by high")
        def low_prio(event):
            calls.append("low")
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("high", HookPoint.PRE_TOOL_USE, high_prio, priority=10)
        runner.register_callable("low", HookPoint.PRE_TOOL_USE, low_prio, priority=90)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.DENY
        # high priority (10) runs first and short-circuits, low never runs
        assert calls == ["high"]

    @pytest.mark.asyncio
    async def test_post_tool_use_all_run(self):
        """PostToolUse 所有 hooks 都执行，不短路。"""
        runner = HookRunner()
        calls = []
        def h1(event):
            calls.append(1)
            return HookResult(decision=HookDecision.DENY)
        def h2(event):
            calls.append(2)
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("h1", HookPoint.POST_TOOL_USE, h1, priority=10)
        runner.register_callable("h2", HookPoint.POST_TOOL_USE, h2, priority=20)
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.POST_TOOL_USE, event)
        # Both run, final result is ALLOW
        assert calls == [1, 2]
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_hook_exception_safe(self):
        """Hook 异常不应崩溃，返回 ALLOW。"""
        runner = HookRunner()
        def boom(event):
            raise RuntimeError("hook error")
        runner.register_callable("boom", HookPoint.PRE_TOOL_USE, boom, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_wrong_hook_point_not_called(self):
        runner = HookRunner()
        calls = []
        def pre_hook(event):
            calls.append("pre")
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("pre", HookPoint.PRE_TOOL_USE, pre_hook, priority=10)
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test")
        await runner.run(HookPoint.POST_TOOL_USE, event)
        assert calls == []  # pre hook should NOT be called for POST

    @pytest.mark.asyncio
    async def test_add_builtin_hooks(self):
        runner = HookRunner()
        runner.add_builtin_hooks()
        assert len(runner._hooks) >= 2  # log_tool + log_failure

    @pytest.mark.asyncio
    async def test_async_hook(self):
        runner = HookRunner()
        import asyncio
        async def async_hook(event):
            await asyncio.sleep(0.01)
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("async", HookPoint.PRE_TOOL_USE, async_hook, priority=10)
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW


class TestHookEdge:
    @pytest.mark.asyncio
    async def test_very_long_input(self):
        runner = HookRunner()
        def log(event):
            return HookResult(decision=HookDecision.ALLOW)
        runner.register_callable("log", HookPoint.POST_TOOL_USE, log, priority=50)
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test",
                          tool_input="x" * 100_000)
        result = await runner.run(HookPoint.POST_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_null_tool_name(self):
        runner = HookRunner()
        event = HookEvent(hook=HookPoint.PRE_TOOL_USE, tool_name="")
        result = await runner.run(HookPoint.PRE_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW

    @pytest.mark.asyncio
    async def test_100_hooks_performance(self):
        runner = HookRunner()
        for i in range(100):
            def make_hook(n=i):
                def h(event, _n=n):
                    return HookResult(decision=HookDecision.ALLOW)
                return h
            runner.register_callable(f"h{i:03d}", HookPoint.POST_TOOL_USE, make_hook(), priority=50)
        event = HookEvent(hook=HookPoint.POST_TOOL_USE, tool_name="test")
        result = await runner.run(HookPoint.POST_TOOL_USE, event)
        assert result.decision == HookDecision.ALLOW
