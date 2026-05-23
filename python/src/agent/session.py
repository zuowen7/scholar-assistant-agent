"""AgentSession — 一次完整任务的会话对象（状态机核心）。

提供可暂停、可恢复、多任务编排的会话管理。

关键设计：
- drive() 是对外的事件流 AsyncGenerator
- 每个 Task 独立运行 ReAct 循环（调用 AgentLoop.step()）
- 实例级状态隔离：两个 AgentSession 互不污染
- 审批等待通过 asyncio.Future 实现
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable

import hashlib

from src.agent.agent import AgentLoop, GLOBAL_MAX_STEPS, TASK_MAX_STEPS, _TOOL_RESULT_MAX_CHARS
from src.agent.error_classifier import classify_error, ErrorType
from src.agent.change_journal import ChangeJournal
from src.agent.hooks import HookContext, HookPoint
from src.agent.models import (
    AgentEvent,
    EVT_ABORTED,
    EVT_APPROVAL_RECEIVED,
    EVT_AWAIT_APPROVAL,
    EVT_DONE,
    EVT_ERROR,
    EVT_RESPONSE,
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
from src.agent.workspace import WorkspaceEnv, workspace_escape_allowed

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
        self.security_gate = SecurityGate(workspace_root=str(workspace.root) if workspace else "")

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

        self.agent.trajectory_recorder.start(query, model=self.agent.model)

        ev_start = AgentEvent(
            type=EVT_SESSION_STARTED,
            content="",
            metadata={"session_id": self.id},
        )
        yield ev_start
        self._dispatch_event(ev_start)

        # 构建初始消息
        self.messages = self.agent._build_messages(query, history)

        # Task decomposition: split complex queries into sub-tasks
        sub_tasks = self._decompose_query(query)
        if sub_tasks and len(sub_tasks) > 1:
            for st in sub_tasks:
                self.task_queue.add(st)
            logger.info("任务分解: %d 个子任务", len(sub_tasks))
        else:
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
                    self.agent._finalize_trajectory(self._query, "", success=False)
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
                nudge = self._skill_nudge(task_title=task.title)
                if nudge:
                    yield AgentEvent(type=EVT_WARNING, content=nudge)

            self.state = SessionState.DONE
            self.agent._finalize_trajectory(self._query, "", success=True)
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
            self.agent._finalize_trajectory(self._query, "", success=False)

    async def _drive_task(self, task) -> AsyncGenerator[AgentEvent, None]:
        """驱动单个任务的 ReAct 循环。

        工具调用前经 SecurityGate 门控 — BANNED 直接拒绝，
        MODERATE/DESTRUCTIVE 触发 await_approval → Future 等待用户决定后再执行。
        """
        task_step = 0
        self.consecutive_errors = 0
        _recent_fingerprints: list[str] = []  # (tool_name, args_hash) 用于精确循环检测
        _loop_hint = ""

        while (
            task_step < self.config.max_task_steps
            and self.global_step < self.config.max_global_steps
            and self.state != SessionState.ABORTED
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
                execute_tools=False,  # 先门控，后执行
            )

            if self.state == SessionState.ABORTED:
                raise SessionAborted()

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
                # 区分错误类型：API 限流/超时不计入 consecutive_errors，工具/格式错误才计
                _err_type = classify_error(Exception(step_result.error))
                _is_transient = _err_type in (
                    ErrorType.RATE_LIMIT, ErrorType.OVERLOADED,
                    ErrorType.SERVER_ERROR, ErrorType.TIMEOUT,
                )
                if not _is_transient:
                    self.consecutive_errors += 1
                if self.consecutive_errors >= 5:
                    continue
                yield AgentEvent(
                    type=EVT_ERROR if self.consecutive_errors >= 3 else EVT_WARNING,
                    content=step_result.error,
                )
                continue

            self.consecutive_errors = 0

            # 工具循环检测：基于 (tool_name, args_hash) 精确匹配，连续 ≥2 次完全相同则提示
            if step_result.tool_calls:
                import json as _json
                for tc in step_result.tool_calls:
                    _args_hash = hashlib.md5(
                        _json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False).encode()
                    ).hexdigest()[:8]
                    _recent_fingerprints.append(f"{tc.name}:{_args_hash}")
                if len(_recent_fingerprints) >= 2:
                    last2 = _recent_fingerprints[-2:]
                    if last2[0] == last2[1]:
                        _loop_hint = (
                            f"[系统提示] 你已连续 2 次以完全相同的参数调用 {step_result.tool_calls[0].name}，"
                            "结果不会改变。请基于已有信息直接给出最终回答，不要再重复调用。"
                        )
                        _recent_fingerprints.clear()
                elif len(_recent_fingerprints) >= 3:
                    # 退化检测：仅工具名相同（参数不同）连续 3 次也提示
                    last3_names = [fp.split(":")[0] for fp in _recent_fingerprints[-3:]]
                    if len(set(last3_names)) == 1:
                        _loop_hint = (
                            f"[系统提示] 你已连续 3 次调用 {last3_names[0]}，"
                            "请考虑换一种方式或直接给出最终回答。"
                        )
                        _recent_fingerprints.clear()

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
                    yield AgentEvent(
                        type=EVT_RESPONSE,
                        content=step_result.final_answer or "",
                        metadata={"task_id": task.id},
                    )
                    return
                continue

            # ── SecurityGate + 审批执行 ──
            # 先对每个工具做门控分类
            gated: list[tuple[Any, Any]] = []  # (ToolCall, gate_result)
            for tc in step_result.tool_calls:
                gated.append((tc, self.security_gate.classify(tc.name, tc.arguments)))

            # 分离：可立即执行的 vs 需要审批的 vs banned
            auto_exec: list[tuple[Any, Any]] = []
            needs_approval_list: list[tuple[Any, Any]] = []
            for tc, gate in gated:
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
                if gate.force_approval or (
                    not self.config.auto_approve
                    and gate.needs_approval
                    and "*" not in self.approved_categories
                ):
                    needs_approval_list.append((tc, gate))
                else:
                    auto_exec.append((tc, gate))

            # 可立即执行的工具 → 并行
            if auto_exec:
                if len(auto_exec) > 1:
                    results = await asyncio.gather(*[
                        self.agent._execute_single_tool(tc, self._query)
                        for tc, _ in auto_exec
                    ])
                    for (tc, _), result in zip(auto_exec, results):
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
                else:
                    tc, _ = auto_exec[0]
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
                if self.state == SessionState.ABORTED:
                    raise SessionAborted()

            # 需要审批的工具 → 串行（避免审批顺序错乱）
            for tc, gate in needs_approval_list:
                evt_id = f"evt_{uuid.uuid4().hex[:8]}"
                approval_evt = AgentEvent(
                    type=EVT_AWAIT_APPROVAL,
                    content=f"Agent 想要执行 '{tc.name}'",
                    event_id=evt_id,
                    metadata={
                        "tool_name": tc.name,
                        "args": tc.arguments,
                        "risk": gate.risk.name.lower(),
                        "reason": gate.reason,
                    },
                )
                self._dispatch_event(approval_evt)
                yield approval_evt

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

                # allow_once (or allow_session) → 执行
                # For workspace-escape approvals, temporarily allow out-of-workspace path resolution.
                _escape_token = workspace_escape_allowed.set(True) if gate.force_approval else None
                try:
                    result = await self.agent._execute_single_tool(tc, self._query)
                finally:
                    if _escape_token is not None:
                        workspace_escape_allowed.reset(_escape_token)
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
                if self.state == SessionState.ABORTED:
                    raise SessionAborted()

            # 循环检测提示：在所有 tool result 之后注入，不破坏消息序列
            if _loop_hint:
                self.messages.append(Message(role="user", content=_loop_hint))
                _loop_hint = ""

        # 步数耗尽 — 强制生成最终总结
        if task_step >= self.config.max_task_steps:
            yield AgentEvent(
                type=EVT_WARNING,
                content=f"任务步数达到上限 ({self.config.max_task_steps})，正在生成总结...",
                metadata={"code": "TASK_STEP_LIMIT"},
            )
            try:
                # 追加一条提示消息，引导 LLM 生成总结
                self.messages.append(Message(
                    role="user",
                    content="[系统提示] 已达到最大推理步数。请基于已收集的信息，直接给出最终回答，不要再调用任何工具。",
                ))
                final_step = await self.agent.step(
                    self.messages,
                    step_num=self.global_step + 1,
                    max_steps=self.global_step + 1,
                    execute_tools=False,
                )
                final_answer = ""
                for ev in final_step.events:
                    if ev.type == "response":
                        final_answer = ev.content
                        break
                if final_answer:
                    if self.agent.memory:
                        try:
                            self.agent.memory.add_memory(
                                content=f"Q: {self._query}\nA: {final_answer[:2000]}",
                                category="conversation",
                                source="session",
                                importance=0.5,
                            )
                        except Exception:
                            pass
                    yield AgentEvent(
                        type=EVT_RESPONSE,
                        content=final_answer,
                        metadata={"task_id": task.id},
                    )
            except Exception as e:
                logger.warning("步数耗尽后生成总结失败: %s", e)

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

    def _skill_nudge(self, task_title: str = "", success: bool = True,
                     tools_used: list[str] | None = None,
                     error_type: str | None = None) -> str | None:
        """Check if skill system wants to nudge the agent, and record task patterns.

        Returns:
            Nudge message or None.
        """
        skills = getattr(self.agent, "skills", None)
        if skills is None:
            return None
        try:
            # Record task pattern for auto-skill generation (
            if self._query:
                skills.record_pattern(
                    query=self._query,
                    task_title=task_title,
                    success=success,
                    tools_used=tools_used,
                    error_type=error_type,
                )
            return skills.nudge_check()
        except Exception:
            return None

    @staticmethod
    def _decompose_query(query: str) -> list[str] | None:
        """Lightweight rule-based task decomposition.

        Splits queries that explicitly enumerate multiple steps into separate
        sub-tasks.  Returns None (single-task) when no decomposition is needed.
        """
        import re as _re

        # Pattern 1: numbered list "1. xxx  2. xxx" or "第一步xxx 第二步xxx"
        # Split on the markers, keeping what follows
        parts = _re.split(r"\s*(?:\d+[.)、]|第[一二三四五六七八九十]+步[：:]?)\s*", query)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
        if len(parts) >= 2:
            return parts

        # Pattern 2: Chinese semicolon or semicolon-separated distinct tasks
        if "；" in query or "; " in query:
            parts = _re.split(r"[；;]\s*", query)
            parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
            if len(parts) >= 2:
                return parts

        # Pattern 3: explicit connector words indicating sequential tasks
        connectors = ["然后", "接着", "之后", "再", "最后"]
        parts = [query]
        for conn in connectors:
            new_parts: list[str] = []
            for p in parts:
                sub = p.split(conn, 1)
                new_parts.extend(sub)
            parts = new_parts
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]
        if len(parts) >= 3:
            return parts

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

                nudge = self._skill_nudge(task_title=task.title)
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
