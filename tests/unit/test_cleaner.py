"""文本清洗模块单元测试"""

from src.cleaner.pipeline import clean_text


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
