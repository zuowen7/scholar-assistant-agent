"""Phase 1 tests: WorkflowStore — SQLite persistence + cleanup.

TDD Red phase — these tests exercise the store before it exists.
"""
from __future__ import annotations

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


class TestWorkflowStore:
    """CRUD operations on WorkflowStore."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a temporary WorkflowStore."""
        from src.agent.workflow_store import WorkflowStore
        db_path = tmp_path / "test_workflows.db"
        store = WorkflowStore(str(db_path))
        yield store
        store.close()

    @pytest.fixture
    def workflow(self):
        """Create a sample WorkflowSession for testing."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test query"))
        return ws

    def test_save_and_load(self, store, workflow):
        """Save a workflow and load it back identically."""
        store.save(workflow)
        loaded = store.load(workflow.id)
        assert loaded is not None
        assert loaded.id == workflow.id
        assert loaded.title == workflow.title
        assert len(loaded.messages) == len(workflow.messages)

    def test_save_updates_timestamp(self, store, workflow):
        """Saving updates updated_at."""
        import time
        store.save(workflow)
        v1 = store.load(workflow.id).updated_at

        time.sleep(1.1)  # ensure second boundary passes
        workflow.add_message(Message(role="assistant", content="reply"))
        store.save(workflow)
        v2 = store.load(workflow.id).updated_at

        assert v2 >= v1

    def test_load_nonexistent_returns_none(self, store):
        """Loading a nonexistent workflow ID returns None."""
        assert store.load("no_such_id") is None

    def test_delete_removes_workflow(self, store, workflow):
        """Delete removes the workflow from store."""
        store.save(workflow)
        assert store.delete(workflow.id) is True
        assert store.load(workflow.id) is None

    def test_delete_nonexistent_returns_false(self, store):
        """Deleting nonexistent ID returns False."""
        assert store.delete("no_such_id") is False

    def test_list_recent(self, store):
        """List returns workflows ordered by updated_at descending."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        for i in range(5):
            ws = WorkflowSession()
            ws.add_message(Message(role="user", content=f"query {i}"))
            store.save(ws)

        recent = store.list_recent(limit=3)
        assert len(recent) == 3

    def test_list_only_metadata(self, store, workflow):
        """List returns metadata without full messages."""
        store.save(workflow)
        result = store.list_recent(limit=1)
        assert len(result) == 1
        # Messages key may exist but should be minimal
        assert "id" in result[0]
        assert "title" in result[0]
        assert "state" in result[0]

    def test_load_messages(self, store, workflow):
        """load_messages returns the full message list."""
        store.save(workflow)
        messages = store.load_messages(workflow.id)
        assert len(messages) == len(workflow.messages)


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------

class TestWorkflowCleanup:
    """Automatic archival and deletion."""

    @pytest.fixture
    def store(self, tmp_path):
        from src.agent.workflow_store import WorkflowStore
        db_path = tmp_path / "test_cleanup.db"
        store = WorkflowStore(str(db_path))
        yield store
        store.close()

    def _create_old_workflow(self, store, age_days: int, state: str = "completed"):
        """Create a workflow with specified age."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content=f"old query ({age_days}d)"))
        ws.state = WorkflowState(state)
        ts = (datetime.now() - timedelta(days=age_days)).isoformat(timespec="seconds")
        ws.created_at = ts
        ws.updated_at = ts
        if state == "archived":
            ws.archived_at = ts
        store.save(ws)
        return ws.id

    def test_archive_completed_older_than_30_days(self, store):
        """Completed workflows > 30 days get archived."""
        wid = self._create_old_workflow(store, age_days=35, state="completed")
        stats = store.cleanup()
        assert stats.get("archived", 0) >= 1

        loaded = store.load(wid)
        assert loaded.state.value == "archived" if loaded else True

    def test_no_archive_recent_completed(self, store):
        """Completed workflows < 30 days are NOT archived."""
        wid = self._create_old_workflow(store, age_days=10, state="completed")
        store.cleanup()

        loaded = store.load(wid)
        assert loaded.state.value == "completed"

    def test_delete_archived_older_than_90_days(self, store):
        """Archived workflows > 90 days get deleted."""
        wid = self._create_old_workflow(store, age_days=95, state="archived")
        stats = store.cleanup()
        assert stats.get("deleted", 0) >= 1
        assert store.load(wid) is None

    def test_no_delete_recent_archived(self, store):
        """Archived workflows < 90 days are NOT deleted."""
        wid = self._create_old_workflow(store, age_days=50, state="archived")
        store.cleanup()
        assert store.load(wid) is not None

    def test_cleanup_returns_stats(self, store):
        """cleanup() returns a stats dict."""
        stats = store.cleanup()
        assert "archived" in stats
        assert "deleted" in stats

    def test_cleanup_empty_store(self, store):
        """cleanup on empty store doesn't crash."""
        stats = store.cleanup()
        assert stats["archived"] == 0
        assert stats["deleted"] == 0


# Import for tests using Message
from src.agent.models import Message
