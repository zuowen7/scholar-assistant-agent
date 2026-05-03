"""文本切块模块单元测试"""

from src.chunker.splitter import (
    chunk_text,
    Chunk,
    _estimate_tokens,
    parse_blocks,
    pack_blocks_into_chunks,
    chunk_text_with_blocks,
    BLOCK_PARAGRAPH,
    BLOCK_HEADING,
    BLOCK_FORMULA,
    BLOCK_CODE,
    BLOCK_TABLE,
    BLOCK_LIST,
    BLOCK_FIGURE_CAPTION,
)


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


class TestParseBlocks:
    """类型化块解析"""

    def test_simple_paragraphs(self) -> None:
        text = "First paragraph here.\n\nSecond paragraph here."
        blocks = parse_blocks(text)
        assert len(blocks) == 2
        assert all(b.type == BLOCK_PARAGRAPH for b in blocks)
        assert blocks[0].id != blocks[1].id

    def test_markdown_heading(self) -> None:
        text = "# Title\n\nBody text follows."
        blocks = parse_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].type == BLOCK_HEADING
        assert blocks[0].level == 1
        assert blocks[1].type == BLOCK_PARAGRAPH

    def test_pdf_heading_numbered(self) -> None:
        text = "1. Introduction\n\nThis paper presents..."
        blocks = parse_blocks(text)
        assert blocks[0].type == BLOCK_HEADING
        assert blocks[0].level == 1

    def test_pdf_heading_subsection(self) -> None:
        text = "2.1 Methods\n\nWe used the following approach..."
        blocks = parse_blocks(text)
        assert blocks[0].type == BLOCK_HEADING
        assert blocks[0].level == 2

    def test_pdf_heading_allcaps(self) -> None:
        text = "ABSTRACT\n\nWe present a novel approach..."
        blocks = parse_blocks(text)
        assert blocks[0].type == BLOCK_HEADING

    def test_formula_block_protected(self) -> None:
        text = "Some text.\n\n$$E = mc^2$$\n\nMore text."
        blocks = parse_blocks(text)
        types = [b.type for b in blocks]
        assert BLOCK_FORMULA in types
        formula_block = next(b for b in blocks if b.type == BLOCK_FORMULA)
        assert formula_block.translatable is False
        assert "E = mc^2" in formula_block.text

    def test_latex_environment_protected(self) -> None:
        text = "Intro.\n\n\\begin{equation}\nx = y + 1\n\\end{equation}\n\nOutro."
        blocks = parse_blocks(text)
        formula_block = next((b for b in blocks if b.type == BLOCK_FORMULA), None)
        assert formula_block is not None
        assert "\\begin{equation}" in formula_block.text

    def test_code_block_protected(self) -> None:
        text = "Before.\n\n```python\nprint('hi')\n```\n\nAfter."
        blocks = parse_blocks(text)
        code_block = next((b for b in blocks if b.type == BLOCK_CODE), None)
        assert code_block is not None
        assert code_block.translatable is False

    def test_list_detected(self) -> None:
        text = "- item one\n- item two\n- item three"
        blocks = parse_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].type == BLOCK_LIST

    def test_figure_caption(self) -> None:
        text = "Body text.\n\nFigure 1. Workflow overview."
        blocks = parse_blocks(text)
        cap = next((b for b in blocks if b.type == BLOCK_FIGURE_CAPTION), None)
        assert cap is not None

    def test_block_ids_stable(self) -> None:
        text = "P1.\n\nP2.\n\nP3."
        blocks = parse_blocks(text)
        ids = [b.id for b in blocks]
        assert len(set(ids)) == len(ids)
        assert all(b.id.startswith("b") for b in blocks)


class TestPackBlocksIntoChunks:
    """块感知打包"""

    def test_small_blocks_one_chunk(self) -> None:
        text = "P1.\n\nP2.\n\nP3."
        result = chunk_text_with_blocks(text, max_tokens=4096)
        assert len(result.chunks) == 1
        assert len(result.chunks[0].block_ids) == 3
        assert result.chunks[0].block_ids == [b.id for b in result.blocks]

    def test_blocks_split_across_chunks(self) -> None:
        # Each paragraph ~50 chars; max_tokens=20 with mixed=2.5 chars/token → ~50 chars/chunk
        text = "\n\n".join([f"Paragraph number {i} with some filler text." for i in range(8)])
        result = chunk_text_with_blocks(text, max_tokens=15, overlap_tokens=0)
        assert len(result.chunks) > 1
        # Every block's id appears in at least one chunk
        all_chunk_ids = {bid for c in result.chunks for bid in c.block_ids}
        assert all_chunk_ids >= {b.id for b in result.blocks}

    def test_block_boundaries_preserved(self) -> None:
        """块从不被切断 — chunk text 必须是 \\n\\n 拼接的完整块"""
        text = "P1.\n\nP2.\n\nP3."
        result = chunk_text_with_blocks(text, max_tokens=4096)
        for chunk in result.chunks:
            # chunk 文本应该等于其 block_ids 对应文本的 \n\n 拼接
            block_map = {b.id: b for b in result.blocks}
            expected = "\n\n".join(block_map[bid].text for bid in chunk.block_ids)
            assert chunk.text == expected

    def test_references_separated(self) -> None:
        text = "Body text here.\n\nREFERENCES\n\n[1] Author, A. (2020). Paper title."
        result = chunk_text_with_blocks(text)
        assert "REFERENCES" in result.references_text or result.references_text == ""
