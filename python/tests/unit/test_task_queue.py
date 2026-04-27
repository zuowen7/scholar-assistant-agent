"""TaskQueue 单元测试 — 任务队列 CRUD 和状态转换。"""

import pytest

from src.agent.task_queue import Task, TaskQueue, TaskStatus


class TestTask:
    def test_auto_id(self):
        t = Task(title="test")
        assert t.id.startswith("t_")
        assert t.status == TaskStatus.PENDING

    def test_explicit_id(self):
        t = Task(id="custom_1", title="test")
        assert t.id == "custom_1"


class TestTaskQueue:
    def test_add_and_next(self):
        q = TaskQueue()
        q.add("step 1")
        q.add("step 2")

        t1 = q.next()
        assert t1 is not None
        assert t1.title == "step 1"
        assert t1.status == TaskStatus.RUNNING
        assert q.has_pending() is True

        t2 = q.next()
        assert t2 is not None
        assert t2.title == "step 2"
        assert q.has_pending() is False

    def test_next_returns_none_when_empty(self):
        q = TaskQueue()
        assert q.next() is None

    def test_mark_done(self):
        q = TaskQueue()
        t = q.add("task")
        q.next()
        assert q.mark_done(t.id) is True
        assert t.status == TaskStatus.DONE
        assert q.done_count == 1

    def test_mark_done_nonexistent(self):
        q = TaskQueue()
        assert q.mark_done("nope") is False

    def test_mark_blocked(self):
        q = TaskQueue()
        t = q.add("task")
        q.next()
        q.mark_blocked(t.id)
        assert t.status == TaskStatus.BLOCKED

    def test_has_running(self):
        q = TaskQueue()
        q.add("task")
        assert q.has_running() is False
        q.next()
        assert q.has_running() is True

    def test_add_many(self):
        q = TaskQueue()
        tasks = q.add_many(["a", "b", "c"])
        assert len(tasks) == 3
        assert q.total_count == 3

    def test_done_count(self):
        q = TaskQueue()
        q.add_many(["a", "b", "c"])
        t1 = q.next()
        q.mark_done(t1.id)
        assert q.done_count == 1
        assert q.total_count == 3

    def test_clear(self):
        q = TaskQueue()
        q.add_many(["a", "b"])
        q.clear()
        assert q.total_count == 0
        assert q.has_pending() is False

    def test_all_tasks_copy(self):
        q = TaskQueue()
        q.add("task")
        tasks = q.all_tasks
        assert len(tasks) == 1
        # mutating copy doesn't affect queue
        tasks.clear()
        assert q.total_count == 1
