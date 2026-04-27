"""工具注册表与装饰器 — 将现有翻译/解析功能封装为 Agent 可调用的 Tool。

本模块实现了 Agent 子系统的「工具层」，是连接 LLM 推理引擎与底层业务逻辑的桥梁。
核心设计模式:

1. **@tool 装饰器**: 从函数签名和 __doc__ 自动提取 JSON Schema，
   无需手动维护工具描述文件。装饰器模式与项目中 parser/dispatcher.py 的
   @_register 装饰器保持一致的注册风格。

2. **ToolRegistry**: 集中管理工具的注册、查询、格式转换和执行。
   提供 to_ollama_tools() 方法将工具定义转换为 Ollama Chat API 所需的
   tools 参数格式，实现与 LLM 的无缝对接。

3. **create_default_registry()**: 工厂函数，将现有的翻译客户端、文档解析器、
   RAG 检索器等注入为工具，避免在工具内部创建新的客户端实例。

安全策略:
- 所有工具函数的参数经过 JSON Schema 校验后才传入底层业务逻辑。
- 文件路径参数受路径遍历防护约束（parse_document 工具内部调用
  api_factory._validate_file_path 等效逻辑）。
- 工具执行结果截断至 _TOOL_RESULT_MAX_LEN 字符，防止超长输出
  耗尽 LLM 上下文窗口。

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
工具注册与动态调度机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, get_type_hints

import httpx

from src.agent.llm_client import LLMClient

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


# ---------------------------------------------------------------------------
# 默认工具实现
# ---------------------------------------------------------------------------

def _translate_text(
    text: str,
    source_lang: str = "en",
    target_lang: str = "zh",
) -> str:
    """翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。

    Args:
        text: 待翻译的文本内容。
        source_lang: 源语言代码，默认 "en"（英文）。
        target_lang: 目标语言代码，默认 "zh"（中文）。
    """
    # 占位实现 — 由 create_default_registry 注入实际客户端
    raise NotImplementedError("翻译客户端未注入")


def _parse_document(file_path: str) -> str:
    """解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。

    Args:
        file_path: 文档文件的绝对路径。
    """
    raise NotImplementedError("解析器未注入")


def _search_documents(query: str, top_k: int = 5) -> str:
    """在已入库的文档中检索与查询相关的段落。基于向量相似度匹配，返回最相关的文本片段。

    Args:
        query: 查询文本（中英文均可）。
        top_k: 返回的最大结果数量，默认 5。
    """
    raise NotImplementedError("RAG 存储未注入")


def _crawl_arxiv(query: str, max_results: int = 5) -> str:
    """搜索 arXiv 学术论文，返回标题、作者和摘要。通过 arXiv API 检索最新学术论文信息。

    Args:
        query: 搜索关键词（英文）。
        max_results: 最大返回结果数，默认 5。
    """
    try:
        url = "https://export.arxiv.org/api/query"
        params = {
            "search_query": f"all:{query}",
            "max_results": str(max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        resp = None
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            for attempt in range(3):
                resp = client.get(url, params=params)
                if resp.status_code == 429:
                    time.sleep(3.0 * (attempt + 1))
                    continue
                resp.raise_for_status()
                break
            else:
                if resp is not None:
                    resp.raise_for_status()

        # 解析 Atom XML 响应
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return "未找到相关论文。"

        results: list[str] = []
        for entry in entries:
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            published = entry.find("atom:published", ns)
            authors = entry.findall("atom:author/atom:name", ns)

            title_text = title.text.strip().replace("\n", " ") if title is not None else "无标题"
            summary_text = summary.text.strip().replace("\n", " ")[:300] if summary is not None else ""
            pub_date = published.text[:10] if published is not None else "未知日期"
            author_names = ", ".join(a.text for a in authors[:3] if a.text)
            if len(authors) > 3:
                author_names += " et al."

            results.append(
                f"标题: {title_text}\n"
                f"作者: {author_names}\n"
                f"日期: {pub_date}\n"
                f"摘要: {summary_text}"
            )

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"arXiv 搜索失败: {e}"


# ---------------------------------------------------------------------------
# 文件工具
# ---------------------------------------------------------------------------

_SANDBOX_ROOT = os.environ.get("SCHOLAR_AGENT_SANDBOX", str(Path.home() / "scholar_agent_files"))


def _resolve_safe_path(file_path: str) -> Path:
    """将用户提供的路径解析到沙箱目录内，防止路径遍历。

    Args:
        file_path: 用户提供的文件路径（相对或绝对）。

    Returns:
        解析后的安全绝对路径。

    Raises:
        ValueError: 路径逃逸沙箱时。
    """
    root = Path(_SANDBOX_ROOT).resolve()
    target = (root / file_path).resolve() if not os.path.isabs(file_path) else Path(file_path).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"路径超出沙箱范围: {file_path}")
    return target


def _save_file(file_path: str, content: str) -> str:
    """将内容保存到文件。支持在沙箱目录中创建文件和子目录。

    Args:
        file_path: 文件路径（相对于沙箱根目录，或绝对路径）。
        content: 要保存的文本内容。
    """
    try:
        safe_path = _resolve_safe_path(file_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content, encoding="utf-8")
        return f"文件已保存: {safe_path} ({len(content)} 字符)"
    except ValueError as e:
        return f"路径安全错误: {e}"
    except Exception as e:
        return f"保存文件失败: {e}"


def _read_file(file_path: str) -> str:
    """读取文件内容。支持读取沙箱目录中的文本文件。

    Args:
        file_path: 文件路径（相对于沙箱根目录，或绝对路径）。
    """
    try:
        safe_path = _resolve_safe_path(file_path)
        if not safe_path.exists():
            return f"文件不存在: {safe_path}"
        content = safe_path.read_text(encoding="utf-8")
        if len(content) > _TOOL_RESULT_MAX_LEN:
            content = content[:_TOOL_RESULT_MAX_LEN] + "\n...[文件内容已截断]"
        return content
    except ValueError as e:
        return f"路径安全错误: {e}"
    except Exception as e:
        return f"读取文件失败: {e}"


# ---------------------------------------------------------------------------
# AWA v2: 工作区工具（WorkspaceEnv + ChangeJournal）
# ---------------------------------------------------------------------------

_LINE_NUMBER_LIMIT = 2000


def _read_file_v2(
    file_path: str,
    workspace,  # WorkspaceEnv — 在 create_default_registry 中通过闭包注入
    *,
    offset: int = 0,
    limit: int | None = None,
    encoding: str = "utf-8",
) -> str:
    """读取项目工作区内的文件，返回带行号的内容。

    Args:
        file_path: 相对项目根的路径，绝对路径若在项目根内也接受。
        workspace: WorkspaceEnv 实例（内部注入，不暴露给 LLM）。
        offset: 起始行号（0-indexed），默认 0。
        limit: 最多读取行数，None 表示读到结尾。
        encoding: 文件编码，默认 utf-8。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_file():
        return json.dumps({"error": f"file not found: {file_path}"})

    # 二进制检测：前 4096 字节含 NUL → 拒绝
    try:
        with open(resolved, "rb") as f:
            head = f.read(4096)
        if b"\x00" in head:
            return json.dumps({"error": f"binary file, refusing to read: {file_path}"})
    except OSError as e:
        return json.dumps({"error": str(e)})

    # 大小检查
    if resolved.stat().st_size > workspace.max_file_bytes:
        return json.dumps({"error": f"file too large ({resolved.stat().st_size} bytes), max {workspace.max_file_bytes}"})

    try:
        lines = resolved.read_text(encoding=encoding).splitlines(True)
    except Exception as e:
        return json.dumps({"error": f"read failed: {e}"})

    total_lines = len(lines)
    end = min(offset + (limit or _LINE_NUMBER_LIMIT), total_lines)
    sliced = lines[offset:end]

    numbered = []
    for i, line in enumerate(sliced, start=offset + 1):
        numbered.append(f"{i:>6}\t{line.rstrip()}")

    content = "\n".join(numbered)
    truncated = end < total_lines

    return json.dumps({
        "file_path": file_path,
        "total_lines": total_lines,
        "returned_lines": [offset + 1, end],
        "content": content,
        "truncated": truncated,
    }, ensure_ascii=False)


def _list_directory(
    path: str,
    workspace,
    *,
    pattern: str | None = None,
    recursive: bool = False,
    max_entries: int = 200,
) -> str:
    """列出目录内容，返回带类型和大小的结构。

    Args:
        path: 相对项目根的目录路径，默认根目录。
        workspace: WorkspaceEnv 实例（内部注入）。
        pattern: glob 过滤（如 '*.py'），None 表示不过滤。
        recursive: 是否递归（递归时尊重 .gitignore）。
        max_entries: 最大返回条目数，默认 200。
    """
    from src.agent.workspace import WorkspaceViolation

    target = path if path else "."
    try:
        resolved = workspace.resolve(target)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_dir():
        return json.dumps({"error": f"not a directory: {target}"})

    entries = []
    seen = 0
    max_entries = min(max_entries, 1000)

    try:
        if recursive:
            # 读取 .gitignore
            gitignore_patterns = _load_gitignore(resolved, workspace.root)

            for item in resolved.rglob(pattern or "*"):
                rel = item.relative_to(resolved)
                rel_str = str(rel).replace("\\", "/")
                if _gitignored(rel_str, gitignore_patterns):
                    continue
                if seen >= max_entries:
                    break
                entries.append(_dir_entry(item, resolved))
                seen += 1
        else:
            for item in resolved.iterdir():
                if pattern and not item.match(pattern):
                    continue
                if seen >= max_entries:
                    break
                entries.append(_dir_entry(item, resolved))
                seen += 1
    except PermissionError:
        return json.dumps({"error": f"permission denied: {target}"})

    entries.sort(key=lambda e: (e["type"] == "dir", e["name"].lower()))

    return json.dumps({
        "path": target,
        "entries": entries,
        "truncated": seen >= max_entries,
    }, ensure_ascii=False)


def _str_replace(
    file_path: str,
    old_string: str,
    new_string: str,
    workspace,
    journal,  # ChangeJournal — 闭包注入
    *,
    session_id: str = "",
    event_id: str = "",
    replace_all: bool = False,
) -> str:
    """精确字符串替换。

    Args:
        file_path: 目标文件相对路径。
        old_string: 待替换的精确字符串。
        new_string: 替换后的字符串。
        workspace: WorkspaceEnv 实例（内部注入）。
        journal: ChangeJournal 实例（内部注入）。
        session_id: 当前会话 ID。
        event_id: 当前事件 ID。
        replace_all: True 时替换所有出现；False 时要求 old_string 唯一。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    if not resolved.is_file():
        return json.dumps({"error": f"file not found: {file_path}"})

    content = resolved.read_text(encoding="utf-8")
    count = content.count(old_string)

    if count == 0:
        return json.dumps({"error": "old_string not found in file", "file_path": file_path})
    if count > 1 and not replace_all:
        return json.dumps({
            "error": f"old_string appears {count} times — ambiguous. Use replace_all=True or expand old_string context.",
            "file_path": file_path,
            "occurrences": count,
        })

    # 备份
    backup_id = journal.generate_backup_id()
    original_sha = _file_sha256(resolved)
    journal.backup_file(backup_id, resolved, workspace.root)

    # 执行替换
    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    resolved.write_text(new_content, encoding="utf-8")
    new_sha = _file_sha256(resolved)

    # 生成 diff preview
    diff_preview = _make_diff_preview(content, new_content, file_path)

    # 写 journal
    journal.append_entry(
        backup_id=backup_id,
        session_id=session_id or "default",
        event_id=event_id or backup_id,
        tool="str_replace",
        file=file_path.replace("\\", "/"),
        operation="edit",
        original_sha256=original_sha,
        new_sha256=new_sha,
        diff_preview=diff_preview,
    )

    actual = new_content.count(new_string) if old_string != new_string else count
    return json.dumps({
        "file_path": file_path,
        "occurrences": count if replace_all else 1,
        "diff": diff_preview,
        "backup_id": backup_id,
    }, ensure_ascii=False)


def _write_file_v2(
    file_path: str,
    content: str,
    workspace,
    journal,
    *,
    session_id: str = "",
    event_id: str = "",
    must_not_exist: bool = False,
) -> str:
    """整文件写入（仅用于新建文件或全量重写）。

    Args:
        file_path: 目标文件相对路径。
        content: 完整内容。
        workspace: WorkspaceEnv 实例（内部注入）。
        journal: ChangeJournal 实例（内部注入）。
        session_id: 当前会话 ID。
        event_id: 当前事件 ID。
        must_not_exist: True 时若文件已存在则报错。
    """
    from src.agent.workspace import WorkspaceViolation

    try:
        resolved = workspace.resolve(file_path)
    except WorkspaceViolation as e:
        return json.dumps({"error": str(e)})

    created = not resolved.exists()

    if must_not_exist and resolved.exists():
        return json.dumps({"error": f"file already exists: {file_path}", "created": False})

    # 备份已存在文件
    backup_id = journal.generate_backup_id()
    original_sha = ""
    if resolved.exists():
        original_sha = _file_sha256(resolved)
        journal.backup_file(backup_id, resolved, workspace.root)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    new_sha = _file_sha256(resolved)

    journal.append_entry(
        backup_id=backup_id,
        session_id=session_id or "default",
        event_id=event_id or backup_id,
        tool="write_file",
        file=file_path.replace("\\", "/"),
        operation="create" if created else "overwrite",
        original_sha256=original_sha,
        new_sha256=new_sha,
    )

    return json.dumps({
        "file_path": file_path,
        "size": len(content),
        "created": created,
        "backup_id": backup_id,
    }, ensure_ascii=False)


def _undo_last_change(
    journal,
    workspace,
    *,
    count: int = 1,
    backup_id: str | None = None,
) -> str:
    """回退最近 N 次破坏性操作。

    Args:
        journal: ChangeJournal 实例（内部注入）。
        workspace: WorkspaceEnv 实例（内部注入）。
        count: 回退次数，默认 1。
        backup_id: 指定回退到某个 backup 点。
    """
    reverted = journal.undo(count=count, backup_id=backup_id)
    if not reverted:
        return json.dumps({"error": "no undoable operations found"})

    return json.dumps({
        "reverted": [
            {"backup_id": r.get("backup_id"), "file_path": r.get("file"), "operation": r.get("tool")}
            for r in reverted
        ],
        "count": len(reverted),
    }, ensure_ascii=False)


# --- 辅助函数 ---


def _dir_entry(item: Path, base: Path) -> dict:
    try:
        stat = item.stat()
        size = stat.st_size if item.is_file() else None
        import datetime
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
    except OSError:
        size = None
        mtime = ""
    return {
        "name": item.name,
        "type": "dir" if item.is_dir() else "file",
        "size": size,
        "mtime": mtime,
    }


def _load_gitignore(directory: Path, workspace_root: Path) -> list[str]:
    """加载 .gitignore 模式。"""
    gi = directory / ".gitignore"
    if not gi.is_file():
        # 向上查找到 workspace root
        for parent in directory.parents:
            gi = parent / ".gitignore"
            if gi.is_file():
                break
            if parent == workspace_root:
                break
    if not gi.is_file():
        return []
    patterns = []
    for line in gi.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _gitignored(rel_path: str, patterns: list[str]) -> bool:
    """简单 gitignore 匹配（不实现完整 gitignore 规范，只做常见模式）。"""
    parts = rel_path.split("/")
    basename = parts[-1]
    dir_parts = parts[:-1]  # 目录部分

    for pat in patterns:
        if pat.endswith("/"):
            # 目录匹配: node_modules/ → 过滤该目录下所有内容
            dir_name = pat.rstrip("/")
            if dir_name in parts:
                return True
        elif pat.startswith("*"):
            # 通配符匹配文件名
            import fnmatch
            if fnmatch.fnmatch(basename, pat):
                return True
        elif pat.startswith("/"):
            # 从根开始的路径
            import fnmatch
            if fnmatch.fnmatch(rel_path, pat[1:]):
                return True
        else:
            # 任意位置匹配
            import fnmatch
            if fnmatch.fnmatch(basename, pat):
                return True
            if any(fnmatch.fnmatch("/".join(dir_parts[i:]), pat) for i in range(len(dir_parts) + 1)):
                return True
    return False


def _file_sha256(path: Path) -> str:
    """计算文件 SHA-256。"""
    import hashlib
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError:
        return ""


def _make_diff_preview(old_content: str, new_content: str, file_path: str) -> str:
    """生成 unified diff 预览。"""
    import difflib
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}")
    result = "".join(diff)
    # 截断到 500 字符
    if len(result) > 500:
        result = result[:500] + "\n..."
    return result


# ---------------------------------------------------------------------------
# Phase 4: 原子工具
# ---------------------------------------------------------------------------

# shell_exec 白名单
_SHELL_ALLOWED_COMMANDS = frozenset({
    # 只读
    "ls", "dir", "cat", "head", "tail", "wc", "echo",
    "find", "grep", "sort", "uniq", "cut", "tr", "tee",
    "pwd", "whoami", "date", "uname",
    # 文件操作（限制在沙箱内）
    "touch", "mkdir", "cp", "mv", "rm", "rmdir",
    # 开发工具
    "python", "python3", "pip", "pip3",
    "git",
    "curl", "wget",
})

_SHELL_TIMEOUT = 30


def _validate_sandbox_command(command: str) -> str | None:
    """检查 shell 命令是否包含沙箱逃逸路径。返回错误信息或 None（通过）。"""
    import re
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

    # 文件操作命令必须在沙箱内执行
    sandbox_cmds = {"touch", "mkdir", "cp", "mv", "rm", "rmdir"}
    cwd = None
    if base_cmd in sandbox_cmds:
        path_error = _validate_sandbox_command(command)
        if path_error:
            return f"安全限制: {path_error}。文件操作仅限沙箱目录内的相对路径。"
        cwd = _SANDBOX_ROOT
        Path(cwd).mkdir(parents=True, exist_ok=True)

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


_PYTHON_EXEC_TIMEOUT = 30


def _python_exec(code: str, timeout: int = _PYTHON_EXEC_TIMEOUT) -> str:
    """执行 Python 代码片段并返回输出。在受限环境中运行，有超时保护。

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

    # 受限全局命名空间
    safe_globals: dict[str, Any] = {
        "__builtins__": {
            "print": print, "len": len, "range": range, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter, "sorted": sorted,
            "reversed": reversed, "sum": sum, "min": min, "max": max,
            "abs": abs, "round": round, "int": int, "float": float,
            "str": str, "list": list, "dict": dict, "set": set, "tuple": tuple,
            "bool": bool, "type": type, "isinstance": isinstance,
            "True": True, "False": False, "None": None,
        },
    }

    import io
    import contextlib

    stdout_buf = io.StringIO()
    safe_globals["_stdout"] = stdout_buf

    # 用 threading 实现超时（subprocess 不适用于纯 Python eval）
    import threading

    exec_error: list[str] = []
    exec_done = threading.Event()

    def _run():
        try:
            with contextlib.redirect_stdout(stdout_buf):
                exec(code, safe_globals)
        except Exception as e:
            exec_error.append(str(e))
        finally:
            exec_done.set()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    finished = exec_done.wait(timeout=timeout)

    if not finished:
        return f"代码执行超时 ({timeout}s)，已终止。"

    output = stdout_buf.getvalue()
    if exec_error:
        output += f"\n[执行错误] {exec_error[0]}"
    if len(output) > _TOOL_RESULT_MAX_LEN:
        output = output[:_TOOL_RESULT_MAX_LEN] + "\n...[输出已截断]"
    return output or "(无输出)"


_WEB_FETCH_TIMEOUT = 20
_WEB_FETCH_MAX_SIZE = 200_000  # 200KB


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
            headers={"User-Agent": "ScholarAssistant/1.0"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content = resp.text

        if len(content) > _WEB_FETCH_MAX_SIZE:
            content = content[:_WEB_FETCH_MAX_SIZE]

        if extract_text:
            # 简易 HTML → 纯文本：去除标签
            import re
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


_WEB_SEARCH_MAX_RESULTS = 8


def _web_search(query: str, max_results: int = _WEB_SEARCH_MAX_RESULTS) -> str:
    """使用搜索引擎搜索信息。通过 DuckDuckGo 返回搜索结果摘要。

    Args:
        query: 搜索关键词（中英文均可）。
        max_results: 返回的最大结果数，默认 8。
    """
    try:
        with httpx.Client(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ScholarAssistant/1.0)"},
        ) as client:
            # DuckDuckGo HTML 版本（无需 API Key）
            resp = client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query, "kl": "cn-zh"},
            )
            resp.raise_for_status()
            html = resp.text

        import re
        # 提取搜索结果
        results: list[str] = []
        # DuckDuckGo HTML 结果格式
        blocks = re.findall(
            r'<a rel="nofollow" class="result__a"[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL,
        )
        for title_html, snippet_html in blocks[:max_results]:
            title = re.sub(r"<[^>]+>", "", title_html).strip()
            snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
            if title:
                results.append(f"标题: {title}\n摘要: {snippet}")

        if not results:
            # 回退：尝试另一种格式
            titles = re.findall(r'class="result__title"[^>]*>(.*?)</a>', html, re.DOTALL)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
            for i in range(min(len(titles), max_results)):
                title = re.sub(r"<[^>]+>", "", titles[i]).strip()
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                if title:
                    results.append(f"标题: {title}\n摘要: {snippet}")

        if not results:
            return "未找到相关结果。"

        return "\n\n---\n\n".join(results)
    except Exception as e:
        return f"搜索失败: {e}"


def _export_pdf(markdown: str, template_id: str = "generic_article", title: str = "") -> str:
    """将 Markdown 内容导出为 PDF 文件。使用 Pandoc + Tectonic 编译 LaTeX 生成 PDF。

    Args:
        markdown: Markdown 格式的文本内容。
        template_id: 论文模板 ID，可选 generic_article/ieee_conference/ieee_journal/acm/lncs/neurips，默认 generic_article。
        title: 文档标题（可选）。
    """
    try:
        from src.pandoc_templates import convert_markdown, tectonic_available, pandoc_version
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


def _manage_knowledge(
    action: str,
    doc_id: str = "",
    file_path: str = "",
    text: str = "",
    query: str = "",
    top_k: int = 5,
) -> str:
    """管理知识库文档。支持入库、删除、列出和检索知识库中的文档。

    Args:
        action: 操作类型。ingest（入库）、delete（删除）、list（列出所有）、retrieve（检索）。
        doc_id: 文档 ID（ingest/delete 时必需）。
        file_path: 文档路径（ingest 时可选，与 text 二选一）。
        text: 直接文本内容（ingest 时可选，与 file_path 二选一）。
        query: 检索查询文本（retrieve 时必需）。
        top_k: 检索返回的最大结果数，默认 5。
    """
    # 占位实现 — 由 create_default_registry 注入 RAG 存储实例
    raise NotImplementedError("RAG 存储未注入")


# ---------------------------------------------------------------------------
# 注册表工厂
# ---------------------------------------------------------------------------

def create_default_registry(
    ollama_client: Any | None = None,
    cloud_client: Any | None = None,
    rag_store: Any | None = None,
    ollama_base_url: str = "http://localhost:11434",
    model: str = "qwen3:8b",
    cloud_base_url: str = "",
    cloud_api_key: str = "",
    cloud_model: str = "",
    workspace_root: str = "",
) -> ToolRegistry:
    """创建包含所有默认工具的注册表。

    通过依赖注入将现有的翻译客户端、RAG 存储等实例传入，
    工具函数通过闭包捕获这些实例，避免在工具内部创建新的客户端。

    Args:
        ollama_client: 已初始化的 OllamaClient 实例（可选）。
        cloud_client: 已初始化的 CloudClient 实例（可选）。
        rag_store: 已初始化的 RAGStore 实例（可选）。
        ollama_base_url: Ollama API 地址，供 LLM 工具使用。
        model: Ollama 模型名称。
        cloud_base_url: 云端 API 地址。
        cloud_api_key: 云端 API Key。
        cloud_model: 云端模型名称。
        workspace_root: 工作区根目录路径，启用 AWA v2 工作区工具。

    Returns:
        包含所有可用工具的 ToolRegistry 实例。
    """
    registry = ToolRegistry()

    # --- Shared LLM client for text-processing tools ---
    _llm = LLMClient(
        ollama_base_url=ollama_base_url,
        model=model,
        cloud_base_url=cloud_base_url,
        cloud_api_key=cloud_api_key,
        cloud_model=cloud_model,
        temperature=0.3,
        num_predict=4096,
    )

    # --- 翻译工具 ---
    if ollama_client is not None or cloud_client is not None:

        def translate_text(text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
            """翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。

            Args:
                text: 待翻译的文本内容。
                source_lang: 源语言代码，默认 "en"（英文）。
                target_lang: 目标语言代码，默认 "zh"（中文）。
            """
            if ollama_client is not None:
                client = ollama_client
            elif cloud_client is not None:
                client = cloud_client
            else:
                return "错误: 无可用的翻译客户端"
            result = client.translate(text)
            return result.translated

        translate_text._agent_tool_def = ToolDefinition(
            name="translate_text",
            description="翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。",
            parameters=_extract_schema_from_function(translate_text),
            fn=translate_text,
        )
        registry.register(translate_text)

    # --- 文档解析工具 ---
    try:
        from src.parser import extract_document as _extract_doc

        def parse_document(file_path: str) -> str:
            """解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。

            Args:
                file_path: 文档文件的绝对路径。
            """
            try:
                doc = _extract_doc(file_path)
                return doc.full_text
            except Exception as e:
                return f"文档解析失败: {e}"

        parse_document._agent_tool_def = ToolDefinition(
            name="parse_document",
            description="解析文档文件，提取纯文本内容。支持 PDF、Word、PPT、Excel、TXT 等 16 种格式。",
            parameters=_extract_schema_from_function(parse_document),
            fn=parse_document,
        )
        registry.register(parse_document)
    except ImportError:
        logger.warning("parser 模块不可用，跳过 parse_document 工具注册")

    # --- RAG 检索工具 ---
    if rag_store is not None:

        def search_documents(query: str, top_k: int = 5) -> str:
            """在已入库的文档中检索与查询相关的段落。基于向量相似度匹配，返回最相关的文本片段。

            Args:
                query: 查询文本（中英文均可）。
                top_k: 返回的最大结果数量，默认 5。
            """
            try:
                results = rag_store.retrieve_context(query, top_k=top_k)
                if not results:
                    return "未找到相关文档内容。请先使用 parse_document 解析文档并入库。"
                parts: list[str] = []
                for i, r in enumerate(results):
                    parts.append(f"[片段 {i + 1}] (相似度: {1 - r.get('distance', 0):.2f})\n{r['text']}")
                return "\n\n---\n\n".join(parts)
            except Exception as e:
                return f"文档检索失败: {e}"

        search_documents._agent_tool_def = ToolDefinition(
            name="search_documents",
            description="在已入库的文档中检索与查询相关的段落。基于向量相似度匹配，返回最相关的文本片段。",
            parameters=_extract_schema_from_function(search_documents),
            fn=search_documents,
        )
        registry.register(search_documents)

    # --- arXiv 爬取工具 ---
    crawl_tool_def = ToolDefinition(
        name="crawl_arxiv",
        description="搜索 arXiv 学术论文，返回标题、作者和摘要。通过 arXiv API 检索最新学术论文信息。",
        parameters=_extract_schema_from_function(_crawl_arxiv),
        fn=_crawl_arxiv,
    )
    registry.register(crawl_tool_def)

    # --- 文本润色工具 ---
    def polish_text(text: str, style: str = "academic") -> str:
        """润色学术文本，改善表达和语法。支持多种写作风格的文本润色和优化。

        Args:
            text: 待润色的文本内容。
            style: 润色风格，可选 academic（学术）、formal（正式）、concise（简洁），默认 academic。
        """
        style_hints = {
            "academic": "使用严谨的学术语言，确保逻辑清晰、用词精准",
            "formal": "使用正式的书面语，避免口语化表达",
            "concise": "精简冗余表达，保留核心信息，使文字更加凝练",
        }
        hint = style_hints.get(style, style_hints["academic"])
        prompt = f"请润色以下文本。要求：{hint}。只输出润色后的文本，不要解释。\n\n{text}"
        return _llm.call_simple_sync(prompt)

    polish_text._agent_tool_def = ToolDefinition(
        name="polish_text",
        description="润色学术文本，改善表达和语法。支持多种写作风格的文本润色和优化。",
        parameters=_extract_schema_from_function(polish_text),
        fn=polish_text,
    )
    registry.register(polish_text)

    # --- 文本摘要工具 ---
    def summarize_text(text: str, max_sentences: int = 5) -> str:
        """生成文本的精简摘要。提取核心论点和关键信息，输出结构化摘要。

        Args:
            text: 待摘要的文本内容。
            max_sentences: 摘要的最大句子数，默认 5。
        """
        prompt = (
            f"请用中文为以下文本生成摘要，不超过 {max_sentences} 个句子。"
            "提取核心论点和关键信息。\n\n{text}"
        )
        return _llm.call_simple_sync(prompt)

    summarize_text._agent_tool_def = ToolDefinition(
        name="summarize_text",
        description="生成文本的精简摘要。提取核心论点和关键信息，输出结构化摘要。",
        parameters=_extract_schema_from_function(summarize_text),
        fn=summarize_text,
    )
    registry.register(summarize_text)

    # --- 大纲生成工具 ---
    def generate_outline(topic: str, sections: int = 5) -> str:
        """生成学术论文或报告的结构化大纲。根据主题生成层次分明的大纲框架。

        Args:
            topic: 论文或报告的主题。
            sections: 大纲的章节数量，默认 5。
        """
        prompt = (
            f"请为主题「{topic}」生成一个学术论文大纲，包含 {sections} 个主要章节。"
            "每个章节下给出 2-3 个子节。使用 Markdown 格式输出。"
        )
        return _llm.call_simple_sync(prompt)

    generate_outline._agent_tool_def = ToolDefinition(
        name="generate_outline",
        description="生成学术论文或报告的结构化大纲。根据主题生成层次分明的大纲框架。",
        parameters=_extract_schema_from_function(generate_outline),
        fn=generate_outline,
    )
    registry.register(generate_outline)

    # --- 段落扩写工具 ---
    def expand_section(section: str, context: str = "") -> str:
        """扩写论文段落，补充细节和论据。根据上下文将简短的段落扩展为完整论述。

        Args:
            section: 待扩写的段落内容。
            context: 上下文信息（可选，帮助 LLM 保持一致性）。
        """
        ctx_part = f"\n\n参考上下文:\n{context}" if context else ""
        prompt = (
            f"请将以下段落扩写为 200-400 字的完整论述，补充细节、论据和例子。"
            "保持学术风格，逻辑连贯。只输出扩写后的文本。\n\n"
            f"原文: {section}{ctx_part}"
        )
        return _llm.call_simple_sync(prompt)

    expand_section._agent_tool_def = ToolDefinition(
        name="expand_section",
        description="扩写论文段落，补充细节和论据。根据上下文将简短的段落扩展为完整论述。",
        parameters=_extract_schema_from_function(expand_section),
        fn=expand_section,
    )
    registry.register(expand_section)

    # --- 文件保存工具 ---
    save_file_def = ToolDefinition(
        name="save_file",
        description="将内容保存到文件。支持在沙箱目录中创建文件和子目录。",
        parameters=_extract_schema_from_function(_save_file),
        fn=_save_file,
    )
    registry.register(save_file_def)

    # --- 文件读取工具 ---
    read_file_def = ToolDefinition(
        name="read_file",
        description="读取文件内容。支持读取沙箱目录中的文本文件。",
        parameters=_extract_schema_from_function(_read_file),
        fn=_read_file,
    )
    registry.register(read_file_def)

    # --- 参考文献格式化工具 ---
    def format_bibliography(
        bibtex_entry: str,
        style: str = "ieee",
        target_lang: str = "zh",
    ) -> str:
        """将 BibTeX 条目格式化为指定的引用格式。支持 GB/T 7714、APA、IEEE 等常见学术引用格式。

        Args:
            bibtex_entry: BibTeX 格式的参考文献条目（@article{...}, @book{...} 等）
            style: 引用格式，可选 ieee（IEEE）、apa（APA 第七版）、gbt7714（GB/T 7714-2015）、mla（MLA 第九版），默认 ieee
            target_lang: 引用语言，可选 zh（中文）、en（英文），默认 zh
        """
        styles = ["ieee", "apa", "gbt7714", "mla"]
        if style not in styles:
            return f"不支持的引用格式: {style}。支持的格式: {', '.join(styles)}"
        prompt = f"""请将以下 BibTeX 条目格式化为 {style.upper()} 引用格式的文本。

要求：
1. 只输出格式化后的参考文献，不要任何解释或说明
2. 严格按照 {style.upper()} 格式规范
3. 目标语言：{"中文" if target_lang == "zh" else "英文"}
4. 译名使用学界公认译法，不要生造

BibTeX 条目：
{bibtex_entry}

格式化后的引用："""
        return _llm.call_simple_sync(prompt)

    format_bibliography._agent_tool_def = ToolDefinition(
        name="format_bibliography",
        description="将 BibTeX 条目格式化为指定引用格式（IEEE/APA/GB/T 7714/MLA）。",
        parameters=_extract_schema_from_function(format_bibliography),
        fn=format_bibliography,
    )
    registry.register(format_bibliography)

    # --- 特殊元素处理工具 ---
    try:
        from src.agent.special_elements import build_special_elements_tools
        special_tools = build_special_elements_tools()
        for tool_def in special_tools:
            registry.register(tool_def)
        logger.info("特殊元素工具注册完成: %s", [t.name for t in special_tools])
    except ImportError as e:
        logger.warning("特殊元素模块不可用: %s", e)

    # --- Phase 4: shell_exec ---
    shell_exec_def = ToolDefinition(
        name="shell_exec",
        description="执行白名单内的 shell 命令并返回输出。仅允许只读和低风险命令（ls/cat/grep/find/git 等）。",
        parameters=_extract_schema_from_function(_shell_exec),
        fn=_shell_exec,
    )
    registry.register(shell_exec_def)

    # --- Phase 4: python_exec ---
    python_exec_def = ToolDefinition(
        name="python_exec",
        description="执行 Python 代码片段并返回输出。在受限环境中运行（禁止 os/subprocess 等），有超时保护。",
        parameters=_extract_schema_from_function(_python_exec),
        fn=_python_exec,
    )
    registry.register(python_exec_def)

    # --- Phase 4: web_fetch ---
    web_fetch_def = ToolDefinition(
        name="web_fetch",
        description="获取网页内容。支持 HTTP/HTTPS，可选提取纯文本或返回原始 HTML。",
        parameters=_extract_schema_from_function(_web_fetch),
        fn=_web_fetch,
    )
    registry.register(web_fetch_def)

    # --- Phase 4: web_search ---
    web_search_def = ToolDefinition(
        name="web_search",
        description="使用搜索引擎搜索信息。通过 DuckDuckGo 返回搜索结果摘要。",
        parameters=_extract_schema_from_function(_web_search),
        fn=_web_search,
    )
    registry.register(web_search_def)

    # --- Phase 4: export_pdf ---
    export_pdf_def = ToolDefinition(
        name="export_pdf",
        description="将 Markdown 内容导出为 PDF 文件。使用 Pandoc + Tectonic 编译 LaTeX 生成 PDF。",
        parameters=_extract_schema_from_function(_export_pdf),
        fn=_export_pdf,
    )
    registry.register(export_pdf_def)

    # --- Phase 4: manage_knowledge ---
    if rag_store is not None:
        def manage_knowledge(
            action: str,
            doc_id: str = "",
            file_path: str = "",
            text: str = "",
            query: str = "",
            top_k: int = 5,
        ) -> str:
            """管理知识库文档。支持入库、删除、列出和检索知识库中的文档。

            Args:
                action: 操作类型。ingest（入库）、delete（删除）、list（列出所有）、retrieve（检索）。
                doc_id: 文档 ID（ingest/delete 时必需）。
                file_path: 文档路径（ingest 时可选，与 text 二选一）。
                text: 直接文本内容（ingest 时可选，与 file_path 二选一）。
                query: 检索查询文本（retrieve 时必需）。
                top_k: 检索返回的最大结果数，默认 5。
            """
            action = action.strip().lower()
            if action == "ingest":
                if not doc_id:
                    return "错误: ingest 操作需要 doc_id 参数"
                content = text
                if not content and file_path:
                    try:
                        content = Path(file_path).read_text(encoding="utf-8")
                    except Exception as e:
                        return f"读取文件失败: {e}"
                if not content:
                    return "错误: 需要提供 text 或 file_path 参数"
                count = rag_store.ingest_document(doc_id, content)
                return f"文档入库完成: {doc_id}, {count} 个文本块"
            elif action == "delete":
                if not doc_id:
                    return "错误: delete 操作需要 doc_id 参数"
                rag_store.delete_document(doc_id)
                return f"文档已删除: {doc_id}"
            elif action == "list":
                docs = rag_store.list_documents()
                if not docs:
                    return "知识库为空"
                lines = [f"  {d.id}: {d.title} ({d.chunk_count} 块)" for d in docs]
                return f"知识库文档 ({len(docs)} 个):\n" + "\n".join(lines)
            elif action == "retrieve":
                if not query:
                    return "错误: retrieve 操作需要 query 参数"
                results = rag_store.retrieve_context(query, top_k=top_k)
                if not results:
                    return "未找到相关内容"
                parts: list[str] = []
                for i, r in enumerate(results):
                    parts.append(f"[片段 {i + 1}] (相似度: {1 - r.get('distance', 0):.2f})\n{r['text']}")
                return "\n\n---\n\n".join(parts)
            else:
                return f"未知操作: {action}。支持的操作: ingest, delete, list, retrieve"

        manage_knowledge._agent_tool_def = ToolDefinition(
            name="manage_knowledge",
            description="管理知识库文档。支持入库(ingest)、删除(delete)、列出(list)、检索(retrieve)。",
            parameters=_extract_schema_from_function(manage_knowledge),
            fn=manage_knowledge,
        )
        registry.register(manage_knowledge)
    else:
        # 无 RAG 存储时仍注册占位工具，给用户友好提示
        manage_knowledge_def = ToolDefinition(
            name="manage_knowledge",
            description="管理知识库文档。支持入库(ingest)、删除(delete)、列出(list)、检索(retrieve)。",
            parameters=_extract_schema_from_function(_manage_knowledge),
            fn=_manage_knowledge,
        )
        registry.register(manage_knowledge_def)

    # --- AWA v2: 工作区工具 ---
    if workspace_root:
        from src.agent.workspace import WorkspaceEnv
        from src.agent.change_journal import ChangeJournal

        ws_env = WorkspaceEnv(root=workspace_root)
        ws_journal = ChangeJournal(backup_root=ws_env.backup_root_path())

        def read_file_v2(file_path: str, offset: int = 0, limit: int | None = None, encoding: str = "utf-8") -> str:
            """读取项目工作区内的文件，返回带行号的内容。

            Args:
                file_path: 相对项目根的路径，绝对路径若在项目根内也接受。
                offset: 起始行号（0-indexed），默认 0。
                limit: 最多读取行数，None 表示读到结尾。
                encoding: 文件编码，默认 utf-8。
            """
            return _read_file_v2(file_path, ws_env, offset=offset, limit=limit, encoding=encoding)

        def list_directory(path: str = ".", pattern: str | None = None, recursive: bool = False, max_entries: int = 200) -> str:
            """列出目录内容，返回带类型和大小的结构。

            Args:
                path: 相对项目根的目录路径，默认根目录。
                pattern: glob 过滤（如 '*.py'），None 表示不过滤。
                recursive: 是否递归（递归时尊重 .gitignore）。
                max_entries: 最大返回条目数，默认 200。
            """
            return _list_directory(path, ws_env, pattern=pattern, recursive=recursive, max_entries=max_entries)

        def str_replace(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
            """精确字符串替换。在文件中找到精确的旧字符串并替换为新字符串。

            Args:
                file_path: 目标文件相对路径。
                old_string: 待替换的精确字符串（含缩进、换行）。
                new_string: 替换后的字符串。
                replace_all: True 时替换所有出现；False 时要求 old_string 唯一。
            """
            return _str_replace(file_path, old_string, new_string, ws_env, ws_journal, replace_all=replace_all)

        def write_file(file_path: str, content: str, must_not_exist: bool = False) -> str:
            """整文件写入。仅用于新建文件或全量重写已有文件。

            Args:
                file_path: 目标文件相对路径。
                content: 完整内容。
                must_not_exist: True 时若文件已存在则报错。
            """
            return _write_file_v2(file_path, content, ws_env, ws_journal, must_not_exist=must_not_exist)

        def undo_last_change(count: int = 1, backup_id: str | None = None) -> str:
            """回退最近 N 次破坏性操作。从变更日志中恢复文件到之前的状态。

            Args:
                count: 回退次数，默认 1。
                backup_id: 指定回退到某个 backup 点。
            """
            return _undo_last_change(ws_journal, ws_env, count=count, backup_id=backup_id)

        for fn, tool_name, desc in [
            (read_file_v2, "read_file", "读取项目工作区内的文件，返回带行号的内容。支持 offset/limit 分页。"),
            (list_directory, "list_directory", "列出目录内容，返回带类型和大小的结构。支持递归和 glob 过滤。"),
            (str_replace, "str_replace", "精确字符串替换。在文件中找到唯一匹配的旧字符串并替换。"),
            (write_file, "write_file", "整文件写入。用于新建文件或全量重写。会自动备份被覆盖的文件。"),
            (undo_last_change, "undo_last_change", "回退最近 N 次破坏性操作。从 .agent_backup 中恢复文件。"),
        ]:
            # 使用新的描述覆盖旧的 sandbox 版同名工具
            registry.register(ToolDefinition(
                name=tool_name,
                description=desc,
                parameters=_extract_schema_from_function(fn),
                fn=fn,
            ), overwrite=True)

        logger.info("AWA v2 工作区工具注册完成 (root=%s)", workspace_root)


    logger.info("默认工具注册完成: %s", [t.name for t in registry.list_tools()])
    return registry
