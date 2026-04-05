"""翻译客户端单元测试"""

from src.translator.ollama_client import (
    _strip_think_tags,
    _strip_preamble,
    _validate_translation,
    TranslationResult,
)


def _make_result(original: str, translated: str) -> TranslationResult:
    return TranslationResult(original=original, translated=translated, model="test")


class TestStripThinkTags:
    """Qwen3 think 标签清理"""

    def test_basic_think_tag(self) -> None:
        text = "<think >some reasoning</think >翻译结果"
        assert _strip_think_tags(text) == "翻译结果"

    def test_multiline_think_tag(self) -> None:
        text = "<think >\nline1\nline2\n</think >result"
        assert _strip_think_tags(text) == "result"

    def test_no_think_tag(self) -> None:
        text = "直接翻译结果"
        assert _strip_think_tags(text) == "直接翻译结果"

    def test_empty_after_strip(self) -> None:
        text = "<think >only thinking</think >"
        assert _strip_think_tags(text) == ""


class TestStripPreamble:
    """前言清理"""

    def test_here_is_translation(self) -> None:
        text = "Here is the translation:\n你好世界"
        assert _strip_preamble(text) == "你好世界"

    def test_chinese_preamble(self) -> None:
        text = "以下是翻译：\n你好世界"
        assert _strip_preamble(text) == "你好世界"

    def test_no_preamble(self) -> None:
        text = "这是翻译结果"
        assert _strip_preamble(text) == text


class TestValidateTranslation:
    """翻译结果校验"""

    def test_valid_translation(self) -> None:
        r = _make_result("Hello world, this is a test.", "你好世界，这是一个测试。")
        assert _validate_translation(r) is True

    def test_empty_translation(self) -> None:
        r = _make_result("Hello world", "")
        assert _validate_translation(r) is False

    def test_too_short_translation(self) -> None:
        r = _make_result("A" * 100, "短")
        assert _validate_translation(r) is False
