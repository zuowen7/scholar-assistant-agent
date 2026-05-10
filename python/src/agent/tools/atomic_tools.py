"""原子工具 — 低风险、沙箱化的原子操作工具。

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
    # 文件操作（限制在沙箱内；rm/rmdir 已由 SecurityGate 黑名单拦截，此处不再列入）
    "touch", "mkdir", "cp", "mv",
    # 开发工具
    "python", "python3", "pip", "pip3",
    # git (read-only subcommands enforced below)
    "git",
})

# git subcommands allowed (read-only)
_GIT_ALLOWED_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "tag", "remote",
    "stash", "blame", "shortlog", "describe", "reflog", "ls-files",
    "ls-tree", "rev-parse", "config", "--version", "--help",
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

    # git: restrict to read-only subcommands
    if base_cmd == "git":
        parts = command.strip().split()
        subcmd = ""
        for p in parts[1:]:
            if not p.startswith("-"):
                subcmd = p
                break
        if subcmd not in _GIT_ALLOWED_SUBCOMMANDS:
            allowed = ", ".join(sorted(_GIT_ALLOWED_SUBCOMMANDS))
            return f"git 子命令 '{subcmd}' 不在白名单中。允许的只读子命令: {allowed}"

    # 文件操作命令必须在沙箱内执行
    sandbox_cmds = {"touch", "mkdir", "cp", "mv"}
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
    """执行 Python 代码片段并返回输出。使用子进程隔离，超时可真正终止。

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
    _DANGEROUS_ATTRS = frozenset({
        "__import__", "__builtins__", "__globals__", "__locals__",
        "__code__", "__class__", "__base__", "__bases__", "__subclasses__",
        "__mro__", "__dict__", "__reduce__", "__reduce_ex__",
        "__init_subclass__", "__module__",
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
        elif isinstance(node, _ast.Attribute):
            if node.attr in _DANGEROUS_ATTRS:
                return f"禁止访问受限属性: {node.attr}"
        elif isinstance(node, _ast.Name):
            if node.id in _DANGEROUS_ATTRS:
                return f"禁止使用受限名称: {node.id}"

    # Use subprocess for true process isolation — can be killed on timeout
    import sys
    import json

    # Wrapper script that runs user code with restricted builtins in a subprocess
    _runner_code = (
        "import sys, json, io, contextlib\n"
        "code = json.loads(sys.argv[1])\n"
        "safe_builtins = {\n"
        "    'print': print, 'len': len, 'range': range, 'enumerate': enumerate,\n"
        "    'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,\n"
        "    'reversed': reversed, 'sum': sum, 'min': min, 'max': max,\n"
        "    'abs': abs, 'round': round, 'int': int, 'float': float,\n"
        "    'str': str, 'list': list, 'dict': dict, 'set': set, 'tuple': tuple,\n"
        "    'bool': bool, 'type': type, 'isinstance': isinstance,\n"
        "    'True': True, 'False': False, 'None': None,\n"
        "    'repr': repr, 'hasattr': hasattr, 'getattr': getattr,\n"
        "    'abs': abs, 'round': round, 'pow': pow, 'divmod': divmod,\n"
        "    'hex': hex, 'oct': oct, 'bin': bin, 'chr': chr, 'ord': ord,\n"
        "    'input': lambda *a: '',\n"
        "}\n"
        "buf = io.StringIO()\n"
        "g = {'__builtins__': safe_builtins}\n"
        "err = None\n"
        "try:\n"
        "    with contextlib.redirect_stdout(buf):\n"
        "        exec(code, g)\n"
        "except Exception as e:\n"
        "    err = str(e)\n"
        "out = buf.getvalue()\n"
        "if err:\n"
        "    out += f'\\n[执行错误] {err}'\n"
        "sys.stdout.write(out)\n"
    )

    try:
        # -X utf8: force UTF-8 mode in child so argv (with Chinese chars in
        # the runner script) and stdout are decoded/encoded as UTF-8 on Windows.
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", _runner_code, json.dumps(code, ensure_ascii=False)],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
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
        return f"代码执行超时 ({timeout}s)，进程已终止。"
    except Exception as e:
        return f"代码执行失败: {e}"


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
            headers={"User-Agent": "Yanmo/1.0"},
            trust_env=False,
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
    """使用搜索引擎搜索信息。通过 Bing 返回搜索结果摘要。

    Args:
        query: 搜索关键词（中英文均可）。
        max_results: 返回的最大结果数，默认 8。
    """
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            trust_env=False,
        ) as client:
            resp = client.get(
                "https://cn.bing.com/search",
                params={"q": query, "count": max_results},
            )
            resp.raise_for_status()
            html = resp.text

        results: list[str] = []
        titles = re.findall(
            r'<h2[^>]*>\s*<a[^>]*href="(https?://[^"]+)"[^>]*h="ID=SERP[^"]*"[^>]*>(.*?)</a>\s*</h2>',
            html, re.DOTALL,
        )
        snippets = re.findall(
            r'<div class="b_caption">\s*<p[^>]*>(.*?)</p>\s*</div>',
            html, re.DOTALL,
        )
        for i in range(min(len(titles), max_results)):
            url = titles[i][0]
            title = re.sub(r"<[^>]+>", "", titles[i][1]).strip()
            snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
            if title:
                results.append(f"标题: {title}\n链接: {url}\n摘要: {snippet}")

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
