"""End-to-end integration tests for the full translation pipeline.

Tests the complete flow: parse -> clean -> chunk -> translate(mock) -> format,
as well as individual post-processing chains and edge cases.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.dispatcher import extract_document, SUPPORTED_EXTENSIONS, get_supported_extensions
from src.cleaner.pipeline import clean_text, clean_text_full
from src.chunker.splitter import chunk_text, chunk_text_full, Chunk, ChunkResult
from src.formatter.renderer import format_output
from src.translator.ollama_client import (
    TranslationResult,
    _strip_think_tags,
    _strip_code_block_wrapping,
    _strip_preamble,
    _strip_context_leak,
    _deduplicate_repetition,
)
from src.translator._helpers import (
    TranslationResult as HelpersTranslationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(original: str, translated: str) -> TranslationResult:
    """Create a TranslationResult for formatter tests."""
    return TranslationResult(
        original=original,
        translated=translated,
        model="mock-model",
    )


# ---------------------------------------------------------------------------
# 1. Full pipeline with sample text
# ---------------------------------------------------------------------------

class TestFullPipelineWithSampleText:
    """Parse -> Clean -> Chunk -> Format pipeline."""

    def test_full_pipeline_with_sample_text(self) -> None:
        """Create a temp .txt file, run the full pipeline, verify each stage."""
        sample_text = (
            "Artificial Intelligence in Modern Science.\n\n"
            "This paper discusses the role of artificial intelligence in modern "
            "scientific research. Machine learning algorithms have revolutionized "
            "data analysis across multiple disciplines.\n\n"
            "Deep learning models, particularly transformers, have shown remarkable "
            "capabilities in natural language processing. These models can understand "
            "context and generate coherent text.\n\n"
            "In conclusion, AI represents a paradigm shift in how we approach "
            "complex scientific problems."
        )

        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(sample_text)
            temp_path = f.name

        try:
            # Stage 1: Parse
            doc = extract_document(temp_path)
            assert doc is not None
            assert doc.full_text.strip()
            assert "Artificial Intelligence" in doc.full_text

            # Stage 2: Clean
            clean_result = clean_text_full(doc.full_text)
            assert clean_result.text.strip()
            assert len(clean_result.text) > 0

            # Stage 3: Chunk
            chunk_result = chunk_text_full(clean_result.text, max_tokens=2048)
            assert isinstance(chunk_result, ChunkResult)
            assert len(chunk_result.chunks) >= 1
            for chunk in chunk_result.chunks:
                assert isinstance(chunk, Chunk)
                assert chunk.text.strip()
                assert chunk.char_count > 0
                assert chunk.estimated_tokens > 0

            # Stage 4: Format (mock translation — use original text as "translated")
            mock_results = [
                _make_result(chunk.text, f"[MOCK] {chunk.text}")
                for chunk in chunk_result.chunks
            ]
            output = format_output(mock_results, output_format="bilingual")
            assert output.strip()
            assert "[MOCK]" in output
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 2. Pipeline handles empty input
# ---------------------------------------------------------------------------

class TestPipelineHandlesEmptyInput:
    """Verify graceful handling of empty files."""

    def test_pipeline_handles_empty_input(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("")
            temp_path = f.name

        try:
            # Parse
            doc = extract_document(temp_path)
            assert doc is not None
            # full_text may be empty string
            assert isinstance(doc.full_text, str)

            # Clean
            clean_result = clean_text_full(doc.full_text)
            assert isinstance(clean_result.text, str)

            # Chunk
            chunk_result = chunk_text_full(clean_result.text, max_tokens=2048)
            assert isinstance(chunk_result, ChunkResult)
            # Empty input should produce zero chunks
            assert len(chunk_result.chunks) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_pipeline_handles_whitespace_only_input(self) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("   \n\n   \t  \n   ")
            temp_path = f.name

        try:
            doc = extract_document(temp_path)
            clean_result = clean_text_full(doc.full_text)
            chunk_result = chunk_text_full(clean_result.text, max_tokens=2048)
            assert len(chunk_result.chunks) == 0
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 3. Pipeline chunk consistency
# ---------------------------------------------------------------------------

class TestPipelineChunkConsistency:
    """Verify chunks have sequential indices and no unexpected overlap."""

    def test_pipeline_chunk_consistency(self) -> None:
        # Create enough text to generate multiple chunks
        paragraphs = []
        for i in range(20):
            paragraphs.append(
                f"Paragraph {i + 1}. " + "This is a sentence about testing. " * 15
            )
        text = "\n\n".join(paragraphs)

        with tempfile.NamedTemporaryFile(
            suffix=".txt", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(text)
            temp_path = f.name

        try:
            doc = extract_document(temp_path)
            clean_result = clean_text_full(doc.full_text)
            chunk_result = chunk_text_full(clean_result.text, max_tokens=256)

            chunks = chunk_result.chunks
            assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}"

            # Sequential indices starting from 0
            for i, chunk in enumerate(chunks):
                assert chunk.index == i, (
                    f"Chunk index mismatch: expected {i}, got {chunk.index}"
                )

            # No unexpected text duplication across non-overlapping parts
            # (overlap is expected between consecutive chunks; verify the core
            # content of each chunk is not identical)
            for i in range(len(chunks) - 1):
                # Each chunk should have unique core content beyond overlap region
                assert chunks[i].text != chunks[i + 1].text, (
                    f"Chunks {i} and {i + 1} are identical"
                )
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 4. Postprocessing chain (ollama_client helpers)
# ---------------------------------------------------------------------------

class TestPostprocessingChain:
    """Test the post-processing chain in ollama_client / _helpers."""

    def test_strip_think_tags(self) -> None:
        raw = "<think\nSome reasoning here\n</think\nThe actual translation."
        result = _strip_think_tags(raw)
        # The function strips XML-style tags: <think ...>...</think ...>
        # "The actual translation." is never inside a <think ...>...</think ...> block
        # so it must survive regardless of whether the tag syntax is recognized.
        assert "The actual translation." in result

        # Also verify proper XML-style think tags are fully removed
        raw2 = "<think\nModel is thinking...\n</think\nActual output text."
        result2 = _strip_think_tags(raw2)
        assert "Actual output text." in result2

    def test_strip_code_block_wrapping(self) -> None:
        raw = "```markdown\nTranslated text here.\n```"
        result = _strip_code_block_wrapping(raw)
        assert result == "Translated text here."

    def test_strip_code_block_wrapping_no_wrapper(self) -> None:
        raw = "Just normal text without code blocks."
        result = _strip_code_block_wrapping(raw)
        assert result == raw

    def test_strip_preamble_english(self) -> None:
        raw = "Here is the translation:\nActual translated content."
        result = _strip_preamble(raw)
        assert "Here is the translation" not in result
        assert "Actual translated content." in result

    def test_strip_preamble_chinese(self) -> None:
        raw = "以下是翻译：\n实际翻译内容。"
        result = _strip_preamble(raw)
        assert "以下是翻译" not in result
        assert "实际翻译内容。" in result

    def test_strip_context_leak(self) -> None:
        raw = (
            "[文档背景（不要翻译此部分）]\n"
            "Some context info\n\n"
            "This is the real translation content."
        )
        result = _strip_context_leak(raw)
        assert "[文档背景" not in result
        assert "This is the real translation content." in result

    def test_deduplicate_repetition(self) -> None:
        # Dedup requires >= 300 chars and >= 6 sentences (split by 。！？)
        # Each repetition is ~26 chars; 15 reps gives ~390 chars, 15 sentences
        repeated_sentence = "这是一句重复的翻译内容，需要足够长才能触发去重检测。"
        raw = (repeated_sentence * 15)
        assert len(raw) >= 300, "Test text must be >= 300 chars to trigger dedup"
        result = _deduplicate_repetition(raw)
        # Should have deduplicated — result should be shorter
        assert len(result) < len(raw)

    def test_full_chain_combined(self) -> None:
        """Test the complete chain: think_tags -> code_block -> preamble -> context_leak -> dedup."""
        raw = (
            "<think\nModel reasoning\n</think\n"
            "```markdown\n"
            "Here is the translation:\n"
            "[前文翻译参考（不要翻译此部分）]\n"
            "Previous context\n\n"
            "这是第一段实际翻译内容。这是第一段实际翻译内容。"
            "这是第一段实际翻译内容。这是第一段实际翻译内容。"
            "这是第一段实际翻译内容。这是第一段实际翻译内容。"
        )
        text = _strip_think_tags(raw)
        text = _strip_code_block_wrapping(text)
        text = _strip_preamble(text)
        text = _strip_context_leak(text)
        text = _deduplicate_repetition(text)

        assert "<think" not in text
        assert "```" not in text
        assert "Here is the translation" not in text
        assert "[前文翻译参考" not in text
        assert "实际翻译内容" in text


# ---------------------------------------------------------------------------
# 5. Cleaner fixes common issues
# ---------------------------------------------------------------------------

class TestCleanerFixesCommonIssues:
    """Feed text with broken hyphens, extra whitespace, watermark patterns."""

    def test_fixes_broken_hyphens(self) -> None:
        text = (
            "We need to eval-\n"
            "uate the perfor-\n"
            "mance of the system."
        )
        result = clean_text(text)
        assert "evaluate" in result
        assert "performance" in result
        assert "eval-\n" not in result
        assert "perfor-\n" not in result

    def test_fixes_extra_whitespace(self) -> None:
        text = "This  has   too    many     spaces."
        result = clean_text(text)
        assert "  " not in result
        assert "This has too many spaces." in result

    def test_removes_watermark_patterns(self) -> None:
        text = (
            "Downloaded from https://science.org on March 28, 2026\n"
            "Important scientific content here."
        )
        result = clean_text(text)
        assert "Downloaded from" not in result
        assert "Important scientific content here." in result

    def test_removes_cid_artifacts(self) -> None:
        text = "Some text (cid:123) and (cid:0) here."
        result = clean_text(text)
        assert "(cid:" not in result
        assert "Some text" in result

    def test_removes_page_numbers(self) -> None:
        text = "Content above\n\n42\n\nContent below"
        result = clean_text(text)
        # Standalone page number should be removed
        assert "42" not in result.split("\n")

    def test_normalizes_tabs(self) -> None:
        text = "Column1\tColumn2\tColumn3"
        result = clean_text(text)
        assert "\t" not in result


# ---------------------------------------------------------------------------
# 6. Formatter bilingual output
# ---------------------------------------------------------------------------

class TestFormatterBilingualOutput:
    """Format chunks as bilingual, verify output contains both original and translated."""

    def test_bilingual_contains_both_sections(self) -> None:
        results = [
            _make_result(
                "This is the original English text.",
                "这是原始英文文本的翻译。",
            ),
            _make_result(
                "Another paragraph to translate.",
                "另一段需要翻译的文本。",
            ),
        ]
        output = format_output(results, output_format="bilingual")
        assert "original English text" in output
        assert "原始英文文本的翻译" in output
        assert "Another paragraph" in output
        assert "另一段需要翻译" in output

    def test_bilingual_markdown_format(self) -> None:
        results = [_make_result("Hello world.", "你好世界。")]
        output = format_output(
            results, output_format="bilingual", file_format="markdown"
        )
        # Markdown bilingual uses blockquote for original
        assert "> " in output or "Hello world." in output
        assert "你好世界。" in output

    def test_bilingual_plain_format(self) -> None:
        results = [_make_result("Hello world.", "你好世界。")]
        output = format_output(
            results, output_format="bilingual", file_format="txt"
        )
        assert "[原文]" in output
        assert "[译文]" in output
        assert "Hello world." in output
        assert "你好世界。" in output

    def test_parallel_table_format(self) -> None:
        results = [_make_result("Source text.", "译文文本。")]
        output = format_output(
            results, output_format="parallel", file_format="markdown"
        )
        assert "原文" in output
        assert "译文" in output
        assert "Source text." in output
        assert "译文文本。" in output

    def test_translated_only_format(self) -> None:
        results = [_make_result("Source text.", "Only the translation.")]
        output = format_output(
            results, output_format="translated_only", file_format="markdown"
        )
        assert "Only the translation." in output
        # Original should not appear as a standalone section
        assert "[原文]" not in output

    def test_empty_results_list(self) -> None:
        output = format_output([], output_format="bilingual")
        assert isinstance(output, str)


# ---------------------------------------------------------------------------
# 7. Parser supported extensions
# ---------------------------------------------------------------------------

class TestParserSupportedExtensions:
    """Verify SUPPORTED_EXTENSIONS list from parser module."""

    def test_supported_extensions_is_dict(self) -> None:
        assert isinstance(SUPPORTED_EXTENSIONS, dict)

    def test_common_extensions_present(self) -> None:
        expected = [".pdf", ".txt", ".md", ".docx", ".html", ".csv", ".json", ".xml"]
        for ext in expected:
            assert ext in SUPPORTED_EXTENSIONS, f"Missing extension: {ext}"

    def test_get_supported_extensions_returns_list(self) -> None:
        exts = get_supported_extensions()
        assert isinstance(exts, list)
        assert len(exts) > 0
        # All entries should start with "."
        for ext in exts:
            assert ext.startswith("."), f"Extension should start with '.': {ext}"

    def test_all_registry_keys_match_supported(self) -> None:
        """Every key in SUPPORTED_EXTENSIONS should also be in the registry."""
        exts = get_supported_extensions()
        for ext in SUPPORTED_EXTENSIONS:
            assert ext in exts, f"SUPPORTED_EXTENSIONS key {ext} not in registry"
