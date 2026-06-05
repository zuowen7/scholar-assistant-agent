"""Test infrastructure — shared fixtures for all test categories.

Test Categories:
  - Happy path: standard unit tests, one per expected behavior
  - Edge (@pytest.mark.edge): boundary values, malformed input, Unicode, binary
  - Fault (@pytest.mark.fault): DB corruption, network failure, resource exhaustion
  - Stress (@pytest.mark.stress): concurrency, large payloads, rapid cycles
  - Property (@pytest.mark.property): Hypothesis random-input invariants

Bug Fix Protocol:
  Every time a bug is found and fixed, add a test in the appropriate category
  that would have caught it BEFORE the fix was applied. This is non-negotiable.
"""
import pytest
import tempfile
import threading
import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Temp file fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    """Temporary directory that auto-cleans."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def temp_db():
    """In-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Workflow fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workflow_store_fixture(tmp_path):
    """WorkflowStore backed by temp directory."""
    from src.agent.workflow_store import WorkflowStore
    store = WorkflowStore(str(tmp_path / "test.db"))
    yield store
    store.close()


@pytest.fixture
def workflow_session_fixture():
    """Fresh WorkflowSession with one user message."""
    from src.agent.workflow_session import WorkflowSession
    from src.agent.models import Message

    ws = WorkflowSession()
    ws.add_message(Message(role="user", content="test fixture query"))
    return ws


# ---------------------------------------------------------------------------
# Agent fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_no_llm():
    """AgentLoop with no LLM connection (for unit testing internal logic)."""
    from src.agent.agent import AgentLoop
    return AgentLoop(
        ollama_base_url="http://localhost:11434",
        model="test-model",
        tool_registry=None,
    )


# ---------------------------------------------------------------------------
# Debug helper for test output
# ---------------------------------------------------------------------------

def dump_test_state(obj, label: str = "") -> None:
    """Print object state for debugging a failing test."""
    import json
    print(f"\n=== {label} ===")
    if hasattr(obj, "to_dict"):
        print(json.dumps(obj.to_dict(), indent=2, default=str, ensure_ascii=False))
    elif isinstance(obj, dict):
        print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))
    else:
        print(str(obj))
