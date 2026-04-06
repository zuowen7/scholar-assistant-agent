"""输出格式化模块单元测试"""

import tempfile
from pathlib import Path

from src.formatter.renderer import (
    format_output,
    save_output,
    _md_table_escape,
    _merge_chunks,
    _split_paragraphs,
    _strip_overlap,
)
from src.translator.ollama_client import TranslationResult


def _make_result(original: str, translated: str) -> TranslationResult:
    return TranslationResult(
        original=original,
        translated=translated,
        model="qwen3",
    )


class TestFormatMarkdown:
    def test_bilingual_format(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="bilingual", file_format="markdown")
        assert "> Hello" in output
        assert "你好" in output

    def test_translated_only(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="translated_only", file_format="markdown")
        assert "你好" in output
        assert "原文" not in output

    def test_parallel_format(self) -> None:
        results = [_make_result("Hello", "你好"), _make_result("World", "世界")]
        output = format_output(results, output_format="parallel", file_format="markdown")
        assert "| 原文 | 译文 |" in output
        assert "| --- | --- |" in output
        assert "Hello" in output
        assert "你好" in output

    def test_bilingual_multiple_chunks(self) -> None:
        results = [
            _make_result("First paragraph.\n\nSecond paragraph.", "第一段。\n\n第二段。"),
            _make_result("Third paragraph.", "第三段。"),
        ]
        output = format_output(results, output_format="bilingual")
        assert "> First paragraph." in output
        assert "第一段。" in output


class TestFormatPlain:
    def test_bilingual_plain(self) -> None:
        results = [_make_result("Hello", "你好")]
        output = format_output(results, output_format="bilingual", file_format="txt")
        assert "[原文]" in output
        assert "[译文]" in output


class TestMergeChunks:
    def test_single_chunk(self) -> None:
        results = [_make_result("Para 1\n\nPara 2", "段落一\n\n段落二")]
        orig, trans = _merge_chunks(results)
        assert len(orig) == 2
        assert len(trans) == 2

    def test_overlapping_chunks_stripped(self) -> None:
        """overlap 导致的重复段落应被去除"""
        overlap_text = "This is the overlapping paragraph that appears in both chunks."
        results = [
            _make_result(f"Para A\n\n{overlap_text}", f"段落甲\n\n这是重叠段落。"),
            _make_result(f"{overlap_text}\n\nPara B", "这是重叠段落。\n\n段落乙"),
        ]
        orig, trans = _merge_chunks(results)
        # 重叠段只保留一份
        overlap_count = sum(1 for p in orig if "overlapping" in p)
        assert overlap_count == 1

    def test_no_overlap(self) -> None:
        results = [
            _make_result("Para A", "段落甲"),
            _make_result("Para B", "段落乙"),
        ]
        orig, trans = _merge_chunks(results)
        assert len(orig) == 2
        assert len(trans) == 2


class TestStripOverlap:
    def test_identical_prefix_stripped(self) -> None:
        orig = ["Identical first paragraph.", "Unique para B."]
        trans = ["完全相同的第一段。", "独特段落乙。"]
        prev = "Identical first paragraph."
        o, t = _strip_overlap(orig, trans, prev)
        assert len(o) == 1
        assert "Unique" in o[0]

    def test_no_overlap_keeps_all(self) -> None:
        orig = ["Completely different paragraph."]
        trans = ["完全不同的段落。"]
        prev = "Something else entirely."
        o, t = _strip_overlap(orig, trans, prev)
        assert len(o) == 1

    def test_short_prev_ignored(self) -> None:
        orig = ["Some paragraph"]
        trans = ["某段落"]
        prev = "short"
        o, t = _strip_overlap(orig, trans, prev)
        assert len(o) == 1


class TestSplitParagraphs:
    def test_double_newline_split(self) -> None:
        paras = _split_paragraphs("Para 1\n\nPara 2\n\nPara 3")
        assert len(paras) == 3

    def test_triple_newline(self) -> None:
        paras = _split_paragraphs("Para 1\n\n\nPara 2")
        assert len(paras) == 2

    def test_empty_input(self) -> None:
        paras = _split_paragraphs("   ")
        assert paras == []


class TestSaveOutput:
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
    def test_pipe_escaped(self) -> None:
        assert _md_table_escape("a|b") == "a\\|b"

    def test_newline_escaped(self) -> None:
        assert _md_table_escape("a\nb") == "a<br>b"

    def test_backslash_escaped(self) -> None:
        assert _md_table_escape("a\\b") == "a\\\\b"
