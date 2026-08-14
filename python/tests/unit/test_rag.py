"""RAG 路由辅助函数单元测试 — 切块与翻译入库 doc_id 稳定性"""

from routers.rag import _chunk_text, build_translation_doc_id


class TestChunkText:
    def test_empty_text(self):
        assert _chunk_text("") == []
        assert _chunk_text("   \n\n  ") == []

    def test_single_paragraph(self):
        chunks = _chunk_text("这是单独的一段。")
        assert len(chunks) == 1
        assert chunks[0] == "这是单独的一段。"

    def test_multiple_paragraphs(self):
        text = "第一段。\n\n第二段。\n\n第三段。"
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert "第一段。" in chunks[0]
        assert "第三段。" in chunks[0]

    def test_long_text_is_chunked(self):
        text = "\n\n".join(f"第{i}段" + "内容" * 200 for i in range(30))
        chunks = _chunk_text(text)
        assert len(chunks) > 1
        assert all(c.strip() for c in chunks)

    def test_crlf_normalized(self):
        chunks = _chunk_text("第一段。\r\n\r\n第二段。")
        assert len(chunks) == 1
        assert "\r\n" not in chunks[0]


class TestBuildTranslationDocId:
    def test_stable_for_same_source(self):
        assert build_translation_doc_id("同一篇文献的原文") == build_translation_doc_id(
            "同一篇文献的原文"
        )

    def test_differs_for_different_source(self):
        assert build_translation_doc_id("文献A") != build_translation_doc_id("文献B")

    def test_prefix_and_length(self):
        doc_id = build_translation_doc_id("任意内容")
        assert doc_id.startswith("trans_")
        assert len(doc_id) == len("trans_") + 16
