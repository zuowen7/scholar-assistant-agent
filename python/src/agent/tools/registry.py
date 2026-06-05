"""工具注册表工厂 — 创建包含所有默认工具的注册表。

本模块实现了 create_default_registry() 工厂函数，通过依赖注入将现有的
翻译客户端、RAG 存储等实例传入，工具函数通过闭包捕获这些实例。

版权声明: 本模块属于 Scholar Assistant Agent 子系统。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.agent.llm_client import LLMClient
from src.agent.tools.core import ToolRegistry, ToolDefinition, _extract_schema_from_function

# 导入工具实现
from src.agent.tools.atomic_tools import _export_pdf, _python_exec, _shell_exec, _web_fetch, _web_search
from src.agent.tools.builtin_tools import _crawl_arxiv, _manage_knowledge
from src.agent.tools.workspace_tools import (
    _build_git_command,
    _git_op,
    _glob_files,
    _grep_files,
    _list_directory,
    _read_file_v2,
    _run_command_v2,
    _str_replace,
    _undo_last_change,
    _write_file_v2,
)

logger = logging.getLogger(__name__)


def _format_argument_graph(g: Any) -> str:
    """把 ArgGraph 渲染成 Agent 友好的文本：节点 + 边 + 结构 gap + 已存 AI issues。"""
    node_map = {n.id: n for n in g.nodes}
    lines: list[str] = [
        f"== 论证图: \"{g.title}\" ({len(g.nodes)} 节点, {len(g.edges)} 边) ==",
    ]
    if g.source_doc:
        lines.append(f"绑定文件: {g.source_doc}")

    lines.append("\n节点:")
    for n in g.nodes:
        text = (n.text or "").strip().replace("\n", " ")
        if len(text) > 90:
            text = text[:90] + "…"
        lines.append(f"  [{n.node_type}] {n.id} {text}")

    if g.edges:
        lines.append("\n边:")
        for e in g.edges:
            s = node_map.get(e.source_id)
            t = node_map.get(e.target_id)
            s_lbl = f"{e.source_id}({s.node_type})" if s else e.source_id
            t_lbl = f"{e.target_id}({t.node_type})" if t else e.target_id
            lines.append(f"  {s_lbl} --{e.relation_type}--> {t_lbl}")

    # ── 结构 gap 分析（确定性、免费，不调 AI）──
    incoming: dict[str, list] = {}
    outgoing: dict[str, list] = {}
    for e in g.edges:
        incoming.setdefault(e.target_id, []).append(e)
        outgoing.setdefault(e.source_id, []).append(e)
    connected = {e.source_id for e in g.edges} | {e.target_id for e in g.edges}

    unsupported_claims = [
        n for n in g.nodes
        if n.node_type == "claim"
        and not any(e.relation_type in ("supports", "warrants") for e in incoming.get(n.id, []))
    ]
    floating_grounds = [
        n for n in g.nodes
        if n.node_type == "grounds"
        and not any(e.relation_type == "supports" for e in outgoing.get(n.id, []))
    ]
    unanswered_rebuttals = [
        n for n in g.nodes
        if n.node_type == "rebuttal"
        and not any(e.relation_type == "counters" for e in incoming.get(n.id, []))
    ]
    isolated = [n for n in g.nodes if n.id not in connected]

    def _brief(n) -> str:
        t = (n.text or "").strip().replace("\n", " ")
        return f"{n.id}: \"{t[:70] + '…' if len(t) > 70 else t}\""

    gap_lines: list[str] = []
    if unsupported_claims:
        gap_lines.append("❌ 悬空主张（无 grounds/warrant 支撑）:")
        gap_lines += [f"   {_brief(n)}" for n in unsupported_claims]
    if floating_grounds:
        gap_lines.append("⚠️ 未接入图的证据（grounds 未连到任何 claim）:")
        gap_lines += [f"   {_brief(n)}" for n in floating_grounds]
    if unanswered_rebuttals:
        gap_lines.append("❓ 未回应的反驳（rebuttal 无 counter）:")
        gap_lines += [f"   {_brief(n)}" for n in unanswered_rebuttals]
    if isolated:
        gap_lines.append("🔗 孤立节点（无任何边）:")
        gap_lines += [f"   [{n.node_type}] {_brief(n)}" for n in isolated]

    lines.append("\n== Gap 分析 ==")
    lines.append("\n".join(gap_lines) if gap_lines else "  结构完整：无悬空主张/未接入证据/未回应反驳/孤立节点。")

    # ── 已存的 AI critique issues（如有）──
    issues = getattr(g, "issues", None) or []
    if issues:
        lines.append(f"\n== 已记录的 AI 审查问题 ({len(issues)} 条) ==")
        for iss in issues:
            sev = getattr(iss, "severity", "info")
            cat = getattr(iss, "category", "other")
            msg = getattr(iss, "message", "")
            lines.append(f"  [{sev}] {cat}: {msg}")

    return "\n".join(lines)


def _format_argument_ledger(ledger: Any) -> str:
    """把 Ledger 渲染成 Agent 友好的文本：承诺按兑付状态分组。"""
    promises = list(ledger.promises)
    groups: dict[str, list] = {"unpaid": [], "mismatch": [], "partial": [], "paid": [], "unknown": []}
    for p in promises:
        groups.setdefault(p.status, []).append(p)

    title = ledger.doc_title or ledger.doc_id
    counts = " | ".join(
        f"{len(groups[s])} {s}" for s in ("paid", "partial", "unpaid", "mismatch", "unknown") if groups.get(s)
    )
    lines = [f"== 论证账本: \"{title}\" ({len(promises)} 条承诺) ==", f"状态分布: {counts}"]

    labels = {
        "unpaid": "✗ 未兑付 (UNPAID)",
        "mismatch": "✗ 与正文不符 (MISMATCH)",
        "partial": "⚠️ 部分兑付 (PARTIAL)",
        "paid": "✓ 已兑付 (PAID)",
        "unknown": "? 未判定 (UNKNOWN)",
    }
    # 优先展示问题项（unpaid/mismatch/partial），paid 放后
    for status in ("unpaid", "mismatch", "partial", "paid", "unknown"):
        items = groups.get(status) or []
        if not items:
            continue
        lines.append(f"\n{labels[status]} ({len(items)}):")
        for p in items:
            text = (p.text or "").strip().replace("\n", " ")
            if len(text) > 100:
                text = text[:100] + "…"
            lines.append(f"  [{p.id}] {text}")
            if getattr(p, "note", None):
                note = p.note.strip().replace("\n", " ")
                lines.append(f"        → {note[:120]}")
    return "\n".join(lines)


def create_default_registry(
    ollama_client: Any | None = None,
    cloud_client: Any | None = None,
    rag_store: Any | None = None,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    cloud_base_url: str = "",
    cloud_api_key: str = "",
    cloud_model: str = "",
    workspace_root: str = "",
    graph_store: Any | None = None,
    companion_store: Any | None = None,
) -> ToolRegistry:
    """创建包含所有默认工具的注册表。

    通过依赖注入将现有的翻译客户端、RAG 存储等实例传入，
    工具函数通过闭包捕获这些实例，避免在工具内部创建新的客户端。

    Args:
        ollama_client: 已初始化的 OllamaClient 实例（可选）。
        cloud_client: 已初始化的 CloudClient 实例（可选）。
        rag_store: 已初始化的 RAGStore 实例（可选）。
        ollama_base_url: Ollama API 地址，供 LLM 工具使用。
        model: Ollama 模型名称。
        cloud_base_url: 云端 API 地址。
        cloud_api_key: 云端 API Key。
        cloud_model: 云端模型名称。
        workspace_root: 工作区根目录路径，启用 AWA v2 工作区工具。

    Returns:
        包含所有可用工具的 ToolRegistry 实例。
    """
    registry = ToolRegistry()

    # --- Shared LLM client for text-processing tools ---
    _llm = LLMClient(
        ollama_base_url=ollama_base_url,
        model=model,
        cloud_base_url=cloud_base_url,
        cloud_api_key=cloud_api_key,
        cloud_model=cloud_model,
        temperature=0.3,
        num_predict=4096,
    )

    # --- 翻译工具 ---
    if ollama_client is not None or cloud_client is not None:

        def translate_text(text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
            """翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。

            Args:
                text: 待翻译的文本内容。
                source_lang: 源语言代码，默认 "en"（英文）。
                target_lang: 目标语言代码，默认 "zh"（中文）。
            """
            if ollama_client is not None:
                client = ollama_client
            elif cloud_client is not None:
                client = cloud_client
            else:
                return "错误: 无可用的翻译客户端"
            result = client.translate(text)
            return result.translated

        translate_text._agent_tool_def = ToolDefinition(
            name="translate_text",
            description="翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。",
            parameters=_extract_schema_from_function(translate_text),
            fn=translate_text,
        )
        registry.register(translate_text)

    # --- 文档解析工具 ---
    try:
        from src.parser import extract_document as _extract_doc

        def parse_document(file_path: str) -> str:
            """解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。

            Args:
                file_path: 文档文件的绝对路径。
            """
            try:
                doc = _extract_doc(file_path)
                return doc.full_text
            except Exception as e:
                return f"文档解析失败: {e}"

        parse_document._agent_tool_def = ToolDefinition(
            name="parse_document",
            description="解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。",
            parameters=_extract_schema_from_function(parse_document),
            fn=parse_document,
        )
        registry.register(parse_document)
    except ImportError:
        logger.warning("parser 模块不可用，跳过 parse_document 工具注册")

    # --- RAG 检索工具 ---
    if rag_store is not None:

        def search_documents(query: str, top_k: int = 5) -> str:
            """检索你的个人文献库（历史翻译收录的论文）。仅当需要回忆当前项目之外、历史读过的文献时调用；当前项目的文件请优先用 read_file / grep_files 直接读取，速度更快、结果更精确。

            Args:
                query: 查询文本（中英文均可）。
                top_k: 返回的最大结果数量，默认 5。
            """
            try:
                results = rag_store.retrieve_context(query, top_k=top_k)
                if not results:
                    return "未找到相关文档内容。请先使用 parse_document 解析文档并入库。"
                parts: list[str] = []
                for i, r in enumerate(results):
                    parts.append(f"[片段 {i + 1}] (相似度: {1 - r.get('distance', 0):.2f})\n{r['text']}")
                return "\n\n---\n\n".join(parts)
            except Exception as e:
                return f"文档检索失败: {e}"

        search_documents._agent_tool_def = ToolDefinition(
            name="search_documents",
            description="检索你的个人文献库（历史翻译收录的论文）。仅当需要回忆当前项目之外、历史读过的文献时调用；当前项目的文件请优先用 read_file / grep_files 直接读取，速度更快、结果更精确。",
            parameters=_extract_schema_from_function(search_documents),
            fn=search_documents,
        )
        registry.register(search_documents)

    # --- 论证图工具（Agent 的"符号表"）---
    if graph_store is not None:

        def read_argument_graph(file_path: str = "", graph_id: str = "") -> str:
            """读取论文的 Toulmin 论证图，了解论证结构和逻辑漏洞。这是论文的"符号表"：claim（主张）、grounds（依据）、warrant（论证保证）、backing（支撑）、rebuttal（反驳）之间的支撑关系。

            用它来回答"我的论证哪里有漏洞"、"哪个主张还没有证据支撑"、"有没有没回应的反驳"。

            Args:
                file_path: 论文文件路径（优先）。返回该文件对应的论证图 + gap 分析。
                graph_id: 论证图 ID（可选）。当你已从列表得到具体 ID 时用。
                          两者都为空时，列出所有可用论证图供你选择。
            """
            try:
                if graph_id:
                    g = graph_store.get(graph_id)
                elif file_path:
                    g = graph_store.get_by_source_doc(file_path)
                else:
                    graphs = graph_store.list_graphs()
                    if not graphs:
                        return "暂无论证图。用户需先在编辑器的论证面板中提取论证图。"
                    lines = [f"共 {len(graphs)} 个论证图："]
                    for gi in sorted(graphs, key=lambda x: x.get("updated_at", 0), reverse=True):
                        lines.append(
                            f"  • {gi['id']} — \"{gi['title']}\" "
                            f"({gi['node_count']} 节点, source_doc={gi.get('source_doc') or '未绑定'})"
                        )
                    lines.append("\n传入 file_path 或 graph_id 获取完整结构 + gap 分析。")
                    return "\n".join(lines)
                if g is None:
                    return f"未找到对应论证图（file_path={file_path!r}, graph_id={graph_id!r}）。可不带参数调用以列出全部。"
                return _format_argument_graph(g)
            except Exception as e:
                return f"读取论证图失败: {e}"

        read_argument_graph._agent_tool_def = ToolDefinition(
            name="read_argument_graph",
            description="读取论文的 Toulmin 论证图（claim/grounds/warrant/backing/rebuttal 及支撑关系）+ 结构 gap 分析（悬空主张/未接入证据/未回应反驳/孤立节点）。用于精准定位论证漏洞。传 file_path 按文件查，无参列出全部。",
            parameters=_extract_schema_from_function(read_argument_graph),
            fn=read_argument_graph,
        )
        registry.register(read_argument_graph)

    # --- 论证账本工具（承诺 ↔ 兑付追踪）---
    if companion_store is not None:

        def read_argument_ledger(file_path: str = "", doc_id: str = "") -> str:
            """读取论文的论证账本：abstract/intro 里的每条承诺，以及正文是否兑付（paid 已兑付 / partial 部分 / unpaid 未兑付 / mismatch 与正文不符）。

            用它来回答"我在摘要里承诺了什么但正文没做到"、"哪些 claim 过度宣称"。这是给出改稿建议的最强信号。

            Args:
                file_path: 论文文件路径（优先，对已打开文件 doc_id 即为路径）。
                doc_id: 账本 doc_id（可选）。两者都为空时列出所有账本。
            """
            try:
                if doc_id:
                    ledger = companion_store.get_ledger(doc_id)
                elif file_path:
                    ledger = companion_store.get_ledger_by_path(file_path)
                else:
                    ledgers = companion_store.list_ledgers()
                    if not ledgers:
                        return "暂无论证账本。用户需先在编辑器的论证陪练面板中构建账本。"
                    lines = [f"共 {len(ledgers)} 个论证账本："]
                    for li in sorted(ledgers, key=lambda x: x.get("last_built_at", 0), reverse=True):
                        lines.append(
                            f"  • doc_id={li['doc_id']} — \"{li.get('doc_title') or '无标题'}\" "
                            f"({li['promise_count']} 条承诺)"
                        )
                    lines.append("\n传入 file_path 或 doc_id 查看承诺兑付状态。")
                    return "\n".join(lines)
                if ledger is None:
                    return f"未找到对应账本（file_path={file_path!r}, doc_id={doc_id!r}）。可不带参数调用以列出全部。"
                return _format_argument_ledger(ledger)
            except Exception as e:
                return f"读取论证账本失败: {e}"

        read_argument_ledger._agent_tool_def = ToolDefinition(
            name="read_argument_ledger",
            description="读取论文的论证账本：abstract/intro 承诺 ↔ 正文兑付状态（paid/partial/unpaid/mismatch）。用于发现过度宣称、未兑付承诺。传 file_path 按文件查，无参列出全部。",
            parameters=_extract_schema_from_function(read_argument_ledger),
            fn=read_argument_ledger,
        )
        registry.register(read_argument_ledger)

    # --- arXiv 爬取工具 ---
    crawl_tool_def = ToolDefinition(
        name="crawl_arxiv",
        description="搜索 arXiv 学术论文，返回标题、作者和摘要。通过 arXiv API 检索最新学术论文信息。",
        parameters=_extract_schema_from_function(_crawl_arxiv),
        fn=_crawl_arxiv,
    )
    registry.register(crawl_tool_def)

    # --- 参考文献格式化工具 ---
    def format_bibliography(
        bibtex_entry: str,
        style: str = "ieee",
        target_lang: str = "zh",
    ) -> str:
        """将 BibTeX 条目格式化为指定的引用格式。支持 GB/T 7714、APA、IEEE 等常见学术引用格式。

        Args:
            bibtex_entry: BibTeX 格式的参考文献条目（@article{...}, @book{...} 等）
            style: 引用格式，可选 ieee（IEEE）、apa（APA 第七版）、gbt7714（GB/T 7714-2015）、mla（MLA 第九版），默认 ieee
            target_lang: 引用语言，可选 zh（中文）、en（英文），默认 zh
        """
        styles = ["ieee", "apa", "gbt7714", "mla"]
        if style not in styles:
            return f"不支持的引用格式: {style}。支持的格式: {', '.join(styles)}"
        prompt = f"""请将以下 BibTeX 条目格式化为 {style.upper()} 引用格式的文本。

要求：
1. 只输出格式化后的参考文献，不要任何解释或说明
2. 严格按照 {style.upper()} 格式规范
3. 目标语言：{"中文" if target_lang == "zh" else "英文"}
4. 译名使用学界公认译法，不要生造

BibTeX 条目：
{bibtex_entry}

格式化后的引用："""
        return _llm.call_simple_sync(prompt)

    format_bibliography._agent_tool_def = ToolDefinition(
        name="format_bibliography",
        description="将 BibTeX 条目格式化为指定引用格式（IEEE/APA/GB/T 7714/MLA）。",
        parameters=_extract_schema_from_function(format_bibliography),
        fn=format_bibliography,
    )
    registry.register(format_bibliography)

    # --- 科研图表生成工具 (P3: 借鉴 nature-figure) ---
    try:
        from src.agent.tools.figure_tools import generate_figure, list_figure_types

        def generate_scientific_figure(
            figure_type: str = "bar",
            figure_claim: str = "",
            data_description: str = "",
        ) -> str:
            """生成发表级别的科研图表。支持 bar/line/scatter/heatmap/distribution/multipanel。

            使用 nature-figure 方法：先定核心结论→选择图表类型→生成 Nature 风格脚本。
            输出 SVG+PDF+PNG 三种格式，使用语义色板，确保文本可编辑。

            Args:
                figure_type: 图表类型 (bar/line/scatter/heatmap/distribution/multipanel)
                figure_claim: 图表要辩护的一句话核心主张
                data_description: 数据结构描述
            """
            return generate_figure(
                figure_type=figure_type,
                figure_claim=figure_claim,
                data_description=data_description,
            )

        def list_available_figure_types() -> str:
            """列出所有可用的科研图表类型及其特性。"""
            return list_figure_types()

        generate_scientific_figure._agent_tool_def = ToolDefinition(
            name="generate_figure",
            description="生成发表级别的科研图表 (bar/line/scatter/heatmap/distribution/multipanel)。使用 Nature 风格配色和排版。",
            parameters=_extract_schema_from_function(generate_scientific_figure),
            fn=generate_scientific_figure,
        )
        registry.register(generate_scientific_figure)

        list_available_figure_types._agent_tool_def = ToolDefinition(
            name="list_figure_types",
            description="列出所有可用的科研图表类型及其特性。",
            parameters=_extract_schema_from_function(list_available_figure_types),
            fn=list_available_figure_types,
        )
        registry.register(list_available_figure_types)

        logger.info("图表生成工具注册完成")
    except ImportError as e:
        logger.warning("图表生成工具不可用: %s", e)

    # --- 特殊元素处理工具 ---
    try:
        from src.agent.special_elements import build_special_elements_tools
        special_tools = build_special_elements_tools()
        for tool_def in special_tools:
            registry.register(tool_def)
        logger.info("特殊元素工具注册完成: %s", [t.name for t in special_tools])
    except ImportError as e:
        logger.warning("特殊元素模块不可用: %s", e)

    # --- shell_exec ---
    shell_exec_def = ToolDefinition(
        name="shell_exec",
        description="执行白名单内的只读 shell 命令（ls/cat/grep/find/git status 等）。不支持 pip/python/npm 等开发命令——需要安装包或运行脚本请用 run_command。",
        parameters=_extract_schema_from_function(_shell_exec),
        fn=_shell_exec,
    )
    registry.register(shell_exec_def)

    # --- python_exec ---
    python_exec_def = ToolDefinition(
        name="python_exec",
        description="执行 Python 代码片段并返回输出。受限环境（禁止 os/subprocess 等）。需要安装包或调用系统命令请用 run_command。",
        parameters=_extract_schema_from_function(_python_exec),
        fn=_python_exec,
    )
    registry.register(python_exec_def)

    # --- web_fetch ---
    web_fetch_def = ToolDefinition(
        name="web_fetch",
        description="获取网页内容。支持 HTTP/HTTPS，可选提取纯文本或返回原始 HTML。",
        parameters=_extract_schema_from_function(_web_fetch),
        fn=_web_fetch,
    )
    registry.register(web_fetch_def)

    # --- web_search ---
    web_search_def = ToolDefinition(
        name="web_search",
        description="使用搜索引擎搜索信息。通过 Bing 返回搜索结果摘要。",
        parameters=_extract_schema_from_function(_web_search),
        fn=_web_search,
    )
    registry.register(web_search_def)

    # --- export_pdf ---
    export_pdf_def = ToolDefinition(
        name="export_pdf",
        description="将 Markdown 内容导出为 PDF 文件。使用 Pandoc + Tectonic 编译 LaTeX 生成 PDF。",
        parameters=_extract_schema_from_function(_export_pdf),
        fn=_export_pdf,
    )
    registry.register(export_pdf_def)

    # --- manage_knowledge ---
    if rag_store is not None:
        def manage_knowledge(
            action: str,
            doc_id: str = "",
            file_path: str = "",
            text: str = "",
            query: str = "",
            top_k: int = 5,
        ) -> str:
            """管理知识库文档。支持入库、删除、列出和检索知识库中的文档。

            Args:
                action: 操作类型。ingest（入库）、delete（删除）、list（列出所有）、retrieve（检索）。
                doc_id: 文档 ID（ingest/delete 时必需）。
                file_path: 文档路径（ingest 时可选，与 text 二选一）。
                text: 直接文本内容（ingest 时可选，与 file_path 二选一）。
                query: 检索查询文本（retrieve 时必需）。
                top_k: 检索返回的最大结果数，默认 5。
            """
            action = action.strip().lower()
            if action == "ingest":
                if not doc_id:
                    return "错误: ingest 操作需要 doc_id 参数"
                content = text
                if not content and file_path:
                    try:
                        content = Path(file_path).read_text(encoding="utf-8")
                    except Exception as e:
                        return f"读取文件失败: {e}"
                if not content:
                    return "错误: 需要提供 text 或 file_path 参数"
                count = rag_store.ingest_document(doc_id, content)
                return f"文档入库完成: {doc_id}, {count} 个文本块"
            elif action == "delete":
                if not doc_id:
                    return "错误: delete 操作需要 doc_id 参数"
                rag_store.delete_document(doc_id)
                return f"文档已删除: {doc_id}"
            elif action == "list":
                docs = rag_store.list_documents()
                if not docs:
                    return "知识库为空"
                lines = [f"  {d.id}: {d.title} ({d.chunk_count} 块)" for d in docs]
                return f"知识库文档 ({len(docs)} 个):\n" + "\n".join(lines)
            elif action == "retrieve":
                if not query:
                    return "错误: retrieve 操作需要 query 参数"
                results = rag_store.retrieve_context(query, top_k=top_k)
                if not results:
                    return "未找到相关内容"
                parts: list[str] = []
                for i, r in enumerate(results):
                    parts.append(f"[片段 {i + 1}] (相似度: {1 - r.get('distance', 0):.2f})\n{r['text']}")
                return "\n\n---\n\n".join(parts)
            else:
                return f"未知操作: {action}。支持的操作: ingest, delete, list, retrieve"

        manage_knowledge._agent_tool_def = ToolDefinition(
            name="manage_knowledge",
            description="管理知识库文档。支持入库(ingest)、删除(delete)、列出(list)、检索(retrieve)。",
            parameters=_extract_schema_from_function(manage_knowledge),
            fn=manage_knowledge,
        )
        registry.register(manage_knowledge)
    else:
        # 无 RAG 存储时仍注册占位工具，给用户友好提示
        manage_knowledge_def = ToolDefinition(
            name="manage_knowledge",
            description="管理知识库文档。支持入库(ingest)、删除(delete)、列出(list)、检索(retrieve)。",
            parameters=_extract_schema_from_function(_manage_knowledge),
            fn=_manage_knowledge,
        )
        registry.register(manage_knowledge_def)

    # --- 工作区工具 ---
    # workspace_root 为空时回退到 ~/scholar_agent_files 沙箱目录
    import os
    effective_ws = workspace_root or os.environ.get(
        "SCHOLAR_AGENT_SANDBOX",
        os.path.expanduser("~/scholar_agent_files"),
    )
    os.makedirs(effective_ws, exist_ok=True)

    from src.agent.workspace import WorkspaceEnv
    from src.agent.change_journal import ChangeJournal
    from src.agent.bash_session import BashSession

    ws_env = WorkspaceEnv(root=effective_ws)
    ws_journal = ChangeJournal(backup_root=ws_env.backup_root_path())
    ws_bash = BashSession(workspace_root=effective_ws)

    def read_file_v2(file_path: str, offset: int = 0, limit: int | None = None, encoding: str = "utf-8") -> str:
        """读取项目工作区内的文件，返回带行号的内容。

        Args:
            file_path: 相对项目根的路径，绝对路径若在项目根内也接受。
            offset: 起始行号（0-indexed），默认 0。
            limit: 最多读取行数，None 表示读到结尾。
            encoding: 文件编码，默认 utf-8。
        """
        return _read_file_v2(file_path, ws_env, offset=offset, limit=limit, encoding=encoding)

    def list_directory(path: str = ".", pattern: str | None = None, recursive: bool = False, max_entries: int = 200) -> str:
        """列出目录内容，返回带类型和大小的结构。

        Args:
            path: 相对项目根的目录路径，默认根目录。
            pattern: glob 过滤（如 '*.py'），None 表示不过滤。
            recursive: 是否递归（递归时尊重 .gitignore）。
            max_entries: 最大返回条目数，默认 200。
        """
        return _list_directory(path, ws_env, pattern=pattern, recursive=recursive, max_entries=max_entries)

    def str_replace(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """精确字符串替换。在文件中找到精确的旧字符串并替换为新字符串。

        Args:
            file_path: 目标文件相对路径。
            old_string: 待替换的精确字符串（含缩进、换行）。
            new_string: 替换后的字符串。
            replace_all: True 时替换所有出现；False 时要求 old_string 唯一。
        """
        return _str_replace(file_path, old_string, new_string, ws_env, ws_journal, replace_all=replace_all)

    def write_file(file_path: str, content: str, must_not_exist: bool = False) -> str:
        """整文件写入。仅用于新建文件或全量重写已有文件。

        Args:
            file_path: 目标文件相对路径。
            content: 完整内容。
            must_not_exist: True 时若文件已存在则报错。
        """
        return _write_file_v2(file_path, content, ws_env, ws_journal, must_not_exist=must_not_exist)

    def undo_last_change(count: int = 1, backup_id: str | None = None) -> str:
        """回退最近 N 次破坏性操作。从变更日志中恢复文件到之前的状态。

        Args:
            count: 回退次数，默认 1。
            backup_id: 指定回退到某个 backup 点。
        """
        return _undo_last_change(ws_journal, ws_env, count=count, backup_id=backup_id)

    def run_command(command: str, timeout: int = 120, cwd: str | None = None) -> str:
        """在持久 Shell 会话中执行命令。cwd 和 env 跨命令保持。

        Args:
            command: 要执行的 shell 命令。
            timeout: 超时秒数，默认 120，最大 600。
            cwd: 工作目录（相对项目根），None 表示沿用上次 cwd。
        """
        return _run_command_v2(command, ws_bash, timeout=timeout, cwd=cwd)

    def git_op(operation: str, args: dict | None = None) -> str:
        """受控 git 操作。支持 status/diff/log/show/branch/commit/restore/checkout/add/stash。

        Args:
            operation: 操作名（status/diff/log/show/branch/commit/restore/checkout/add/stash）。
            args: 操作参数字典。
        """
        return _git_op(operation, ws_env, args=args)

    def grep_files(pattern: str, path: str = ".", glob: str = "*", case_sensitive: bool = True, max_results: int = 50, context_lines: int = 0) -> str:
        """在工作区文件中正则搜索内容，返回匹配行。比 list+read 快 10 倍以上。

        Args:
            pattern: 正则表达式或字面字符串。
            path: 搜索根目录（相对项目根），默认 "."。
            glob: 文件过滤 glob，如 "*.py"，默认 "*"。
            case_sensitive: 是否区分大小写，默认 True。
            max_results: 最多返回匹配数，默认 50。
            context_lines: 每条匹配上下各显示 N 行，默认 0。
        """
        return _grep_files(pattern, ws_env, path=path, glob=glob,
                           case_sensitive=case_sensitive, max_results=max_results,
                           context_lines=context_lines)

    def glob_files(pattern: str, path: str = ".", max_results: int = 200) -> str:
        """在工作区中按 glob 模式匹配文件路径，如 '**/*.py'。

        Args:
            pattern: glob 模式，如 "**/*.py" 或 "src/**/*.ts"。
            path: 搜索根目录（相对项目根），默认 "."。
            max_results: 最多返回条目数，默认 200。
        """
        return _glob_files(pattern, ws_env, path=path, max_results=max_results)

    for fn, tool_name, desc in [
        (read_file_v2, "read_file", "读取项目工作区内的文件，返回带行号的内容。支持 offset/limit 分页。"),
        (list_directory, "list_directory", "列出目录内容，返回带类型和大小的结构。支持递归和 glob 过滤。"),
        (grep_files, "grep_files", "在工作区文件中正则搜索内容，返回匹配行。比 list+read 快 10 倍以上。支持 glob 文件过滤和上下文行。"),
        (glob_files, "glob_files", "按 glob 模式匹配工作区文件路径，如 '**/*.py'、'src/**/*.ts'。"),
        (str_replace, "str_replace", "精确字符串替换。在文件中找到唯一匹配的旧字符串并替换。"),
        (write_file, "write_file", "整文件写入。用于新建文件或全量重写。会自动备份被覆盖的文件。"),
        (undo_last_change, "undo_last_change", "回退最近 N 次破坏性操作。从 .agent_backup 中恢复文件。"),
        (run_command, "run_command", "在持久 Shell 会话中执行命令。支持 pip install / python / npm 等开发命令（自动安全审查）。cwd 和 env 跨命令保持。安装 Python 包、运行脚本、导出文件请优先用此工具。"),
        (git_op, "git_op", "受控 git 操作。比直接 shell 更安全，支持 status/diff/log/show/branch/commit 等。"),
    ]:
        registry.register(ToolDefinition(
            name=tool_name,
            description=desc,
            parameters=_extract_schema_from_function(fn),
            fn=fn,
        ))

    logger.info("AWA v2 工作区工具注册完成 (root=%s)", effective_ws)

    # ── Integrity check tools (Phase 5) ──
    try:
        from src.agent.tools.integrity_tools import check_integrity, check_citations

        registry.register(ToolDefinition(
            name="check_integrity",
            description="对文档进行完整性检查：检测虚构引用、异常统计声明（p值越界、百分比异常）、参考文献一致性",
            parameters=_extract_schema_from_function(check_integrity),
            fn=check_integrity,
        ))
        registry.register(ToolDefinition(
            name="check_citations",
            description="检查文档中引用与声明的对齐情况，分析每个引用的上下文",
            parameters=_extract_schema_from_function(check_citations),
            fn=check_citations,
        ))
        logger.info("完整性检查工具注册完成")
    except ImportError:
        logger.warning("Integrity tools not available")

    logger.info("默认工具注册完成: %s", [t.name for t in registry.list_tools()])
    return registry


# 导出公共接口
__all__ = ["create_default_registry"]
