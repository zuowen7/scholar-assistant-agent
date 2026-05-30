"""Memory time-decay + confidence scoring and session lesson extraction tests.

TDD tests for two features borrowed from AutoResearchClaw:
1. Memory time-decay weighting + confidence updates
2. Session lesson extraction + prompt overlay
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.agent.memory import MemoryManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mm(tmp_path: Path | None = None, **kw) -> MemoryManager:
    d = tmp_path or Path(tempfile.mkdtemp())
    return MemoryManager(data_dir=str(d), default_memory=None, **kw)


def _inject_aged_memory(mm: MemoryManager, content: str, days_ago: int,
                        importance: float = 0.5) -> int:
    """Insert a memory with a backdated created_at for time-decay testing."""
    past = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    conn = mm._connect()
    with mm._write_lock:
        cursor = conn.execute(
            "INSERT INTO memories (content, category, source, importance, created_at) "
            "VALUES (?, 'experience', 'review', ?, ?)",
            (content, importance, past),
        )
        conn.commit()
        return cursor.lastrowid or 0


# ===========================================================================
# 1. Time-decay weighting
# ===========================================================================


class TestMemoryTimeDecay:
    """Memory search results should weight recent memories over old ones."""

    def test_recent_memory_ranks_higher_than_old(self, tmp_path):
        mm = _make_mm(tmp_path)
        _inject_aged_memory(mm, "翻译时引用格式必须保留 author-year 风格", days_ago=80, importance=0.7)
        mm.add_memory("翻译长文档时 chunk 对齐比速度更重要", category="experience", source="review", importance=0.7)

        results = mm.search_memories("翻译", limit=5)
        assert len(results) == 2
        # Recent should rank first (higher effective score)
        assert "chunk" in results[0].content

    def test_very_old_memory_below_threshold_excluded(self, tmp_path):
        mm = _make_mm(tmp_path)
        mid = _inject_aged_memory(mm, "过时记忆关于旧版对齐算法", days_ago=300, importance=0.1)
        mm.add_memory("最新发现：新对齐方法效果更好", category="experience", source="review", importance=0.6)

        results = mm.search_memories("对齐", limit=5)
        ids = [r.id for r in results]
        assert mid not in ids, "Very old + low importance memory should be excluded"

    def test_high_importance_old_memory_still_visible(self, tmp_path):
        mm = _make_mm(tmp_path)
        mid = _inject_aged_memory(mm, "重要经验：永远不要删除参考文献段", days_ago=60, importance=0.95)

        results = mm.search_memories("参考文献", limit=5)
        assert any(r.id == mid for r in results), "High-importance old memory should survive decay"


# ===========================================================================
# 2. Confidence scoring
# ===========================================================================


class TestMemoryConfidence:
    """Confidence should adjust dynamically based on usage outcomes."""

    def test_update_confidence_success_increases(self, tmp_path):
        mm = _make_mm(tmp_path)
        mid = mm.add_memory("用户偏好中文回复", category="preference", importance=0.5)
        assert mid > 0
        ok = mm.update_confidence(mid, delta=0.1)
        assert ok is True
        entry = mm._get_by_id(mid)
        assert entry is not None
        assert float(entry["importance"]) == pytest.approx(0.6, abs=0.01)

    def test_update_confidence_failure_decreases(self, tmp_path):
        mm = _make_mm(tmp_path)
        mid = mm.add_memory("错误的经验教训", category="experience", importance=0.7)
        mm.update_confidence(mid, delta=-0.2)
        entry = mm._get_by_id(mid)
        assert float(entry["importance"]) == pytest.approx(0.5, abs=0.01)

    def test_confidence_clamped_to_range(self, tmp_path):
        mm = _make_mm(tmp_path)
        mid = mm.add_memory("测试记忆", category="fact", importance=0.95)
        mm.update_confidence(mid, delta=0.2)
        entry = mm._get_by_id(mid)
        assert float(entry["importance"]) <= 1.0

        mm.update_confidence(mid, delta=-2.0)
        entry = mm._get_by_id(mid)
        assert float(entry["importance"]) >= 0.0

    def test_update_confidence_nonexistent_returns_false(self, tmp_path):
        mm = _make_mm(tmp_path)
        assert mm.update_confidence(99999, delta=0.1) is False


# ===========================================================================
# 3. Lesson extraction + overlay
# ===========================================================================


class TestLessonStore:
    """Agent session lesson extraction and prompt overlay."""

    def test_record_lesson(self, tmp_path):
        from src.agent.lesson_store import LessonStore
        store = LessonStore(data_dir=str(tmp_path))
        store.record("str_replace", category="writing", severity="warning",
                     description="删除了参考文献段落")

        lessons = store.load_all()
        assert len(lessons) == 1
        assert "参考文献" in lessons[0]["description"]
        assert lessons[0]["tool"] == "str_replace"

    def test_build_overlay_returns_relevant_lessons(self, tmp_path):
        from src.agent.lesson_store import LessonStore
        store = LessonStore(data_dir=str(tmp_path))
        store.record("str_replace", category="writing", severity="warning",
                     description="上次改论文时丢了参考文献")
        store.record("write_file", category="writing", severity="error",
                     description="写入了错误路径")
        store.record("run_command", category="system", severity="info",
                     description="pytest 通过了")

        overlay = store.build_overlay("str_replace")
        assert "参考文献" in overlay
        # Tool-specific overlay should prioritize same-tool lessons
        assert overlay.index("参考文献") < overlay.index("pytest") if "pytest" in overlay else True

    def test_overlay_excludes_expired_lessons(self, tmp_path):
        from src.agent.lesson_store import LessonStore
        store = LessonStore(data_dir=str(tmp_path))
        # Record a lesson with an old timestamp
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(timespec="seconds")
        store.record("str_replace", category="writing", severity="warning",
                     description="过时的教训", timestamp=old_ts)

        overlay = store.build_overlay("str_replace")
        assert "过时的教训" not in overlay

    def test_empty_store_returns_empty_overlay(self, tmp_path):
        from src.agent.lesson_store import LessonStore
        store = LessonStore(data_dir=str(tmp_path))
        assert store.build_overlay("write_file") == ""

    def test_record_from_session_events(self, tmp_path):
        from src.agent.lesson_store import LessonStore, extract_lessons_from_events
        from src.agent.models import AgentEvent

        events = [
            AgentEvent(type="tool_call", content="",
                       metadata={"tool_name": "str_replace", "args": {"file_path": "draft.md"}}),
            AgentEvent(type="tool_result", content="error: file not found",
                       metadata={"tool_name": "str_replace", "error": True}),
            AgentEvent(type="tool_call", content="",
                       metadata={"tool_name": "write_file", "args": {"file_path": "out.md"}}),
            AgentEvent(type="tool_result", content="wrote 1200 bytes",
                       metadata={"tool_name": "write_file"}),
            AgentEvent(type="warning", content="",
                       metadata={"code": "LOOP_FORCE_STOP"}),
        ]
        lessons = extract_lessons_from_events(events)
        assert any(l["tool"] == "str_replace" and l["severity"] == "error" for l in lessons)
        assert any(l["tool"] == "agent_loop" and "循环" in l["description"] for l in lessons)
        # Successful write_file should NOT produce a lesson
        assert not any(l["tool"] == "write_file" for l in lessons)
