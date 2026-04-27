"""End-to-end tests for bilingual PDF overlay export."""

from pathlib import Path

import fitz
import pytest

from src.formatter.pdf_overlay import overlay_translation
from src.parser.extractor import TextBlock, extract_document_with_layout


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal 1-page PDF with real selectable text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter
    page.insert_text((50, 100), "This is the first test sentence.", fontsize=10)
    page.insert_text((50, 120), "Another paragraph with more content here.", fontsize=10)
    page.insert_text((50, 140), "A third line to ensure block extraction works.", fontsize=10)
    pdf_path = tmp_path / "sample.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def mock_blocks() -> list[TextBlock]:
    return [
        TextBlock(
            page=0,
            bbox=(50.0, 100.0, 562.0, 120.0),
            text="This is a test sentence.",
            font_size=10.0,
            block_id="abc123",
            font_name="Helvetica",
        ),
        TextBlock(
            page=0,
            bbox=(50.0, 130.0, 562.0, 150.0),
            text="Another paragraph here.",
            font_size=10.0,
            block_id="def456",
            font_name="Helvetica",
        ),
    ]


class TestExtractDocumentWithLayout:

    def test_extracts_blocks_with_bboxes(self, sample_pdf):
        doc, blocks = extract_document_with_layout(sample_pdf)
        assert doc.page_count >= 1
        assert len(blocks) > 0, "Should extract at least one text block"

        for block in blocks:
            assert block.page >= 0
            assert len(block.bbox) == 4
            x0, y0, x1, y1 = block.bbox
            assert x1 >= x0
            assert y1 >= y0
            assert block.text
            assert block.block_id

    def test_block_ids_are_unique(self, sample_pdf):
        _, blocks = extract_document_with_layout(sample_pdf)
        block_ids = [b.block_id for b in blocks]
        assert len(block_ids) == len(set(block_ids)), "Block IDs must be unique"


class TestPdfOverlayTranslation:

    def test_overlay_produces_output_file(self, sample_pdf, mock_blocks, tmp_path):
        translations = {"abc123": "这是测试句子。", "def456": "这里是另一个段落。"}
        out_path = tmp_path / "bilingual.pdf"
        result = overlay_translation(
            src_pdf=sample_pdf,
            blocks=mock_blocks,
            translations=translations,
            output=out_path,
            mode="below",
        )
        assert result == out_path
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_output_larger_than_source(self, sample_pdf, mock_blocks, tmp_path):
        translations = {"abc123": "这是测试句子。", "def456": "这里是另一个段落。"}
        out_path = tmp_path / "larger.pdf"
        overlay_translation(
            src_pdf=sample_pdf,
            blocks=mock_blocks,
            translations=translations,
            output=out_path,
            mode="below",
        )
        assert out_path.stat().st_size > sample_pdf.stat().st_size, \
            "Bilingual PDF should be larger than original"

    def test_overlay_can_be_reopened_by_fitz(self, sample_pdf, mock_blocks, tmp_path):
        translations = {"abc123": "测试", "def456": "测试段落"}
        out_path = tmp_path / "reopen.pdf"
        result = overlay_translation(
            src_pdf=sample_pdf,
            blocks=mock_blocks,
            translations=translations,
            output=out_path,
            mode="replace",
        )
        with fitz.open(result) as reopened:
            with fitz.open(sample_pdf) as orig:
                assert len(reopened) == len(orig), "Page count must match original"

    def test_all_three_modes_complete_without_error(self, sample_pdf, mock_blocks, tmp_path):
        translations = {"abc123": "below模式测试", "def456": "测试文本二"}
        for mode in ("below", "above", "replace"):
            out_path = tmp_path / f"mode_{mode}.pdf"
            result = overlay_translation(
                src_pdf=sample_pdf,
                blocks=mock_blocks,
                translations=translations,
                output=out_path,
                mode=mode,
            )
            assert result.exists(), f"Mode '{mode}' should produce output file"

    def test_missing_translations_are_skipped(self, sample_pdf, mock_blocks, tmp_path):
        translations = {"abc123": "有翻译的块"}  # def456 intentionally missing
        out_path = tmp_path / "partial.pdf"
        result = overlay_translation(
            src_pdf=sample_pdf,
            blocks=mock_blocks,
            translations=translations,
            output=out_path,
            mode="below",
        )
        assert result.exists()
        assert out_path.stat().st_size > 0


class TestTextBlockModel:

    def test_block_id_auto_generated(self):
        block = TextBlock(page=0, bbox=(0, 0, 100, 20), text="Test",
                          font_size=10.0, block_id="")
        assert block.block_id != ""
        assert len(block.block_id) == 12

    def test_bbox_properties(self):
        block = TextBlock(page=0, bbox=(50.0, 100.0, 200.0, 130.0),
                          text="Test", font_size=10.0, block_id="test")
        assert block.width == 150.0
        assert block.height == 30.0

    def test_text_ratio(self):
        block = TextBlock(page=0, bbox=(0, 0, 100, 20), text="Hello",
                          font_size=10.0, block_id="test")
        assert block.text_ratio("这是非常长的翻译文本") > 1.0
        assert block.text_ratio("短") < 1.0
        assert block.text_ratio("World") == 1.0
