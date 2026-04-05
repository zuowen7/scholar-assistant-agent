"""输出格式化模块单元测试"""

import tempfile
from pathlib import Path

from src.formatter.renderer import format_output, save_output, _md_table_escape
from src.translator.ollama_client import TranslationResult


def _make_result(original: str, translated: str) -> TranslationResult:
    return TranslationResult(
        original=original,
        translated=translated,
        model="qwen3",
    )


class TestFormatMarkdown:
    """Markdown 格式输出"""

    def test_bilingual_format(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="bilingual", file_format="markdown")
        assert "> Hello" in output
        assert "你好" in output
        assert "第 1 部分" in output

    def test_translated_only(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="translated_only", file_format="markdown")
        assert "你好" in output
        # 不应包含原文标签
        assert "原文" not in output


    def test_parallel_format(self) -> None:
        results = [_make_result("Hello", "你好"), _make_result("World", "世界")]
        output = format_output(results, output_format="parallel", file_format="markdown")
        assert "| 原文 | 译文 |" in output
        assert "| --- | --- |" in output
        assert "Hello" in output
        assert "你好" in output


class TestFormatPlain:
    """纯文本格式输出"""

    def test_bilingual_plain(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="bilingual", file_format="txt")
        assert "[原文]" in output
        assert "[译文]" in output


class TestSaveOutput:
    """文件保存"""

    def test_save_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = save_output("test content", Path(tmp) / "output.md")
            assert path.exists()
            assert path.read_text(encoding="utf-8") == "test content"

    def test_save_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = save_output("test", Path(tmp) / "sub" / "dir" / "out.md")
            assert path.exists()


class TestMdTableEscape:
    """Markdown 表格转义"""

    def test_pipe_escaped(self) -> None:
        assert _md_table_escape("a|b") == "a\\|b"

    def test_newline_escaped(self) -> None:
        assert _md_table_escape("a\nb") == "a<br>b"

    def test_backslash_escaped(self) -> None:
        assert _md_table_escape("a\\b") == "a\\\\b"
