"""MCP Vision 和 Citation 索引单元测试"""

import sys
import types
from unittest.mock import AsyncMock, patch

import src.mcp.vision_client as vision_client_module
from src.citation.indexer import CitationIndexer
from src.mcp.vision_client import CLAUDE_PROMPTS, OPENAI_PROMPTS, VisionClient, VisionResult


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

    def test_prompts_cover_all_analysis_types(self):
        expected = {"general", "ocr", "chart", "table", "formula"}
        assert expected <= set(OPENAI_PROMPTS)
        assert expected <= set(CLAUDE_PROMPTS)

    def test_ocr_prompt_asks_for_transcription_not_summary(self):
        assert "逐行转写" in OPENAI_PROMPTS["ocr"] or "逐行转写" in CLAUDE_PROMPTS["ocr"]
        assert "不要翻译" in OPENAI_PROMPTS["ocr"] or "不要翻译" in CLAUDE_PROMPTS["ocr"]

    async def test_ocr_image_routes_to_ocr_analysis_type(self):
        client = VisionClient()
        expected = VisionResult(text="识别出的文字")
        with patch.object(
            client, "analyze_image", new=AsyncMock(return_value=expected)
        ) as mock_analyze:
            result = await client.ocr_image("fake.png")
        mock_analyze.assert_awaited_once_with("fake.png", analysis_type="ocr")
        assert result.text == "识别出的文字"

    async def test_recognize_formula_routes_to_formula_analysis_type(self):
        client = VisionClient()
        expected = VisionResult(text="E = mc^2")
        with patch.object(
            client, "analyze_image", new=AsyncMock(return_value=expected)
        ) as mock_analyze:
            result = await client.recognize_formula("fake.png")
        mock_analyze.assert_awaited_once_with("fake.png", analysis_type="formula")
        assert result.text == "E = mc^2"

    async def test_analyze_chart_routes_to_chart_analysis_type(self):
        client = VisionClient()
        expected = VisionResult(text="柱状图")
        with patch.object(
            client, "analyze_image", new=AsyncMock(return_value=expected)
        ) as mock_analyze:
            result = await client.analyze_chart("fake.png")
        mock_analyze.assert_awaited_once_with("fake.png", analysis_type="chart")
        assert result.text == "柱状图"

    async def test_analyze_image_without_api_key_returns_placeholder(self):
        client = VisionClient(api_key="")
        with patch.object(
            client, "_get_credentials", return_value=("https://api.openai.com/v1", "", "gpt-4o")
        ):
            result = await client.analyze_image("fake.png", analysis_type="ocr")
        assert "API Key" in result.text

    def test_load_config_in_frozen_mode_reads_runtime_config_dir(self, tmp_path, monkeypatch):
        """冻结环境（PYZ 无真实 __file__）下应回退到 api_factory 的运行时配置目录。"""
        runtime_cfg = tmp_path / "runtime-config"
        runtime_cfg.mkdir()
        (runtime_cfg / "default.yaml").write_text(
            "vision:\n  api_key: from-default\n  base_url: https://api.openai.com/v1\n",
            encoding="utf-8",
        )
        (runtime_cfg / "default.local.yaml").write_text(
            "vision:\n  api_key: from-local\n  model: glm-4v-flash\n",
            encoding="utf-8",
        )
        api_factory_stub = types.ModuleType("api_factory")
        api_factory_stub.CONFIG_PATH = str(runtime_cfg / "default.yaml")
        monkeypatch.setitem(sys.modules, "api_factory", api_factory_stub)
        # 模拟 PyInstaller：模块 __file__ 指向不存在的 PYZ 内路径
        monkeypatch.setattr(
            vision_client_module, "__file__", "Z:/nonexistent/_internal/vision_client.pyc"
        )

        config = VisionClient()._load_config()

        assert config["vision"]["api_key"] == "from-local"  # local 覆盖 default
        assert config["vision"]["model"] == "glm-4v-flash"
        assert config["vision"]["base_url"] == "https://api.openai.com/v1"

    def test_get_proxy_from_network_config(self, monkeypatch):
        client = VisionClient()
        monkeypatch.setattr(
            client, "_load_config", lambda: {"network": {"proxy": "http://127.0.0.1:7897"}}
        )
        assert client._get_proxy() == "http://127.0.0.1:7897"

    def test_get_proxy_falls_back_to_env(self, monkeypatch):
        client = VisionClient()
        monkeypatch.setattr(client, "_load_config", lambda: {})
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7898")
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        assert client._get_proxy() == "http://127.0.0.1:7898"

    def test_get_proxy_none_when_unconfigured(self, monkeypatch):
        client = VisionClient()
        monkeypatch.setattr(client, "_load_config", lambda: {})
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        assert client._get_proxy() is None

    async def test_analyze_image_passes_proxy_to_httpx_client(self, monkeypatch):
        captured: dict = {}

        class _FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "识别出的文字"}}]}

        class _FakeAsyncClient:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, *args, **kwargs):
                return _FakeResponse()

        httpx_stub = types.ModuleType("httpx")
        httpx_stub.AsyncClient = _FakeAsyncClient
        # _analyze_openai 优先 aiohttp，令其导入失败以强制走 httpx 分支
        monkeypatch.setitem(sys.modules, "aiohttp", None)
        monkeypatch.setitem(sys.modules, "httpx", httpx_stub)

        client = VisionClient()
        monkeypatch.setattr(client, "_get_proxy", lambda: "http://127.0.0.1:7897")
        with (
            patch.object(
                client,
                "_get_credentials",
                return_value=("https://example.com/v1", "k", "m"),
            ),
            patch.object(client, "_encode_image", return_value="b64"),
        ):
            result = await client.analyze_image("fake.png", analysis_type="ocr")

        assert captured.get("proxy") == "http://127.0.0.1:7897"
        assert result.text == "识别出的文字"


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
        indexer.set_bibliography(
            [
                {
                    "key": "smith2020",
                    "author": "Smith, J.",
                    "title": "Deep Learning",
                    "year": "2020",
                },
            ]
        )
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="ieee")
        assert "[1]" in bib
        assert "Smith, J." in bib
        assert "Deep Learning" in bib

    def test_render_bibliography_apa(self):
        indexer = CitationIndexer()
        indexer.set_bibliography(
            [
                {
                    "key": "smith2020",
                    "author": "Smith, J.",
                    "title": "Deep Learning",
                    "year": "2020",
                },
            ]
        )
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="apa")
        assert "[1]" in bib
        assert "(2020)" in bib

    def test_render_bibliography_gbt7714(self):
        indexer = CitationIndexer()
        indexer.set_bibliography(
            [
                {
                    "key": "smith2020",
                    "author": "Smith, J.",
                    "title": "Deep Learning",
                    "journal": "AI Journal",
                    "year": "2020",
                },
            ]
        )
        index = {"smith2020": 1}
        bib = indexer.render_bibliography(index, style="gbt7714")
        assert "[1]" in bib
        assert "Smith, J." in bib

    def test_process_full_workflow(self):
        indexer = CitationIndexer()
        indexer.set_bibliography(
            [
                {
                    "key": "smith2020",
                    "author": "Smith, J.",
                    "title": "Deep Learning",
                    "year": "2020",
                },
                {"key": "jones2021", "author": "Jones, A.", "title": "AI Advances", "year": "2021"},
            ]
        )

        text = "[@jones2021] 指出 [@smith2020] 的方法有效"
        result = indexer.process(text)

        assert result["text"] != text  # 已替换
        assert "[1]" in result["text"] or "[2]" in result["text"]
        assert len(result["citations"]) == 2
        assert result["bibliography"]  # 有参考文献节
