"""块对齐翻译单元测试"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.chunker import Block, BlockChunk
from src.translator._helpers import TranslationResult
from src.translator.block_translator import (
    _align_translation_to_blocks,
    translate_block_chunk,
)


def _mk_block(bid: str, type_: str, text: str, translatable: bool = True) -> Block:
    return Block(id=bid, type=type_, text=text, translatable=translatable)


class TestAlignment:
    """对齐逻辑（不需要 LLM）"""

    def test_perfect_alignment(self) -> None:
        blocks = [
            _mk_block("b1", "paragraph", "First paragraph."),
            _mk_block("b2", "paragraph", "Second paragraph."),
            _mk_block("b3", "paragraph", "Third paragraph."),
        ]
        translation = "第一段。\n\n第二段。\n\n第三段。"
        out, aligned = _align_translation_to_blocks(blocks, translation)
        assert aligned is True
        assert len(out) == 3
        assert out[0].translated == "第一段。"
        assert out[1].translated == "第二段。"
        assert out[2].translated == "第三段。"

    def test_skips_non_translatable(self) -> None:
        blocks = [
            _mk_block("b1", "paragraph", "Para before."),
            _mk_block("b2", "formula", "$$E=mc^2$$", translatable=False),
            _mk_block("b3", "paragraph", "Para after."),
        ]
        # LLM 只看到 2 个段落（公式被跳过）
        translation = "段前。\n\n段后。"
        out, aligned = _align_translation_to_blocks(blocks, translation)
        assert aligned is True
        assert out[0].translated == "段前。"
        assert out[1].translated == "$$E=mc^2$$"  # 公式原样直通
        assert out[1].translatable is False
        assert out[2].translated == "段后。"

    def test_misaligned_falls_back(self) -> None:
        """LLM 输出段落数不等于输入数 → 走兜底分配"""
        blocks = [
            _mk_block("b1", "paragraph", "A" * 30),
            _mk_block("b2", "paragraph", "B" * 60),
        ]
        # LLM 把两段合并成一段
        translation = "中文译文一整段没有空行分隔" * 5
        out, aligned = _align_translation_to_blocks(blocks, translation)
        assert aligned is False
        # 兜底：每块都有译文（虽然按字符比例切的可能不准确）
        assert len(out) == 2
        assert all(o.translated for o in out)

    def test_no_translatable_blocks(self) -> None:
        """整 chunk 全是公式/代码 → 直通原文"""
        blocks = [
            _mk_block("b1", "formula", "$$x=1$$", translatable=False),
            _mk_block("b2", "code", "```\nprint()\n```", translatable=False),
        ]
        out, aligned = _align_translation_to_blocks(blocks, "")
        assert aligned is True
        assert out[0].translated == "$$x=1$$"
        assert out[1].translated == "```\nprint()\n```"


class TestTranslateBlockChunk:
    """整 chunk 翻译流"""

    def test_calls_client_with_joined_translatable(self) -> None:
        blocks = [
            _mk_block("b1", "paragraph", "Hello world."),
            _mk_block("b2", "formula", "$$x$$", translatable=False),
            _mk_block("b3", "paragraph", "Goodbye world."),
        ]
        chunk = BlockChunk(
            index=0,
            text="...",
            char_count=0,
            estimated_tokens=0,
            block_ids=["b1", "b2", "b3"],
        )
        blocks_by_id = {b.id: b for b in blocks}

        client = MagicMock()
        client.translate.return_value = TranslationResult(
            original="Hello world.\n\nGoodbye world.",
            translated="你好世界。\n\n再见世界。",
            model="mock",
        )

        result = asyncio.run(translate_block_chunk(client, chunk, blocks_by_id))
        assert result.aligned is True
        assert result.block_translations[0].translated == "你好世界。"
        assert result.block_translations[1].translated == "$$x$$"
        assert result.block_translations[2].translated == "再见世界。"

        # 客户端只应该看到可翻译块的拼接
        called_text = client.translate.call_args[0][0]
        assert "Hello world." in called_text
        assert "Goodbye world." in called_text
        assert "$$x$$" not in called_text

    def test_client_failure_falls_back_to_original(self) -> None:
        blocks = [_mk_block("b1", "paragraph", "Source text.")]
        chunk = BlockChunk(
            index=0,
            text="Source text.",
            char_count=12,
            estimated_tokens=3,
            block_ids=["b1"],
        )
        client = MagicMock()
        client.translate.side_effect = ConnectionError("network down")

        result = asyncio.run(translate_block_chunk(client, chunk, {b.id: b for b in blocks}))
        assert result.is_fallback is True
        assert result.error is not None
        assert result.block_translations[0].translated == "Source text."  # 原文直通

    def test_all_non_translatable_skips_llm(self) -> None:
        blocks = [
            _mk_block("b1", "formula", "$$y=x$$", translatable=False),
            _mk_block("b2", "code", "```\nx=1\n```", translatable=False),
        ]
        chunk = BlockChunk(
            index=0,
            text="...",
            char_count=0,
            estimated_tokens=0,
            block_ids=["b1", "b2"],
        )
        client = MagicMock()
        result = asyncio.run(
            translate_block_chunk(client, chunk, {b.id: b for b in blocks})
        )
        # LLM 未被调用
        client.translate.assert_not_called()
        assert result.aligned is True
        assert result.block_translations[0].translated == "$$y=x$$"
