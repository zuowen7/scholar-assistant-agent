"""Integration tests: lesson overlay injected into Agent system prompt."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent.lesson_store import LessonStore, extract_lessons_from_events
from src.agent.models import AgentEvent


class TestLessonOverlayInAgent:
    def test_lesson_overlay_injected_into_extra_sections(self, tmp_path):
        from src.agent.agent import AgentLoop
        from src.agent.lesson_store import LessonStore

        store = LessonStore(data_dir=str(tmp_path / "lessons"))
        store.record("str_replace", category="writing", severity="error",
                     description="删除了参考文献段落，导致论文不完整")

        agent = AgentLoop(
            ollama_base_url="http://localhost:99999",
            model="test",
            memory_dir=str(tmp_path / "memory"),
            lesson_store=store,
        )

        messages = agent._build_messages("帮我替换论文中的一段文字")
        system_msg = messages[0].content

        assert "参考文献" in system_msg
        assert "过往经验教训" in system_msg

    def test_no_lesson_overlay_when_store_empty(self, tmp_path):
        from src.agent.agent import AgentLoop
        from src.agent.lesson_store import LessonStore

        store = LessonStore(data_dir=str(tmp_path / "lessons"))
        agent = AgentLoop(
            ollama_base_url="http://localhost:99999",
            model="test",
            memory_dir=str(tmp_path / "memory"),
            lesson_store=store,
        )

        messages = agent._build_messages("帮我替换论文中的一段文字")
        system_msg = messages[0].content
        assert "过往经验教训" not in system_msg

    def test_extract_and_record_from_events(self, tmp_path):
        store = LessonStore(data_dir=str(tmp_path / "lessons"))
        events = [
            AgentEvent(type="tool_result", content="error: file not found",
                       metadata={"tool_name": "str_replace", "error": True}),
            AgentEvent(type="tool_result", content="wrote 500 bytes",
                       metadata={"tool_name": "write_file"}),
        ]

        lessons = extract_lessons_from_events(events)
        for l in lessons:
            store.record(**l)

        all_lessons = store.load_all()
        assert len(all_lessons) == 1
        assert all_lessons[0]["tool"] == "str_replace"
