"""Phase 4 原子工具 — 低风险、沙箱化的原子操作工具。

本模块实现了 Agent 的原子操作工具集，包括：
- shell_exec: 白名单 shell 命令执行
- python_exec: 受限 Python 代码执行
- web_fetch: 网页内容获取
- web_search: 搜索引擎查询
- export_pdf: Markdown 转 PDF 导出

所有工具都设计了安全限制和超时保护。

版权声明: 本模块属于 Scholar Assistant Agent 子系统。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 从 core 导入共享常量
from src.agent.tools.core import _TOOL_RESULT_MAX_LEN

# 沙箱根目录
_SANDBOX_ROOT = os.environ.get("SCHOLAR_AGENT_SANDBOX", str(os.path.expanduser("~/scholar_agent_files")))

# shell_exec 白名单
_SHELL_ALLOWED_COMMANDS = frozenset({
    # 只读
    "ls", "dir", "cat", "head", "tail", "wc", "echo",
    "find", "grep", "sort", "uniq", "cut", "tr", "tee",
    "pwd", "whoami", "date", "uname",
    # 文件操作（限制在沙箱内）
    "touch", "mkdir", "cp", "mv", "rm", "rmdir",
    # 开发工具
    "python", "python3", "pip", "pip3",
    "git",
    "curl", "wget",
})

_SHELL_TIMEOUT = 30
_PYTHON_EXEC_TIMEOUT = 30
_WEB_FETCH_TIMEOUT = 20
_WEB_FETCH_MAX_SIZE = 200_000  # 200KB
_WEB_SEARCH_MAX_RESULTS = 8


# ---------------------------------------------------------------------------
# shell_exec 工具
# ---------------------------------------------------------------------------

def _validate_sandbox_command(command: str) -> str | None:
    """检查 shell 命令是否包含沙箱逃逸路径。返回错误信息或 None（通过）。"""
    # 路径遍历
    if ".." in command:
        return "不允许使用 '..' 路径遍历"
    # Windows 盘符绝对路径 (C:\, D:/ 等)
    if re.search(r"[A-Za-z]:[\\\/]", command):
        return "不允许使用绝对路径"
    # Unix 绝对路径 (排除选项参数如 -R/recursive)
    # 匹配独立的 /path（前面是空格或行首，后面跟路径字符）
    if re.search(r"(?:^|\s)(\/[^\s]*)", command):
        # 排除命令选项中出现的 /（如 grep -P/(?=...) ）
        for match in re.finditer(r"(?:^|\s)(\/[^\s]*)", command):
            path = match.group(1)
            # 允许 / 在正则或选项中（如 grep -E, sed 等）
            if not path.startswith("//") and len(path) > 1:
                return "不允许使用绝对路径"
    return None


def _shell_exec(command: str, timeout: int = _SHELL_TIMEOUT) -> str:
    """执行白名单内的 shell 命令并返回输出。文件操作限制在沙箱目录内，超时自动终止。

    Args:
        command: 要执行的 shell 命令字符串。
        timeout: 执行超时秒数，默认 30。
    """
    base_cmd = command.strip().split()[0] if command.strip() else ""
    if base_cmd not in _SHELL_ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(_SHELL_ALLOWED_COMMANDS))
        return f"命令 '{base_cmd}' 不在白名单中。允许的命令: {allowed}"

    # 文件操作命令必须在沙箱内执行
    sandbox_cmds = {"touch", "mkdir", "cp", "mv", "rm", "rmdir"}
    cwd = None
    if base_cmd in sandbox_cmds:
        path_error = _validate_sandbox_command(command)
        if path_error:
            return f"安全限制: {path_error}。文件操作仅限沙箱目录内的相对路径。"
        cwd = _SANDBOX_ROOT
        os.makedirs(cwd, exist_ok=True)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        if len(output) > _TOOL_RESULT_MAX_LEN:
            output = output[:_TOOL_RESULT_MAX_LEN] + "\n...[输出已截断]"
        return output or "(无输出)"
    except subprocess.TimeoutExpired:
        return f"命令执行超时 ({timeout}s)，已终止。"
    except Exception as e:
        return f"命令执行失败: {e}"


# ---------------------------------------------------------------------------
# python_exec 工具
# ---------------------------------------------------------------------------

def _python_exec(code: str, timeout: int = _PYTHON_EXEC_TIMEOUT) -> str:
    """执行 Python 代码片段并返回输出。在受限环境中运行，有超时保护。

    Args:
        code: 要执行的 Python 代码字符串。
        timeout: 执行超时秒数，默认 30。
    """
    import ast as _ast

    # AST 安全审查：禁止 import os/sys/subprocess 等
    try:
        tree = _ast.parse(code)
    except SyntaxError as e:
        return f"语法错误: {e}"

    _DANGEROUS_MODULES = frozenset({
        "os", "sys", "subprocess", "shutil", "pathlib",
        "socket", "http", "urllib", "ctypes", "multiprocessing",
    })
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in _DANGEROUS_MODULES:
                    return f"禁止导入模块: {mod}"
        elif isinstance(node, _ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod in _DANGEROUS_MODULES:
                    return f"禁止从模块导入: {mod}"

    # 受限全局命名空间
    safe_globals: dict[str, Any] = {
        "__builtins__": {
            "print": print, "len": len, "range": range, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter, "sorted": sorted,
            "reversed": reversed, "sum": sum, "min": min, "max": max,
            "abs": abs, "round": round, "int": int, "float": float,
            "str": str, "list": list, "dict": dict, "set": set, "tuple": tuple,
            "bool": bool, "type": type, "isinstance": isinstance,
            "True": True, "False": False, "None": None,
        },
    }

    import io
    import contextlib

    stdout_buf = io.StringIO()
    safe_globals["_stdout"] = stdout_buf

    # 用 threading 实现超时（subprocess 不适用于纯 Python eval）
    exec_error: list[str] = []
    exec_done = threading.Event()

    def _run():
        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, safe_globals)
        except Exception as e:
            exec_error.append(str(e))
        finally:
            exec_done.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    finished = exec_done.wait(timeout=timeout)

    if not finished:
        return f"代码执行超时 ({timeout}s)，已终止。"

    output = stdout_buf.getvalue()
    if exec_error:
        output += f"\n[执行错误] {exec_error[0]}"
    if len(output) > _TOOL_RESULT_MAX_LEN:
        output = output[:_TOOL_RESULT_MAX_LEN] + "\n...[输出已截断]"
    return output or "(无输出)"


# ---------------------------------------------------------------------------
# web_fetch 工具
# ---------------------------------------------------------------------------

def _web_fetch(url: str, extract_text: bool = True) -> str:
    """获取网页内容。支持 HTTP/HTTPS，可选提取纯文本或返回原始 HTML。

    Args:
        url: 要获取的网页 URL（必须以 http:// 或 https:// 开头）。
        extract_text: 是否提取纯文本（去除 HTML 标签），默认 True。
    """
    if not url.startswith(("http://", "https://")):
        return "URL 必须以 http:// 或 https:// 开头"
    try:
        with httpx.Client(
            timeout=_WEB_FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "ScholarAssistant/1.0"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content = resp.text

        if len(content) > _WEB_FETCH_MAX_SIZE:
            content = content[:_WEB_FETCH_MAX_SIZE]

        if extract_text:
            # 简易 HTML → 纯文本：去除标签
            content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        if len(content) > _TOOL_RESULT_MAX_LEN:
            content = content[:_TOOL_RESULT_MAX_LEN] + "\n...[内容已截断]"
        return content
    except httpx.TimeoutException:
        return f"请求超时 ({_WEB_FETCH_TIMEOUT}s)"
    except httpx.HTTPStatusError as e:
        return f"HTTP 错误 {e.response.status_code}"
    except Exception as e:
        return f"获取网页失败: {e}"


# ---------------------------------------------------------------------------
# web_search 工具
# ---------------------------------------------------------------------------

def _web_search(query: str, max_results: int = _WEB_SEARCH_MAX_RESULTS) -> str:
    """使用搜索引擎搜索信息。通过 DuckDuckGo 返回搜索结果摘要。

    Args:
        query: 搜索关键词（中英文均可）。
        max_results: 返回的最大结果数，默认 8。
    """
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ScholarAssistant/1.0)"},
        ) as client:
            # DuckDuckGo HTML 版本（无需 API Key）
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "cn-zh"},
            )
            resp.raise_for_status()
            html = resp.text

        # 提取搜索结果
        results: list[str] = []
        # DuckDuckGo HTML 结果格式
        blocks = re.findall(
            r'<a rel="nofollow" class="result__a"[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )
        for title_html, snippet_html in blocks[:max_results]:
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
            if title:
                results.append(f"标题: {title}\n摘要: {snippet}")

        if not results:
            # 回退：尝试另一种格式
            titles = re.findall(r'class="result__title"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            for i in range(min(len(titles), max_results)):
                title = re.sub(r"<[^>]+>", "", titles[i]).strip()
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                if title:
                    results.append(f"标题: {title}\n摘要: {snippet}")

        if not results:
            return "未找到相关结果。"

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"搜索失败: {e}"


# ---------------------------------------------------------------------------
# export_pdf 工具
# ---------------------------------------------------------------------------

def _export_pdf(markdown: str, template_id: str = "generic_article", title: str = "") -> str:
    """将 Markdown 内容导出为 PDF 文件。使用 Pandoc + Tectonic 编译 LaTeX 生成 PDF。

    Args:
        markdown: Markdown 格式的文本内容。
        template_id: 论文模板 ID，可选 generic_article/ieee_conference/ieee_journal/acm/lncs/neurips，默认 generic_article。
        title: 文档标题（可选）。
    """
    try:
        from src.pandoc_templates import convert_markdown
    except ImportError:
        return "PDF 导出模块不可用（pandoc_templates 未安装）"

    metadata = {}
    if title:
        metadata["title"] = title

    result = convert_markdown(
        markdown_text=markdown,
        template_id=template_id,
        output_format="pdf",
        metadata=metadata,
    )

    if result.get("success"):
        pdf_path = result.get("pdf_path", result.get("output_path", ""))
        return f"PDF 导出成功: {pdf_path}"
    else:
        error = result.get("error", "未知错误")
        hint = ""
        if "Tectonic" in error or "tectonic" in error.lower():
            hint = "\n提示：请先安装 Tectonic（https://github.com/typst/tectonic/releases）"
        elif "Pandoc" in error:
            hint = "\n提示：请先安装 Pandoc（https://pandoc.org/installing.html）"
        return f"PDF 导出失败: {error}{hint}"


# 导出公共接口
__all__ = [
    "_shell_exec",
    "_python_exec",
    "_web_fetch",
    "_web_search",
    "_export_pdf",
]
