"""PDF 解析模块单元测试"""

from unittest.mock import MagicMock, patch

from src.parser.extractor import (
    DocumentContent,
    PageContent,
    _detect_columns,
    _extract_dual_column_with_char_spaces,
    _filter_header_footer,
    _repair_word_spacing,
)


class TestPageContent:
    """PageContent 数据类"""

    def test_default_dual_column_false(self) -> None:
        pc = PageContent(page_num=1, text="hello", width=600, height=800)
        assert pc.is_dual_column is False

    def test_explicit_dual_column(self) -> None:
        pc = PageContent(page_num=1, text="hello", width=600, height=800, is_dual_column=True)
        assert pc.is_dual_column is True


class TestDocumentContent:
    """DocumentContent 数据类"""

    def test_full_text(self) -> None:
        pages = [
            PageContent(page_num=1, text="Page one", width=600, height=800),
            PageContent(page_num=2, text="Page two", width=600, height=800),
        ]
        doc = DocumentContent(pages=pages, source_path="test.pdf")
        assert "Page one" in doc.full_text
        assert "Page two" in doc.full_text

    def test_empty_pages_skipped(self) -> None:
        pages = [
            PageContent(page_num=1, text="Content", width=600, height=800),
            PageContent(page_num=2, text="   ", width=600, height=800),
        ]
        doc = DocumentContent(pages=pages, source_path="test.pdf")
        assert doc.full_text == "Content"


class TestDetectColumns:
    """双栏检测逻辑"""

    def _make_page(self, width: float, words: list[dict]) -> MagicMock:
        page = MagicMock()
        page.width = width
        page.extract_words.return_value = words
        return page

    def _word(self, x0: float, x1: float, text: str = "w") -> dict:
        return {"text": text, "x0": x0, "x1": x1, "top": 100, "bottom": 110}

    def test_single_column_few_words(self) -> None:
        """词数太少 → 单栏"""
        words = [self._word(50, 100) for _ in range(10)]
        page = self._make_page(600, words)
        assert _detect_columns(page) is False

    def test_single_column_left_only(self) -> None:
        """所有词都在左侧 → 单栏"""
        words = [self._word(50, 150) for _ in range(200)]
        page = self._make_page(600, words)
        assert _detect_columns(page) is False

    def test_dual_column_detected(self) -> None:
        """左右两侧都有大量词 → 双栏"""
        words = []
        # 左栏 100 个词
        for _ in range(100):
            words.append(self._word(50, 150))
        # 右栏 100 个词
        for _ in range(100):
            words.append(self._word(450, 550))
        page = self._make_page(600, words)
        assert _detect_columns(page) is True

    def test_dual_column_with_center_content(self) -> None:
        """中间有大量内容时仍判为双栏"""
        words = []
        for _ in range(100):
            words.append(self._word(50, 150))
        for _ in range(100):
            words.append(self._word(450, 550))
        # 中间少量跨栏内容
        for _ in range(10):
            words.append(self._word(280, 320))
        page = self._make_page(600, words)
        assert _detect_columns(page) is True

    def test_not_dual_if_center_dense(self) -> None:
        """中间区域密集 → 不判定为双栏"""
        words = []
        for _ in range(100):
            words.append(self._word(50, 150))
        for _ in range(100):
            words.append(self._word(450, 550))
        # 中间大量内容
        for _ in range(60):
            words.append(self._word(280, 320))
        page = self._make_page(600, words)
        assert _detect_columns(page) is False


class TestFilterHeaderFooter:
    """页眉页脚过滤"""

    def test_returns_text_when_no_words(self) -> None:
        page = MagicMock()
        page.extract_words.return_value = []
        result = _filter_header_footer("some text", page)
        assert result == "some text"

    def test_returns_text_when_all_body(self) -> None:
        page = MagicMock()
        page.width = 600
        page.height = 800
        # 所有词都在正文区域
        words = [{"text": "hello", "x0": 50, "x1": 100, "top": 100, "bottom": 110}]
        page.extract_words.return_value = words
        result = _filter_header_footer("hello", page)
        assert result == "hello"


class TestMissingSpaceRepair:
    @staticmethod
    def _chars(text: str, *, top: float, start: float, word_gaps: set[int]) -> list[dict]:
        chars: list[dict] = []
        x = start
        for index, char in enumerate(text):
            if char == " ":
                x += 1.2
                continue
            if index in word_gaps:
                x += 1.2
            chars.append({"text": char, "x0": x, "x1": x + 0.4, "top": top, "size": 9.0})
            x += 0.4
        return chars

    def test_repairs_collapsed_word_from_character_gaps(self) -> None:
        page = MagicMock()
        page.chars = self._chars(
            "Journalists rely on agency",
            top=100.0,
            start=50.0,
            word_gaps={12, 17, 20},
        )
        word = {
            "text": "Journalistsrelyonagency",
            "x0": 50.0,
            "x1": page.chars[-1]["x1"],
            "top": 100.0,
        }

        repaired = _repair_word_spacing(page, word)

        assert repaired["text"] == "Journalists rely on agency"
        assert repaired["x0"] == word["x0"]
        assert repaired["x1"] == word["x1"]

    def test_dual_column_character_fallback_keeps_columns_separate(self) -> None:
        page = MagicMock()
        page.width = 600.0
        page.height = 800.0
        left = self._chars("Left one", top=100.0, start=60.0, word_gaps={5})
        left += self._chars("Left two", top=120.0, start=60.0, word_gaps={5})
        right = self._chars("Right one", top=100.0, start=360.0, word_gaps={6})
        right += self._chars("Right two", top=120.0, start=360.0, word_gaps={6})
        page.chars = left + right

        text = _extract_dual_column_with_char_spaces(page)

        assert text == "Left one\nLeft two\n\nRight one\nRight two"
