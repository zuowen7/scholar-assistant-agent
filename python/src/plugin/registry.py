"""Plugin Registry — MCP 插件系统的核心注册表。

设计原则：
- **声明式工具定义**：每个插件声明自己的工具 JSON Schema，不直接持有执行逻辑
- **执行逻辑分离**：工具执行由 FastAPI 路由 handler 处理，registry 只负责注册和发现
- **向后兼容**：不破坏现有的 mcp_server.py（stdio transport），插件定义可被 Agent 直接复用

核心类：

    ToolSpec        — 单个工具的声明（名字/描述/参数 schema）
    PluginServer    — 一个插件服务器 = 名字 + 版本 + 工具列表
    PluginRegistry  — 全局单例，管理所有已注册插件，导出工具定义和 FastAPI 路由
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from starlette.requests import Request

logger = logging.getLogger(__name__)


def _make_route_handler(tool_handler: Callable) -> Callable:
    """创建插件路由处理器，捕获 tool_handler 闭包。

    定义在模块级别，确保 FastAPI 能正确解析 Request 类型注解。
    """
    async def route_fn(request: Request) -> Any:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return await tool_handler(body)
    return route_fn


@dataclass
class ToolSpec:
    """声明式工具规格 — 不包含执行逻辑，只包含元数据。

    字段与 MCP tool schema 对齐：
    - name: 工具唯一标识符（PluginServer 内不可重复）
    - description: 人类可读描述（用于 LLM 判断何时调用）
    - inputSchema: JSON Schema 格式的参数定义（与 MCP types.Tool 一致）
    - handler: 可选的 FastAPI 路由 handler（注册时注入）
    """
    name: str
    description: str
    inputSchema: dict[str, Any]
    handler: Callable[..., Any] | None = None

    def to_mcp_dict(self) -> dict[str, Any]:
        """导出为 MCP JSON Schema 格式（用于 Agent 工具注入）。"""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }

    def to_fastapi_route(self, method: str = "POST", path: str | None = None) -> dict[str, Any] | None:
        """如果有 handler，生成 FastAPI 路由信息。

        Returns:
            None 如果没有 handler（纯声明式工具，仅供 Agent 使用）
            dict 包含 {path, method, handler} 用于动态注册
        """
        if self.handler is None:
            return None
        if path is None:
            path = f"/plugin/{self.name}"
        return {
            "path": path,
            "method": method,
            "handler": self.handler,
        }


@dataclass
class PluginServer:
    """一个插件服务器 — 包含多个 ToolSpec。

    对应 MCP Protocol 中的一个 Server 实例。例如：
    - "scholar-assistant" server: translate_text, parse_document, search_documents...
    - "zotero" server: search_items, get_item, export_bibtex...
    - "arxiv" server: search, download_pdf...
    """
    name: str
    version: str
    description: str = ""
    tools: list[ToolSpec] = field(default_factory=list)
    instructions: str = ""

    def register_tool(self, tool: ToolSpec) -> None:
        """注册一个工具到此服务器。"""
        # 防止重复注册同名工具
        existing = {t.name for t in self.tools}
        if tool.name in existing:
            logger.warning("工具 %s 已存在于插件 %s，跳过注册", tool.name, self.name)
            return
        self.tools.append(tool)

    def get_tool(self, name: str) -> ToolSpec | None:
        return next((t for t in self.tools if t.name == name), None)

    def to_mcp_tools(self) -> list[dict[str, Any]]:
        """导出所有工具为 MCP JSON 格式。"""
        return [t.to_mcp_dict() for t in self.tools]

    def list_routes(self) -> list[dict[str, Any]]:
        """列出所有有 handler 的工具，生成 FastAPI 路由信息。"""
        routes = []
        for tool in self.tools:
            route = tool.to_fastapi_route()
            if route:
                route["plugin"] = self.name
                routes.append(route)
        return routes


class PluginRegistry:
    """全局插件注册表 — 管理所有 PluginServer。

    设计为 create_app() 时创建一次，之后所有端点共享。

    用法：

        registry = PluginRegistry()

        # 注册内置插件
        from src.plugin.builtin import register_builtin
        register_builtin(registry)

        # 注册自定义插件
        registry.register(plugin_server)

        # 获取所有工具定义（供 Agent 注入）
        all_tools = registry.get_all_tools()

        # 将所有路由注入 FastAPI
        registry.attach_to_app(app)
    """

    def __init__(self):
        self._servers: dict[str, PluginServer] = {}
        self._tool_map: dict[str, tuple[str, ToolSpec]] = {}  # tool_name -> (server_name, spec)

    # ── 注册 ───────────────────────────────────────────────────────────

    def register(self, server: PluginServer) -> None:
        """注册一个 PluginServer。"""
        if server.name in self._servers:
            logger.warning("插件 %s 已注册，更新工具列表", server.name)
            # 合并工具列表
            existing = self._servers[server.name]
            for tool in server.tools:
                existing.register_tool(tool)
            # 更新 tool_map
            for tool in existing.tools:
                self._tool_map[tool.name] = (existing.name, tool)
            return

        self._servers[server.name] = server
        for tool in server.tools:
            self._tool_map[tool.name] = (server.name, tool)
        logger.info("插件已注册: %s (v%s, %d tools)", server.name, server.version, len(server.tools))

    def register_tool(self, server_name: str, tool: ToolSpec) -> None:
        """向指定服务器注册单个工具（服务器不存在则自动创建）。"""
        if server_name not in self._servers:
            self._servers[server_name] = PluginServer(name=server_name, version="0.0.0")
        self._servers[server_name].register_tool(tool)
        self._tool_map[tool.name] = (server_name, tool)

    # ── 查询 ───────────────────────────────────────────────────────────

    def get_server(self, name: str) -> PluginServer | None:
        return self._servers.get(name)

    def get_tool(self, name: str) -> ToolSpec | None:
        info = self._tool_map.get(name)
        return info[1] if info else None

    def get_all_tools(self) -> list[dict[str, Any]]:
        """返回所有工具的 MCP JSON Schema 列表（供 Agent 工具注入）。"""
        tools = []
        for server in self._servers.values():
            tools.extend(server.to_mcp_tools())
        return tools

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def list_server_tools(self, server_name: str) -> list[ToolSpec]:
        server = self._servers.get(server_name)
        return server.tools if server else []

    # ── FastAPI 集成 ──────────────────────────────────────────────────

    def attach_to_app(self, app: FastAPI) -> int:
        """将所有带 handler 的工具注册为 FastAPI 路由。

        Returns:
            注册的路由数量。
        """
        count = 0
        for server in self._servers.values():
            for route_info in server.list_routes():
                path = route_info["path"]
                method = route_info["method"]
                handler = route_info["handler"]

                route_fn = _make_route_handler(handler)
                app.api_route(path, methods=[method.upper()])(route_fn)
                count += 1
                logger.debug("路由已注册: %s %s (%s)", method, path, server.name)

        logger.info("插件路由注册完成: %d 条", count)
        return count

    # ── 统计 ──────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "server_count": len(self._servers),
            "total_tools": len(self._tool_map),
            "servers": {
                name: {
                    "version": s.version,
                    "tool_count": len(s.tools),
                }
                for name, s in self._servers.items()
            },
        }
