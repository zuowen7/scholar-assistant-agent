"""AgentSession — 一次完整任务的会话对象（Phase 2: 状态机核心）。

取代原有 AgentLoop.run() 的一次性 AsyncGenerator 模式，
提供可暂停、可恢复、多任务编排的会话管理。

关键设计：
- drive() 是对外的事件流 AsyncGenerator
- 每个 Task 独立运行 ReAct 循环（调用 AgentLoop.step()）
- 实例级状态隔离：两个 AgentSession 互不污染
- 审批等待通过 asyncio.Future 实现（Phase 3 接入）
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable

from src.agent.agent import AgentLoop, GLOBAL_MAX_STEPS, TASK_MAX_STEPS, _TOOL_RESULT_MAX_CHARS
from src.agent.change_journal import ChangeJournal
from src.agent.hooks import HookContext, HookPoint
from src.agent.models import (
    AgentEvent,
    EVT_ABORTED,
    EVT_APPROVAL_RECEIVED,
    EVT_AWAIT_APPROVAL,
    EVT_DONE,
    EVT_ERROR,
    EVT_SESSION_STARTED,
    EVT_TASK_DONE,
    EVT_TASK_STARTED,
    EVT_THOUGHT,
    EVT_TOOL_CALL,
    EVT_TOOL_RESULT,
    EVT_WARNING,
    Message,
    SessionState,
)
from src.agent.security_gate import SecurityGate, ToolRiskLevel
from src.agent.task_queue import TaskQueue
from src.agent.workspace import WorkspaceEnv

logger = logging.getLogger(__name__)

_APPROVAL_TIMEOUT = 600  # seconds


class SessionAborted(Exception):
    """用户主动中止会话。"""


@dataclass
class SessionConfig:
    """会话配置。"""
    max_task_steps: int = TASK_MAX_STEPS
    max_global_steps: int = GLOBAL_MAX_STEPS
    auto_approve: bool = True  # dev mode: auto-approve all tool calls
    approval_timeout: int = _APPROVAL_TIMEOUT


class AgentSession:
    """一次完整任务的会话对象。

    管理会话生命周期、消息历史、任务队列、审批状态。
    所有实例级状态集中于此，AgentLoop 仅提供无状态的单步执行。

    Attributes:
        id: 会话唯一标识。
        state: 当前生命周期状态。
        task_queue: 子任务队列。
        messages: 消息历史。
        config: 会话配置。
        pending_approvals: 等待审批的 Future 字典。
        approved_categories: 已通过审批的类别集合。
    """

    def __init__(
        self,
        agent: AgentLoop,
        workspace: WorkspaceEnv | None = None,
        journal: ChangeJournal | None = None,
        config: SessionConfig | None = None,
        session_id: str = "",
        session_store: Any | None = None,
        event_callback: Callable[[AgentEvent], None] | None = None,
        created_at: str = "",
    ) -> None:
        self.id = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        self.agent = agent
        self.workspace = workspace
        self.journal = journal
        self.config = config or SessionConfig()
        self.state = SessionState.INITIALIZING

        self.task_queue = TaskQueue()
        self.messages: list[Message] = []
        self.global_step = 0
        self.created_at = created_at or datetime.now().isoformat(timespec="seconds")

        self.pending_approvals: dict[str, Any] = {}
        self.approved_categories: set[str] = set()
        self.consecutive_errors = 0
        self.security_gate = SecurityGate()

        self._store = session_store
        self._event_callback = event_callback
        self._query = ""

    async def drive(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """驱动会话的主事件流。每次 yield 一个 AgentEvent。

        Args:
            query: 用户查询。
            history: 对话历史。

        Yields:
            AgentEvent 事件。
        """
        self._query = query
        self.state = SessionState.INITIALIZING
        ev_start = AgentEvent(
            type=EVT_SESSION_STARTED,
            content="",
            metadata={"session_id": self.id},
        )
        yield ev_start
        self._dispatch_event(ev_start)

        # 构建初始消息
        self.messages = self.agent._build_messages(query, history)

        # Plan-and-Execute
        self.state = SessionState.PLANNING
        plan = await self.agent._generate_plan(query, self.messages)
        if plan:
            ev_plan = AgentEvent(type=EVT_THOUGHT, content=f"执行计划:\n{plan}")
            yield ev_plan
            self._dispatch_event(ev_plan)
            plan_text = f"\n\n## 执行计划\n请按以下步骤执行：\n{plan}"
            if self.messages and self.messages[0].role == "system":
                self.messages[0] = Message(
                    role="system",
                    content=self.messages[0].content + plan_text,
                )
            else:
                self.messages.insert(0, Message(role="system", content=plan_text))

            # 将计划拆解为任务
            steps = [line.strip() for line in plan.split("\n") if line.strip()]
            self.task_queue.add_many(steps)
        else:
            # 简单任务：单任务队列
            self.task_queue.add(query)

        self.state = SessionState.EXECUTING
        self._checkpoint()

        try:
            while self.task_queue.has_pending():
                task = self.task_queue.next()
                if task is None:
                    break

                ev_ts = AgentEvent(
                    type=EVT_TASK_STARTED,
                    content="",
                    metadata={
                        "task_id": task.id,
                        "title": task.title,
                        "index": self.task_queue.done_count + 1,
                        "total": self.task_queue.total_count,
                    },
                )
                yield ev_ts
                self._dispatch_event(ev_ts)

                try:
                    async for ev in self._drive_task(task):
                        yield ev
                        self._dispatch_event(ev)
                except SessionAborted:
                    self.state = SessionState.ABORTED
                    ev_aborted = AgentEvent(
                        type=EVT_ABORTED,
                        content="",
                        metadata={"session_id": self.id},
                    )
                    yield ev_aborted
                    self._dispatch_event(ev_aborted)
                    self._checkpoint()
                    return

                self.task_queue.mark_done(task.id)

                ev_td = AgentEvent(
                    type=EVT_TASK_DONE,
                    content="",
                    metadata={"task_id": task.id, "status": "ok"},
                )
                yield ev_td
                self._dispatch_event(ev_td)
                self._checkpoint()

                # Skill nudge check after each task completion
                nudge = self._skill_nudge()
                if nudge:
                    yield AgentEvent(type=EVT_WARNING, content=nudge)

            self.state = SessionState.DONE
            ev_done = AgentEvent(
                type=EVT_DONE,
                content="",
                metadata={
                    "session_id": self.id,
                    "token_usage": self.agent.llm.token_usage.to_dict(),
                    "tasks_done": self.task_queue.done_count,
                },
            )
            yield ev_done
            self._dispatch_event(ev_done)
            self._checkpoint()
        except GeneratorExit:
            # Client disconnected — save checkpoint for resume
            self.state = SessionState.IDLE
            self._checkpoint()
            raise
        except Exception as e:
            logger.error("Session drive 异常: %s", e, exc_info=True)
            self.state = SessionState.ABORTED
            ev_err = AgentEvent(type="error", content=f"会话异常: {e}")
            yield ev_err
            self._dispatch_event(ev_err)
            self._checkpoint()

    async def _drive_task(self, task) -> AsyncGenerator[AgentEvent, None]:
        """驱动单个任务的 ReAct 循环。

        Phase 3: 工具调用前经 SecurityGate 门控 — BANNED 直接拒绝，
        MODERATE/DESTRUCTIVE 触发 await_approval → Future 等待用户决定后再执行。
        """
        task_step = 0
        self.consecutive_errors = 0

        while (
            task_step < self.config.max_task_steps
            and self.global_step < self.config.max_global_steps
        ):
            task_step += 1
            self.global_step += 1

            if self.consecutive_errors >= 5:
                yield AgentEvent(
                    type=EVT_WARNING,
                    content="连续 5 次错误，暂停会话。",
                    metadata={"code": "CIRCUIT_BREAKER"},
                )
                break

            step_result = await self.agent.step(
                self.messages,
                step_num=self.global_step,
                max_steps=self.config.max_global_steps,
                execute_tools=False,  # Phase 3: 先门控，后执行
            )

            # 转发推理事件（response → thought 避免前端提前终止）
            for ev in step_result.events:
                if ev.type == "response":
                    if ev.content:
                        yield AgentEvent(
                            type=EVT_THOUGHT,
                            content=ev.content,
                            metadata={"task_id": task.id},
                        )
                    continue
                if ev.type == "tool_call":
                    ev.metadata = ev.metadata or {}
                    ev.metadata["event_id"] = ev.event_id
                yield ev

            if step_result.error:
                self.consecutive_errors += 1
                if self.consecutive_errors >= 5:
                    continue
                yield AgentEvent(
                    type=EVT_ERROR if self.consecutive_errors >= 3 else EVT_WARNING,
                    content=step_result.error,
                )
                continue

            self.consecutive_errors = 0

            # 无工具调用 → 最终回答
            if not step_result.tool_calls:
                if step_result.is_final:
                    if step_result.final_answer and self.agent.memory:
                        try:
                            self.agent.memory.add_memory(
                                content=f"Q: {self._query}\nA: {step_result.final_answer[:2000]}",
                                category="conversation",
                                source="session",
                                importance=0.5,
                            )
                        except Exception as e:
                            logger.warning("记忆存储失败（不影响推理）: %s", e)
                    return
                continue

            # ── Phase 3: SecurityGate + 审批执行 ──
            for tc in step_result.tool_calls:
                gate = self.security_gate.classify(tc.name, tc.arguments)

                if gate.is_banned:
                    error_msg = f"Tool '{tc.name}' blocked: {gate.reason}"
                    self.messages.append(Message(
                        role="tool", content=error_msg, tool_call_id=tc.id,
                    ))
                    yield AgentEvent(
                        type=EVT_TOOL_RESULT,
                        content=error_msg,
                        metadata={"tool_name": tc.name, "error": True},
                    )
                    logger.warning("SecurityGate banned: %s %s → %s", tc.name, tc.arguments, gate.reason)
                    continue

                # 是否需要用户审批？
                needs_approval = (
                    not self.config.auto_approve
                    and gate.needs_approval
                    and "*" not in self.approved_categories
                )

                if needs_approval:
                    evt_id = f"evt_{uuid.uuid4().hex[:8]}"
                    approval_evt = AgentEvent(
                        type=EVT_AWAIT_APPROVAL,
                        content=f"Agent 想要执行 '{tc.name}'",
                        event_id=evt_id,
                        metadata={
                            "tool": tc.name,
                            "args": tc.arguments,
                            "risk": gate.risk.name.lower(),
                            "reason": gate.reason,
                        },
                    )
                    self._dispatch_event(approval_evt)
                    yield approval_evt

                    # 创建 Future 并等待用户通过 REST 端点裁决
                    loop = asyncio.get_running_loop()
                    fut: asyncio.Future = loop.create_future()
                    self.pending_approvals[evt_id] = fut
                    try:
                        decision = await asyncio.wait_for(
                            fut, timeout=self.config.approval_timeout,
                        )
                    except asyncio.TimeoutError:
                        decision = "deny"
                    finally:
                        self.pending_approvals.pop(evt_id, None)

                    yield AgentEvent(
                        type=EVT_APPROVAL_RECEIVED,
                        content=f"审批结果: {decision}",
                        event_id=evt_id,
                    )

                    if decision == "deny":
                        self.messages.append(Message(
                            role="tool",
                            content=f"User denied execution of '{tc.name}': {gate.reason}",
                            tool_call_id=tc.id,
                        ))
                        continue
                    if decision == "allow_session":
                        self.approved_categories.add("*")
                    if decision == "abort":
                        raise SessionAborted()
                    # allow_once → 继续执行

                # 执行工具
                result = await self.agent._execute_single_tool(tc, self._query)
                self.messages.append(Message(
                    role="tool",
                    content=result[:_TOOL_RESULT_MAX_CHARS],
                    tool_call_id=tc.id,
                ))
                yield AgentEvent(
                    type=EVT_TOOL_RESULT,
                    content=result[:500] + ("..." if len(result) > 500 else ""),
                    metadata={"tool_name": tc.name},
                )

        # 步数耗尽
        if task_step >= self.config.max_task_steps:
            yield AgentEvent(
                type=EVT_WARNING,
                content=f"任务步数达到上限 ({self.config.max_task_steps})",
                metadata={"code": "TASK_STEP_LIMIT"},
            )

    async def abort(self) -> None:
        """中止会话。"""
        for fut in self.pending_approvals.values():
            if not fut.done():
                fut.set_result("abort")
        self.state = SessionState.ABORTED

    async def approve(self, event_id: str, decision: str) -> bool:
        """处理审批决定。

        Args:
            event_id: 待审批的事件 ID。
            decision: allow_once / allow_session / deny / abort。

        Returns:
            是否成功处理。
        """
        fut = self.pending_approvals.get(event_id)
        if fut is None or fut.done():
            return False

        if decision == "allow_session":
            self.approved_categories.add("*")

        fut.set_result(decision)
        return True

    def _checkpoint(self) -> None:
        """Persist current session state to SessionStore (if configured)."""
        if self._store is None:
            return
        try:
            data = self._store.serialize_session(self, query=self._query)
            data["created_at"] = self.created_at
            self._store.save(data)
        except Exception as e:
            logger.warning("Session checkpoint failed: %s", e)

    def _dispatch_event(self, event: AgentEvent) -> None:
        """Send event to callback (trajectory recorder, etc.)."""
        if self._event_callback is not None:
            try:
                self._event_callback(event)
            except Exception as e:
                logger.warning("Event callback error: %s", e)

    def _skill_nudge(self) -> str | None:
        """Check if skill system wants to nudge the agent.

        Returns:
            Nudge message or None.
        """
        skills = getattr(self.agent, "skills", None)
        if skills is None:
            return None
        try:
            return skills.nudge_check()
        except Exception:
            return None

    async def resume(
        self,
        agent: AgentLoop,
        history: list[Message] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Resume a paused session from its last checkpoint.

        Restores messages and task queue, then continues executing pending tasks.

        Args:
            agent: New AgentLoop instance for this resume.
            history: Optional history to prepend.

        Yields:
            AgentEvent events from the resumed execution.
        """
        self.agent = agent
        self.state = SessionState.EXECUTING

        yield AgentEvent(
            type=EVT_SESSION_STARTED,
            content="",
            metadata={
                "session_id": self.id,
                "resumed": True,
                "resumed_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        try:
            while self.task_queue.has_pending():
                task = self.task_queue.next()
                if task is None:
                    break

                yield AgentEvent(
                    type=EVT_TASK_STARTED,
                    content="",
                    metadata={
                        "task_id": task.id,
                        "title": task.title,
                        "index": self.task_queue.done_count + 1,
                        "total": self.task_queue.total_count,
                    },
                )

                try:
                    async for ev in self._drive_task(task):
                        yield ev
                        self._dispatch_event(ev)
                except SessionAborted:
                    self.state = SessionState.ABORTED
                    yield AgentEvent(
                        type=EVT_ABORTED,
                        content="",
                        metadata={"session_id": self.id},
                    )
                    self._checkpoint()
                    return

                self.task_queue.mark_done(task.id)

                ev_td = AgentEvent(
                    type=EVT_TASK_DONE,
                    content="",
                    metadata={"task_id": task.id, "status": "ok"},
                )
                yield ev_td
                self._dispatch_event(ev_td)
                self._checkpoint()

                nudge = self._skill_nudge()
                if nudge:
                    yield AgentEvent(type=EVT_WARNING, content=nudge)

            self.state = SessionState.DONE
            ev_done = AgentEvent(
                type=EVT_DONE,
                content="",
                metadata={
                    "session_id": self.id,
                    "token_usage": self.agent.llm.token_usage.to_dict(),
                    "tasks_done": self.task_queue.done_count,
                },
            )
            yield ev_done
            self._dispatch_event(ev_done)
            self._checkpoint()
        except GeneratorExit:
            self.state = SessionState.IDLE
            self._checkpoint()
            raise
        except Exception as e:
            logger.error("Session resume 异常: %s", e, exc_info=True)
            self.state = SessionState.ABORTED
            yield AgentEvent(type="error", content=f"恢复会话异常: {e}")
            self._checkpoint()
