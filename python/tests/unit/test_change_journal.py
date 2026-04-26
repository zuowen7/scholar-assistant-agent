"""ChangeJournal 单元测试 — 备份、journal、undo。"""

import json
import pytest
from pathlib import Path

from src.agent.change_journal import ChangeJournal, _sha256


@pytest.fixture
def journal(tmp_path):
    """创建临时 ChangeJournal。"""
    backup_root = tmp_path / ".agent_backup"
    return ChangeJournal(backup_root=backup_root)


@pytest.fixture
def workspace_files(tmp_path):
    """创建临时工作区文件。"""
    f = tmp_path / "src" / "main.py"
    f.parent.mkdir(parents=True)
    f.write_text("print('hello')\n", encoding="utf-8")
    return tmp_path, f


class TestBackupFile:
    def test_backup_creates_copy(self, journal, workspace_files):
        ws_root, src_file = workspace_files
        bid = journal.generate_backup_id()
        journal.backup_file(bid, src_file, ws_root)

        backup_file = journal._root / bid / "files" / "src" / "main.py"
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == "print('hello')\n"

    def test_backup_preserves_original(self, journal, workspace_files):
        ws_root, src_file = workspace_files
        bid = journal.generate_backup_id()
        journal.backup_file(bid, src_file, ws_root)

        assert src_file.read_text(encoding="utf-8") == "print('hello')\n"

    def test_meta_json_written(self, journal, workspace_files):
        ws_root, src_file = workspace_files
        bid = journal.generate_backup_id()
        journal.backup_file(bid, src_file, ws_root)

        meta_path = journal._root / bid / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["backup_id"] == bid
        assert meta["original_path"] == "src/main.py"
        assert len(meta["original_sha256"]) == 64


class TestAppendEntry:
    def test_append_creates_journal(self, journal, tmp_path):
        assert not journal.journal_path.exists()

        journal.append_entry(
            backup_id="bid_1",
            session_id="sess_1",
            event_id="evt_1",
            tool="str_replace",
            file="src/main.py",
            operation="edit",
            original_sha256="abc",
            new_sha256="def",
            diff_preview="@@ -1 +1 @@",
        )

        assert journal.journal_path.exists()

    def test_append_multiple_entries(self, journal):
        for i in range(3):
            journal.append_entry(
                backup_id=f"bid_{i}",
                session_id="sess",
                event_id=f"evt_{i}",
                tool="str_replace",
                file=f"file_{i}.py",
                operation="edit",
            )

        entries = journal.read_entries()
        assert len(entries) == 3
        assert entries[0]["file"] == "file_0.py"
        assert entries[2]["file"] == "file_2.py"

    def test_diff_preview_truncated(self, journal):
        long_diff = "x" * 1000
        journal.append_entry(
            backup_id="bid_long",
            session_id="s",
            event_id="e",
            tool="str_replace",
            file="f.py",
            operation="edit",
            diff_preview=long_diff,
        )
        entries = journal.read_entries()
        assert len(entries[0]["diff_preview"]) == 500


class TestUndo:
    def test_undo_restores_file(self, journal, workspace_files):
        ws_root, src_file = workspace_files
        original = src_file.read_text(encoding="utf-8")

        bid = journal.generate_backup_id()
        journal.backup_file(bid, src_file, ws_root)
        journal.append_entry(
            backup_id=bid, session_id="s", event_id="e",
            tool="str_replace", file="src/main.py", operation="edit",
        )

        # 修改文件
        src_file.write_text("print('modified')\n", encoding="utf-8")
        assert src_file.read_text(encoding="utf-8") != original

        # undo
        reverted = journal.undo(count=1)
        assert len(reverted) == 1
        assert src_file.read_text(encoding="utf-8") == original

    def test_undo_marks_undone_at(self, journal, workspace_files):
        ws_root, src_file = workspace_files
        bid = journal.generate_backup_id()
        journal.backup_file(bid, src_file, ws_root)
        journal.append_entry(
            backup_id=bid, session_id="s", event_id="e",
            tool="str_replace", file="src/main.py", operation="edit",
        )

        reverted = journal.undo(count=1)
        assert reverted[0]["undone_at"] is not None

        # 已 undone 的不会被再次 undo
        reverted2 = journal.undo(count=1)
        assert len(reverted2) == 0

    def test_undo_by_backup_id(self, journal, workspace_files):
        ws_root, src_file = workspace_files

        # 创建两个 backup
        bid1 = journal.generate_backup_id()
        journal.backup_file(bid1, src_file, ws_root)
        journal.append_entry(
            backup_id=bid1, session_id="s", event_id="e1",
            tool="str_replace", file="src/main.py", operation="edit",
        )

        src_file.write_text("v2\n", encoding="utf-8")
        bid2 = journal.generate_backup_id()
        journal.backup_file(bid2, src_file, ws_root)
        journal.append_entry(
            backup_id=bid2, session_id="s", event_id="e2",
            tool="str_replace", file="src/main.py", operation="edit",
        )

        # 按 backup_id undo 第二个
        reverted = journal.undo(backup_id=bid2)
        assert len(reverted) == 1
        assert reverted[0]["backup_id"] == bid2


class TestSHA256:
    def test_sha256_existing_file(self, workspace_files):
        _, f = workspace_files
        h = _sha256(f)
        assert len(h) == 64
        assert h.isalnum()

    def test_sha256_missing_file(self, tmp_path):
        h = _sha256(tmp_path / "nonexistent")
        assert h == ""
