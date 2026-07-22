"""McpManager — MCP server 生命周期管理。

参考 claw-code runtime/mcp_stdio.rs:
  - spawn MCP server as subprocess (stdio transport)
  - JSON-RPC handshake: initialize → tools/list
  - call_tool: tools/call via JSON-RPC
  - shutdown: send notification, terminate process
  - lifecycle phases: NotStarted → Initializing → Ready → Failed/Shutdown
  - required vs optional servers
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from src.agent_v2.types import ToolDefinition, ToolError

logger = logging.getLogger(__name__)


class McpLifecycleState(Enum):
    NOT_STARTED = "not_started"
    INITIALIZING = "initializing"
    READY = "ready"
    FAILED = "failed"
    SHUTDOWN = "shutdown"


@dataclass
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    required: bool = False
    timeout_seconds: float = 30.0
    tool_call_timeout: float = 60.0


@dataclass
class McpServerState:
    config: McpServerConfig
    lifecycle: McpLifecycleState = McpLifecycleState.NOT_STARTED
    process: asyncio.subprocess.Process | None = None
    tools: list[ToolDefinition] = field(default_factory=list)
    error: str = ""


class McpManager:
    """MCP server 生命周期管理。

    参考 claw-code McpServerManager:
      - startup_all(): 启动所有配置的 MCP server
      - get_all_tools(): 返回所有 server 提供的工具
      - call_tool(): 通过 JSON-RPC 调用 MCP server 的工具
      - shutdown_all(): 关闭所有 server
      - 降级: required server 失败 → 报错; optional → 跳过
    """

    def __init__(self, configs: list[McpServerConfig] | None = None):
        self._servers: dict[str, McpServerState] = {}
        if configs:
            for cfg in configs:
                self._servers[cfg.name] = McpServerState(config=cfg)

    async def startup_all(self) -> list[str]:
        """启动所有 MCP server。返回失败的 server 名称列表。"""
        failures = []
        for name, state in self._servers.items():
            try:
                await self._start_server(state)
            except Exception as e:
                state.lifecycle = McpLifecycleState.FAILED
                state.error = str(e)
                if state.config.required:
                    failures.append(name)
                else:
                    logger.warning("optional MCP server '%s' failed: %s", name, e)
        return failures

    async def _start_server(self, state: McpServerState) -> None:
        state.lifecycle = McpLifecycleState.INITIALIZING
        try:
            process = await asyncio.create_subprocess_exec(
                state.config.command,
                *state.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            state.process = process
            # Initialize handshake
            await self._send_jsonrpc(state, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "scholar-assistant", "version": "0.3.6"},
            })
            # Send initialized notification
            await self._send_notification(state, "notifications/initialized")
            # Discover tools
            tools_result = await self._send_jsonrpc(state, "tools/list", {})
            state.tools = [
                ToolDefinition(name=t["name"], description=t.get("description", ""),
                               input_schema=t.get("inputSchema", {}))
                for t in tools_result.get("tools", [])
            ]
            state.lifecycle = McpLifecycleState.READY
        except Exception as e:
            if state.process:
                await self._dispose_process(state.process)
            raise

    @staticmethod
    async def _dispose_process(process: asyncio.subprocess.Process) -> None:
        """Stop a child and drain its pipes before the event loop is closed.

        Merely calling ``terminate()``/``wait()`` leaves Proactor pipe
        transports pending on Windows, which later surfaces as unraisable
        exceptions during an unrelated test or application shutdown.
        """
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.communicate(), timeout=5.0)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.communicate()
        except (BrokenPipeError, ConnectionResetError):
            await process.wait()
        # Give the Proactor loop one cycle to deliver connection_lost callbacks.
        await asyncio.sleep(0)

    async def _send_jsonrpc(self, state: McpServerState, method: str, params: dict) -> dict:
        if not state.process or not state.process.stdin or not state.process.stdout:
            raise McpError(f"server '{state.config.name}' has no process")
        request_id = uuid.uuid4().hex[:8]
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        msg = json.dumps(request) + "\n"
        state.process.stdin.write(msg.encode())
        await state.process.stdin.drain()
        # Read response
        try:
            line = await asyncio.wait_for(state.process.stdout.readline(), timeout=state.config.timeout_seconds)
        except asyncio.TimeoutError:
            raise McpError(f"timeout waiting for response from '{state.config.name}'")
        if not line:
            raise McpError(f"server '{state.config.name}' closed stdout")
        response = json.loads(line.decode())
        if "error" in response:
            raise McpError(f"JSON-RPC error from '{state.config.name}': {response['error']}")
        return response.get("result", {})

    async def _send_notification(self, state: McpServerState, method: str) -> None:
        if not state.process or not state.process.stdin:
            return
        notification = {"jsonrpc": "2.0", "method": method}
        msg = json.dumps(notification) + "\n"
        state.process.stdin.write(msg.encode())
        await state.process.stdin.drain()

    def get_all_tools(self) -> list[ToolDefinition]:
        tools = []
        for state in self._servers.values():
            if state.lifecycle == McpLifecycleState.READY:
                tools.extend(state.tools)
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """通过 JSON-RPC 调用 MCP server 的工具。"""
        for state in self._servers.values():
            if state.lifecycle != McpLifecycleState.READY:
                continue
            if any(t.name == tool_name for t in state.tools):
                try:
                    result = await self._send_jsonrpc(state, "tools/call", {
                        "name": tool_name,
                        "arguments": arguments,
                    })
                    contents = result.get("content", [])
                    texts = [c.get("text", "") for c in contents if c.get("type") == "text"]
                    return "\n".join(texts) if texts else json.dumps(result)
                except McpError:
                    raise
                except Exception as e:
                    raise McpError(f"tool call failed: {e}")
        raise McpError(f"tool '{tool_name}' not found in any MCP server")

    async def shutdown_all(self) -> None:
        for name, state in self._servers.items():
            if state.process:
                try:
                    await self._dispose_process(state.process)
                except Exception as exc:
                    logger.warning("failed to stop MCP server '%s': %s", name, exc)
            state.lifecycle = McpLifecycleState.SHUTDOWN

    def get_state(self, name: str) -> McpServerState | None:
        return self._servers.get(name)

    @property
    def server_names(self) -> list[str]:
        return list(self._servers.keys())


class McpError(Exception):
    pass
