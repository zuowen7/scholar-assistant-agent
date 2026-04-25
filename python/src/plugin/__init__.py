"""Plugin Registry — MCP 风格的插件工具注册系统。

快速上手：

    from src.plugin import PluginRegistry, register_builtin, create_builtin_server

    # 创建注册表
    registry = PluginRegistry()

    # 注册内置插件
    register_builtin(registry)

    # 获取所有工具（供 Agent 注入）
    all_tools = registry.get_all_tools()

    # 将路由注入 FastAPI
    registry.attach_to_app(app)

    # 查看统计
    print(registry.get_stats())
"""

from __future__ import annotations

from src.plugin.registry import (
    PluginRegistry,
    PluginServer,
    ToolSpec,
)
from src.plugin.builtin import register_builtin, create_builtin_server
from src.plugin.loader import discover_plugins, load_from_config, load_plugins

__all__ = [
    "PluginRegistry",
    "PluginServer",
    "ToolSpec",
    "register_builtin",
    "create_builtin_server",
    "discover_plugins",
    "load_from_config",
    "load_plugins",
]
