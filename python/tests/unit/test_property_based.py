"""Property-based testing with Hypothesis — verify invariants for ALL inputs.

These tests use random input generation to find edge cases that human-written
tests miss. Each test defines an INVARIANT that must hold for any valid input.
"""
from __future__ import annotations

import json
import pytest
import pytest
pytestmark = pytest.mark.property
from hypothesis import given, strategies as st, settings, HealthCheck
from pathlib import Path
import tempfile


# ===================================================================
# WorkflowSession invariants
# ===================================================================

class TestWorkflowSessionProperties:
    """Universal properties that must hold for WorkflowSession."""

    @given(st.text(min_size=1, max_size=200))
    def test_title_never_exceeds_50_chars(self, first_message):
        """Property: title is always ≤ 50 characters regardless of input size."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content=first_message))
        assert len(ws.title) <= 50

    @given(st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=50))
    def test_stages_always_in_pipeline_order(self, raw_stages):
        """Property: after advancing, current_stage is always a valid pipeline stage."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.workflow_session import PIPELINE_STAGES

        ws = WorkflowSession()
        valid_stages = [s for s in raw_stages if s in PIPELINE_STAGES]
        for s in valid_stages:
            ws.advance_to(s)

        assert ws.current_stage in PIPELINE_STAGES or ws.current_stage == ""

    @given(
        st.lists(st.sampled_from(["user", "assistant", "system", "tool"]),
                 min_size=1, max_size=20),
    )
    def test_message_count_monotonic(self, roles):
        """Property: messages.length = number of add_message calls."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        count = 0
        for role in roles:
            ws.add_message(Message(role=role, content=f"msg_{count}"))
            count += 1
        assert len(ws.messages) == count

    @given(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.text(min_size=1, max_size=200),
            min_size=1, max_size=30,
        )
    )
    def test_serialize_deserialize_roundtrip(self, random_messages):
        """Property: to_dict → from_dict preserves all message data."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        for role, content in random_messages.items():
            r = "user" if len(role) % 2 == 0 else "assistant"
            ws.add_message(Message(role=r, content=content))

        data = ws.to_dict()
        restored = WorkflowSession.from_dict(data)

        assert restored.id == ws.id
        assert restored.title == ws.title
        assert len(restored.messages) == len(ws.messages)
        for i, msg in enumerate(ws.messages):
            assert restored.messages[i].content == msg.content
            assert restored.messages[i].role == msg.role


# ===================================================================
# Scratchpad invariants
# ===================================================================

class TestScratchpadProperties:
    """Universal properties for scratchpad."""

    @given(st.text(min_size=1, max_size=5000), st.text(min_size=1, max_size=50))
    def test_write_then_read_identity(self, value, key):
        """Property: scratchpad_read(scratchpad_store(k, v)) == v."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        agent._scratchpad_store(key, value)
        assert agent.scratchpad_read(key) == value

    @given(
        st.lists(st.tuples(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=500)),
                 min_size=1, max_size=50, unique_by=(lambda x: x[0],))
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_scratchpad_never_exceeds_max(self, key_values):
        """Property: scratchpad size never exceeds max_entries."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        for key, value in key_values:
            agent._scratchpad_store(key, value)

        assert len(agent._scratchpad) <= agent._SCRATCHPAD_MAX_ENTRIES


# ===================================================================
# Socratic invariants
# ===================================================================

class TestSocraticProperties:
    """Universal properties for Socratic mode."""

    @given(st.text(min_size=0, max_size=1000))
    def test_intent_detection_never_crashes(self, message):
        """Property: _has_socratic_intent never raises for any string."""
        from src.agent.socratic_prompt import _has_socratic_intent

        try:
            _has_socratic_intent(message)
        except Exception as e:
            pytest.fail(f"_has_socratic_intent crashed on {message!r}: {e}")

    @given(st.text(min_size=0, max_size=1000))
    def test_stage_detection_never_crashes(self, message):
        """Property: _detect_pipeline_stage never raises for any string."""
        from src.agent.socratic_prompt import _detect_pipeline_stage

        try:
            _detect_pipeline_stage(message)
        except Exception as e:
            pytest.fail(f"_detect_pipeline_stage crashed on {message!r}: {e}")

    @given(st.text(min_size=1, max_size=500))
    def test_stage_detection_output_is_valid(self, message):
        """Property: _detect_pipeline_stage returns None or a valid stage."""
        from src.agent.socratic_prompt import _detect_pipeline_stage
        from src.agent.workflow_session import PIPELINE_STAGES

        result = _detect_pipeline_stage(message)
        assert result is None or result in PIPELINE_STAGES


# ===================================================================
# Integrity tool invariants
# ===================================================================

class TestIntegrityProperties:
    """Universal properties for integrity checking."""

    @given(st.text(min_size=0, max_size=10000))
    def test_check_integrity_never_crashes(self, text):
        """Property: check_integrity never crashes on any text input."""
        from src.agent.tools.integrity_tools import check_integrity

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = f.name

        try:
            result = check_integrity(file_path=path)
            parsed = json.loads(result)
            assert isinstance(parsed, dict)
            assert "issues" in parsed or "error" in parsed
        finally:
            Path(path).unlink(missing_ok=True)

    @given(
        st.floats(min_value=-10, max_value=10),
        st.booleans(),
    )
    def test_p_value_never_false_positives_on_valid(self, p_val, include_n):
        """Property: p values in [0,1] are never flagged as impossible."""
        from src.agent.tools.integrity_tools import check_integrity

        if 0 <= p_val <= 1:
            n_clause = ", n=100" if include_n else ""
            text = f"Results show significant improvement (p = {p_val}{n_clause})."

            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                f.write(text)
                path = f.name

            try:
                result = json.loads(check_integrity(file_path=path))
                impossible = [i for i in result.get("issues", [])
                              if i["type"] == "impossible_p_value"]
                assert len(impossible) == 0, f"Flagged p={p_val} as impossible!"
            finally:
                Path(path).unlink(missing_ok=True)


# ===================================================================
# Plan result invariants
# ===================================================================

class TestPlanResultProperties:
    """Universal properties for _parse_plan_result."""

    @given(st.text(min_size=0, max_size=5000))
    def test_parse_plan_never_crashes(self, raw_text):
        """Property: _parse_plan_result never raises on any string."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        try:
            result = agent._parse_plan_result(raw_text)
            assert result.needs_tools in (True, False)
            assert isinstance(result.plan_text, str)
            assert isinstance(result.estimated_tools, list)
        except Exception as e:
            pytest.fail(f"_parse_plan_result crashed on {raw_text!r}: {e}")

    @given(
        st.booleans(),
        st.text(max_size=200),
        st.lists(st.text(min_size=1, max_size=30), max_size=10),
    )
    def test_parse_plan_result_must_be_valid_json_even_with_whitespace(self, needs, plan, tools):
        """Property: Valid JSON wrapped in whitespace parses correctly."""
        from src.agent.agent import AgentLoop

        agent = AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test",
            tool_registry=None,
        )
        import json as _json
        valid_json = _json.dumps(
            {"needs_tools": needs, "plan": plan, "tools": tools},
            ensure_ascii=False,
        )
        # Wrap in whitespace and markdown artifacts
        wrapped = f"  \n  {valid_json}  \n  "
        result = agent._parse_plan_result(wrapped)
        assert result.needs_tools == needs
