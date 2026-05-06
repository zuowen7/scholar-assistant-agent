"""Argument flatten 单元测试 — 覆盖四阶段管道的所有核心路径。

测试分组:
  TestDfsOrder          — DFS 遍历顺序
  TestClassifyChainType — 论证链类型分类
  TestGetSectionTitle   — 章节标题映射
  TestBuildTreeOutline  — 树概要文本生成
  TestContextSummary    — 滚动摘要构造
  TestFetchRefContext   — RAG 文献片段获取
  TestEnrichReferences  — 文献元数据丰富
  TestFormatMarkdown    — Markdown 格式化输出
  TestBibtexEntries     — BibTeX 条目生成
  TestMinimalLatex      — 兜底 LaTeX 生成
  TestExpandNode        — 节点 LLM 扩写（含上下文注入）
  TestGenerateAbstract  — Abstract 生成
  TestGenerateTransitions — 过渡句生成（含 JSON 解析边界）
  TestFlattenStream     — 完整管道 SSE 事件流
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.argument.flatten import ArgumentFlattener, _CHAIN_TO_SECTION, _CLASSIC_CHAIN_KEYWORDS


# ── 测试辅助工厂 ─────────────────────────────────────────────────────────────

def _make_flattener() -> ArgumentFlattener:
    return ArgumentFlattener()


def _minimal_tree() -> dict:
    """最简树：root + 3 个 depth=1 子节点（problem / verification / conclusion）。"""
    return {
        "root_id": "root",
        "nodes": {
            "root": {
                "topic": "自适应控制研究",
                "content": "",
                "depth": 0,
                "children": ["n1", "n2", "n3"],
                "references": [],
                "domain_tags": [],
                "rule_issues": [],
                "agent_feedback": None,
            },
            "n1": {
                "topic": "控制问题背景",
                "content": "现有方法不足",
                "depth": 1,
                "children": [],
                "references": [],
                "domain_tags": [],
                "rule_issues": [],
                "agent_feedback": None,
            },
            "n2": {
                "topic": "仿真实验验证",
                "content": "MATLAB 仿真",
                "depth": 1,
                "children": [],
                "references": [],
                "domain_tags": [],
                "rule_issues": [],
                "agent_feedback": None,
            },
            "n3": {
                "topic": "结论与展望",
                "content": "未来工作",
                "depth": 1,
                "children": [],
                "references": [],
                "domain_tags": [],
                "rule_issues": [],
                "agent_feedback": None,
            },
        },
    }


def _ref(doc_id: str, key: str) -> dict:
    return {"doc_id": doc_id, "citation_key": key, "relevance_score": 0.8, "binding_type": "user_manual"}


def _mock_rag(chunks: list[dict] | None = None, docs: list | None = None) -> MagicMock:
    rag = MagicMock()
    rag.retrieve_context.return_value = chunks or []
    doc_mock = MagicMock()
    doc_mock.id = "doc1"
    doc_mock.title = "Sample Title"
    doc_mock.metadata = {"authors": "Zhang San", "year": "2023", "journal": "IEEE TAC"}
    rag.list_documents.return_value = docs if docs is not None else [doc_mock]
    return rag


# ── DFS 遍历顺序 ─────────────────────────────────────────────────────────────

class TestDfsOrder:

    def test_single_root_no_children(self):
        f = _make_flattener()
        nodes = {"root": {"children": []}}
        assert f._build_dfs_order(nodes, "root") == ["root"]

    def test_linear_chain(self):
        f = _make_flattener()
        nodes = {
            "a": {"children": ["b"]},
            "b": {"children": ["c"]},
            "c": {"children": []},
        }
        assert f._build_dfs_order(nodes, "a") == ["a", "b", "c"]

    def test_tree_preserves_child_order(self):
        f = _make_flattener()
        nodes = {
            "root": {"children": ["n1", "n2", "n3"]},
            "n1": {"children": []},
            "n2": {"children": []},
            "n3": {"children": []},
        }
        order = f._build_dfs_order(nodes, "root")
        assert order == ["root", "n1", "n2", "n3"]

    def test_subtree_depth_first(self):
        f = _make_flattener()
        nodes = {
            "root": {"children": ["a", "b"]},
            "a":    {"children": ["a1", "a2"]},
            "a1":   {"children": []},
            "a2":   {"children": []},
            "b":    {"children": []},
        }
        order = f._build_dfs_order(nodes, "root")
        # root → a → a1 → a2 → b
        assert order.index("a") < order.index("a1") < order.index("b")
        assert order.index("a1") < order.index("a2")

    def test_empty_root_id_fallback(self):
        f = _make_flattener()
        nodes = {"x": {"children": []}}
        order = f._build_dfs_order(nodes, "")
        assert "x" in order

    def test_missing_root_id_returns_empty(self):
        f = _make_flattener()
        nodes = {"a": {"children": []}}
        # root_id 不在 nodes 中 → 从 stack pop 但 not in nodes → 跳过
        order = f._build_dfs_order(nodes, "nonexistent")
        assert order == []


# ── 链类型分类 ───────────────────────────────────────────────────────────────

class TestClassifyChainType:

    def setup_method(self):
        self.f = _make_flattener()

    def test_problem_keywords(self):
        assert self.f._classify_chain_type("研究背景与挑战", "") == "problem"

    def test_modeling_keywords(self):
        assert self.f._classify_chain_type("系统建模与框架设计", "") == "modeling"

    def test_analysis_keywords(self):
        assert self.f._classify_chain_type("性能分析与评估", "") == "analysis"

    def test_verification_keywords(self):
        assert self.f._classify_chain_type("仿真实验验证", "") == "verification"

    def test_conclusion_keywords(self):
        assert self.f._classify_chain_type("结论与展望", "") == "conclusion"

    def test_english_keywords(self):
        assert self.f._classify_chain_type("Problem Background", "") == "problem"
        assert self.f._classify_chain_type("Experimental Verification", "") == "verification"
        assert self.f._classify_chain_type("Conclusion and Future Work", "") == "conclusion"

    def test_content_also_scored(self):
        # topic 无关键词，content 有关键词
        chain = self.f._classify_chain_type("节点A", "仿真与实验对比")
        assert chain == "verification"

    def test_unknown_when_no_match(self):
        assert self.f._classify_chain_type("随机标题", "随机内容") == "unknown"

    def test_highest_score_wins(self):
        # 同时包含 modeling 和 problem 关键词，modeling 应得更高分（更多命中）
        topic = "系统建模框架结构设计"  # modeling: 建模, 模型, 框架, 结构设计 → 4 hits
        result = self.f._classify_chain_type(topic, "")
        assert result == "modeling"


# ── 章节标题映射 ─────────────────────────────────────────────────────────────

class TestGetSectionTitle:

    def setup_method(self):
        self.f = _make_flattener()

    def test_depth0_always_returns_topic(self):
        assert self.f._get_section_title("论文总标题", "problem", 0, "IEEE") == "论文总标题"

    def test_depth1_problem_maps_to_intro_zh(self):
        title = self.f._get_section_title("问题背景", "problem", 1, "IEEE")
        assert title == "引言"

    def test_depth1_modeling_maps_to_methods_zh(self):
        title = self.f._get_section_title("系统建模", "modeling", 1, "IEEE")
        assert title == "方法"

    def test_depth1_verification_maps_to_results_zh(self):
        title = self.f._get_section_title("实验验证", "verification", 1, "IEEE")
        assert title == "实验与结果"

    def test_depth1_conclusion_maps_to_conclusion_zh(self):
        title = self.f._get_section_title("总结展望", "conclusion", 1, "IEEE")
        assert title == "结论"

    def test_depth1_english_topic_returns_en(self):
        title = self.f._get_section_title("Experimental Setup", "verification", 1, "IEEE")
        assert title == "Experiments and Results"

    def test_depth1_unknown_returns_topic(self):
        title = self.f._get_section_title("随机节点", "unknown", 1, "IEEE")
        assert title == "随机节点"

    def test_depth2_always_returns_topic(self):
        # 子节点标题不替换
        title = self.f._get_section_title("状态空间表示", "modeling", 2, "IEEE")
        assert title == "状态空间表示"

    def test_depth3_returns_topic(self):
        title = self.f._get_section_title("细节推导", "analysis", 3, "IEEE")
        assert title == "细节推导"


# ── 树概要文本生成 ────────────────────────────────────────────────────────────

class TestBuildTreeOutline:

    def setup_method(self):
        self.f = _make_flattener()

    def test_root_shows_label(self):
        nodes = {"root": {"topic": "我的论文", "depth": 0, "content": "", "children": []}}
        outline = self.f._build_tree_outline(nodes, "root", "IEEE")
        assert "[论文]" in outline
        assert "我的论文" in outline

    def test_child_nodes_shown(self):
        nodes = {
            "root": {"topic": "论文", "depth": 0, "content": "", "children": ["c1"]},
            "c1":   {"topic": "背景", "depth": 1, "content": "", "children": []},
        }
        outline = self.f._build_tree_outline(nodes, "root", "IEEE")
        assert "引言" in outline   # 分类后标准章节名
        assert "背景" in outline    # 原始 topic 也出现

    def test_indentation_reflects_depth(self):
        nodes = {
            "root": {"topic": "Root", "depth": 0, "content": "", "children": ["c1"]},
            "c1":   {"topic": "Child", "depth": 1, "content": "", "children": ["gc1"]},
            "gc1":  {"topic": "Grandchild", "depth": 2, "content": "", "children": []},
        }
        outline = self.f._build_tree_outline(nodes, "root", "IEEE")
        lines = outline.split("\n")
        # 孙节点行比子节点行有更多前导空格
        child_line = next(l for l in lines if "Child" in l)
        grand_line = next(l for l in lines if "Grandchild" in l)
        assert len(grand_line) - len(grand_line.lstrip()) > len(child_line) - len(child_line.lstrip())

    def test_missing_root_returns_placeholder(self):
        outline = self.f._build_tree_outline({}, "nonexistent", "IEEE")
        assert "无节点信息" in outline


# ── 滚动摘要构造 ─────────────────────────────────────────────────────────────

class TestContextSummary:

    def setup_method(self):
        self.f = _make_flattener()

    def test_empty_list_returns_first_section_msg(self):
        result = self.f._build_context_summary([])
        assert "首节" in result

    def test_single_summary(self):
        result = self.f._build_context_summary(["[引言] 背景…"])
        assert "引言" in result
        assert "背景" in result

    def test_truncates_to_last_three(self):
        summaries = [f"[节{i}] 内容{i}…" for i in range(6)]
        result = self.f._build_context_summary(summaries)
        # 保留最后 3 条 = 节3/4/5，节0/1/2 不应出现
        assert "节2" not in result
        assert "节5" in result

    def test_bullet_format(self):
        result = self.f._build_context_summary(["测试摘要"])
        assert result.startswith("•")


# ── RAG 文献片段获取 ──────────────────────────────────────────────────────────

class TestFetchRefContext:

    def setup_method(self):
        self.f = _make_flattener()

    def test_no_refs_returns_placeholder(self):
        ctx, enriched = asyncio.run(self.f._fetch_ref_context([], "topic", None))
        assert "无挂载文献" in ctx
        assert enriched == []

    def test_rag_none_returns_not_connected(self):
        refs = [_ref("doc1", "Zhang2023")]
        ctx, enriched = asyncio.run(self.f._fetch_ref_context(refs, "topic", None))
        assert "Zhang2023" in ctx
        assert "RAG 未连接" in ctx
        assert len(enriched) == 1

    def test_rag_with_chunks_injects_text(self):
        rag = _mock_rag(chunks=[{"text": "这篇文献讨论了控制稳定性", "metadata": {"title": "T1"}}])
        refs = [_ref("doc1", "Ctrl2022")]
        ctx, enriched = asyncio.run(self.f._fetch_ref_context(refs, "控制", rag))
        assert "Ctrl2022" in ctx
        assert "控制稳定性" in ctx
        assert enriched[0]["title"] == "T1"

    def test_rag_empty_chunks_shows_no_fragment(self):
        rag = _mock_rag(chunks=[])
        refs = [_ref("doc1", "Empty2020")]
        ctx, _ = asyncio.run(self.f._fetch_ref_context(refs, "topic", rag))
        assert "片段" in ctx

    def test_rag_exception_shows_failed(self):
        rag = MagicMock()
        rag.retrieve_context.side_effect = RuntimeError("connection error")
        refs = [_ref("doc1", "Key")]
        ctx, _ = asyncio.run(self.f._fetch_ref_context(refs, "topic", rag))
        assert "检索失败" in ctx

    def test_multiple_refs_all_appear(self):
        rag = _mock_rag(chunks=[{"text": "片段内容", "metadata": {}}])
        refs = [_ref("d1", "A2021"), _ref("d2", "B2022")]
        ctx, enriched = asyncio.run(self.f._fetch_ref_context(refs, "topic", rag))
        assert "A2021" in ctx
        assert "B2022" in ctx
        assert len(enriched) == 2


# ── 文献元数据丰富 ────────────────────────────────────────────────────────────

class TestEnrichReferences:

    def setup_method(self):
        self.f = _make_flattener()

    def test_no_rag_returns_raw(self):
        refs = [{"doc_id": "d1", "citation_key": "K1", "title": ""}]
        result = self.f._enrich_references(refs, None)
        assert result == refs

    def test_rag_fills_title(self):
        doc = MagicMock()
        doc.id = "d1"
        doc.title = "Control Paper"
        doc.metadata = {"authors": "Li Si", "year": "2022"}
        rag = MagicMock()
        rag.list_documents.return_value = [doc]

        refs = [{"doc_id": "d1", "citation_key": "Li2022", "title": ""}]
        result = self.f._enrich_references(refs, rag)
        assert result[0]["title"] == "Control Paper"
        assert result[0]["metadata"]["authors"] == "Li Si"

    def test_rag_exception_returns_raw(self):
        rag = MagicMock()
        rag.list_documents.side_effect = RuntimeError("db error")
        refs = [{"doc_id": "d1", "citation_key": "K1", "title": ""}]
        result = self.f._enrich_references(refs, rag)
        assert result[0]["citation_key"] == "K1"

    def test_existing_title_not_overwritten(self):
        doc = MagicMock()
        doc.id = "d1"
        doc.title = "New Title"
        doc.metadata = {}
        rag = MagicMock()
        rag.list_documents.return_value = [doc]

        refs = [{"doc_id": "d1", "citation_key": "K1", "title": "Original Title"}]
        result = self.f._enrich_references(refs, rag)
        # 原有 title 不被覆盖（enrichment 只在 title 为空时填充）
        assert result[0]["title"] == "Original Title"


# ── Markdown 格式化 ───────────────────────────────────────────────────────────

class TestFormatMarkdown:

    def setup_method(self):
        self.f = _make_flattener()

    def _sections(self) -> list[dict]:
        return [
            {"depth": 0, "section_title": "Paper Title", "text": "root text"},
            {"depth": 1, "section_title": "Introduction", "text": "intro text"},
            {"depth": 1, "section_title": "Methods",      "text": "methods text"},
        ]

    def test_abstract_included_when_present(self):
        out = self.f._format_markdown("The abstract.", self._sections(), [], False)
        assert "Abstract" in out
        assert "The abstract." in out

    def test_no_abstract_when_empty(self):
        out = self.f._format_markdown("", self._sections(), [], False)
        assert "## Abstract" not in out

    def test_section_titles_as_headings(self):
        out = self.f._format_markdown("", self._sections(), [], False)
        assert "# Paper Title" in out
        assert "## Introduction" in out

    def test_references_included_when_flag_true(self):
        refs = [{"doc_id": "d1", "citation_key": "Wang2023", "title": "A Paper",
                 "metadata": {"authors": "Wang", "year": "2023", "journal": "Nature"}}]
        out = self.f._format_markdown("", self._sections(), refs, True)
        assert "References" in out
        assert "Wang2023" in out

    def test_references_omitted_when_flag_false(self):
        refs = [{"doc_id": "d1", "citation_key": "Wang2023", "title": "A Paper", "metadata": {}}]
        out = self.f._format_markdown("", self._sections(), refs, False)
        assert "References" not in out

    def test_reference_shows_authors_year(self):
        refs = [{"doc_id": "d1", "citation_key": "Li2021", "title": "Control Study",
                 "metadata": {"authors": "Li Ming", "year": "2021", "journal": "IEEE"}}]
        out = self.f._format_markdown("", self._sections(), refs, True)
        assert "Li Ming" in out
        assert "2021" in out

    def test_empty_sections(self):
        out = self.f._format_markdown("Abstract only.", [], [], False)
        assert "Abstract only." in out

    def test_ref_without_metadata_shows_key(self):
        refs = [{"doc_id": "d1", "citation_key": "NoMeta", "title": "", "metadata": {}}]
        out = self.f._format_markdown("", self._sections(), refs, True)
        assert "NoMeta" in out


# ── BibTeX 条目生成 ───────────────────────────────────────────────────────────

class TestBibtexEntries:

    def setup_method(self):
        self.f = _make_flattener()

    def test_article_type_when_journal_present(self):
        refs = [{"citation_key": "Test2023", "doc_id": "d1", "title": "My Paper",
                 "metadata": {"authors": "A B", "year": "2023", "journal": "IEEE TAC"}}]
        entries = self.f._build_bibtex_entries(refs)
        assert len(entries) == 1
        assert "@article{Test2023" in entries[0]
        assert "IEEE TAC" in entries[0]

    def test_misc_type_when_no_journal(self):
        refs = [{"citation_key": "Tech2022", "doc_id": "d1", "title": "Report",
                 "metadata": {"authors": "C D", "year": "2022"}}]
        entries = self.f._build_bibtex_entries(refs)
        assert "@misc{Tech2022" in entries[0]

    def test_year_truncated_to_4_digits(self):
        refs = [{"citation_key": "K", "doc_id": "d1", "title": "T",
                 "metadata": {"year": "2023-05-01"}}]
        entries = self.f._build_bibtex_entries(refs)
        assert "year    = {2023}" in entries[0]

    def test_empty_refs_returns_empty_list(self):
        assert self.f._build_bibtex_entries([]) == []

    def test_multiple_refs_all_generated(self):
        refs = [
            {"citation_key": "A2020", "doc_id": "a", "title": "A", "metadata": {}},
            {"citation_key": "B2021", "doc_id": "b", "title": "B", "metadata": {}},
        ]
        entries = self.f._build_bibtex_entries(refs)
        assert len(entries) == 2
        assert any("A2020" in e for e in entries)
        assert any("B2021" in e for e in entries)


# ── 兜底 LaTeX 生成 ───────────────────────────────────────────────────────────

class TestMinimalLatex:

    def setup_method(self):
        self.f = _make_flattener()

    def test_produces_valid_document_structure(self):
        sections = [{"depth": 1, "section_title": "Introduction", "text": "Intro text."}]
        out = self.f._minimal_latex("Paper Title", "The abstract.", sections)
        assert r"\documentclass" in out
        assert r"\begin{document}" in out
        assert r"\end{document}" in out

    def test_title_in_output(self):
        out = self.f._minimal_latex("My Title", "", [])
        assert "My Title" in out

    def test_abstract_in_output(self):
        out = self.f._minimal_latex("T", "Abstract text here.", [])
        assert r"\begin{abstract}" in out
        assert "Abstract text here." in out

    def test_section_cmd_for_depth1(self):
        sections = [{"depth": 1, "section_title": "Methods", "text": "Method desc."}]
        out = self.f._minimal_latex("T", "", sections)
        assert r"\section{Methods}" in out

    def test_subsection_for_depth2(self):
        sections = [{"depth": 2, "section_title": "Sub", "text": "Detail."}]
        out = self.f._minimal_latex("T", "", sections)
        assert r"\subsection{Sub}" in out

    def test_depth0_root_node_skipped(self):
        # depth=0 是论文标题，不应生成 \section
        sections = [{"depth": 0, "section_title": "Paper Title", "text": "root text"}]
        out = self.f._minimal_latex("Paper Title", "", sections)
        assert r"\section" not in out

    def test_special_chars_escaped(self):
        sections = [{"depth": 1, "section_title": "A & B", "text": "x"}]
        out = self.f._minimal_latex("T", "", sections)
        assert r"\&" in out

    def test_depth3_maps_to_subsubsection(self):
        sections = [{"depth": 3, "section_title": "Deep", "text": "deep text"}]
        out = self.f._minimal_latex("T", "", sections)
        assert r"\subsubsection{Deep}" in out


# ── 节点 LLM 扩写 ─────────────────────────────────────────────────────────────

class TestExpandNode:

    def setup_method(self):
        self.f = _make_flattener()
        self.mock_llm_return = "这是一段扩写后的学术段落。研究表明相关方法具有显著优势。"

    def _run(self, ndata, **kwargs):
        defaults = dict(
            section_title="引言",
            chain_type="problem",
            context_so_far="（首节）",
            tree_outline="[论文] 测试\n  ├─ 引言（背景）",
            rag_context_str="（无文献）",
            cloud_client=None,
            ollama_client=None,
        )
        defaults.update(kwargs)
        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value=self.mock_llm_return)):
            return asyncio.run(self.f._expand_node_with_context(ndata, **defaults))

    def test_llm_result_returned(self):
        ndata = {"topic": "研究背景", "content": "简短备注", "depth": 1,
                 "references": [], "rule_issues": [], "agent_feedback": None}
        result = self._run(ndata)
        assert result == self.mock_llm_return

    def test_llm_failure_falls_back_to_content(self):
        ndata = {"topic": "节点A", "content": "已有内容", "depth": 1,
                 "references": [], "rule_issues": [], "agent_feedback": None}
        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value="")):
            result = asyncio.run(self.f._expand_node_with_context(
                ndata, section_title="S", chain_type="unknown",
                context_so_far="", tree_outline="", rag_context_str="",
                cloud_client=None, ollama_client=None,
            ))
        assert "已有内容" in result

    def test_llm_failure_topic_fallback(self):
        ndata = {"topic": "节点A", "content": "", "depth": 1,
                 "references": [], "rule_issues": [], "agent_feedback": None}
        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value="")):
            result = asyncio.run(self.f._expand_node_with_context(
                ndata, section_title="S", chain_type="unknown",
                context_so_far="", tree_outline="", rag_context_str="",
                cloud_client=None, ollama_client=None,
            ))
        assert "节点A" in result

    def test_rich_content_unknown_skips_llm(self):
        # 超过 200 字、无 references、unknown 类型 → 不调用 LLM
        long_content = "已有详细内容。" * 30  # > 200 字
        ndata = {"topic": "T", "content": long_content, "depth": 1,
                 "references": [], "rule_issues": [], "agent_feedback": None}
        called = []
        async def fake_llm(*a, **kw):
            called.append(1)
            return "LLM output"
        with patch("src.argument.llm_client.call_llm_chat", new=fake_llm):
            result = asyncio.run(self.f._expand_node_with_context(
                ndata, section_title="S", chain_type="unknown",
                context_so_far="", tree_outline="", rag_context_str="",
                cloud_client=None, ollama_client=None,
            ))
        assert called == []
        assert result == long_content

    def test_logic_issues_included_in_prompt(self):
        """rule_issues 和 agent_feedback 应出现在 prompt 中（通过验证 LLM 被调用即可）。"""
        ndata = {"topic": "节点", "content": "", "depth": 1,
                 "references": [], "rule_issues": ["缺少定义"], "agent_feedback": "需要补充实验"}
        captured_prompts = []
        async def capture_prompt(prompt, *a, **kw):
            captured_prompts.append(prompt)
            return "result"
        with patch("src.argument.llm_client.call_llm_chat", new=capture_prompt):
            asyncio.run(self.f._expand_node_with_context(
                ndata, section_title="S", chain_type="problem",
                context_so_far="", tree_outline="", rag_context_str="",
                cloud_client=None, ollama_client=None,
            ))
        assert captured_prompts
        combined = captured_prompts[0]
        assert "缺少定义" in combined
        assert "需要补充实验" in combined


# ── Abstract 生成 ────────────────────────────────────────────────────────────

class TestGenerateAbstract:

    def setup_method(self):
        self.f = _make_flattener()

    def _run(self, sections, title="Paper", llm_return="摘要内容"):
        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value=llm_return)):
            return asyncio.run(self.f._generate_abstract(sections, title, None, None))

    def test_returns_llm_result(self):
        sections = [{"depth": 1, "section_title": "引言", "text": "背景文本"}]
        result = self._run(sections, llm_return="  摘要文字  ")
        assert result == "摘要文字"  # stripped

    def test_empty_sections_returns_empty(self):
        result = self._run([])
        assert result == ""

    def test_only_depth0_sections_returns_empty(self):
        # depth==0 的节点（论文标题节点）不应参与 abstract 生成
        sections = [{"depth": 0, "section_title": "论文", "text": "root"}]
        result = self._run(sections)
        assert result == ""

    def test_llm_failure_returns_empty(self):
        sections = [{"depth": 1, "section_title": "S", "text": "text"}]
        result = self._run(sections, llm_return="")
        assert result == ""

    def test_at_most_six_sections_used(self):
        """超过 6 节时，只截取前 6 节传给 LLM prompt。"""
        sections = [{"depth": 1, "section_title": f"S{i}", "text": f"text{i}"} for i in range(10)]
        captured = []
        async def capture(prompt, *a, **kw):
            captured.append(prompt)
            return "ok"
        with patch("src.argument.llm_client.call_llm_chat", new=capture):
            asyncio.run(self.f._generate_abstract(sections, "T", None, None))
        # S6 ~ S9 不应出现在 prompt 中
        assert "S6" not in captured[0]
        assert "S5" in captured[0]


# ── 过渡句生成 ───────────────────────────────────────────────────────────────

class TestGenerateTransitions:

    def setup_method(self):
        self.f = _make_flattener()

    def _main_sections(self, n=3) -> list[dict]:
        return [
            {"depth": 1, "section_title": f"Section{i}", "text": f"content{i}" * 5}
            for i in range(n)
        ]

    def _run(self, sections, llm_return):
        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value=llm_return)):
            return asyncio.run(self.f._generate_transitions(sections, None, None))

    def test_valid_json_returns_transitions(self):
        payload = json.dumps({"transitions": ["过渡1", "过渡2"]})
        result = self._run(self._main_sections(3), payload)
        assert result == ["过渡1", "过渡2"]

    def test_json_wrapped_in_text(self):
        # LLM 可能在 JSON 前后加文字
        payload = '好的，以下是过渡句：{"transitions": ["句子A", "句子B"]} 希望有帮助。'
        result = self._run(self._main_sections(3), payload)
        assert result == ["句子A", "句子B"]

    def test_invalid_json_returns_empty(self):
        result = self._run(self._main_sections(3), "not json at all")
        assert result == []

    def test_llm_failure_returns_empty(self):
        result = self._run(self._main_sections(3), "")
        assert result == []

    def test_less_than_2_main_sections_returns_empty(self):
        # 只有 1 个 depth==1 节点，不生成过渡
        result = self._run(self._main_sections(1), '{"transitions": ["x"]}')
        assert result == []

    def test_depth0_sections_excluded(self):
        # 混入 depth=0 节点，过渡句只针对 depth==1
        sections = [
            {"depth": 0, "section_title": "Root", "text": "root text"},
            {"depth": 1, "section_title": "S1", "text": "s1" * 5},
            {"depth": 1, "section_title": "S2", "text": "s2" * 5},
        ]
        payload = json.dumps({"transitions": ["s1->s2"]})
        result = self._run(sections, payload)
        assert result == ["s1->s2"]


# ── 完整管道事件流 ────────────────────────────────────────────────────────────

class TestFlattenStream:
    """验证 flatten_stream 在 mock 环境下产生正确的 SSE 事件序列。"""

    def _run_stream(self, tree_data, template="markdown", **kwargs) -> tuple[list[dict], Path]:
        """运行管道，收集所有事件，返回 (events, output_path)。"""
        f = _make_flattener()
        events = []

        async def _collect():
            with tempfile.TemporaryDirectory() as tmpdir:
                async for evt in f.flatten_stream(
                    tree_data=tree_data,
                    template=template,
                    style="IEEE",
                    include_references=True,
                    output_dir=tmpdir,
                    cloud_client=None,
                    ollama_client=None,
                    rag_store=None,
                    **kwargs,
                ):
                    events.append(evt)
                    if evt["event"] == "complete":
                        data = json.loads(evt["data"])
                        return events, Path(data["output_path"])
            return events, None

        # mock LLM 调用
        llm_responses = {
            "_expand_node_with_context": "扩写段落内容：本节详细阐述了相关方法与实验结果。",
            "_generate_abstract": "本文研究了自适应控制问题，提出了新方法，实验验证有效。",
            "_generate_transitions": '{"transitions": ["基于上述背景，", "在此基础上，"]}',
        }

        call_count = [0]
        async def fake_llm(prompt, *a, **kw):
            call_count[0] += 1
            # 根据 prompt 内容判断调用类型
            if "过渡句" in prompt:
                return llm_responses["_generate_transitions"]
            elif "摘要" in prompt or "Abstract" in prompt:
                return llm_responses["_generate_abstract"]
            else:
                return llm_responses["_expand_node_with_context"]

        with patch("src.argument.llm_client.call_llm_chat", new=fake_llm):
            return asyncio.run(_collect())

    def test_empty_tree_yields_nothing(self):
        events, _ = self._run_stream({"root_id": "", "nodes": {}})
        assert events == []

    def test_complete_event_present(self):
        events, _ = self._run_stream(_minimal_tree())
        event_types = [e["event"] for e in events]
        assert "complete" in event_types

    def test_node_processing_events_emitted(self):
        events, _ = self._run_stream(_minimal_tree())
        processing = [e for e in events if e["event"] == "node_processing"]
        # 最小树有 4 个节点（root + 3 children）
        assert len(processing) == 4

    def test_node_complete_events_emitted(self):
        events, _ = self._run_stream(_minimal_tree())
        completed = [e for e in events if e["event"] == "node_complete"]
        assert len(completed) == 4

    def test_polish_start_event_emitted(self):
        events, _ = self._run_stream(_minimal_tree())
        event_types = [e["event"] for e in events]
        assert "polish_start" in event_types

    def test_reference_processing_event_emitted(self):
        events, _ = self._run_stream(_minimal_tree())
        event_types = [e["event"] for e in events]
        assert "reference_processing" in event_types

    def test_complete_event_has_required_fields(self):
        events, _ = self._run_stream(_minimal_tree())
        complete = next(e for e in events if e["event"] == "complete")
        data = json.loads(complete["data"])
        assert "output_path" in data
        assert "word_count" in data
        assert "section_count" in data
        assert data["section_count"] == 4  # root + 3 children

    def test_output_file_written(self):
        f = _make_flattener()
        tree = _minimal_tree()

        async def collect():
            with tempfile.TemporaryDirectory() as tmpdir:
                async for evt in f.flatten_stream(
                    tree_data=tree,
                    template="markdown",
                    style="IEEE",
                    include_references=True,
                    output_dir=tmpdir,
                    cloud_client=None,
                    ollama_client=None,
                ):
                    if evt["event"] == "complete":
                        path = Path(json.loads(evt["data"])["output_path"])
                        assert path.exists()
                        content = path.read_text(encoding="utf-8")
                        assert len(content) > 0
                        return

        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value="扩写内容")):
            asyncio.run(collect())

    def test_latex_template_produces_tex_file(self):
        f = _make_flattener()
        tree = _minimal_tree()

        async def collect():
            with tempfile.TemporaryDirectory() as tmpdir:
                async for evt in f.flatten_stream(
                    tree_data=tree,
                    template="latex",
                    style="IEEE",
                    include_references=True,
                    output_dir=tmpdir,
                    cloud_client=None,
                    ollama_client=None,
                    latex_template="generic_article",
                ):
                    if evt["event"] == "complete":
                        path = Path(json.loads(evt["data"])["output_path"])
                        assert path.suffix == ".tex"
                        return

        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value="content")):
            asyncio.run(collect())

    def test_node_with_references_gets_rag_called(self):
        """挂载了 references 的节点应触发 RAG 检索。"""
        tree = _minimal_tree()
        tree["nodes"]["n1"]["references"] = [_ref("doc1", "Zhang2023")]

        rag = _mock_rag(chunks=[{"text": "文献片段", "metadata": {"title": "T"}}])
        f = _make_flattener()

        async def collect():
            with tempfile.TemporaryDirectory() as tmpdir:
                async for evt in f.flatten_stream(
                    tree_data=tree,
                    template="markdown",
                    style="IEEE",
                    include_references=True,
                    output_dir=tmpdir,
                    cloud_client=None,
                    ollama_client=None,
                    rag_store=rag,
                ):
                    pass

        with patch("src.argument.llm_client.call_llm_chat",
                   new=AsyncMock(return_value="content")):
            asyncio.run(collect())

        rag.retrieve_context.assert_called()

    def test_event_order_correct(self):
        """processing → complete 在 complete 之前，polish_start 在 complete 之前。"""
        events, _ = self._run_stream(_minimal_tree())
        types = [e["event"] for e in events]
        assert types.index("node_processing") < types.index("complete")
        assert types.index("polish_start") < types.index("complete")

    def test_transition_injected_in_section_text(self):
        """生成的过渡句应被注入到第 2 个主节点的文本开头。"""
        f = _make_flattener()
        tree = _minimal_tree()

        captured_sections = []

        original_format = f._format_markdown

        def patched_format(abstract, sections, refs, include_refs):
            captured_sections.extend(sections)
            return original_format(abstract, sections, refs, include_refs)

        f._format_markdown = patched_format

        async def collect():
            with tempfile.TemporaryDirectory() as tmpdir:
                async for _ in f.flatten_stream(
                    tree_data=tree,
                    template="markdown",
                    style="IEEE",
                    include_references=False,
                    output_dir=tmpdir,
                    cloud_client=None,
                    ollama_client=None,
                ):
                    pass

        transitions_json = '{"transitions": ["承接上文，", "在此基础上，"]}'

        async def fake_llm(prompt, *a, **kw):
            if "过渡句" in prompt:
                return transitions_json
            return "段落内容"

        with patch("src.argument.llm_client.call_llm_chat", new=fake_llm):
            asyncio.run(collect())

        main_secs = [s for s in captured_sections if s["depth"] == 1]
        if len(main_secs) >= 2:
            assert main_secs[1]["text"].startswith("承接上文，")


# ── 新增字段：models.py 的 FlattenRequest ──────────────────────────────────────

class TestFlattenRequestModel:
    def test_latex_template_default(self):
        from src.argument.models import FlattenRequest
        req = FlattenRequest()
        assert req.latex_template == "generic_article"

    def test_latex_template_custom(self):
        from src.argument.models import FlattenRequest
        req = FlattenRequest(latex_template="ieee_conference")
        assert req.latex_template == "ieee_conference"

    def test_style_default(self):
        from src.argument.models import FlattenRequest
        req = FlattenRequest()
        assert req.style == "IEEE"
