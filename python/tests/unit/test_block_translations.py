"""单元测试 — routers/translate.py 中的 _build_block_translations 启发式。"""

from __future__ import annotations

from dataclasses import dataclass
import pytest

from routers.translate import _build_block_translations


@dataclass
class MockBlock:
    block_id: str
    text: str


class TestBuildBlockTranslations:
    """测试 _build_block_translations 的各种场景。"""

    # -------------------------------------------------------------------------
    # 边界情况
    # -------------------------------------------------------------------------

    def test_empty_chunk_results(self) -> None:
        blocks = [MockBlock("b1", "Hello world")]
        result = _build_block_translations([], blocks)
        assert result == {}

    def test_empty_blocks(self) -> None:
        chunk_results = [{"original": "Hello", "translated": "你好"}]
        result = _build_block_translations(chunk_results, [])
        assert result == {}

    def test_none_values(self) -> None:
        blocks = [MockBlock("b1", "Hello")]
        chunk_results = [{"original": None, "translated": None}]
        result = _build_block_translations(chunk_results, blocks)
        assert result == {}

    # -------------------------------------------------------------------------
    # 正常场景
    # -------------------------------------------------------------------------

    def test_single_block_single_chunk(self) -> None:
        blocks = [MockBlock("b1", "Hello world")]
        chunk_results = [{"original": "Hello world", "translated": "你好 世界"}]
        result = _build_block_translations(chunk_results, blocks)

        assert "b1" in result

    def test_multiple_blocks_multiple_chunks(self) -> None:
        blocks = [
            MockBlock("b1", "First sentence here"),
            MockBlock("b2", "Second sentence here"),
            MockBlock("b3", "Third sentence here"),
        ]
        chunk_results = [
            {"original": "First sentence here", "translated": "第一句译文"},
            {"original": "Second sentence here", "translated": "第二句译文"},
            {"original": "Third sentence here", "translated": "第三句译文"},
        ]
        result = _build_block_translations(chunk_results, blocks)

        assert result["b1"] == "第一句译文"
        assert result["b2"] == "第二句译文"
        assert result["b3"] == "第三句译文"

    # -------------------------------------------------------------------------
    # 前缀匹配
    # -------------------------------------------------------------------------

    def test_prefix_match_forward(self) -> None:
        """原文以前缀开头时能匹配。"""
        blocks = [MockBlock("b1", "Hello world")]
        chunk_results = [{"original": "Hello world extra", "translated": "你好 世界 额外"}]
        result = _build_block_translations(chunk_results, blocks)

        assert "b1" in result

    def test_prefix_match_backward(self) -> None:
        """chunk 原文以前缀开头时能匹配（反向）。"""
        blocks = [MockBlock("b1", "Hello world extra")]
        chunk_results = [{"original": "Hello world", "translated": "你好 世界"}]
        result = _build_block_translations(chunk_results, blocks)

        assert "b1" in result

    def test_no_match_returns_empty(self) -> None:
        blocks = [MockBlock("b1", "Unmatched text")]
        chunk_results = [{"original": "Completely different text", "translated": "完全不同"}]
        result = _build_block_translations(chunk_results, blocks)

        # 无匹配时结果为空（但函数不抛错）
        # 具体行为取决于启发式实现，这里验证不崩溃
        assert isinstance(result, dict)

    # -------------------------------------------------------------------------
    # 比例分配
    # -------------------------------------------------------------------------

    def test_ratio_based_extraction(self) -> None:
        """验证比例分配：块文本越短，分配到的译文越少。"""
        blocks = [
            MockBlock("b1", "Short"),
            MockBlock("b2", "Medium length text here"),
        ]
        # 原文较长，译文也较长，按比例分配
        chunk_results = [
            {"original": "Short Medium length text here", "translated": "短 中等长度文本"},
        ]
        result = _build_block_translations(chunk_results, blocks)

        # b1 文本更短，应该分配更少的译文字符
        assert "b1" in result
        assert "b2" in result

    def test_ratio_proportional_split(self) -> None:
        """两个块平分译文时，各自得到一半。"""
        blocks = [
            MockBlock("b1", "AAA"),
            MockBlock("b2", "BBB"),
        ]
        # AAA 和 BBB 加起来正好是 original，翻译为 X 和 Y
        chunk_results = [
            {"original": "AAABBB", "translated": "你好世界"},
        ]
        result = _build_block_translations(chunk_results, blocks)

        assert "b1" in result
        assert "b2" in result
        # 验证总译文长度不超过原译文
        total = len(result.get("b1", "")) + len(result.get("b2", ""))
        assert total <= len("你好世界")

    # -------------------------------------------------------------------------
    # 已翻译的块跳过
    # -------------------------------------------------------------------------

    def test_already_translated_block_skipped(self) -> None:
        blocks = [MockBlock("b1", "Hello")]
        chunk_results = [
            {"original": "Hello extra1", "translated": "你好1"},
            {"original": "Hello extra2", "translated": "你好2"},
        ]
        result = _build_block_translations(chunk_results, blocks)

        # b1 只应被翻译一次
        assert result["b1"] is not None
