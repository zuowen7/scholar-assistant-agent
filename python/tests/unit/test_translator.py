"""翻译客户端单元测试"""

from src.translator.ollama_client import _strip_think_tags


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
