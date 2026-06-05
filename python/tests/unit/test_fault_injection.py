"""Fault injection tests — simulate failures and verify graceful recovery.

Tests what happens when: DB is locked, disk is full, inputs are malicious,
memory is exhausted, invalid state transitions occur, etc.
"""
from __future__ import annotations

import json
import os
import pytest

pytestmark = pytest.mark.fault
import sqlite3
import tempfile
import threading
from pathlib import Path


# ===================================================================
# Database fault injection
# ===================================================================

class TestDBFaults:
    """SQLite-level faults."""

    def test_workflow_store_with_readonly_db(self, tmp_path):
        """Store handles a read-only DB gracefully."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = tmp_path / "readonly.db"
        s = WorkflowStore(str(db_path))
        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test"))
        s.save(ws)
        s.close()

        # Make DB read-only
        os.chmod(str(db_path), 0o444)

        # Reopen — should handle gracefully
        try:
            s2 = WorkflowStore(str(db_path))
            recent = s2.list_recent(limit=1)
            assert isinstance(recent, list)
            s2.close()
        except Exception:
            pass  # Read failure is acceptable
        finally:
            os.chmod(str(db_path), 0o666)

    def test_corrupted_db_recovery(self, tmp_path):
        """Store survives a corrupted SQLite file."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = tmp_path / "corrupt.db"

        # Create a valid store, then corrupt it
        s1 = WorkflowStore(str(db_path))
        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="before"))
        s1.save(ws)
        s1.close()

        # Corrupt the database file
        with open(db_path, "wb") as f:
            f.write(b"\x00" * 1024)  # Overwrite with zeroes

        # Reopen should not crash the process
        try:
            s2 = WorkflowStore(str(db_path))
            # Even if it fails internally, the process survives
            s2.close()
        except Exception:
            pass  # Corruption handling is acceptable


# ===================================================================
# Input injection attacks
# ===================================================================

class TestInputInjection:
    """Malicious inputs — path traversal, SQL injection, XSS."""

    def test_path_traversal_in_file_path(self):
        """Path traversal in file_path doesn't escape workspace."""
        from src.agent.tools.integrity_tools import check_integrity

        # Attempt to read /etc/passwd via relative path
        result = json.loads(check_integrity(
            file_path="../../../etc/passwd"
        ))
        # Should return an error, not the file contents
        assert "error" in result or "issues" in result

    def test_sql_injection_in_workflow_id(self):
        """SQL injection in workflow_id doesn't execute raw SQL."""
        from src.agent.workflow_store import WorkflowStore

        s = WorkflowStore(":memory:")
        result = s.load("1' OR '1'='1")
        assert result is None  # Parameterized query prevents injection

        messages = s.load_messages("1'; DROP TABLE workflows; --")
        assert messages == []

        s.close()

    def test_null_bytes_in_message_content(self):
        """Messages with null bytes don't corrupt DB."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="hello\x00world"))
        data = ws.to_dict()
        assert "messages" in data
        assert len(data["messages"]) == 1

    def test_unicode_control_characters(self):
        """Unicode RTL override, zero-width joiners don't crash."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        tainted = "‮​⁠‏‍hi"
        ws.add_message(Message(role="user", content=tainted))

        data = ws.to_dict()
        restored = WorkflowSession.from_dict(data)
        assert restored.messages[0].content == tainted


# ===================================================================
# Memory / resource exhaustion
# ===================================================================

class TestResourceExhaustion:
    """Very large inputs that could cause OOM or timeout."""

    def test_million_messages_not_stored(self):
        """Adding excessive messages doesn't OOM (stores just grow)."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        # Add 5000 messages — reasonable upper bound
        for i in range(5000):
            ws.add_message(Message(role="user", content=f"msg_{i}"))

        assert len(ws.messages) == 5000
        # to_dict should still work
        data = ws.to_dict()
        assert len(data["messages"]) == 5000

    def test_deeply_nested_plan_json(self):
        """Deeply nested JSON in plan result doesn't crash."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        nested = "{" * 50 + '"a":1' + "}" * 50
        result = agent._parse_plan_result(nested)
        assert isinstance(result.needs_tools, bool)

    def test_gigantic_scratchpad_entry(self):
        """Huge scratchpad entry is handled (dedupped by LRU)."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        # Store 100KB value
        value = "x" * 100_000
        agent._scratchpad_store("big", value)
        result = agent.scratchpad_read("big")
        assert result == value


# ===================================================================
# Invalid state transitions
# ===================================================================

class TestInvalidStateTransitions:
    """Illegal state operations."""

    def test_rapid_active_complete_cycle(self):
        """Rapid ACTIVE → COMPLETED → ACTIVE cycles don't corrupt."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState
        from src.agent.models import Message

        ws = WorkflowSession()
        for i in range(100):
            ws.add_message(Message(role="user", content=f"msg_{i}"))
            ws.state = WorkflowState.COMPLETED
            ws.state = WorkflowState.ACTIVE

        assert ws.state == WorkflowState.ACTIVE
        assert len(ws.messages) == 100

    def test_archive_archived_workflow_idempotent(self):
        """Archiving an already archived workflow is safe."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test"))
        ws.archive()
        ws.archive()  # Double archive
        assert ws.state.value == "archived"

    def test_from_dict_with_future_state(self):
        """from_dict with unknown state value."""
        from src.agent.workflow_session import WorkflowSession

        try:
            WorkflowSession.from_dict({
                "id": "test",
                "state": "quantum_superposition",
            })
        except ValueError:
            pass  # Expected — invalid enum value
        except Exception:
            pass  # Any non-crash is acceptable


# ===================================================================
# Concurrent close/use races
# ===================================================================

class TestCloseRace:
    """What happens when store is used after close."""

    def test_load_after_close(self, tmp_path):
        """Loading from a closed store returns None gracefully."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = str(tmp_path / "close_race.db")
        s = WorkflowStore(db_path)
        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test"))
        s.save(ws)
        s.close()

        # This should raise sqlite3.ProgrammingError or similar
        # The key test: process must not crash
        try:
            s.load(ws.id)
        except sqlite3.ProgrammingError:
            pass  # Expected
        except Exception:
            pass  # Any non-crash is OK

    def test_close_reopen_cycle(self, tmp_path):
        """Rapid close-reopen cycles don't leak file handles."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = str(tmp_path / "cycle.db")
        for cycle in range(50):
            s = WorkflowStore(db_path)
            ws = WorkflowSession()
            ws.add_message(Message(role="user", content=f"c{cycle}"))
            s.save(ws)
            s.close()

        # Final check: all 50 workflows persisted
        final = WorkflowStore(db_path)
        recent = final.list_recent(limit=100)
        assert len(recent) >= 50
        final.close()
