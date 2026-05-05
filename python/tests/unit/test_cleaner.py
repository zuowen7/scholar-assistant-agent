"""文本清洗模块单元测试"""

from src.cleaner.pipeline import (
    clean_text,
    clean_text_full,
    _remove_watermarks,
    _detect_references,
    _remove_orphan_unicode,
    _is_continuation,
)


class TestFixHyphenation:
    """连字符断词修复"""

    def test_basic_hyphenation(self) -> None:
        assert clean_text("infor-\nmation") == "information"

    def test_multiple_hyphenations(self) -> None:
        text = "trans-\nlation and infor-\nmation"
        result = clean_text(text)
        assert "translation" in result
        assert "information" in result


class TestMergeParagraphLines:
    """段落内换行合并"""

    def test_single_paragraph_split(self) -> None:
        text = "This is the first line\nof a single paragraph."
        result = clean_text(text)
        assert "first line of a single paragraph." in result

    def test_separate_paragraphs_preserved(self) -> None:
        text = "First paragraph ends.\n\nSecond paragraph here."
        result = clean_text(text)
        assert "First paragraph ends." in result
        assert "Second paragraph here." in result


class TestRemovePageNumbers:
    """页码移除"""

    def test_bare_number(self) -> None:
        text = "Some text\n\n12\n\nMore text"
        result = clean_text(text)
        assert "12" not in result.split("\n")

    def test_dashed_number(self) -> None:
        text = "Text above\n- 42 -\nText below"
        result = clean_text(text)
        assert "- 42 -" not in result


class TestNormalizeWhitespace:
    """空白规范化"""

    def test_multiple_spaces(self) -> None:
        text = "too   many    spaces"
        result = clean_text(text)
        assert "too many spaces" in result

    def test_tabs(self) -> None:
        text = "tab\there"
        result = clean_text(text)
        assert "tab here" in result


class TestRemoveWatermarks:
    """水印过滤"""

    def test_downloaded_from(self) -> None:
        text = "Body text\nDownloaded from https://science.org on March 2026\nMore body"
        result = _remove_watermarks(text)
        assert "Downloaded from" not in result
        assert "Body text" in result
        assert "More body" in result

    def test_journal_header(self) -> None:
        text = "PERSPECTIVES\nSome article text here."
        result = _remove_watermarks(text)
        assert "PERSPECTIVES" not in result
        assert "Some article text here." in result

    def test_science_date_line(self) -> None:
        text = "1322 26 MARCH 2026 Science\nArticle begins here."
        result = _remove_watermarks(text)
        assert "1322 26 MARCH 2026 Science" not in result
        assert "Article begins here." in result

    def test_no_false_positives(self) -> None:
        text = "This is normal text about perspectives in science."
        result = _remove_watermarks(text)
        assert result == text


class TestDetectReferences:
    """引用区检测"""

    def test_references_section(self) -> None:
        text = "Main text here.\n\nREFERENCES\n1. Smith et al."
        pos, ref_text = _detect_references(text)
        assert pos >= 0
        assert "REFERENCES" in ref_text

    def test_references_and_notes(self) -> None:
        text = "Body.\n\nREFERENCES AND NOTES\n1. Author (2020)."
        pos, ref_text = _detect_references(text)
        assert pos >= 0
        assert "REFERENCES AND NOTES" in ref_text

    def test_bibliography(self) -> None:
        text = "End of article.\n\nBIBLIOGRAPHY\nItem 1."
        pos, ref_text = _detect_references(text)
        assert pos >= 0
        assert "BIBLIOGRAPHY" in ref_text

    def test_no_references(self) -> None:
        text = "Just a regular article with no references section."
        pos, ref_text = _detect_references(text)
        assert pos == -1
        assert ref_text == ""

    def test_case_insensitive(self) -> None:
        text = "Text.\n\nReferences\n1. Item."
        pos, ref_text = _detect_references(text)
        assert pos >= 0

    def test_supplementary_materials(self) -> None:
        text = "Conclusion.\n\nSUPPLEMENTARY MATERIALS\nFigure S1."
        pos, ref_text = _detect_references(text)
        assert pos >= 0
        assert "SUPPLEMENTARY MATERIALS" in ref_text


class TestCleanTextFull:
    """完整清洗结果"""

    def test_clean_result_no_references(self) -> None:
        result = clean_text_full("Simple text.\nMore text.")
        assert result.has_references is False
        assert result.references_start == -1
        assert result.references_text == ""

    def test_clean_result_with_references(self) -> None:
        text = "Main body.\n\nREFERENCES\n1. Smith."
        result = clean_text_full(text)
        assert result.has_references is True
        assert result.references_start >= 0
        assert "REFERENCES" in result.references_text
        # 正文部分应包含 body 但不含引用
        assert "Main body" in result.text


class TestRemoveOrphanUnicode:
    """P1-2: 噪声字符 ó ó 移除"""

    def test_standalone_noise_removed(self):
        text = "Some text.\nó ó\nMore text."
        result = _remove_orphan_unicode(text)
        assert "ó ó" not in result
        assert "Some text." in result
        assert "More text." in result

    def test_inline_noise_at_line_end_removed(self):
        text = "waiting to be discovered. ó ó"
        result = _remove_orphan_unicode(text)
        assert "ó ó" not in result
        assert "waiting to be discovered." in result

    def test_single_noise_char_removed(self):
        text = "Text above\nñ\nText below"
        result = _remove_orphan_unicode(text)
        assert "ñ" not in result.split("\n")

    def test_chinese_text_preserved(self):
        text = "这是中文文本\n另一行中文"
        result = _remove_orphan_unicode(text)
        assert "中文" in result

    def test_normal_accented_text_preserved(self):
        text = "The role of café in culture."
        result = _remove_orphan_unicode(text)
        assert "café" in result


class TestContinuationRules:
    """P0-2: 形容词+名词续行规则"""

    def test_other_countries_merged(self):
        prev = "deficits in other"
        cur = "countries (for example,"
        assert _is_continuation(prev, cur) is True

    def test_western_australia_merged(self):
        prev = "drought in western"
        cur = "Australia, and cool"
        assert _is_continuation(prev, cur) is True

    def test_these_effects_merged(self):
        prev = "manifestations of these"
        cur = "effects on society"
        assert _is_continuation(prev, cur) is True

    def test_mid_sentence_countries(self):
        prev = "This affected many"
        cur = "countries around the world"
        assert _is_continuation(prev, cur) is True

    def test_mid_sentence_which(self):
        prev = "A complex system"
        cur = "which includes many components"
        assert _is_continuation(prev, cur) is True

    def test_new_paragraph_not_merged(self):
        prev = "This concludes the section."
        cur = "Introduction to the next topic"
        assert _is_continuation(prev, cur) is False
