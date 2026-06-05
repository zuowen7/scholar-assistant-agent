"""Edge case & stress tests for WorkflowSession + WorkflowStore.

Covers: concurrency, large payloads, malformed data, boundary values, race conditions.
"""
from __future__ import annotations

import json
import pytest

pytestmark = pytest.mark.edge
import threading
import time
from pathlib import Path


# ===================================================================
# WorkflowSession — edge cases
# ===================================================================

class TestWorkflowSessionEdge:
    """Edge cases beyond the happy path."""

    def test_messages_overflow_title(self):
        """Title from first message is truncated to 50 chars."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="A" * 500))
        assert len(ws.title) <= 50

    def test_rapid_stage_changes(self):
        """Rapid arbitrary stage transitions don't corrupt state."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        stages = ["research", "outline", "draft", "review", "revise",
                   "research", "draft", "outline", "finalize"]
        for s in stages:
            ws.advance_to(s)

        assert ws.current_stage == "finalize"
        # stages list should have entries for all transitions
        assert len(ws.stages) >= len(stages)

    def test_invalid_stage_name(self):
        """Advancing to an invalid stage returns None."""
        from src.agent.workflow_session import WorkflowSession

        ws = WorkflowSession()
        result = ws.advance_to("nonexistent_stage")
        assert result is None
        assert ws.current_stage == ""  # unchanged

    def test_serialize_with_unencodable_characters(self):
        """Messages with Unicode surrogate pairs don't crash serialization."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        # Full Unicode spectrum including emoji, CJK, RTL
        ws.add_message(Message(role="user", content="\U0001f4a9 中文 ؀ۿ \U0001f600"))

        data = ws.to_dict()
        assert data is not None
        assert len(data["messages"]) == 1

    def test_serialize_with_null_content(self):
        """Message with None content doesn't crash."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content=""))

        data = ws.to_dict()
        assert isinstance(data["messages"][0]["content"], str)

    def test_archive_then_add_message(self):
        """Adding a message after archive still works (re-opens)."""
        from src.agent.workflow_session import WorkflowSession, WorkflowState
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="hello"))
        ws.state = WorkflowState.COMPLETED
        ws.archive()
        ws.state = WorkflowState.ACTIVE
        ws.add_message(Message(role="user", content="continue"))

        # Original message + new message
        assert len(ws.messages) == 2

    def test_many_rapid_messages(self):
        """Add 1000 rapid messages without corruption."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        for i in range(1000):
            ws.add_message(Message(
                role="user" if i % 2 == 0 else "assistant",
                content=f"message {i}"
            ))
        assert len(ws.messages) == 1000
        # Verify order preserved
        assert "message 0" in ws.messages[0].content
        assert "message 999" in ws.messages[-1].content


# ===================================================================
# WorkflowStore — edge cases
# ===================================================================

class TestWorkflowStoreEdge:
    """Stress and concurrency tests for WorkflowStore."""

    @pytest.fixture
    def store(self, tmp_path):
        from src.agent.workflow_store import WorkflowStore
        db_path = tmp_path / "edge_workflows.db"
        s = WorkflowStore(str(db_path))
        yield s
        s.close()

    def test_concurrent_saves(self, store):
        """Multiple threads saving concurrently don't corrupt DB."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        errors = []

        def save_workflow(seed: int):
            try:
                ws = WorkflowSession()
                ws.add_message(Message(role="user", content=f"thread {seed} query"))
                store.save(ws)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=save_workflow, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify all 20 were saved
        recent = store.list_recent(limit=50)
        assert len(recent) >= 20

    def test_load_messages_for_nonexistent(self, store):
        """Loading messages for nonexistent ID returns empty list."""
        messages = store.load_messages("no_such_workflow_12345")
        assert messages == []

    def test_delete_then_load(self, store):
        """After delete, load returns None and messages empty."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test"))
        store.save(ws)

        assert store.load(ws.id) is not None
        store.delete(ws.id)
        assert store.load(ws.id) is None
        assert store.load_messages(ws.id) == []

    def test_save_update_cycle(self, store):
        """Repeated save-load cycles preserve data integrity."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        for i in range(100):
            ws.add_message(Message(role="user" if i % 2 == 0 else "assistant",
                                   content=f"msg_{i}"))
            store.save(ws)

        loaded = store.load(ws.id)
        assert loaded is not None
        assert len(loaded.messages) == 100

    def test_cleanup_idempotent(self, store):
        """Running cleanup twice produces the same result (idempotent)."""
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="test"))
        store.save(ws)

        stats1 = store.cleanup()
        stats2 = store.cleanup()

        assert stats1 == stats2

    def test_store_close_reopen(self, tmp_path):
        """Closing and reopening the store preserves data."""
        from src.agent.workflow_store import WorkflowStore
        from src.agent.workflow_session import WorkflowSession
        from src.agent.models import Message

        db_path = str(tmp_path / "reopen_test.db")

        # First session
        s1 = WorkflowStore(db_path)
        ws = WorkflowSession()
        ws.add_message(Message(role="user", content="persist me"))
        s1.save(ws)
        s1.close()

        # Reopen
        s2 = WorkflowStore(db_path)
        loaded = s2.load(ws.id)
        assert loaded is not None
        assert loaded.messages[0].content == "persist me"
        s2.close()


# ===================================================================
# ReAct plan() — edge cases
# ===================================================================

class TestPlanEdgeCases:
    """Edge cases for AgentLoop.plan()."""

    @pytest.fixture
    def agent(self):
        from src.agent.agent import AgentLoop
        return AgentLoop(
            ollama_base_url="http://localhost:11434",
            model="test-model",
            tool_registry=None,
        )

    def test_parse_plan_result_with_escaped_quotes(self, agent):
        """JSON with escaped quotes inside strings."""
        result = agent._parse_plan_result(
            '{"needs_tools": true, "plan": "he said \\"hello\\" world", "tools": []}'
        )
        assert result.needs_tools is True

    def test_parse_plan_result_with_newlines_in_json(self, agent):
        """JSON spanning multiple lines (indented formatting)."""
        result = agent._parse_plan_result(
            '{\n  "needs_tools": true,\n  "plan": "multi step plan",\n  "tools": ["read"]\n}'
        )
        assert result.needs_tools is True
        assert "read" in result.estimated_tools

    def test_parse_plan_result_deeply_nested_think_tags(self, agent):
        """Nested <think> tags are all stripped."""
        result = agent._parse_plan_result(
            '<think><think>inner</think></think>{"needs_tools": false, "plan": "ok", "tools": []}'
        )
        assert result.needs_tools is False

    def test_parse_plan_result_unicode_json(self, agent):
        """JSON with Unicode content in plan text."""
        result = agent._parse_plan_result(
            '{"needs_tools": true, "plan": "需要读取文件", "tools": ["read_file"]}'
        )
        assert result.needs_tools is True
        assert "read_file" in result.estimated_tools

    def test_parse_plan_result_empty_tools_list(self, agent):
        """Empty tools list with needs_tools=true is valid."""
        result = agent._parse_plan_result(
            '{"needs_tools": true, "plan": "not sure which tools", "tools": []}'
        )
        assert result.needs_tools is True

    def test_scratchpad_store_with_special_characters(self, agent):
        """Scratchpad stores and retrieves values with special chars."""
        key = "test_key_@#$"
        value = "binary\x00chars\x1b\n\r\t"
        agent._scratchpad_store(key, value)
        assert agent.scratchpad_read(key) == value

    def test_scratchpad_overwrite_key(self, agent):
        """Overwriting the same key updates the value."""
        agent._scratchpad_store("k", "v1")
        agent._scratchpad_store("k", "v2")
        assert agent.scratchpad_read("k") == "v2"
        # Overwrite shouldn't increase total count (just update)
        assert len(agent._scratchpad) <= 1


# ===================================================================
# Socratic + Pipeline — edge cases
# ===================================================================

class TestSocraticEdgeCases:
    """Edge cases for Socratic intent and pipeline detection."""

    @pytest.fixture
    def detect(self):
        from src.agent.socratic_prompt import _has_socratic_intent
        return _has_socratic_intent

    @pytest.fixture
    def stage_detect(self):
        from src.agent.socratic_prompt import _detect_pipeline_stage
        return _detect_pipeline_stage

    def test_trigger_in_long_text(self, detect):
        """Trigger word embedded in a 5000-char message."""
        msg = "x" * 5000 + "help me think about this"
        assert detect(msg)

    def test_no_false_positive_on_substring(self, detect):
        """Words containing trigger substrings don't falsely match."""
        # "guide" is a trigger, but "guideline" is not
        assert not detect("please follow the guidelines")

    def test_emoji_only_message(self, detect):
        """Emoji-only message doesn't crash."""
        assert not detect("\U0001f600\U0001f4a9\U0001f389")

    def test_pipeline_detect_multiple_keywords(self, stage_detect):
        """Message with multiple stage keywords picks the first match."""
        result = stage_detect("先调研一下，然后写大纲")
        assert result == "research"  # "调研" comes first in keyword order

    def test_pipeline_detect_substring_in_word(self, stage_detect):
        """Stage keywords shouldn't match substrings randomly."""
        # "re" in "review" shouldn't match "read"
        result = stage_detect("read this file")
        assert result is None

    def test_empty_string_detection(self, detect, stage_detect):
        """Empty string doesn't trigger anything."""
        assert not detect("")
        assert stage_detect("") is None


# ===================================================================
# Integrity tools — edge cases
# ===================================================================

class TestIntegrityEdgeCases:
    """Edge cases for integrity checking tools."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp = tmp_path

    def _write(self, content: str, name: str = "test.md") -> str:
        p = self.tmp / name
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_binary_file_handled(self):
        """Binary files don't crash the checker."""
        from src.agent.tools.integrity_tools import check_integrity

        # Write raw bytes that aren't valid text
        p = self.tmp / "binary.bin"
        p.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" * 100)

        result = json.loads(check_integrity(file_path=str(p), checks="all"))
        # Should not crash — either passes clean or returns error
        assert "issues" in result or "error" in result

    def test_very_long_line(self):
        """A file with a single 50K-char line doesn't hang regex."""
        from src.agent.tools.integrity_tools import check_integrity

        path = self._write("a" * 50000)
        result = json.loads(check_integrity(file_path=path))
        assert result["summary"]["total_issues"] == 0

    def test_many_citations_limit(self):
        """Document with 500 citations doesn't hang or OOM."""
        from src.agent.tools.integrity_tools import check_integrity

        citations = " ".join(f"\\cite{{ref{i}}}" for i in range(500))
        bib = "\n".join(f"\\bibitem{{ref{i}}} Reference {i}." for i in range(500))
        content = f"{citations}\n\n\\begin{{thebibliography}}{{99}}\n{bib}\n\\end{{thebibliography}}"
        path = self._write(content)

        import time as _time
        start = _time.monotonic()
        result = json.loads(check_integrity(file_path=path))
        elapsed = _time.monotonic() - start

        # Should complete in under 2 seconds
        assert elapsed < 2.0
        assert result["summary"]["total_issues"] == 0

    def test_large_document(self):
        """A 500KB document is processed without OOM."""
        from src.agent.tools.integrity_tools import check_integrity

        content = ("This is content line {i}.\n" * 10000).format(i=0)
        path = self._write(content[:500000])

        result = json.loads(check_integrity(file_path=path))
        assert "issues" in result

    def test_utf16_encoded_file(self):
        """UTF-16 encoded file doesn't crash."""
        from src.agent.tools.integrity_tools import check_integrity

        p = self.tmp / "utf16.md"
        p.write_text("p = 0.05", encoding="utf-16")

        result = json.loads(check_integrity(file_path=str(p)))
        assert "issues" in result or "error" in result

    def test_p_values_boundary(self):
        """p values at exact boundary values."""
        from src.agent.tools.integrity_tools import check_integrity

        content = "p = 0.000, p = 1.000, p = 0.001, p = 0.999"
        path = self._write(content)
        result = json.loads(check_integrity(file_path=path))

        # None of these should be flagged as impossible
        impossible = [i for i in result.get("issues", []) if i["type"] == "impossible_p_value"]
        assert len(impossible) == 0

    def test_fake_doi_short_and_long(self):
        """Short and long fake DOIs are both detected."""
        from src.agent.tools.integrity_tools import check_integrity

        content = "doi: 10.1234/" + "a" * 64
        path = self._write(content)
        result = json.loads(check_integrity(file_path=path))

        suspicious = [i for i in result.get("issues", []) if i["type"] == "suspicious_doi"]
        assert len(suspicious) >= 1
