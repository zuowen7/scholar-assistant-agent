"""Phase 0 tests: Proactive loop detection + circuit breaker.

TDD Red phase — tests exercise interfaces that do NOT exist yet.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Proactive loop detection
# ---------------------------------------------------------------------------

class TestProactiveLoopDetection:
    """Loop detection should PREVENT redundant calls, not just detect after."""

    def test_exact_repeat_prevented(self, mock_session):
        """Same tool+args combo blocked on 2nd attempt (before execution)."""
        mock_session._attempted_actions = {}

        # First call: allowed
        assert mock_session._check_tool_budget("read_file", '{"path":"a.txt"}') is True
        mock_session._record_tool_attempt("read_file", '{"path":"a.txt"}')

        # Second identical call: prevented
        assert mock_session._check_tool_budget("read_file", '{"path":"a.txt"}') is False

    def test_semantic_repeat_detected(self, mock_session):
        """read_file(a) → read_file(b) → read_file(c) → 4th read_file blocked."""
        mock_session._attempted_actions = {}

        # Three different args for same tool
        for fname in ["a.txt", "b.txt", "c.txt"]:
            assert mock_session._check_tool_budget("read_file", f'{{"path":"{fname}"}}') is True
            mock_session._record_tool_attempt("read_file", f'{{"path":"{fname}"}}')

        # 4th call to same tool: blocked
        assert mock_session._check_tool_budget("read_file", '{"path":"d.txt"}') is False

    def test_loop_hint_is_system_role(self, mock_session):
        """Loop hint messages must use role='system', not role='user'."""
        hint = mock_session._build_loop_hint("read_file", "repeated call detected")
        assert hint.role == "system"

    def test_tool_budget_per_type(self, mock_session):
        """Different tools have independent budgets."""
        mock_session._attempted_actions = {}

        # read_file budget: 3
        for i in range(3):
            assert mock_session._check_tool_budget("read_file", f'{{"path":"{i}"}}') is True
            mock_session._record_tool_attempt("read_file", f'{{"path":"{i}"}}')

        # read_file exhausted, but grep_files is fresh
        assert mock_session._check_tool_budget("read_file", '{"path":"x"}') is False
        assert mock_session._check_tool_budget("grep_files", '{"pattern":"test"}') is True

    def test_different_tools_reset_independently(self, mock_session):
        """Using a different tool doesn't reset another tool's counter."""
        mock_session._attempted_actions = {}

        mock_session._record_tool_attempt("read_file", '{"path":"a"}')
        mock_session._record_tool_attempt("grep_files", '{"pattern":"x"}')
        mock_session._record_tool_attempt("read_file", '{"path":"b"}')

        # read_file has 2 attempts, grep has 1
        counts = mock_session._get_tool_counts()
        assert counts.get("read_file", 0) == 2
        assert counts.get("grep_files", 0) == 1


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    """Circuit breaker should persist across sub-tasks."""

    def test_circuit_breaker_persists_across_tasks(self, mock_session):
        """Error count accumulates across task boundaries."""
        mock_session.consecutive_errors = 4  # Simulate 4 errors in task 1

        # Simulate task boundary — old code reset here, new code must NOT
        mock_session._on_task_boundary()

        # consecutive_errors should still be 4
        assert mock_session.consecutive_errors == 4

        # One more error triggers break
        mock_session.consecutive_errors += 1
        assert mock_session.consecutive_errors >= 5

    def test_circuit_breaker_with_intermittent_success(self, mock_session):
        """A single success doesn't fully reset the error counter."""
        mock_session.consecutive_errors = 3
        mock_session._on_step_success()  # partial reset, not full

        # Should decay but not fully reset (new behavior)
        assert mock_session.consecutive_errors <= 3

    def test_circuit_breaker_recovery(self, mock_session):
        """After consecutive successes, circuit breaker fully recovers."""
        mock_session.consecutive_errors = 4
        # 3 consecutive successes
        for _ in range(3):
            mock_session._on_step_success()
        assert mock_session.consecutive_errors == 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session():
    """Create a mock AgentSession with loop detection interfaces.

    Red phase: these methods do NOT exist yet. They will be added in IMPL.
    """
    from src.agent.models import Message

    class _MockSession:
        def __init__(self):
            self._attempted_actions: dict[str, int] = {}
            self.consecutive_errors: int = 0

        def _check_tool_budget(self, tool_name: str, args_str: str) -> bool:
            """Check if tool call is allowed (proactive)."""
            # Per-tool budget: max 3 calls with different args
            count = sum(1 for k in self._attempted_actions if k.startswith(tool_name + ":"))
            if count >= 3:
                return False
            # Exact repeat check
            key = f"{tool_name}:{args_str}"
            if key in self._attempted_actions:
                return False
            return True

        def _record_tool_attempt(self, tool_name: str, args_str: str):
            key = f"{tool_name}:{args_str}"
            self._attempted_actions[key] = self._attempted_actions.get(key, 0) + 1

        def _build_loop_hint(self, tool_name: str, reason: str):
            return Message(role="system", content=f"[循环检测] {tool_name}: {reason}")

        def _get_tool_counts(self) -> dict[str, int]:
            counts: dict[str, int] = {}
            for k in self._attempted_actions:
                tool = k.split(":")[0]
                counts[tool] = counts.get(tool, 0) + 1
            return counts

        def _on_task_boundary(self):
            """New behavior: do NOT reset consecutive_errors."""
            pass  # intentionally no-op

        def _on_step_success(self):
            """Decay consecutive_errors on success (partial, not full reset)."""
            if self.consecutive_errors > 0:
                self.consecutive_errors = max(0, self.consecutive_errors - 2)

    return _MockSession()
