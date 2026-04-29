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
    _list_directory,
    _read_file_v2,
    _run_command_v2,
    _str_replace,
    _undo_last_change,
    _write_file_v2,
)

logger = logging.getLogger(__name__)


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
            """在已入库的文档中检索与查询相关的段落。基于向量相似度匹配，返回最相关的文本片段。

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
            description="在已入库的文档中检索与查询相关的段落。基于向量相似度匹配，返回最相关的文本片段。",
            parameters=_extract_schema_from_function(search_documents),
            fn=search_documents,
        )
        registry.register(search_documents)

    # --- arXiv 爬取工具 ---
    crawl_tool_def = ToolDefinition(
        name="crawl_arxiv",
        description="搜索 arXiv 学术论文，返回标题、作者和摘要。通过 arXiv API 检索最新学术论文信息。",
        parameters=_extract_schema_from_function(_crawl_arxiv),
        fn=_crawl_arxiv,
    )
    registry.register(crawl_tool_def)

    # --- 文本润色工具 ---
    def polish_text(text: str, style: str = "academic") -> str:
        """润色学术文本，改善表达和语法。支持多种写作风格的文本润色和优化。

        Args:
            text: 待润色的文本内容。
            style: 润色风格，可选 academic（学术）、formal（正式）、concise（简洁），默认 academic。
        """
        style_hints = {
            "academic": "使用严谨的学术语言，确保逻辑清晰、用词精准",
            "formal": "使用正式的书面语，避免口语化表达",
            "concise": "精简冗余表达，保留核心信息，使文字更加凝练",
        }
        hint = style_hints.get(style, style_hints["academic"])
        prompt = f"请润色以下文本。要求：{hint}。只输出润色后的文本，不要解释。\n\n{text}"
        return _llm.call_simple_sync(prompt)

    polish_text._agent_tool_def = ToolDefinition(
        name="polish_text",
        description="润色学术文本，改善表达和语法。支持多种写作风格的文本润色和优化。",
        parameters=_extract_schema_from_function(polish_text),
        fn=polish_text,
    )
    registry.register(polish_text)

    # --- 文本摘要工具 ---
    def summarize_text(text: str, max_sentences: int = 5) -> str:
        """生成文本的精简摘要。提取核心论点和关键信息，输出结构化摘要。

        Args:
            text: 待摘要的文本内容。
            max_sentences: 摘要的最大句子数，默认 5。
        """
        prompt = (
            f"请用中文为以下文本生成摘要，不超过 {max_sentences} 个句子。"
            f"提取核心论点和关键信息。\n\n{text}"
        )
        return _llm.call_simple_sync(prompt)

    summarize_text._agent_tool_def = ToolDefinition(
        name="summarize_text",
        description="生成文本的精简摘要。提取核心论点和关键信息，输出结构化摘要。",
        parameters=_extract_schema_from_function(summarize_text),
        fn=summarize_text,
    )
    registry.register(summarize_text)

    # --- 大纲生成工具 ---
    def generate_outline(topic: str, sections: int = 5) -> str:
        """生成学术论文或报告的结构化大纲。根据主题生成层次分明的大纲框架。

        Args:
            topic: 论文或报告的主题。
            sections: 大纲的章节数量，默认 5。
        """
        prompt = (
            f"请为主题「{topic}」生成一个学术论文大纲，包含 {sections} 个主要章节。"
            "每个章节下给出 2-3 个子节。使用 Markdown 格式输出。"
        )
        return _llm.call_simple_sync(prompt)

    generate_outline._agent_tool_def = ToolDefinition(
        name="generate_outline",
        description="生成学术论文或报告的结构化大纲。根据主题生成层次分明的大纲框架。",
        parameters=_extract_schema_from_function(generate_outline),
        fn=generate_outline,
    )
    registry.register(generate_outline)

    # --- 段落扩写工具 ---
    def expand_section(section: str, context: str = "") -> str:
        """扩写论文段落，补充细节和论据。根据上下文将简短的段落扩展为完整论述。

        Args:
            section: 待扩写的段落内容。
            context: 上下文信息（可选，帮助 LLM 保持一致性）。
        """
        ctx_part = f"\n\n参考上下文:\n{context}" if context else ""
        prompt = (
            f"请将以下段落扩写为 200-400 字的完整论述，补充细节、论据和例子。"
            "保持学术风格，逻辑连贯。只输出扩写后的文本。\n\n"
            f"原文: {section}{ctx_part}"
        )
        return _llm.call_simple_sync(prompt)

    expand_section._agent_tool_def = ToolDefinition(
        name="expand_section",
        description="扩写论文段落，补充细节和论据。根据上下文将简短的段落扩展为完整论述。",
        parameters=_extract_schema_from_function(expand_section),
        fn=expand_section,
    )
    registry.register(expand_section)

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

    # --- 特殊元素处理工具 ---
    try:
        from src.agent.special_elements import build_special_elements_tools
        special_tools = build_special_elements_tools()
        for tool_def in special_tools:
            registry.register(tool_def)
        logger.info("特殊元素工具注册完成: %s", [t.name for t in special_tools])
    except ImportError as e:
        logger.warning("特殊元素模块不可用: %s", e)

    # --- Phase 4: shell_exec ---
    shell_exec_def = ToolDefinition(
        name="shell_exec",
        description="执行白名单内的 shell 命令并返回输出。仅允许只读和低风险命令（ls/cat/grep/find/git 等）。",
        parameters=_extract_schema_from_function(_shell_exec),
        fn=_shell_exec,
    )
    registry.register(shell_exec_def)

    # --- Phase 4: python_exec ---
    python_exec_def = ToolDefinition(
        name="python_exec",
        description="执行 Python 代码片段并返回输出。在受限环境中运行（禁止 os/subprocess 等），有超时保护。",
        parameters=_extract_schema_from_function(_python_exec),
        fn=_python_exec,
    )
    registry.register(python_exec_def)

    # --- Phase 4: web_fetch ---
    web_fetch_def = ToolDefinition(
        name="web_fetch",
        description="获取网页内容。支持 HTTP/HTTPS，可选提取纯文本或返回原始 HTML。",
        parameters=_extract_schema_from_function(_web_fetch),
        fn=_web_fetch,
    )
    registry.register(web_fetch_def)

    # --- Phase 4: web_search ---
    web_search_def = ToolDefinition(
        name="web_search",
        description="使用搜索引擎搜索信息。通过 Bing 返回搜索结果摘要。",
        parameters=_extract_schema_from_function(_web_search),
        fn=_web_search,
    )
    registry.register(web_search_def)

    # --- Phase 4: export_pdf ---
    export_pdf_def = ToolDefinition(
        name="export_pdf",
        description="将 Markdown 内容导出为 PDF 文件。使用 Pandoc + Tectonic 编译 LaTeX 生成 PDF。",
        parameters=_extract_schema_from_function(_export_pdf),
        fn=_export_pdf,
    )
    registry.register(export_pdf_def)

    # --- Phase 4: manage_knowledge ---
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

    # --- AWA v2: 工作区工具 ---
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

    for fn, tool_name, desc in [
        (read_file_v2, "read_file", "读取项目工作区内的文件，返回带行号的内容。支持 offset/limit 分页。"),
        (list_directory, "list_directory", "列出目录内容，返回带类型和大小的结构。支持递归和 glob 过滤。"),
        (str_replace, "str_replace", "精确字符串替换。在文件中找到唯一匹配的旧字符串并替换。"),
        (write_file, "write_file", "整文件写入。用于新建文件或全量重写。会自动备份被覆盖的文件。"),
        (undo_last_change, "undo_last_change", "回退最近 N 次破坏性操作。从 .agent_backup 中恢复文件。"),
        (run_command, "run_command", "在持久 Shell 会话中执行命令。cwd 跨命令保持。支持黑/白名单安全检查。"),
        (git_op, "git_op", "受控 git 操作。比直接 shell 更安全，支持 status/diff/log/show/branch/commit 等。"),
    ]:
        registry.register(ToolDefinition(
            name=tool_name,
            description=desc,
            parameters=_extract_schema_from_function(fn),
            fn=fn,
        ))

    logger.info("AWA v2 工作区工具注册完成 (root=%s)", effective_ws)

    logger.info("默认工具注册完成: %s", [t.name for t in registry.list_tools()])
    return registry


# 导出公共接口
__all__ = ["create_default_registry"]
