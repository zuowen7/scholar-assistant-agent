"""工具注册表与装饰器 — Agent 子系统的工具管理层（向后兼容层）。

.. deprecated::
    此文件保留用于向后兼容。新代码应使用 `src.agent.tools` 包。

本模块重新导出了 `src.agent.tools` 包的所有公共接口，确保原有的导入语句继续工作。

原 tools.py (1957 行) 已被拆分为以下模块：
- src.agent.tools.core: 核心框架（ToolDefinition, ToolRegistry, @tool 装饰器）
- src.agent.tools.workspace_tools: AWA v2 工作区工具
- src.agent.tools.atomic_tools: Phase 4 原子工具（shell_exec, python_exec, web_fetch 等）
- src.agent.tools.builtin_tools: 其他内置工具（arxiv, 文件操作等）
- src.agent.tools.registry: create_default_registry 工厂函数

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
工具注册与动态调度机制受软件著作权和发明专利保护。
"""

# 重新导出 tools 包的所有公共接口
from src.agent.tools import (
    ToolDefinition,
    ToolRegistry,
    _TOOL_RESULT_MAX_LEN,
    _extract_schema_from_function,
    create_default_registry,
    set_default_registry,
    tool,
)

__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "tool",
    "set_default_registry",
    "_extract_schema_from_function",
    "_TOOL_RESULT_MAX_LEN",
    "create_default_registry",
]
