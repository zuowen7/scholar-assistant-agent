"""任务队列 — AgentSession 的子任务管理。

TaskQueue 将 Plan-and-Execute 的计划拆解为可追踪的子任务，
每个 Task 独立管理状态（pending → running → done/blocked），
支持顺序执行和状态查询。

设计参考 Claude Code 的 Task 系统：
- AgentSession.drive() 从 TaskQueue 取任务逐个执行
- 每个 Task 内部运行独立的 ReAct 循环
- Task 完成后触发 ON_TASK_COMPLETE hook
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    DONE = auto()
    BLOCKED = auto()


@dataclass
class Task:
    """单个子任务。"""
    id: str = ""
    title: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""

    def __post_init__(self):
        if not self.id:
            object.__setattr__(self, "id", f"t_{uuid.uuid4().hex[:6]}")


class TaskQueue:
    """FIFO 任务队列。"""

    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def add(self, title: str, task_id: str = "") -> Task:
        task = Task(id=task_id, title=title)
        self._tasks.append(task)
        return task

    def add_many(self, titles: list[str]) -> list[Task]:
        return [self.add(t) for t in titles]

    def next(self) -> Task | None:
        for task in self._tasks:
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.RUNNING
                return task
        return None

    def has_pending(self) -> bool:
        return any(t.status == TaskStatus.PENDING for t in self._tasks)

    def has_running(self) -> bool:
        return any(t.status == TaskStatus.RUNNING for t in self._tasks)

    def mark_done(self, task_id: str, result: str = "") -> bool:
        for task in self._tasks:
            if task.id == task_id:
                task.status = TaskStatus.DONE
                task.result = result
                return True
        return False

    def mark_blocked(self, task_id: str) -> bool:
        for task in self._tasks:
            if task.id == task_id:
                task.status = TaskStatus.BLOCKED
                return True
        return False

    @property
    def all_tasks(self) -> list[Task]:
        return list(self._tasks)

    @property
    def done_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == TaskStatus.DONE)

    @property
    def total_count(self) -> int:
        return len(self._tasks)

    def clear(self) -> None:
        self._tasks.clear()
