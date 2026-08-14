"""RAG 路由辅助函数单元测试 — 切块、翻译入库 doc_id 稳定性与检索去重"""

from routers.rag import _chunk_text, _dedupe_hits, build_translation_doc_id


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


class TestDedupeHits:
    def _mk(self, n: int) -> tuple[list[str], list[str], list[dict | None], list[float | None]]:
        ids = [f"chunk{i}" for i in range(n)]
        documents = [f"text{i}" for i in range(n)]
        metadatas = [{"doc_id": f"doc{i % 3}", "title": f"t{i % 3}"} for i in range(n)]
        distances = [float(i) for i in range(n)]
        return ids, documents, metadatas, distances

    def test_caps_per_doc_at_two(self):
        ids, documents, metadatas, distances = self._mk(9)
        hits = _dedupe_hits(ids, documents, metadatas, distances, top_k=9)
        doc_ids = [h["doc_id"] for h in hits]
        # 3 篇文档 × 每篇 2 个 chunk = 6 条
        assert len(hits) == 6
        assert doc_ids.count("doc0") == 2
        assert doc_ids.count("doc1") == 2
        assert doc_ids.count("doc2") == 2

    def test_respects_top_k(self):
        ids, documents, metadatas, distances = self._mk(9)
        hits = _dedupe_hits(ids, documents, metadatas, distances, top_k=3)
        assert len(hits) == 3
        # 保持相关性顺序：最靠前的 chunk 先保留
        assert hits[0]["chunk_id"] == "chunk0"

    def test_missing_metadata_falls_back_to_chunk_id(self):
        hits = _dedupe_hits(["c1", "c2"], ["a", "b"], [None, None], [0.1, 0.2], top_k=2)
        assert hits[0]["doc_id"] == "c1"
        assert hits[1]["doc_id"] == "c2"

    def test_empty(self):
        assert _dedupe_hits([], [], [], [], top_k=5) == []
