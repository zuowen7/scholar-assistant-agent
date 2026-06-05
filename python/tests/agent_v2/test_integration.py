"""端到端集成测试 — IE-001 ~ IE-033。

使用 MockProvider + 真实 ToolRegistry + PermissionPolicy + Session + MCP，
验证完整对话流、权限流程、会话持久化、故障恢复。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.agent_v2.mcp.manager import McpManager, McpServerConfig
from src.agent_v2.providers.mock_provider import MockProvider, Scenario, _text_response, _tool_response
from src.agent_v2.runtime.conversation import ConversationRuntime
from src.agent_v2.runtime.permissions import PermissionMode, PermissionPolicy, policy_from_registry
from src.agent_v2.runtime.session import Session
from src.agent_v2.tools.registry import ToolRegistry, ToolResult, create_default_registry
from src.agent_v2.types import (
    AgentEvent,
    AgentEventType,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


async def _collect(runtime: ConversationRuntime, msg: str) -> list[AgentEvent]:
    events = []
    async for e in runtime.turn(msg):
        events.append(e)
    return events


def _types(events: list[AgentEvent]) -> list[AgentEventType]:
    return [e.type for e in events]


def _mock_server_script(tmp_path: Path) -> Path:
    """创建一个简单的 MCP server 脚本，提供 translate_pdf 工具。"""
    script = tmp_path / "scholar_mock.py"
    script.write_text('''
import json, sys

TOOLS = [
    {"name": "translate_pdf", "description": "Translate a PDF file",
     "inputSchema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
]

def handle(msg):
    method = msg.get("method", "")
    params = msg.get("params", {})
    rid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "scholar-mock", "version": "0.1"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        fp = params.get("arguments", {}).get("file_path", "unknown.pdf")
        return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": f"Translated {fp} successfully. 42 pages processed."}]}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "not found"}}

for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        msg = json.loads(line)
    except: continue
    resp = handle(msg)
    if resp is not None:
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
''', encoding="utf-8")
    return script


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "paper.md").write_text("# Research Paper\n\nAbstract: This paper discusses AI.", encoding="utf-8")
    return tmp_path


# ============================================================================
# 8.1 完整对话流
# ============================================================================

class TestEndToEndFlows:

    @pytest.mark.asyncio
    async def test_ie001_read_and_summarize(self, workspace: Path):
        """IE-001: "读取并总结文件" — read_file → summarize → response"""
        provider = MockProvider(scenarios=[
            Scenario("r0", trigger_patterns=["read and summarize"], turn_index=0,
                     response_factory=lambda m, t: _tool_response("read_file", {"file_path": "paper.md"})),
            Scenario("r1", trigger_patterns=["read and summarize"], turn_index=1,
                     response_factory=lambda m, t: _text_response("The paper discusses AI research.")),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect(rt, "read and summarize the file")
        types = _types(events)

        assert AgentEventType.TOOL_CALL in types
        assert AgentEventType.TOOL_RESULT in types
        assert AgentEventType.RESPONSE in types
        # Verify file was actually read
        tool_results = [e for e in events if e.type == AgentEventType.TOOL_RESULT]
        assert any("AI" in e.data.get("output", "") for e in tool_results)

    @pytest.mark.asyncio
    async def test_ie004_modify_paper(self, workspace: Path):
        """IE-004: "修改论文第3段" — str_replace → 确认 → 修改成功"""
        provider = MockProvider(scenarios=[
            Scenario("fix", trigger_patterns=["fix", "modify", "replace"],
                     response_factory=lambda m, t: _tool_response("str_replace", {
                         "file_path": "paper.md",
                         "old_string": "Abstract: This paper discusses AI.",
                         "new_string": "Abstract: This paper discusses advanced AI techniques.",
                     })),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect(rt, "fix the abstract section")
        types = _types(events)
        assert AgentEventType.TOOL_CALL in types
        # Verify file was actually modified
        content = (workspace / "paper.md").read_text(encoding="utf-8")
        assert "advanced AI techniques" in content


# ============================================================================
# 8.2 权限流程
# ============================================================================

class TestPermissionFlows:

    @pytest.mark.asyncio
    async def test_ie010_readonly_modify_denied(self, workspace: Path):
        """IE-010: ReadOnly 模式修改被拒"""
        provider = MockProvider(scenarios=[
            Scenario("write", trigger_patterns=["create"],
                     response_factory=lambda m, t: _tool_response("write_file", {"file_path": "new.txt", "content": "hello"})),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.READ_ONLY, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect(rt, "create a new file")
        types = _types(events)
        assert AgentEventType.TOOL_DENIED in types
        # File should NOT have been created
        assert not (workspace / "new.txt").exists()

    @pytest.mark.asyncio
    async def test_ie011_path_traversal_denied(self, workspace: Path):
        """IE-011: 路径穿越被拒"""
        provider = MockProvider(scenarios=[
            Scenario("read", trigger_patterns=["read"],
                     response_factory=lambda m, t: _tool_response("read_file", {"file_path": "../../etc/passwd"})),
        ])
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())
        session = Session(workspace=str(workspace))
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)

        events = await _collect(rt, "read the secret file")
        # Permission allows read_file but workspace boundary blocks it
        tool_results = [e for e in events if e.type in (AgentEventType.TOOL_RESULT, AgentEventType.TOOL_ERROR)]
        assert any("outside workspace" in e.data.get("output", "") for e in tool_results)


# ============================================================================
# 8.3 会话持久化
# ============================================================================

class TestSessionPersistence:

    @pytest.mark.asyncio
    async def test_ie020_save_and_restore(self, workspace: Path):
        """IE-020: 会话保存并恢复"""
        session_path = workspace / "session.jsonl"
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

        # First conversation
        session = Session(workspace=str(workspace), model="mock")
        rt = ConversationRuntime(provider=provider, tool_registry=registry, permission_policy=policy, session=session)
        events1 = await _collect(rt, "hello")
        session.save(session_path)

        # Verify saved
        assert session_path.is_file()
        assert session.message_count >= 2

        # Restore and verify
        restored = Session.load(session_path)
        assert restored.message_count == session.message_count
        assert restored.messages[0].text_content() == "hello"

    @pytest.mark.asyncio
    async def test_ie021_cross_restart(self, workspace: Path):
        """IE-021: 跨重启恢复"""
        session_path = workspace / "session.jsonl"
        provider = MockProvider()
        registry = create_default_registry(workspace_root=workspace)
        policy = policy_from_registry(PermissionMode.WORKSPACE_WRITE, registry.permission_specs())

        # First session
        session1 = Session(workspace=str(workspace), model="mock")
        rt1 = ConversationRuntime(provider=MockProvider(), tool_registry=registry, permission_policy=policy, session=session1)
        await _collect(rt1, "first message")
        session1.save(session_path)

        # Second session (simulates restart)
        session2 = Session.load(session_path)
        rt2 = ConversationRuntime(provider=MockProvider(), tool_registry=registry, permission_policy=policy, session=session2)
        events2 = await _collect(rt2, "hello")
        session2.save(session_path)

        # Verify both conversations preserved
        final = Session.load(session_path)
        assert final.message_count >= 4  # 2 from each conversation


# ============================================================================
# 8.4 MCP 集成
# ============================================================================

class TestMcpIntegration:

    @pytest.mark.asyncio
    async def test_ie002_translate_via_mcp(self, workspace: Path):
        """IE-002: MCP server 提供翻译工具"""
        script = _mock_server_script(workspace)
        mcp = McpManager(configs=[
            McpServerConfig(name="scholar", command=sys.executable, args=[str(script)], timeout_seconds=5.0),
        ])
        failures = await mcp.startup_all()
        assert failures == []
        mcp_tools = mcp.get_all_tools()
        assert any(t.name == "translate_pdf" for t in mcp_tools)

        # Call MCP tool
        result = await mcp.call_tool("translate_pdf", {"file_path": "paper.pdf"})
        assert "Translated" in result
        assert "42 pages" in result
        await mcp.shutdown_all()
