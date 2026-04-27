"""Hook 系统单元测试 — 注册、触发、同步/异步、新 HookPoint。"""

from __future__ import annotations

import asyncio

import pytest

from src.agent.hooks import HookContext, HookManager, HookPoint


@pytest.fixture
def mgr():
    return HookManager()


# ---------------------------------------------------------------------------
# HookPoint enum — 验证 Phase 3 新增的 HookPoint
# ---------------------------------------------------------------------------


class TestHookPoints:
    def test_phase3_new_points(self):
        assert HookPoint.ON_APPROVAL_REQUEST.name == "ON_APPROVAL_REQUEST"
        assert HookPoint.ON_APPROVAL_RESPONSE.name == "ON_APPROVAL_RESPONSE"
        assert HookPoint.ON_TASK_START.name == "ON_TASK_START"
        assert HookPoint.ON_TASK_COMPLETE.name == "ON_TASK_COMPLETE"

    def test_total_count(self):
        # 原有 12 + Phase 3 新增 4 = 16
        assert len(HookPoint) == 16

    def test_all_unique(self):
        values = [p.value for p in HookPoint]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# HookContext
# ---------------------------------------------------------------------------


class TestHookContext:
    def test_defaults(self):
        ctx = HookContext(point=HookPoint.ON_TOOL_CALL)
        assert ctx.data == {}
        assert ctx.agent is None

    def test_with_data(self):
        ctx = HookContext(
            point=HookPoint.ON_TOOL_CALL,
            data={"tool_name": "str_replace"},
        )
        assert ctx.data["tool_name"] == "str_replace"


# ---------------------------------------------------------------------------
# 注册 + 触发
# ---------------------------------------------------------------------------


class TestRegisterAndTrigger:
    @pytest.mark.anyio
    async def test_sync_hook_triggered(self, mgr):
        calls = []
        mgr.add_hook(HookPoint.ON_TOOL_CALL, lambda ctx: calls.append(ctx.data))
        await mgr.trigger(HookContext(point=HookPoint.ON_TOOL_CALL, data={"x": 1}))
        assert len(calls) == 1
        assert calls[0] == {"x": 1}

    @pytest.mark.anyio
    async def test_async_hook_triggered(self, mgr):
        calls = []

        async def async_hook(ctx):
            calls.append(ctx.point.name)

        mgr.add_hook(HookPoint.ON_LLM_CALL, async_hook)
        await mgr.trigger(HookContext(point=HookPoint.ON_LLM_CALL))
        assert calls == ["ON_LLM_CALL"]

    @pytest.mark.anyio
    async def test_multiple_hooks_ordered(self, mgr):
        order = []
        mgr.add_hook(HookPoint.ON_AGENT_START, lambda ctx: order.append(1))
        mgr.add_hook(HookPoint.ON_AGENT_START, lambda ctx: order.append(2))
        mgr.add_hook(HookPoint.ON_AGENT_START, lambda ctx: order.append(3))
        await mgr.trigger(HookContext(point=HookPoint.ON_AGENT_START))
        assert order == [1, 2, 3]

    @pytest.mark.anyio
    async def test_hook_failure_doesnt_stop_others(self, mgr):
        results = []

        def failing(ctx):
            raise RuntimeError("boom")

        mgr.add_hook(HookPoint.ON_ERROR, failing)
        mgr.add_hook(HookPoint.ON_ERROR, lambda ctx: results.append("ok"))
        await mgr.trigger(HookContext(point=HookPoint.ON_ERROR))
        assert results == ["ok"]

    @pytest.mark.anyio
    async def test_no_hooks_no_error(self, mgr):
        await mgr.trigger(HookContext(point=HookPoint.ON_SESSION_END))


# ---------------------------------------------------------------------------
# Decorator 注册
# ---------------------------------------------------------------------------


class TestDecorator:
    @pytest.mark.anyio
    async def test_decorator_registers(self, mgr):
        calls = []

        @mgr.register(HookPoint.ON_MEMORY_WRITE)
        def my_hook(ctx):
            calls.append(True)

        await mgr.trigger(HookContext(point=HookPoint.ON_MEMORY_WRITE))
        assert calls == [True]


# ---------------------------------------------------------------------------
# 同步触发
# ---------------------------------------------------------------------------


class TestSyncTrigger:
    def test_sync_hook(self, mgr):
        calls = []
        mgr.add_hook(HookPoint.ON_TOOL_RESULT, lambda ctx: calls.append(1))
        mgr.trigger_sync(HookContext(point=HookPoint.ON_TOOL_RESULT))
        assert calls == [1]

    def test_async_hook_skipped(self, mgr):
        calls = []

        async def async_hook(ctx):
            calls.append(1)

        mgr.add_hook(HookPoint.ON_TOOL_RESULT, async_hook)
        mgr.trigger_sync(HookContext(point=HookPoint.ON_TOOL_RESULT))
        assert calls == []


# ---------------------------------------------------------------------------
# remove_hook + clear
# ---------------------------------------------------------------------------


class TestRemoveAndClear:
    @pytest.mark.anyio
    async def test_remove_hook(self, mgr):
        calls = []

        def hook(ctx):
            calls.append(1)

        mgr.add_hook(HookPoint.ON_AGENT_END, hook)
        mgr.remove_hook(HookPoint.ON_AGENT_END, hook)
        await mgr.trigger(HookContext(point=HookPoint.ON_AGENT_END))
        assert calls == []

    def test_clear(self, mgr):
        mgr.add_hook(HookPoint.ON_AGENT_START, lambda ctx: None)
        mgr.add_hook(HookPoint.ON_AGENT_END, lambda ctx: None)
        mgr.clear()
        assert mgr.get_hooks(HookPoint.ON_AGENT_START) == []

    def test_get_hooks(self, mgr):
        h1 = lambda ctx: None  # noqa: E731
        h2 = lambda ctx: None  # noqa: E731
        mgr.add_hook(HookPoint.ON_SKILL_CREATE, h1)
        mgr.add_hook(HookPoint.ON_SKILL_CREATE, h2)
        hooks = mgr.get_hooks(HookPoint.ON_SKILL_CREATE)
        assert len(hooks) == 2
        assert h1 in hooks
        assert h2 in hooks


# ---------------------------------------------------------------------------
# Phase 3: Approval / Task hook 点
# ---------------------------------------------------------------------------


class TestPhase3HookPoints:
    @pytest.mark.anyio
    async def test_approval_request_hook(self, mgr):
        captured = {}

        def capture_approval(ctx):
            captured.update(ctx.data)

        mgr.add_hook(HookPoint.ON_APPROVAL_REQUEST, capture_approval)
        await mgr.trigger(HookContext(
            point=HookPoint.ON_APPROVAL_REQUEST,
            data={"tool": "str_replace", "risk": "destructive"},
        ))
        assert captured["tool"] == "str_replace"
        assert captured["risk"] == "destructive"

    @pytest.mark.anyio
    async def test_approval_response_hook(self, mgr):
        captured = {}

        mgr.add_hook(HookPoint.ON_APPROVAL_RESPONSE, lambda ctx: captured.update(ctx.data))
        await mgr.trigger(HookContext(
            point=HookPoint.ON_APPROVAL_RESPONSE,
            data={"decision": "allow_once"},
        ))
        assert captured["decision"] == "allow_once"

    @pytest.mark.anyio
    async def test_task_start_hook(self, mgr):
        tasks = []
        mgr.add_hook(HookPoint.ON_TASK_START, lambda ctx: tasks.append(ctx.data.get("task_id")))
        await mgr.trigger(HookContext(
            point=HookPoint.ON_TASK_START,
            data={"task_id": "t_001"},
        ))
        assert tasks == ["t_001"]

    @pytest.mark.anyio
    async def test_task_complete_hook(self, mgr):
        results = []
        mgr.add_hook(HookPoint.ON_TASK_COMPLETE, lambda ctx: results.append(ctx.data.get("status")))
        await mgr.trigger(HookContext(
            point=HookPoint.ON_TASK_COMPLETE,
            data={"task_id": "t_001", "status": "ok"},
        ))
        assert results == ["ok"]
