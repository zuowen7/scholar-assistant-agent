"""Agent 论证图/账本工具 — read_argument_graph / read_argument_ledger 与 store 查找。

覆盖："Agent 当符号表"接线：source_doc/doc_id = 文件路径做键。
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _graph_store(tmp_path: Path):
    from src.argument.graph_store import ArgGraphStore
    return ArgGraphStore(runtime_dir=tmp_path)


def _companion_store(tmp_path: Path):
    from src.argument.companion_store import CompanionStore
    return CompanionStore(runtime_dir=tmp_path)


def _build_graph_with_gap():
    from src.argument.models_v2 import ArgGraph, ArgNode, ArgEdge, ArgIssue
    g = ArgGraph(title="Paper", source_doc="draft/intro.md")
    claim = ArgNode(node_type="claim", text="Method is SOTA")
    grounds = ArgNode(node_type="grounds", text="Table 2: 95%")
    bad_claim = ArgNode(node_type="claim", text="Method is 2x faster")  # unsupported + isolated
    reb = ArgNode(node_type="rebuttal", text="Benchmark saturated")     # unanswered
    g.nodes = [claim, grounds, bad_claim, reb]
    g.edges = [
        ArgEdge(source_id=grounds.id, target_id=claim.id, relation_type="supports"),
        ArgEdge(source_id=reb.id, target_id=claim.id, relation_type="rebuts"),
    ]
    g.issues = [ArgIssue(severity="warning", category="missing_grounds", message="bad_claim lacks grounds")]
    return g, claim, grounds, bad_claim, reb


def _build_ledger():
    from src.argument.companion_models import Ledger, Promise
    led = Ledger(doc_id="draft/intro.md", doc_title="Paper")
    led.promises = [
        Promise(text="superior accuracy", kind="claim", source_anchor_id="a1", status="paid", note="Sec 4.1"),
        Promise(text="theoretical guarantees", kind="claim", source_anchor_id="a2", status="unpaid", note="no proof"),
        Promise(text="5 baselines", kind="claim", source_anchor_id="a3", status="partial"),
    ]
    return led


# ── store 查找：source_doc / doc_id = 文件路径 ──────────────────────────────

class TestStoreLookupByPath:
    def test_get_by_source_doc_exact(self, tmp_path):
        store = _graph_store(tmp_path)
        g, *_ = _build_graph_with_gap()
        store._cache[g.id] = g
        assert store.get_by_source_doc("draft/intro.md").id == g.id

    def test_get_by_source_doc_miss(self, tmp_path):
        store = _graph_store(tmp_path)
        g, *_ = _build_graph_with_gap()
        store._cache[g.id] = g
        assert store.get_by_source_doc("draft/other.md") is None

    def test_get_by_source_doc_empty(self, tmp_path):
        store = _graph_store(tmp_path)
        assert store.get_by_source_doc("") is None

    def test_get_by_source_doc_returns_most_recent(self, tmp_path):
        from src.argument.models_v2 import ArgGraph
        store = _graph_store(tmp_path)
        old = ArgGraph(title="old", source_doc="p.md"); old.updated_at = 100.0
        new = ArgGraph(title="new", source_doc="p.md"); new.updated_at = 200.0
        store._cache[old.id] = old
        store._cache[new.id] = new
        assert store.get_by_source_doc("p.md").id == new.id

    def test_get_ledger_by_path_exact(self, tmp_path):
        store = _companion_store(tmp_path)
        led = _build_ledger()
        store._ledgers[led.doc_id] = led
        assert store.get_ledger_by_path("draft/intro.md").doc_id == led.doc_id

    def test_get_ledger_by_path_miss(self, tmp_path):
        store = _companion_store(tmp_path)
        led = _build_ledger()
        store._ledgers[led.doc_id] = led
        assert store.get_ledger_by_path("draft/nope.md") is None


# ── 格式化输出 ──────────────────────────────────────────────────────────────

class TestFormatters:
    def test_format_graph_gap_analysis(self):
        from src.agent.tools.registry import _format_argument_graph
        g, claim, grounds, bad_claim, reb = _build_graph_with_gap()
        out = _format_argument_graph(g)
        assert "悬空主张" in out          # unsupported claim detected
        assert "未回应的反驳" in out      # unanswered rebuttal detected
        assert "孤立节点" in out          # isolated node detected
        assert bad_claim.id in out
        assert reb.id in out
        assert "missing_grounds" in out   # stored AI issue surfaced
        assert "draft/intro.md" in out    # source_doc shown

    def test_format_graph_no_gaps(self):
        from src.agent.tools.registry import _format_argument_graph
        from src.argument.models_v2 import ArgGraph, ArgNode, ArgEdge
        g = ArgGraph(title="Clean")
        c = ArgNode(node_type="claim", text="C")
        gr = ArgNode(node_type="grounds", text="G")
        g.nodes = [c, gr]
        g.edges = [ArgEdge(source_id=gr.id, target_id=c.id, relation_type="supports")]
        out = _format_argument_graph(g)
        assert "结构完整" in out

    def test_format_ledger_groups_by_status(self):
        from src.agent.tools.registry import _format_argument_ledger
        out = _format_argument_ledger(_build_ledger())
        assert "未兑付" in out
        assert "部分兑付" in out
        assert "已兑付" in out
        # unpaid should appear before paid (problems first)
        assert out.index("未兑付") < out.index("已兑付")


# ── 工具注册 + 调用行为 ──────────────────────────────────────────────────────

class TestToolRegistration:
    def test_tools_registered_when_stores_present(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        reg = create_default_registry(
            graph_store=_graph_store(tmp_path),
            companion_store=_companion_store(tmp_path),
            workspace_root=str(tmp_path),
        )
        assert "read_argument_graph" in reg._tools
        assert "read_argument_ledger" in reg._tools

    def test_tools_absent_without_stores(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        reg = create_default_registry(workspace_root=str(tmp_path))
        assert "read_argument_graph" not in reg._tools
        assert "read_argument_ledger" not in reg._tools

    def test_read_graph_by_file_path(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        gs = _graph_store(tmp_path)
        g, *_ = _build_graph_with_gap()
        gs._cache[g.id] = g
        reg = create_default_registry(graph_store=gs, workspace_root=str(tmp_path))
        fn = reg._tools["read_argument_graph"].fn
        out = fn(file_path="draft/intro.md")
        assert "论证图" in out
        assert "Gap 分析" in out

    def test_read_graph_list_mode(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        gs = _graph_store(tmp_path)
        g, *_ = _build_graph_with_gap()
        gs._cache[g.id] = g
        reg = create_default_registry(graph_store=gs, workspace_root=str(tmp_path))
        fn = reg._tools["read_argument_graph"].fn
        out = fn()  # no args → list mode
        assert g.id in out

    def test_read_graph_not_found(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        reg = create_default_registry(graph_store=_graph_store(tmp_path), workspace_root=str(tmp_path))
        fn = reg._tools["read_argument_graph"].fn
        out = fn(file_path="nonexistent.md")
        assert "未找到" in out

    def test_read_ledger_by_file_path(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        cs = _companion_store(tmp_path)
        led = _build_ledger()
        cs._ledgers[led.doc_id] = led
        reg = create_default_registry(companion_store=cs, workspace_root=str(tmp_path))
        fn = reg._tools["read_argument_ledger"].fn
        out = fn(file_path="draft/intro.md")
        assert "论证账本" in out
        assert "未兑付" in out

    def test_read_ledger_list_mode(self, tmp_path):
        from src.agent.tools.registry import create_default_registry
        cs = _companion_store(tmp_path)
        led = _build_ledger()
        cs._ledgers[led.doc_id] = led
        reg = create_default_registry(companion_store=cs, workspace_root=str(tmp_path))
        fn = reg._tools["read_argument_ledger"].fn
        out = fn()  # no args → list mode
        assert led.doc_id in out
