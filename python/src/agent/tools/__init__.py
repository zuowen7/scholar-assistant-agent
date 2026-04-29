"""工具注册表与装饰器 — Agent 子系统的工具管理层。

本模块提供了 Agent 工具系统的核心接口：
- ToolDefinition: 工具定义数据结构
- ToolRegistry: 工具注册表，管理工具的注册、查询、执行
- @tool 装饰器: 从函数自动提取 JSON Schema 并注册为工具
- create_default_registry(): 创建包含所有默认工具的注册表

为了保持向后兼容，本模块重新导出了所有原有的公共接口。
原有的 tools.py 已被拆分为以下模块：
- core.py: 核心框架（ToolDefinition, ToolRegistry, @tool 装饰器）
- workspace_tools.py: 工作区工具
- atomic_tools.py: 原子工具（shell_exec, python_exec, web_fetch 等）
- builtin_tools.py: 其他内置工具（arxiv, 文件操作等）
- registry.py: create_default_registry 工厂函数

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
工具注册与动态调度机制受软件著作权和发明专利保护。
"""

# 核心框架
from src.agent.tools.core import (
    ToolDefinition,
    ToolRegistry,
    _extract_schema_from_function,
    _TOOL_RESULT_MAX_LEN,
    set_default_registry,
    tool,
)

# 注册表工厂
from src.agent.tools.registry import create_default_registry

# 工作区工具（导出用于测试）
from src.agent.tools.workspace_tools import (
    _build_git_command,
    _git_op,
    _list_directory,
    _read_file_v2,
    _run_command_v2,
    _str_replace,
    _undo_last_change,
    _write_file_v2,
)

# 原子工具（导出用于测试）
from src.agent.tools.atomic_tools import (
    _export_pdf,
    _python_exec,
    _shell_exec,
    _web_fetch,
    _web_search,
)

# 内置工具（导出用于测试）
from src.agent.tools.builtin_tools import (
    _crawl_arxiv,
    _manage_knowledge,
)

# 向后兼容：导出所有原有接口
__all__ = [
    # 核心框架
    "ToolDefinition",
    "ToolRegistry",
    "tool",
    "set_default_registry",
    "_extract_schema_from_function",
    "_TOOL_RESULT_MAX_LEN",
    # 注册表工厂
    "create_default_registry",
    # 工作区工具（用于测试）
    "_build_git_command",
    "_git_op",
    "_list_directory",
    "_read_file_v2",
    "_run_command_v2",
    "_str_replace",
    "_undo_last_change",
    "_write_file_v2",
    # 原子工具（用于测试）
    "_export_pdf",
    "_python_exec",
    "_shell_exec",
    "_web_fetch",
    "_web_search",
    # 内置工具（用于测试）
    "_crawl_arxiv",
    "_manage_knowledge",
]
