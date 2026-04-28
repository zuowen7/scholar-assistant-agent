"""工具注册表与装饰器核心框架。

本模块实现了 Agent 子系统的「工具层」核心功能：
- ToolDefinition: 工具定义数据结构
- @tool 装饰器: 从函数签名和 __doc__ 自动提取 JSON Schema
- ToolRegistry: 工具注册表，管理工具的注册、查询、格式转换和执行

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
工具注册与动态调度机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

logger = logging.getLogger(__name__)

# 工具执行结果的最大字符长度，超出部分截断并附加省略标记
_TOOL_RESULT_MAX_LEN = 4000


# ---------------------------------------------------------------------------
# 工具定义
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    """工具定义 — 描述一个可被 LLM 调用的工具的完整元信息。

    该数据结构是 ToolRegistry 与 Ollama Chat API 之间的契约:
    - name 和 description 供 LLM 理解工具的用途。
    - parameters (JSON Schema) 描述工具接受的参数结构。
    - fn 是实际执行工具逻辑的 Python 函数。

    Attributes:
        name: 工具的唯一标识名称（对应 @tool 装饰器的 name 参数）。
        description: 工具的功能描述，供 LLM 在推理时判断是否应调用该工具。
        parameters: JSON Schema 格式的参数描述，包含各参数的类型、默认值和说明。
        fn: 被装饰的原始函数，工具执行时直接调用。
    """

    name: str
    description: str
    parameters: dict
    fn: Callable


# ---------------------------------------------------------------------------
# JSON Schema 类型映射
# ---------------------------------------------------------------------------

_PYTHON_TYPE_TO_JSON_SCHEMA: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _extract_schema_from_function(fn: Callable) -> dict:
    """从函数签名和 __doc__ 自动生成 JSON Schema 参数描述。

    解析策略:
    1. 使用 inspect.signature() 提取参数名、类型注解和默认值。
    2. 从 Google 风格 __doc__ 的 Args: 段落提取参数说明。
    3. 类型注解通过 _PYTHON_TYPE_TO_JSON_SCHEMA 映射为 JSON Schema 类型。
    4. 有默认值的参数标记为非必需 (required 列表中排除)。

    Args:
        fn: 被装饰的函数。

    Returns:
        符合 JSON Schema 规范的字典，包含 type="object"、properties 和 required。
    """
    sig = inspect.signature(fn)
    hints = get_type_hints(fn) if hasattr(fn, "__annotations__") else {}

    # 从 docstring 提取 Args 段的参数描述
    param_docs: dict[str, str] = {}
    if fn.__doc__:
        args_match = re.search(r"Args:\s*\n((?:\s+\w+.*\n)*)", fn.__doc__)
        if args_match:
            for line in args_match.group(1).strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 匹配 "param_name: 描述" 或 "param_name (type): 描述"
                m = re.match(r"(\w+)\s*(?:\([^)]*\))?\s*[:：]\s*(.+)", line)
                if m:
                    param_docs[m.group(1)] = m.group(2).strip()

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        prop: dict[str, Any] = {}

        # 类型映射
        type_hint = hints.get(param_name)
        if type_hint in _PYTHON_TYPE_TO_JSON_SCHEMA:
            prop["type"] = _PYTHON_TYPE_TO_JSON_SCHEMA[type_hint]
        else:
            prop["type"] = "string"  # 默认当作字符串

        # 参数描述
        if param_name in param_docs:
            prop["description"] = param_docs[param_name]

        # 默认值
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
        elif param.default is not None:
            prop["default"] = param.default

        properties[param_name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


# ---------------------------------------------------------------------------
# @tool 装饰器
# ---------------------------------------------------------------------------

# 全局默认注册表 — 当不指定 registry 时，@tool 装饰器将工具注册到此处
_DEFAULT_REGISTRY: ToolRegistry | None = None


def tool(fn: Callable | None = None, *, name: str | None = None, registry: ToolRegistry | None = None):
    """装饰器: 将函数注册为 Agent 可调用的工具。

    自动提取被装饰函数的 __doc__ (首行作为描述) 和类型注解 (转换为 JSON Schema)，
    生成 LLM 能理解的工具描述。装饰器模式与项目中 parser/dispatcher.py 的
    @_register 装饰器保持一致的注册风格。

    支持两种使用方式:
    - @tool                          # 无参数，使用函数名作为工具名
    - @tool(name="custom_name")      # 指定工具名

    Args:
        fn: 被装饰的函数（由 Python 装饰器机制自动传入）。
        name: 工具名称，默认使用函数名。
        registry: 目标注册表，默认使用全局注册表。

    Returns:
        原函数（不修改其行为），副作用是将其注册到 ToolRegistry。
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = ""
        if func.__doc__:
            # 取 docstring 第一行非空内容作为简短描述
            tool_desc = func.__doc__.strip().split("\n")[0].strip()
        parameters = _extract_schema_from_function(func)

        tool_def = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
            fn=func,
        )

        target = registry or _DEFAULT_REGISTRY
        if target is not None:
            target.register(tool_def)
        else:
            # 延迟注册：存储在函数属性上，等 ToolRegistry 创建时收集
            if not hasattr(func, "_agent_tool_def"):
                func._agent_tool_def = tool_def

        return func

    if fn is not None:
        # 无参数调用: @tool
        return decorator(fn)
    # 带参数调用: @tool(name=...)
    return decorator


def set_default_registry(registry: ToolRegistry) -> None:
    """设置全局默认注册表。

    Args:
        registry: 要设置为默认的 ToolRegistry 实例。
    """
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = registry


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

class ToolRegistry:
    """工具注册表 — Agent 子系统的工具管理中心。

    职责:
    1. 收集和索引所有已注册的工具 (ToolDefinition)。
    2. 将工具定义转换为 Ollama Chat API 所需的 tools 参数格式。
    3. 根据 LLM 的工具调用请求，异步执行对应的工具函数。

    线程安全: 本类不维护可变状态的竞争条件（注册阶段为初始化时一次性完成），
    execute() 中的 asyncio.to_thread() 本身是线程安全的。
    """

    # 工具结果缓存的最大条目数
    _CACHE_MAX_SIZE = 64

    def __init__(self, enable_cache: bool = True) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._enable_cache = enable_cache
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()

    def register(self, tool_def_or_fn: ToolDefinition | Callable, name: str | None = None, *, overwrite: bool = False) -> None:
        """注册一个工具到注册表。

        支持两种参数类型:
        - 传入 ToolDefinition 实例直接注册。
        - 传入被 @tool 装饰的函数，从其 _agent_tool_def 属性提取定义。

        Args:
            tool_def_or_fn: ToolDefinition 实例或被 @tool 装饰的函数。
            name: 可选的工具名覆盖，默认使用 ToolDefinition 中的名称。
            overwrite: True 时允许覆盖同名已注册工具。
        """
        if isinstance(tool_def_or_fn, ToolDefinition):
            td = tool_def_or_fn
        elif callable(tool_def_or_fn):
            td = getattr(tool_def_or_fn, "_agent_tool_def", None)
            if td is None:
                raise ValueError(f"函数 {tool_def_or_fn.__name__} 未被 @tool 装饰")
        else:
            raise TypeError(f"不支持的注册类型: {type(tool_def_or_fn)}")

        final_name = name or td.name
        if final_name in self._tools and not overwrite:
            logger.warning("工具 '%s' 已注册，跳过重复注册", final_name)
            return
        td_copy = ToolDefinition(
            name=final_name,
            description=td.description,
            parameters=td.parameters,
            fn=td.fn,
        )
        self._tools[final_name] = td_copy
        logger.info("工具注册: %s (%s)", final_name, td_copy.description[:50])

    def get(self, name: str) -> ToolDefinition | None:
        """按名称查询已注册的工具。

        Args:
            name: 工具名称。

        Returns:
            ToolDefinition 或 None（未找到时）。
        """
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """返回所有已注册工具的列表。"""
        return list(self._tools.values())

    def to_ollama_tools(self) -> list[dict]:
        """将所有工具定义转换为 Ollama Chat API 所需的 tools 参数格式。

        Ollama 使用 OpenAI 兼容的 function calling 格式:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": { JSON Schema }
            }
        }

        Returns:
            符合 Ollama tools 参数格式的字典列表。
        """
        result: list[dict] = []
        for td in self._tools.values():
            result.append({
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            })
        return result

    async def execute(self, name: str, arguments: dict) -> str:
        """异步执行指定工具，将结果序列化为字符串。

        执行策略:
        - 先检查缓存，命中则直接返回。
        - 工具函数本身是同步的（复用现有 OllamaClient / parser 等同步代码）。
        - 通过 asyncio.to_thread() 在独立线程中执行，避免阻塞事件循环。
        - 执行结果截断至 _TOOL_RESULT_MAX_LEN 字符，保护 LLM 上下文窗口。
        - 异常被捕获并格式化为错误字符串返回给 LLM（不中断 ReAct 循环）。

        Args:
            name: 工具名称。
            arguments: 工具参数字典。

        Returns:
            工具执行结果的字符串表示，或错误信息。

        Raises:
            ValueError: 工具名称未注册时。
        """
        td = self._tools.get(name)
        if td is None:
            raise ValueError(f"未注册的工具: {name}")

        # 检查缓存
        cache_key = self._make_cache_key(name, arguments)
        if self._enable_cache and cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            cached_result, _ = self._cache[cache_key]
            logger.debug("工具缓存命中: %s", name)
            return cached_result

        try:
            result = await asyncio.to_thread(td.fn, **arguments)
            result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as e:
            logger.exception("工具 %s 执行失败", name)
            result_str = f"工具执行错误 ({name}): {e}"

        if len(result_str) > _TOOL_RESULT_MAX_LEN:
            result_str = result_str[:_TOOL_RESULT_MAX_LEN] + "\n...[结果已截断]"

        # 存入缓存（仅缓存成功结果，不缓存错误）
        if self._enable_cache and not result_str.startswith("工具执行错误"):
            self._cache[cache_key] = (result_str, time.monotonic())
            if len(self._cache) > self._CACHE_MAX_SIZE:
                self._cache.popitem(last=False)

        return result_str

    def _make_cache_key(self, name: str, arguments: dict) -> str:
        """生成工具调用的缓存键。

        Args:
            name: 工具名称。
            arguments: 参数字典。

        Returns:
            缓存键字符串。
        """
        args_json = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        args_hash = hashlib.md5(args_json.encode()).hexdigest()[:12]
        return f"{name}:{args_hash}"

    def clear_cache(self) -> None:
        """清空工具结果缓存。"""
        self._cache.clear()


# 导出公共接口
__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "tool",
    "set_default_registry",
    "_extract_schema_from_function",
    "_TOOL_RESULT_MAX_LEN",
]
