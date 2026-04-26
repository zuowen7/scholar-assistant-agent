"""str_replace / write_file / list_directory / read_file / undo 工具集成测试。"""

import json
import pytest
from pathlib import Path

from src.agent.workspace import WorkspaceEnv
from src.agent.change_journal import ChangeJournal
from src.agent.tools import (
    _read_file_v2,
    _list_directory,
    _str_replace,
    _write_file_v2,
    _undo_last_change,
)


@pytest.fixture
def workspace(tmp_path):
    """创建临时工作区 + 文件。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# Hello\n\nWorld\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules/\n__pycache__/\n*.pyc\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "foo.js").write_text("// foo", encoding="utf-8")
    ws = WorkspaceEnv(root=tmp_path)
    journal = ChangeJournal(backup_root=ws.backup_root_path())
    return ws, journal


class TestReadFileV2:
    def test_read_full_file(self, workspace):
        ws, _ = workspace
        result = json.loads(_read_file_v2("src/main.py", ws))
        assert result["file_path"] == "src/main.py"
        assert "print('hello')" in result["content"]
        assert result["total_lines"] == 1
        assert result["truncated"] is False

    def test_read_with_offset(self, workspace):
        ws, _ = workspace
        result = json.loads(_read_file_v2("docs/readme.md", ws, offset=1))
        assert result["returned_lines"] == [2, 3]

    def test_read_not_found(self, workspace):
        ws, _ = workspace
        result = json.loads(_read_file_v2("nonexistent.py", ws))
        assert "error" in result

    def test_read_denied_file(self, workspace):
        ws, _ = workspace
        result = json.loads(_read_file_v2(".env", ws))
        assert "error" in result

    def test_read_path_escape(self, workspace):
        ws, _ = workspace
        result = json.loads(_read_file_v2("../../etc/passwd", ws))
        assert "error" in result


class TestListDirectory:
    def test_list_root(self, workspace):
        ws, _ = workspace
        result = json.loads(_list_directory(".", ws))
        assert "entries" in result
        names = [e["name"] for e in result["entries"]]
        assert "src" in names
        assert "docs" in names

    def test_list_subdirectory(self, workspace):
        ws, _ = workspace
        result = json.loads(_list_directory("src", ws))
        names = [e["name"] for e in result["entries"]]
        assert "main.py" in names
        assert "util.py" in names

    def test_list_with_pattern(self, workspace):
        ws, _ = workspace
        result = json.loads(_list_directory("src", ws, pattern="*.py"))
        names = [e["name"] for e in result["entries"]]
        assert all(n.endswith(".py") for n in names)

    def test_list_nonexistent_dir(self, workspace):
        ws, _ = workspace
        result = json.loads(_list_directory("nope", ws))
        assert "error" in result

    def test_list_recursive_gitignore(self, workspace):
        ws, _ = workspace
        # node_modules 内容应被 .gitignore 过滤
        result = json.loads(_list_directory(".", ws, recursive=True, pattern="*"))
        # node_modules 目录可能出现在顶层，但里面的文件不应出现
        entries = result.get("entries", [])
        names = [e["name"] for e in entries]
        # foo.js (在 node_modules 内) 不应出现
        assert "foo.js" not in names


class TestStrReplace:
    def test_simple_replace(self, workspace):
        ws, journal = workspace
        result = json.loads(_str_replace(
            "src/main.py", "hello", "world", ws, journal,
        ))
        assert "backup_id" in result
        assert result["occurrences"] == 1
        assert (ws.root / "src" / "main.py").read_text(encoding="utf-8") == "print('world')\n"

    def test_replace_not_found(self, workspace):
        ws, journal = workspace
        result = json.loads(_str_replace(
            "src/main.py", "nonexistent_text", "x", ws, journal,
        ))
        assert "error" in result

    def test_replace_ambiguous(self, workspace):
        ws, journal = workspace
        # "return" 出现一次，但 "a" 在 util.py 中出现多次
        result = json.loads(_str_replace(
            "src/util.py", "a", "b", ws, journal,
        ))
        assert "error" in result
        assert "ambiguous" in result["error"]

    def test_replace_all(self, workspace):
        ws, journal = workspace
        result = json.loads(_str_replace(
            "src/util.py", "a", "b", ws, journal, replace_all=True,
        ))
        assert result["occurrences"] > 1

    def test_replace_creates_backup(self, workspace):
        ws, journal = workspace
        original = (ws.root / "src" / "main.py").read_text(encoding="utf-8")
        _str_replace("src/main.py", "hello", "world", ws, journal)

        entries = journal.read_entries()
        assert len(entries) == 1
        assert entries[0]["tool"] == "str_replace"
        assert entries[0]["file"] == "src/main.py"

    def test_replace_denied_path(self, workspace):
        ws, journal = workspace
        result = json.loads(_str_replace(
            ".env", "123", "456", ws, journal,
        ))
        assert "error" in result


class TestWriteFile:
    def test_create_new_file(self, workspace):
        ws, journal = workspace
        result = json.loads(_write_file_v2(
            "new_file.py", "print('new')", ws, journal,
        ))
        assert result["created"] is True
        assert (ws.root / "new_file.py").read_text(encoding="utf-8") == "print('new')"

    def test_overwrite_existing(self, workspace):
        ws, journal = workspace
        result = json.loads(_write_file_v2(
            "src/main.py", "print('overwritten')", ws, journal,
        ))
        assert result["created"] is False
        assert (ws.root / "src" / "main.py").read_text(encoding="utf-8") == "print('overwritten')"

    def test_must_not_exist(self, workspace):
        ws, journal = workspace
        result = json.loads(_write_file_v2(
            "src/main.py", "x", ws, journal, must_not_exist=True,
        ))
        assert "error" in result
        assert "already exists" in result["error"]

    def test_overwrite_creates_backup(self, workspace):
        ws, journal = workspace
        original = (ws.root / "src" / "main.py").read_text(encoding="utf-8")
        _write_file_v2("src/main.py", "new content", ws, journal)

        entries = journal.read_entries()
        assert len(entries) == 1
        assert entries[0]["operation"] == "overwrite"


class TestUndo:
    def test_undo_str_replace(self, workspace):
        ws, journal = workspace
        original = (ws.root / "src" / "main.py").read_text(encoding="utf-8")

        _str_replace("src/main.py", "hello", "world", ws, journal)
        assert (ws.root / "src" / "main.py").read_text(encoding="utf-8") != original

        result = json.loads(_undo_last_change(journal, ws, count=1))
        assert result["count"] == 1
        assert (ws.root / "src" / "main.py").read_text(encoding="utf-8") == original

    def test_undo_write_file(self, workspace):
        ws, journal = workspace
        original = (ws.root / "src" / "main.py").read_text(encoding="utf-8")

        _write_file_v2("src/main.py", "overwritten", ws, journal)

        result = json.loads(_undo_last_change(journal, ws, count=1))
        assert result["count"] == 1
        assert (ws.root / "src" / "main.py").read_text(encoding="utf-8") == original

    def test_undo_nothing_to_undo(self, workspace):
        ws, journal = workspace
        result = json.loads(_undo_last_change(journal, ws))
        assert "error" in result
