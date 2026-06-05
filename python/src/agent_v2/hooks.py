"""Hooks 系统 — 生命周期拦截器。

参考 claw-code:
  - runtime/hooks.rs: HookRunner + HookEvent + HookAbortSignal
  - plugins/src/hooks.rs: plugin hook definitions

Hook 类型:
  - PreToolUse: 工具调用前拦截（可 Allow/Deny/Ask）
  - PostToolUse: 工具调用后回调（日志、通知）
  - PostToolUseFailure: 工具失败回调（重试、降级）
  - Init: Agent 初始化
  - Shutdown: Agent 关闭
"""
from __future__ import annotations

import json
import logging
import subprocess
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


class HookDefinition:
    """单个 hook 定义。"""

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


class HookRunner:
    """Hook 执行器。参考 claw-code HookRunner。

    支持两种 hook：
    1. Python callable（进程内，快速）
    2. Shell command（进程外 stdin → stdout，灵活）
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
        """注册内置 hooks。"""
        # Log all tool calls
        def _log_tool_call(event: HookEvent) -> HookResult:
            logger.info("tool_call: %s input_len=%d", event.tool_name, len(event.tool_input))
            return HookResult(decision=HookDecision.ALLOW)

        # Log all tool failures
        def _log_tool_failure(event: HookEvent) -> HookResult:
            logger.warning("tool_failure: %s error=%s", event.tool_name, event.tool_result[:200])
            return HookResult(decision=HookDecision.ALLOW)

        self.register_callable("builtin:log_tool", HookPoint.POST_TOOL_USE,
                               _log_tool_call, priority=100)
        self.register_callable("builtin:log_failure", HookPoint.POST_TOOL_USE_FAILURE,
                               _log_tool_failure, priority=100)

    async def run(self, hook_point: HookPoint, event: HookEvent) -> HookResult:
        """执行匹配 hook_point 的所有 hooks。参考 claw-code HookRunner.run()。

        短路逻辑：
        - PreToolUse: 第一个 DENY 或 ASK 决定立即返回
        - 其他 hook 类型: 所有 hooks 都执行，返回 ALLOW
        """
        event.hook = hook_point
        final = HookResult(decision=HookDecision.ALLOW)

        for hook in self._hooks:
            if hook.hook_point != hook_point:
                continue

            result = await self._execute_hook(hook, event)

            if hook_point == HookPoint.PRE_TOOL_USE:
                if result.decision == HookDecision.DENY:
                    return result
                if result.decision == HookDecision.ASK:
                    return result

        return final

    async def _execute_hook(self, hook: HookDefinition, event: HookEvent) -> HookResult:
        # Check for callable
        key = f"{hook.hook_point.value}:{hook.name}"
        func = self._callables.get(key)
        if func is not None:
            try:
                import asyncio
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
                if proc.returncode == 0:
                    return HookResult(decision=HookDecision.ALLOW)
                elif proc.returncode == 2:
                    return HookResult(decision=HookDecision.DENY, reason=stdout.decode()[:200])
                elif proc.returncode == 3:
                    return HookResult(decision=HookDecision.ASK, reason=stdout.decode()[:200])
                return HookResult(decision=HookDecision.ALLOW)
            except Exception as e:
                logger.warning("shell hook '%s' failed: %s", hook.name, e)

        return HookResult(decision=HookDecision.ALLOW)


async def _create_subprocess(command: str):
    import asyncio
    return await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


# Import needed for async subprocess
import asyncio
