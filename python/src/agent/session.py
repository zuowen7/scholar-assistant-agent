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

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from src.agent.agent import AgentLoop, GLOBAL_MAX_STEPS, TASK_MAX_STEPS
from src.agent.change_journal import ChangeJournal
from src.agent.hooks import HookContext, HookPoint
from src.agent.models import (
    AgentEvent,
    EVT_ABORTED,
    EVT_APPROVAL_RECEIVED,
    EVT_AWAIT_APPROVAL,
    EVT_DONE,
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

        self.pending_approvals: dict[str, Any] = {}
        self.approved_categories: set[str] = set()
        self.consecutive_errors = 0
        self.security_gate = SecurityGate()

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
        self.state = SessionState.INITIALIZING
        yield AgentEvent(
            type=EVT_SESSION_STARTED,
            content="",
            metadata={"session_id": self.id},
        )

        # 构建初始消息
        self.messages = self.agent._build_messages(query, history)

        # Plan-and-Execute
        self.state = SessionState.PLANNING
        plan = await self.agent._generate_plan(query, self.messages)
        if plan:
            yield AgentEvent(type=EVT_THOUGHT, content=f"执行计划:\n{plan}")
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
                except SessionAborted:
                    self.state = SessionState.ABORTED
                    yield AgentEvent(
                        type=EVT_ABORTED,
                        content="",
                        metadata={"session_id": self.id},
                    )
                    return

                self.task_queue.mark_done(task.id)

                yield AgentEvent(
                    type=EVT_TASK_DONE,
                    content="",
                    metadata={"task_id": task.id, "status": "ok"},
                )

            self.state = SessionState.DONE
            yield AgentEvent(
                type=EVT_DONE,
                content="",
                metadata={
                    "session_id": self.id,
                    "token_usage": self.agent.llm.token_usage.to_dict(),
                    "tasks_done": self.task_queue.done_count,
                },
            )
        except GeneratorExit:
            raise
        except Exception as e:
            logger.error("Session drive 异常: %s", e, exc_info=True)
            self.state = SessionState.ABORTED
            yield AgentEvent(type="error", content=f"会话异常: {e}")

    async def _drive_task(self, task) -> AsyncGenerator[AgentEvent, None]:
        """驱动单个任务的 ReAct 循环。"""
        task_step = 0
        self.consecutive_errors = 0

        while (
            task_step < self.config.max_task_steps
            and self.global_step < self.config.max_global_steps
        ):
            task_step += 1
            self.global_step += 1

            # 全局熔断检查
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
            )

            # 转发事件
            for ev in step_result.events:
                # 为 tool_call 事件附加 event_id 用于审批关联
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

            # SecurityGate: 对 tool_calls 做风险判定和审批拦截
            if step_result.tool_calls and not self.config.auto_approve:
                await self._classify_and_gate(step_result)

            if step_result.is_final:
                if step_result.final_answer and self.agent.memory:
                    try:
                        self.agent.memory.add_memory(
                            content=f"Q: {self.messages[-1].content if self.messages else ''}\nA: {step_result.final_answer[:2000]}",
                            category="conversation",
                            source="session",
                            importance=0.5,
                        )
                    except Exception as e:
                        logger.warning("记忆存储失败（不影响推理）: %s", e)
                return

        # 步数耗尽
        if task_step >= self.config.max_task_steps:
            yield AgentEvent(
                type=EVT_WARNING,
                content=f"任务步数达到上限 ({self.config.max_task_steps})",
                metadata={"code": "TASK_STEP_LIMIT"},
            )

    async def _classify_and_gate(self, step_result) -> None:
        """对 step_result 中的 tool_calls 做 SecurityGate 风险判定。

        对 BANNED 调用直接注入拒绝结果到 messages；
        对 MODERATE/DESTRUCTIVE 调用触发 await_approval 等待用户决定。
        此方法修改 messages，由 _drive_task 下一轮继续处理。
        """
        for tc in step_result.tool_calls:
            gate = self.security_gate.classify(tc.name, tc.arguments)

            if gate.is_banned:
                # 直接拒绝，不执行也不询问
                error_msg = f"Tool '{tc.name}' blocked: {gate.reason}"
                self.messages.append(Message(
                    role="tool",
                    content=error_msg,
                    tool_call_id=tc.id,
                ))
                logger.warning("SecurityGate banned: %s %s → %s", tc.name, tc.arguments, gate.reason)

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
