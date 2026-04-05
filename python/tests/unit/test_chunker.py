"""文本切块模块单元测试"""

from src.chunker.splitter import chunk_text, Chunk, _estimate_tokens, _split_sentences


class TestEstimateTokens:
    """Token 估算"""

    def test_english_text(self) -> None:
        tokens = _estimate_tokens("Hello world, this is a test.")
        assert tokens > 0

    def test_chinese_text(self) -> None:
        tokens = _estimate_tokens("这是一段中文测试文本")
        assert tokens > 0

    def test_empty_string(self) -> None:
        assert _estimate_tokens("") >= 1


class TestSplitSentences:
    """句子分割测试"""

    def test_basic_sentences(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        parts = _split_sentences(text)
        assert len(parts) == 3
        assert parts[0] == "First sentence."
        assert parts[1] == "Second sentence."
        assert parts[2] == "Third sentence."

    def test_single_letter_abbreviation(self) -> None:
        """单字母缩写不应被切分 (J. A. B. 等)"""
        text = "Smith, J. A. proposed a new method."
        parts = _split_sentences(text)
        assert len(parts) == 1
        assert "J. A." in parts[0]

    def test_et_al_abbreviation(self) -> None:
        """et al. 不应被切分"""
        text = "Smith et al. proposed a new method. Jones confirmed the results."
        parts = _split_sentences(text)
        assert len(parts) == 2
        assert "et al." in parts[0]

    def test_fig_abbreviation(self) -> None:
        """Fig. 等缩写不应被切分"""
        text = "As shown in Fig. 3, the results are significant."
        parts = _split_sentences(text)
        assert len(parts) == 1
        assert "Fig. 3" in parts[0]

    def test_journal_abbreviation(self) -> None:
        """期刊缩写不应被切分"""
        text = "Published in Hum. Evol. 125, 50 (2018). This is important."
        parts = _split_sentences(text)
        assert len(parts) == 2
        assert "Hum. Evol." in parts[0]


class TestChunkText:
    """文本切块"""

    def test_short_text_single_chunk(self) -> None:
        text = "This is a short sentence. And another one."
        chunks = chunk_text(text, max_tokens=4096)
        assert len(chunks) == 1

    def test_sentence_strategy(self) -> None:
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, max_tokens=10, strategy="sentence")
        assert len(chunks) > 1

    def test_paragraph_strategy(self) -> None:
        text = "Para one.\n\nPara two.\n\nPara three."
        # max_tokens 足够大时合并为一块
        chunks = chunk_text(text, max_tokens=4096, strategy="paragraph")
        assert len(chunks) >= 1
        # max_tokens 很小时应产生多块
        chunks = chunk_text(text, max_tokens=2, strategy="paragraph")
        assert len(chunks) == 3

    def test_fixed_strategy(self) -> None:
        text = "A" * 200
        chunks = chunk_text(text, max_tokens=10, strategy="fixed")
        assert len(chunks) > 1

    def test_invalid_strategy(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="未知切块策略"):
            chunk_text("test", strategy="invalid")

    def test_chunk_has_required_fields(self) -> None:
        chunks = chunk_text("Hello world. Test text.")
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert isinstance(chunk.text, str)
            assert isinstance(chunk.char_count, int)
            assert isinstance(chunk.estimated_tokens, int)
            assert chunk.char_count > 0
