"""生命周期 Hook 系统 — Agent 运行时的扩展点。

设计参考 Hermes Agent 的全生命周期 Hook 机制：
- 在 Agent 运行的各个关键节点注入自定义逻辑
- 不修改核心代码即可扩展功能（日志、权限、业务规则）
- 支持同步和异步 Hook 函数

Hook 点:
├── on_agent_start — Agent 初始化时
├── on_agent_end — Agent 关闭时
├── on_tool_call — 工具执行前
├── on_tool_result — 工具返回后
├── on_llm_call — LLM 调用前
├── on_llm_response — LLM 返回后
├── on_pre_compress — 上下文压缩前
├── on_post_compress — 上下文压缩后
├── on_memory_write — 写入记忆时
├── on_skill_create — 创建 Skill 时
├── on_error — 错误发生时
└── on_session_end — 会话结束时
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookPoint(Enum):
    """Hook 触发点。"""

    ON_AGENT_START = auto()
    ON_AGENT_END = auto()
    ON_TOOL_CALL = auto()
    ON_TOOL_RESULT = auto()
    ON_LLM_CALL = auto()
    ON_LLM_RESPONSE = auto()
    ON_PRE_COMPRESS = auto()
    ON_POST_COMPRESS = auto()
    ON_MEMORY_WRITE = auto()
    ON_SKILL_CREATE = auto()
    ON_ERROR = auto()
    ON_SESSION_END = auto()
    ON_APPROVAL_REQUEST = auto()
    ON_APPROVAL_RESPONSE = auto()
    ON_TASK_START = auto()
    ON_TASK_COMPLETE = auto()


@dataclass
class HookContext:
    """Hook 上下文 — 传递给 Hook 函数的信息。

    Attributes:
        point: 触发点。
        data: 事件数据（如工具名、结果、错误等）。
        agent: Agent 实例引用（可选）。
    """

    point: HookPoint
    data: dict[str, Any] = field(default_factory=dict)
    agent: Any = None


class HookManager:
    """Hook 管理器 — 注册、管理和触发生命周期 Hook。

    使用示例:
        hooks = HookManager()

        @hooks.register(HookPoint.ON_TOOL_CALL)
        def log_tool_call(ctx: HookContext):
            logger.info("工具调用: %s", ctx.data.get("tool_name"))

        @hooks.register(HookPoint.ON_ERROR)
        async def on_error(ctx: HookContext):
            await notify_admin(ctx.data.get("error"))
    """

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[Callable]] = {}

    def register(self, point: HookPoint) -> Callable:
        """装饰器：注册 Hook 函数。

        Args:
            point: 触发点。

        Returns:
            装饰器函数。
        """

        def decorator(fn: Callable) -> Callable:
            if point not in self._hooks:
                self._hooks[point] = []
            self._hooks[point].append(fn)
            logger.debug("Hook 注册: %s → %s", point.name, fn.__name__)
            return fn

        return decorator

    def add_hook(self, point: HookPoint, fn: Callable) -> None:
        """直接注册 Hook 函数（非装饰器方式）。

        Args:
            point: 触发点。
            fn: Hook 函数。
        """
        if point not in self._hooks:
            self._hooks[point] = []
        self._hooks[point].append(fn)

    def remove_hook(self, point: HookPoint, fn: Callable) -> None:
        """移除已注册的 Hook。

        Args:
            point: 触发点。
            fn: 要移除的 Hook 函数。
        """
        if point in self._hooks:
            self._hooks[point] = [h for h in self._hooks[point] if h is not fn]

    async def trigger(self, ctx: HookContext) -> None:
        """触发指定点的所有 Hook。

        按注册顺序依次执行。单个 Hook 失败不影响后续 Hook。
        支持同步和异步 Hook 函数。

        Args:
            ctx: Hook 上下文。
        """
        hooks = self._hooks.get(ctx.point, [])
        for hook_fn in hooks:
            try:
                result = hook_fn(ctx)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(
                    "Hook %s.%s 执行失败: %s",
                    ctx.point.name, hook_fn.__name__, e,
                )

    def trigger_sync(self, ctx: HookContext) -> None:
        """同步触发指定点的所有 Hook。

        仅执行同步 Hook，跳过异步 Hook。

        Args:
            ctx: Hook 上下文。
        """
        hooks = self._hooks.get(ctx.point, [])
        for hook_fn in hooks:
            try:
                result = hook_fn(ctx)
                if asyncio.iscoroutine(result):
                    logger.debug("跳过异步 Hook: %s", hook_fn.__name__)
                    continue
            except Exception as e:
                logger.warning("Hook %s.%s 执行失败: %s", ctx.point.name, hook_fn.__name__, e)

    def get_hooks(self, point: HookPoint) -> list[Callable]:
        """获取指定点的所有 Hook 函数。

        Args:
            point: 触发点。

        Returns:
            Hook 函数列表。
        """
        return list(self._hooks.get(point, []))

    def clear(self) -> None:
        """移除所有已注册的 Hook。"""
        self._hooks.clear()
