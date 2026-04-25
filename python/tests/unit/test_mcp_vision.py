"""MCP Vision 和 Citation 索引单元测试"""

import pytest
from src.mcp.vision_client import VisionClient, VisionResult
from src.citation.indexer import CitationIndexer, CitationEntry


class TestVisionClient:
    def test_vision_result_to_dict(self):
        result = VisionResult(
            text="这是一张柱状图",
            chart_type="bar",
            chart_description="年度销售数据",
            table_data=[["年份", "销售额"], ["2023", "100万"]],
            key_findings=["2023年最高"],
        )
        d = result.to_dict()
        assert d["text"] == "这是一张柱状图"
        assert d["chart_type"] == "bar"
        assert d["table_data"] == [["年份", "销售额"], ["2023", "100万"]]

    def test_vision_result_empty(self):
        result = VisionResult()
        assert result.text == ""
        assert result.chart_type is None
        assert result.table_data is None
        d = result.to_dict()
        assert d["text"] == ""


class TestCitationIndexer:
    def test_extract_simple_citation(self):
        indexer = CitationIndexer()
        keys = indexer.extract_citations("根据 [@smith2020] 的研究...")
        assert "smith2020" in keys

    def test_extract_multiple_citations(self):
        indexer = CitationIndexer()
        keys = indexer.extract_citations("[@a] 和 [@b] 以及 [@c]")
        assert keys == ["a", "b", "c"]

    def test_extract_citation_with_page(self):
        indexer = CitationIndexer()
        keys = indexer.extract_citations("[@smith2020, p.123]")
        assert "smith2020" in keys

    def test_extract_duplicate_citations(self):
        indexer = CitationIndexer()
        keys = indexer.extract_citations("[@a] 和 [@a] 和 [@b]")
        assert keys == ["a", "a", "b"]

    def test_build_index(self):
        indexer = CitationIndexer()
        index = indexer.build_index("[@b] 和 [@a] 和 [@b]")
        assert index["b"] == 1  # b 先出现
        assert index["a"] == 2

    def test_replace_citations(self):
        indexer = CitationIndexer()
        text = "[@smith2020] 和 [@jones2021]"
        index = indexer.build_index(text)
        replaced = indexer.replace_citations(text, index)
        assert "[1]" in replaced
        assert "[2]" in replaced
        assert "@smith2020" not in replaced

    def test_replace_citations_with_page(self):
        indexer = CitationIndexer()
        text = "[@smith2020, p.123]"
        index = indexer.build_index(text)
        replaced = indexer.replace_citations(text, index)
        assert "[1, p.123]" in replaced

    def test_render_bibliography_ieee(self):
        indexer = CitationIndexer()
        indexer.set_bibliography([
            {"key": "smith2020", "author": "Smith, J.", "title": "Deep Learning", "year": "2020"},
        ])
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="ieee")
        assert "[1]" in bib
        assert "Smith, J." in bib
        assert "Deep Learning" in bib

    def test_render_bibliography_apa(self):
        indexer = CitationIndexer()
        indexer.set_bibliography([
            {"key": "smith2020", "author": "Smith, J.", "title": "Deep Learning", "year": "2020"},
        ])
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="apa")
        assert "[1]" in bib
        assert "(2020)" in bib

    def test_render_bibliography_gbt7714(self):
        indexer = CitationIndexer()
        indexer.set_bibliography([
            {"key": "smith2020", "author": "Smith, J.", "title": "Deep Learning", "journal": "AI Journal", "year": "2020"},
        ])
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="gbt7714")
        assert "[1]" in bib
        assert "Smith, J." in bib

    def test_process_full_workflow(self):
        indexer = CitationIndexer()
        indexer.set_bibliography([
            {"key": "smith2020", "author": "Smith, J.", "title": "Deep Learning", "year": "2020"},
            {"key": "jones2021", "author": "Jones, A.", "title": "AI Advances", "year": "2021"},
        ])

        text = "[@jones2021] 指出 [@smith2020] 的方法有效"
        result = indexer.process(text)

        assert result["text"] != text  # 已替换
        assert "[1]" in result["text"] or "[2]" in result["text"]
        assert len(result["citations"]) == 2
        assert result["bibliography"]  # 有参考文献节
