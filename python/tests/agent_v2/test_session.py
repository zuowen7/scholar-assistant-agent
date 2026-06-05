"""Session 测试 — SE-001 ~ SE-042。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent_v2.runtime.session import (
    Session,
    _MAX_FIELD_CHARS,
    _ROTATE_AFTER_BYTES,
    _truncate,
)
from src.agent_v2.types import (
    Message,
    MessageRole,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolResultBlock,
    ToolUseBlock,
)


@pytest.fixture
def session(tmp_path: Path) -> Session:
    return Session(workspace=str(tmp_path), model="test-model")


@pytest.fixture
def session_path(tmp_path: Path) -> Path:
    return tmp_path / "test_session.jsonl"


# ============================================================================
# 5.1 基础操作
# ============================================================================

class TestBasics:

    def test_se001_create(self, session: Session):
        assert session.session_id
        assert len(session.session_id) == 12

    def test_se002_append_user(self, session: Session):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="hello")]))
        assert session.message_count == 1
        assert session.messages[0].role == MessageRole.USER

    def test_se003_append_assistant(self, session: Session):
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[
            TextBlock(text="hi"), ToolUseBlock(id="tu_1", name="read_file", input='{"file_path":"a.txt"}'),
        ]))
        msg = session.messages[0]
        assert len(msg.blocks) == 2
        assert isinstance(msg.blocks[1], ToolUseBlock)

    def test_se004_append_tool_result(self, session: Session):
        session.append(Message(role=MessageRole.TOOL, blocks=[
            ToolResultBlock(tool_use_id="tu_1", tool_name="read_file", output="file content"),
        ]))
        assert session.messages[0].blocks[0].tool_use_id == "tu_1"

    def test_se005_get_history(self, session: Session):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="a")]))
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="b")]))
        msgs = session.messages
        assert len(msgs) == 2
        assert msgs[0].text_content() == "a"
        assert msgs[1].text_content() == "b"

    def test_se006_token_usage(self, session: Session):
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="x")],
                               usage=TokenUsage(input_tokens=100, output_tokens=50)))
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text="y")],
                               usage=TokenUsage(input_tokens=200, output_tokens=80)))
        assert session.total_tokens() == 430


# ============================================================================
# 5.2 持久化与恢复
# ============================================================================

class TestPersistence:

    def test_se010_save(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="hello")]))
        session.save(session_path)
        assert session_path.is_file()
        content = session_path.read_text(encoding="utf-8")
        assert "hello" in content

    def test_se011_restore(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="hello")]))
        session.append(Message(role=MessageRole.ASSISTANT, blocks=[
            TextBlock(text="world"), ToolUseBlock(id="t1", name="read_file", input='{}'),
        ]))
        session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.message_count == 2
        assert loaded.messages[0].text_content() == "hello"
        assert isinstance(loaded.messages[1].blocks[1], ToolUseBlock)

    def test_se012_resume_continue(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="first")]))
        session.save(session_path)
        loaded = Session.load(session_path)
        loaded.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="second")]))
        loaded.save(session_path)
        final = Session.load(session_path)
        assert final.message_count == 2
        assert final.messages[1].text_content() == "second"

    def test_se013_rotate(self, session: Session, session_path: Path):
        session.meta.model = "rotate-test"
        # Force file to be large enough
        for i in range(1000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="x" * 300)]))
        session.save(session_path)
        assert session_path.stat().st_size >= _ROTATE_AFTER_BYTES
        session.rotate(session_path)
        rotated = Path(str(session_path) + ".1")
        assert rotated.is_file()
        assert not session_path.is_file()

    def test_se014_rotate_keeps_latest(self, session: Session, session_path: Path):
        for i in range(1000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="x" * 300)]))
        session.save(session_path)
        session.rotate(session_path)
        # New session saves to fresh file
        new_session = Session(workspace=str(session_path.parent), model="new")
        new_session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="new content")]))
        new_session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.messages[0].text_content() == "new content"


# ============================================================================
# 5.3 边缘测试
# ============================================================================

class TestEdgeCases:

    def test_se020_empty_session(self, session: Session, session_path: Path):
        session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.message_count == 0

    def test_se021_single_message(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="only one")]))
        session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.message_count == 1

    def test_se022_very_long_message(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="x" * 1_000_000)]))
        session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.message_count == 1
        assert len(loaded.messages[0].text_content()) <= _MAX_FIELD_CHARS + 50

    def test_se023_thousand_turns(self, session: Session, session_path: Path):
        for i in range(1000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=f"msg {i}")]))
            session.append(Message(role=MessageRole.ASSISTANT, blocks=[TextBlock(text=f"reply {i}")]))
        session.save(session_path)
        loaded = Session.load(session_path)
        assert loaded.message_count == 2000

    def test_se025_special_characters(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[
            TextBlock(text="中文 🎉 العربية \n\t\r special <>&\"'"),
        ]))
        session.save(session_path)
        loaded = Session.load(session_path)
        assert "中文" in loaded.messages[0].text_content()

    def test_se026_corrupted_jsonl(self, session: Session, session_path: Path):
        session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="good1")]))
        session.save(session_path)
        # Append a corrupted line
        with open(session_path, "a", encoding="utf-8") as f:
            f.write("NOT JSON!!!\n")
            f.write(json.dumps({"role": "user", "blocks": [{"type": "text", "text": "good2"}]}) + "\n")
        loaded = Session.load(session_path)
        texts = [m.text_content() for m in loaded.messages]
        assert "good1" in texts
        assert "good2" in texts


# ============================================================================
# 5.4 故障注入
# ============================================================================

class TestFaultInjection:

    def test_se033_nonexistent_file(self):
        loaded = Session.load("/nonexistent/path/session.jsonl")
        assert loaded.message_count == 0

    def test_se033b_readonly_dir(self, session: Session, tmp_path: Path):
        ro_dir = tmp_path / "readonly"
        ro_dir.mkdir()
        ro_file = ro_dir / "session.jsonl"
        session.save(ro_file)
        # Make file read-only
        import os
        import stat
        os.chmod(str(ro_file), stat.S_IRUSR)
        try:
            new_session = Session()
            new_session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="test")]))
            with pytest.raises(PermissionError):
                new_session.save(ro_file)
        finally:
            os.chmod(str(ro_file), stat.S_IWUSR)


# ============================================================================
# 5.5 极限测试
# ============================================================================

class TestStress:

    def test_se040_ten_thousand_messages(self, session: Session, session_path: Path):
        import time
        for i in range(10000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text=f"msg{i}")]))
        start = time.monotonic()
        session.save(session_path)
        loaded = Session.load(session_path)
        elapsed = time.monotonic() - start
        assert loaded.message_count == 10000
        assert elapsed < 5.0

    def test_se041_field_truncation(self):
        long_text = "x" * 100_000
        truncated = _truncate(long_text)
        assert len(truncated) <= _MAX_FIELD_CHARS + 50

    def test_se042_rotate_max_files(self, session: Session, session_path: Path):
        for i in range(1000):
            session.append(Message(role=MessageRole.USER, blocks=[TextBlock(text="x" * 300)]))
        session.save(session_path)
        # Rotate multiple times
        for _ in range(5):
            session.rotate(session_path)
        rotated_files = list(session_path.parent.glob(str(session_path.name) + ".*"))
        assert len(rotated_files) <= 3
