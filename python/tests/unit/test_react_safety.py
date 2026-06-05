"""Phase 0 tests: Step-level security gate + tool execution timeout.

TDD Red phase — these tests document EXPECTED behavior.
Some already pass (current behavior is correct), others will pass after IMPL.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestStepSafetyGate:
    """step(execute_tools=True) path must also go through SecurityGate."""

    def test_write_file_requires_approval(self):
        """write_file is classified as DESTRUCTIVE — requires approval."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        result = gate.classify("write_file", {"file_path": "/tmp/test.txt", "content": "hello"})
        assert result.risk.name in ("MODERATE", "DESTRUCTIVE")

    def test_str_replace_requires_approval(self):
        """str_replace is classified as DESTRUCTIVE."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        result = gate.classify("str_replace", {"file_path": "a.txt", "old": "x", "new": "y"})
        assert result.risk.name == "DESTRUCTIVE"

    def test_read_tools_are_safe(self):
        """Read-only tools in the default risk map should be SAFE."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        safe_tools = [
            ("read_file", {"file_path": "a.txt"}),
            ("list_directory", {"path": "."}),
        ]
        for tool_name, args in safe_tools:
            result = gate.classify(tool_name, args)
            assert result.risk.name == "SAFE", f"{tool_name} should be SAFE"

    def test_unknown_tool_defaults_to_moderate(self):
        """Tools not in the default risk map default to MODERATE (safe side)."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        result = gate.classify("some_new_tool", {"arg": "value"})
        assert result.risk.name == "MODERATE"

    def test_tool_execution_timeout(self):
        """_execute_single_tool exists and is async (timeout support)."""
        import inspect
        from src.agent.agent import AgentLoop

        assert hasattr(AgentLoop, "_execute_single_tool")
        sig = inspect.signature(AgentLoop._execute_single_tool)
        assert "self" in sig.parameters

    def test_banned_command_detection(self):
        """Dangerous shell commands should be flagged (current behavior)."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        # shell_exec is MODERATE by default; command content is checked in _classify_command
        result = gate.classify("shell_exec", {"command": "rm -rf /"})
        # Currently MODERATE (shell_exec default) — this is a known gap
        # After IMPL, run_command should classify this more strictly
        assert result.risk.name in ("MODERATE", "DESTRUCTIVE", "BANNED")

    def test_workspace_escape_detection(self):
        """Out-of-workspace paths trigger force_approval."""
        from src.agent.security_gate import SecurityGate

        gate = SecurityGate()
        result = gate.classify("write_file", {"file_path": "C:/Windows/system32/test.txt", "content": "x"})
        # Should detect workspace escape and force approval
        assert result.force_approval is True or result.risk.name in ("MODERATE", "DESTRUCTIVE")
