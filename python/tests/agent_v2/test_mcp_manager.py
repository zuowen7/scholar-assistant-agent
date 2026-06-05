"""McpManager 测试 — MC-001 ~ MC-033。

使用 Python 子进程模拟 MCP server（JSON-RPC over stdio）。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.agent_v2.mcp.manager import (
    McpError,
    McpLifecycleState,
    McpManager,
    McpServerConfig,
)
from src.agent_v2.types import ToolDefinition


# ---------------------------------------------------------------------------
# Helper: write a mock MCP server script
# ---------------------------------------------------------------------------

_MOCK_SERVER_SCRIPT = '''
import json
import sys

TOOLS = [
    {"name": "greet", "description": "Say hello", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}}},
    {"name": "add", "description": "Add numbers", "inputSchema": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]}},
]

def handle_request(msg):
    method = msg.get("method", "")
    params = msg.get("params", {})
    req_id = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "mock", "version": "0.1.0"}}}
    if method == "notifications/initialized":
        return None  # notification, no response
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        if name == "greet":
            text = f"Hello, {args.get('name', 'world')}!"
        elif name == "add":
            text = str(args.get("a", 0) + args.get("b", 0))
        else:
            text = f"unknown tool: {name}"
        return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": text}]}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"method not found: {method}"}}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    resp = handle_request(msg)
    if resp is not None:
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
'''

_CRASH_SERVER_SCRIPT = '''
import sys
sys.exit(1)
'''

_GARBAGE_SERVER_SCRIPT = '''
import sys
for line in sys.stdin:
    sys.stdout.write("NOT JSON!!!\\n")
    sys.stdout.flush()
'''

_EMPTY_SERVER_SCRIPT = '''
import json
import sys

def handle_request(msg):
    method = msg.get("method", "")
    req_id = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "empty", "version": "0.1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": []}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "not found"}}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    resp = handle_request(msg)
    if resp is not None:
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
'''


@pytest.fixture
def mock_server_script(tmp_path: Path) -> Path:
    script = tmp_path / "mock_mcp_server.py"
    script.write_text(_MOCK_SERVER_SCRIPT, encoding="utf-8")
    return script


@pytest.fixture
def manager(mock_server_script: Path) -> McpManager:
    return McpManager(configs=[
        McpServerConfig(
            name="mock",
            command=sys.executable,
            args=[str(mock_server_script)],
            timeout_seconds=5.0,
        ),
    ])


# ============================================================================
# 7.1 生命周期
# ============================================================================

class TestLifecycle:

    @pytest.mark.asyncio
    async def test_mc001_start_server(self, manager: McpManager):
        """MC-001: 启动 MCP server，握手成功"""
        failures = await manager.startup_all()
        assert failures == []
        state = manager.get_state("mock")
        assert state.lifecycle == McpLifecycleState.READY
        await manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_mc002_discover_tools(self, manager: McpManager):
        """MC-002: 发现工具"""
        await manager.startup_all()
        tools = manager.get_all_tools()
        names = {t.name for t in tools}
        assert "greet" in names
        assert "add" in names
        await manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_mc003_call_tool(self, manager: McpManager):
        """MC-003: 调用工具"""
        await manager.startup_all()
        result = await manager.call_tool("greet", {"name": "World"})
        assert "Hello, World" in result
        await manager.shutdown_all()

    @pytest.mark.asyncio
    async def test_mc004_shutdown(self, manager: McpManager):
        """MC-004: 关闭 MCP server"""
        await manager.startup_all()
        state = manager.get_state("mock")
        assert state.lifecycle == McpLifecycleState.READY
        await manager.shutdown_all()
        assert state.lifecycle == McpLifecycleState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_mc005_multi_server(self, tmp_path: Path):
        """MC-005: 多 server 管理"""
        script1 = tmp_path / "s1.py"
        script1.write_text(_MOCK_SERVER_SCRIPT, encoding="utf-8")
        script2 = tmp_path / "s2.py"
        script2.write_text(_EMPTY_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="s1", command=sys.executable, args=[str(script1)], timeout_seconds=5.0),
            McpServerConfig(name="s2", command=sys.executable, args=[str(script2)], timeout_seconds=5.0),
        ])
        failures = await mgr.startup_all()
        assert failures == []
        assert len(mgr.get_all_tools()) == 2  # greet + add from s1
        await mgr.shutdown_all()


# ============================================================================
# 7.2 边缘测试
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_mc010_server_crashes(self, tmp_path: Path):
        """MC-010: server 立即退出"""
        script = tmp_path / "crash.py"
        script.write_text(_CRASH_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="crash", command=sys.executable, args=[str(script)], timeout_seconds=3.0),
        ])
        failures = await mgr.startup_all()
        state = mgr.get_state("crash")
        assert state.lifecycle == McpLifecycleState.FAILED

    @pytest.mark.asyncio
    async def test_mc011_server_garbage(self, tmp_path: Path):
        """MC-011: server 输出垃圾"""
        script = tmp_path / "garbage.py"
        script.write_text(_GARBAGE_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="garbage", command=sys.executable, args=[str(script)], timeout_seconds=3.0),
        ])
        failures = await mgr.startup_all()
        state = mgr.get_state("garbage")
        assert state.lifecycle == McpLifecycleState.FAILED

    @pytest.mark.asyncio
    async def test_mc014_empty_tools(self, tmp_path: Path):
        """MC-014: 空工具列表"""
        script = tmp_path / "empty.py"
        script.write_text(_EMPTY_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="empty", command=sys.executable, args=[str(script)], timeout_seconds=5.0),
        ])
        await mgr.startup_all()
        tools = mgr.get_all_tools()
        assert tools == []
        await mgr.shutdown_all()

    @pytest.mark.asyncio
    async def test_mc025_command_not_exists(self):
        """MC-025: 启动命令不存在"""
        mgr = McpManager(configs=[
            McpServerConfig(name="bad", command="/nonexistent/command_xyz_123", timeout_seconds=3.0),
        ])
        failures = await mgr.startup_all()
        state = mgr.get_state("bad")
        assert state.lifecycle == McpLifecycleState.FAILED


# ============================================================================
# 7.3 故障注入
# ============================================================================

class TestFaultInjection:

    @pytest.mark.asyncio
    async def test_mc021_server_crash_mid_call(self, tmp_path: Path):
        """MC-021: server 中途崩溃 — 验证 call_tool 报错而非静默失败"""
        script = tmp_path / "crashy.py"
        script.write_text(_MOCK_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="crashy", command=sys.executable, args=[str(script)], timeout_seconds=5.0),
        ])
        await mgr.startup_all()
        state = mgr.get_state("crashy")
        assert state.lifecycle == McpLifecycleState.READY
        # Call works normally
        result = await mgr.call_tool("add", {"a": 1, "b": 2})
        assert "3" in result
        # Kill the server process manually
        if state.process and state.process.returncode is None:
            state.process.kill()
            await state.process.wait()
        # Next call should fail
        with pytest.raises(McpError):
            await mgr.call_tool("add", {"a": 1, "b": 2})
        await mgr.shutdown_all()

    @pytest.mark.asyncio
    async def test_mc026_required_server_fails(self, tmp_path: Path):
        """MC-026: 必需 server 失败"""
        script = tmp_path / "crash.py"
        script.write_text(_CRASH_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="required_crash", command=sys.executable, args=[str(script)],
                           required=True, timeout_seconds=3.0),
        ])
        failures = await mgr.startup_all()
        assert "required_crash" in failures

    @pytest.mark.asyncio
    async def test_mc026b_optional_server_failure_ok(self, tmp_path: Path):
        """MC-026b: 可选 server 失败不阻止"""
        script = tmp_path / "crash.py"
        script.write_text(_CRASH_SERVER_SCRIPT, encoding="utf-8")
        mgr = McpManager(configs=[
            McpServerConfig(name="optional_crash", command=sys.executable, args=[str(script)],
                           required=False, timeout_seconds=3.0),
        ])
        failures = await mgr.startup_all()
        assert failures == []  # optional failures not included
