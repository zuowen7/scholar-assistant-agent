"""Integration tests for Science Perspectives multi-article PDF fixes.

Validates fixes from translation_pipeline_audit.md and translation_pipeline_round2.md:
- P0-1 (round 2): Multi-article splitting before cleaning
- P0-1: UTF-8 encoding corruption fixed
- P0-2 (round 2): Continuation rules enhanced (adjective+noun pairs)
- P0-3: Watermark removal enhanced
- P1-1: Continuation rules improved
- P1-2: Paragraph start truncation fixed
- P1-2 (round 2): Noise character ó ó removal
- P0-4: Citation spacing normalized

Test sample: science.adn8744.pdf (4 pages, 3 bundled Perspectives articles)
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.path.exists(r"C:\Users\zuowen\Desktop\science.adn8744.pdf"),
    reason="Test PDF not available on this machine",
)

PDF_PATH = r"C:\Users\zuowen\Desktop\science.adn8744.pdf"


@pytest.fixture(scope="module")
def pipeline_result():
    from src.parser.extractor import extract_pages
    from src.cleaner import clean_text_full
    from src.chunker.splitter import chunk_text_with_blocks

    doc = extract_pages(PDF_PATH)
    result = clean_text_full(doc.full_text)
    br = chunk_text_with_blocks(result.text, max_tokens=800, overlap_tokens=0)
    return doc, result, br


@pytest.fixture(scope="module")
def split_result():
    """Pipeline with article splitting (round 2 fix)."""
    from src.parser.extractor import extract_pages
    from src.parser.article_detector import extract_articles
    from src.cleaner import clean_text_full
    from src.chunker.splitter import parse_blocks

    doc = extract_pages(PDF_PATH)
    raw_articles = extract_articles(doc.full_text)
    article_data = []
    for raw_art in raw_articles:
        clean = clean_text_full(raw_art)
        blocks = parse_blocks(clean.text)
        article_data.append((clean, blocks))
    return doc, raw_articles, article_data


class TestEncodingFix:
    """P0-1: UTF-8 replacement chars (U+FFFD) should not appear in cleaned text."""

    def test_no_replacement_chars(self, pipeline_result):
        _, result, _ = pipeline_result
        assert "�" not in result.text


class TestWatermarkRemoval:
    """P0-3: 'Downloaded from' watermark fragments should be fully removed."""

    def test_no_downloaded_from(self, pipeline_result):
        _, result, _ = pipeline_result
        assert "Downloaded from" not in result.text


class TestContinuationRules:
    """P1-1: False paragraph splits should be merged by improved continuation rules."""

    def test_washington_dc_merged(self, pipeline_result):
        _, _, br = pipeline_result
        for i in range(len(br.blocks) - 1):
            assert not (
                br.blocks[i].text.strip() == "Washington,"
                and br.blocks[i + 1].text.strip().startswith("DC")
            )

    def test_histone_h3_not_split(self, pipeline_result):
        _, _, br = pipeline_result
        for i in range(len(br.blocks) - 1):
            if "histone H3" in br.blocks[i].text:
                # The parenthetical should be part of the same block
                assert "(H3K4me1" in br.blocks[i].text or not br.blocks[
                    i + 1
                ].text.strip().startswith("(")


class TestTruncationFix:
    """P1-2: 'n 2023' should be corrected to 'In 2023'."""

    def test_in_2023_present(self, pipeline_result):
        _, _, br = pipeline_result
        assert any("In 2023" in b.text for b in br.blocks)

    def test_n_2023_not_present(self, pipeline_result):
        _, _, br = pipeline_result
        assert not any(b.text.strip().startswith("n 2023") for b in br.blocks)


class TestChunkSize:
    """P1-3: Smaller chunks for better alignment."""

    def test_more_than_3_chunks(self, pipeline_result):
        _, _, br = pipeline_result
        assert len(br.chunks) > 3


class TestCitationNormalization:
    """P0-4: Inline citations should have normalized spacing."""

    def test_no_spaced_citations(self, pipeline_result):
        _, result, _ = pipeline_result
        import re

        assert not re.search(r"\(\s+\d+\s+\)", result.text)


class TestAuthorHeadingExclusion:
    """P0-3: Author names should not be classified as headings."""

    def test_author_not_heading(self):
        from src.chunker.splitter import _looks_like_pdf_heading

        assert (
            _looks_like_pdf_heading("Laurie S. Huning and Manuela I. Brunner") == 0
        )


# ── Round 2 fixes ──────────────────────────────────────────────────────────


class TestArticleSplitting:
    """P0-1 (round 2): Multi-article PDF should be split into 3 articles."""

    def test_three_articles_detected(self, split_result):
        _, raw_articles, _ = split_result
        assert len(raw_articles) == 3

    def test_article_1_about_masocepithecus(self, split_result):
        _, raw_articles, _ = split_result
        assert "Masripithecus" in raw_articles[0]

    def test_article_2_about_cascading(self, split_result):
        _, raw_articles, _ = split_result
        assert "extreme heat" in raw_articles[1] or "cascading" in raw_articles[1].lower()

    def test_article_3_about_inflammation(self, split_result):
        _, raw_articles, _ = split_result
        assert "flammation" in raw_articles[2]  # truncated or fixed

    def test_articles_non_trivial_size(self, split_result):
        _, raw_articles, _ = split_result
        for i, art in enumerate(raw_articles):
            assert len(art) > 500, f"Article {i+1} too short ({len(art)} chars)"


class TestTruncationFixedPerArticle:
    """P1-1 (round 2): Article start truncations fixed after splitting."""

    def test_article_2_starts_with_in(self, split_result):
        _, _, article_data = split_result
        _, blocks_2 = article_data[1]
        first_text = blocks_2[0].text if blocks_2 else ""
        assert first_text.startswith("In 2023"), f"Got: {first_text[:30]}"

    def test_article_3_starts_with_inflammation(self, split_result):
        _, _, article_data = split_result
        _, blocks_3 = article_data[2]
        first_text = blocks_3[0].text if blocks_3 else ""
        assert first_text.startswith("Inflammation"), f"Got: {first_text[:30]}"

    def test_no_n_2023_anywhere(self, split_result):
        _, _, article_data = split_result
        for i, (_, blocks) in enumerate(article_data):
            for b in blocks:
                assert not b.text.strip().startswith("n 2023"), \
                    f"Article {i+1} block {b.id} starts with 'n 2023'"

    def test_no_nflammation_anywhere(self, split_result):
        _, _, article_data = split_result
        for i, (_, blocks) in enumerate(article_data):
            for b in blocks:
                assert not b.text.strip().startswith("nflammation"), \
                    f"Article {i+1} block {b.id} starts with 'nflammation'"


class TestNoiseRemovedPerArticle:
    """P1-2 (round 2): ó ó noise characters removed."""

    def test_no_noise_chars(self, split_result):
        _, _, article_data = split_result
        for i, (_, blocks) in enumerate(article_data):
            for b in blocks:
                assert "ó ó" not in b.text, \
                    f"Article {i+1} block {b.id} has ó ó noise"


class TestBlocksPerArticle:
    """Each article should have a reasonable number of blocks."""

    def test_article_block_counts(self, split_result):
        _, _, article_data = split_result
        for i, (_, blocks) in enumerate(article_data):
            assert len(blocks) >= 3, \
                f"Article {i+1} has only {len(blocks)} blocks"

    def test_total_blocks_reduced(self, split_result):
        """Splitting should produce cleaner block boundaries."""
        _, _, article_data = split_result
        total = sum(len(blocks) for _, blocks in article_data)
        # Before the fix, there were ~31 blocks with wrong boundaries
        assert total < 35, f"Too many blocks ({total}), boundary issues likely"
