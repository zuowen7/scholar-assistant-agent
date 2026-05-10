"""Phase 4 工具扩展测试 — shell_exec, python_exec, web_fetch, web_search, export_pdf, manage_knowledge"""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agent.tools import (
    ToolRegistry,
    _shell_exec,
    _python_exec,
    _web_fetch,
    _web_search,
    _export_pdf,
    _manage_knowledge,
    create_default_registry,
)


# ── shell_exec ──────────────────────────────────────────────────────


class TestShellExec:
    def test_whitelisted_command(self):
        result = _shell_exec("echo hello")
        assert "hello" in result

    def test_blocked_command(self):
        result = _shell_exec("format C:")
        assert "不在白名单中" in result

    def test_unknown_command(self):
        result = _shell_exec("nmap 127.0.0.1")
        assert "不在白名单中" in result

    def test_git_commands(self):
        result = _shell_exec("git --version")
        assert "git" in result.lower() or "version" in result.lower() or "exit code" in result

    def test_timeout_parameter(self):
        result = _shell_exec("echo fast", timeout=5)
        assert "fast" in result

    def test_mkdir_and_rm_in_sandbox(self):
        import tempfile
        sandbox = tempfile.mkdtemp(prefix="test_sandbox_")
        with patch("src.agent.tools.atomic_tools._SANDBOX_ROOT", sandbox):
            result = _shell_exec("mkdir test_dir")
            assert (Path(sandbox) / "test_dir").exists() or "exit code" not in result
            result = _shell_exec("rmdir test_dir")
            assert not (Path(sandbox) / "test_dir").exists() or "exit code" not in result

    def test_touch_and_rm_in_sandbox(self):
        import tempfile
        sandbox = tempfile.mkdtemp(prefix="test_sandbox_")
        with patch("src.agent.tools.atomic_tools._SANDBOX_ROOT", sandbox):
            result = _shell_exec("touch testfile.txt")
            assert (Path(sandbox) / "testfile.txt").exists() or "exit code" not in result
            result = _shell_exec("rm testfile.txt")
            assert not (Path(sandbox) / "testfile.txt").exists() or "exit code" not in result

    def test_path_traversal_blocked(self):
        result = _shell_exec("touch ../../etc/passwd")
        assert "安全限制" in result

    def test_absolute_path_blocked(self):
        result = _shell_exec("touch /etc/passwd")
        assert "安全限制" in result

    def test_windows_absolute_path_blocked(self):
        result = _shell_exec("rm C:\\Windows\\System32\\config")
        assert "安全限制" in result or "不在白名单" in result


# ── python_exec ──────────────────────────────────────────────────────


class TestPythonExec:
    def test_simple_calc(self):
        result = _python_exec("x = 2 + 3\nprint(x)")
        assert "5" in result

    def test_print_output(self):
        result = _python_exec("print('hello world')")
        assert "hello world" in result

    def test_dangerous_import_os(self):
        result = _python_exec("import os\nprint(os.listdir('.'))")
        assert "禁止导入模块: os" in result

    def test_dangerous_import_subprocess(self):
        result = _python_exec("import subprocess")
        assert "禁止导入模块: subprocess" in result

    def test_dangerous_from_import(self):
        result = _python_exec("from os import path")
        assert "禁止" in result and "os" in result

    def test_syntax_error(self):
        result = _python_exec("def foo(")
        assert "语法错误" in result

    def test_runtime_error(self):
        result = _python_exec("x = 1 / 0")
        assert "执行错误" in result

    def test_allowed_builtins(self):
        result = _python_exec("print(len([1, 2, 3]))")
        assert "3" in result

    def test_allowed_list_comprehension(self):
        result = _python_exec("print([x * 2 for x in range(5)])")
        assert "[0, 2, 4, 6, 8]" in result


# ── web_fetch ──────────────────────────────────────────────────────


class TestWebFetch:
    def test_invalid_url(self):
        result = _web_fetch("ftp://example.com")
        assert "http://" in result or "https://" in result

    def test_relative_url(self):
        result = _web_fetch("/path/to/page")
        assert "http://" in result or "https://" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_extracts_text(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><p>Hello World</p></body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com", extract_text=True)
        assert "Hello World" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_raw_html(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Hello</body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com", extract_text=False)
        assert "<html>" in result


# ── web_search ──────────────────────────────────────────────────────


class TestWebSearch:
    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_search_parses_results(self, mock_client_cls):
        html = """
        <h2><a href="https://example.com/python" h="ID=SERP,5120.1">Python Tutorial</a></h2>
        <div class="b_caption"><p class="b_lineclamp2">Learn Python programming</p></div>
        <h2><a href="https://example.com/docs" h="ID=SERP,5120.2">Python Docs</a></h2>
        <div class="b_caption"><p class="b_lineclamp2">Official documentation</p></div>
        """
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_search("python tutorial")
        assert "Python Tutorial" in result
        assert "Python Docs" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_search_no_results(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>No results</body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_search("xyznonexistent123")
        assert "未找到相关结果" in result


# ── export_pdf ──────────────────────────────────────────────────────


class TestExportPdf:
    def test_export_success(self):
        mock_module = MagicMock(
            convert_markdown=MagicMock(return_value={
                "success": True,
                "pdf_path": "/tmp/test.pdf",
                "output_path": "/tmp/test.pdf",
            }),
            tectonic_available=MagicMock(return_value=True),
            pandoc_version=MagicMock(return_value="3.6"),
        )
        with patch.dict("sys.modules", {"src.pandoc_templates": mock_module}):
            result = _export_pdf("# Title\n\nHello", title="Test")
            assert "PDF 导出成功" in result

    def test_export_failure_with_error(self):
        mock_module = MagicMock(
            convert_markdown=MagicMock(return_value={
                "success": False,
                "error": "Tectonic not found",
            }),
            tectonic_available=MagicMock(return_value=False),
        )
        with patch.dict("sys.modules", {"src.pandoc_templates": mock_module}):
            result = _export_pdf("# Test")
            assert "PDF 导出失败" in result
            assert "Tectonic" in result


# ── manage_knowledge ──────────────────────────────────────────────


    def test_placeholder_without_rag(self):
        # 当 rag_store 未注入时，占位实现应返回友好提示而非抛错
        result = _manage_knowledge(action="list")
        assert "知识库未启用" in result
        assert "manage_knowledge" in result

    def test_with_rag_list_empty(self):
        rag = MagicMock()
        rag.list_documents.return_value = []
        # Use closure-based tool from create_default_registry
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")
        assert manage_tool is not None

        result = manage_tool.fn(action="list")
        assert "知识库为空" in result

    def test_with_rag_ingest(self):
        rag = MagicMock()
        rag.ingest_document.return_value = 5
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")

        result = manage_tool.fn(action="ingest", doc_id="paper1", text="Some text content")
        assert "入库完成" in result
        assert "paper1" in result
        rag.ingest_document.assert_called_once_with("paper1", "Some text content")

    def test_with_rag_delete(self):
        rag = MagicMock()
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")

        result = manage_tool.fn(action="delete", doc_id="paper1")
        assert "已删除" in result
        rag.delete_document.assert_called_once_with("paper1")

    def test_with_rag_retrieve(self):
        rag = MagicMock()
        rag.retrieve_context.return_value = [
            {"text": "Transformer attention mechanism", "distance": 0.15},
            {"text": "Self-attention in NLP", "distance": 0.22},
        ]
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")

        result = manage_tool.fn(action="retrieve", query="attention mechanism", top_k=3)
        assert "Transformer" in result
        assert "Self-attention" in result
        rag.retrieve_context.assert_called_once_with("attention mechanism", top_k=3)

    def test_with_rag_unknown_action(self):
        rag = MagicMock()
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")

        result = manage_tool.fn(action="unknown_action")
        assert "未知操作" in result

    def test_with_rag_ingest_missing_doc_id(self):
        rag = MagicMock()
        registry = create_default_registry(rag_store=rag)
        manage_tool = registry.get("manage_knowledge")

        result = manage_tool.fn(action="ingest", text="content")
        assert "doc_id" in result

    def test_with_rag_ingest_from_file(self):
        rag = MagicMock()
        rag.ingest_document.return_value = 3

        # Create a temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("Test document content for ingestion.")
            tmp_path = f.name

        try:
            registry = create_default_registry(rag_store=rag)
            manage_tool = registry.get("manage_knowledge")
            result = manage_tool.fn(action="ingest", doc_id="doc1", file_path=tmp_path)
            assert "入库完成" in result
        finally:
            os.unlink(tmp_path)


# ── create_default_registry 集成测试 ──────────────────────────────


class TestRegistryIntegration:
    def test_all_phase4_tools_registered(self):
        registry = create_default_registry()
        names = {t.name for t in registry.list_tools()}
        phase4_tools = {
            "shell_exec", "python_exec", "web_fetch",
            "web_search", "export_pdf", "manage_knowledge",
        }
        assert phase4_tools.issubset(names), f"Missing: {phase4_tools - names}"

    def test_tool_definitions_have_required_fields(self):
        registry = create_default_registry()
        for t in registry.list_tools():
            assert t.name, "Tool missing name"
            assert t.description, f"Tool {t.name} missing description"
            assert "properties" in t.parameters, f"Tool {t.name} missing parameters.properties"
            assert callable(t.fn), f"Tool {t.name} fn not callable"

    def test_ollama_tools_format(self):
        registry = create_default_registry()
        tools = registry.to_ollama_tools()
        assert isinstance(tools, list)
        assert all("type" in t and "function" in t for t in tools)

        phase4_names = {"shell_exec", "python_exec", "web_fetch", "web_search", "export_pdf", "manage_knowledge"}
        registered_names = {t["function"]["name"] for t in tools}
        assert phase4_names.issubset(registered_names)
