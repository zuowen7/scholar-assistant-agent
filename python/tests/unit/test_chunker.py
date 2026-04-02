"""文本切块模块单元测试"""

from src.chunker.splitter import chunk_text, Chunk, _estimate_tokens


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
        try:
            chunk_text("test", strategy="invalid")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_chunk_has_required_fields(self) -> None:
        chunks = chunk_text("Hello world. Test text.")
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert isinstance(chunk.text, str)
            assert isinstance(chunk.char_count, int)
            assert isinstance(chunk.estimated_tokens, int)
            assert chunk.char_count > 0
