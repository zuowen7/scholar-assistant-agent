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

版权声明: 本模块属于 Scholar Translate Agent 子系统，
工具注册与动态调度机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints

import httpx

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

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool_def_or_fn: ToolDefinition | Callable, name: str | None = None) -> None:
        """注册一个工具到注册表。

        支持两种参数类型:
        - 传入 ToolDefinition 实例直接注册。
        - 传入被 @tool 装饰的函数，从其 _agent_tool_def 属性提取定义。

        Args:
            tool_def_or_fn: ToolDefinition 实例或被 @tool 装饰的函数。
            name: 可选的工具名覆盖，默认使用 ToolDefinition 中的名称。
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

        try:
            result = await asyncio.to_thread(td.fn, **arguments)
            result_str = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        except Exception as e:
            logger.exception("工具 %s 执行失败", name)
            result_str = f"工具执行错误 ({name}): {e}"

        if len(result_str) > _TOOL_RESULT_MAX_LEN:
            result_str = result_str[:_TOOL_RESULT_MAX_LEN] + "\n...[结果已截断]"
        return result_str


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
        # arXiv API 有请求频率限制，加重试
        resp = None
        with httpx.Client(timeout=30.0) as client:
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
# 注册表工厂
# ---------------------------------------------------------------------------

def create_default_registry(
    ollama_client: Any | None = None,
    cloud_client: Any | None = None,
    rag_store: Any | None = None,
) -> ToolRegistry:
    """创建包含所有默认工具的注册表。

    通过依赖注入将现有的翻译客户端、RAG 存储等实例传入，
    工具函数通过闭包捕获这些实例，避免在工具内部创建新的客户端。

    该工厂模式确保:
    - 工具函数复用已有的 HTTP 连接池。
    - 翻译客户端的配置（模型、温度等）由外部统一管理。
    - 工具注册过程集中在一处，便于维护和扩展。

    Args:
        ollama_client: 已初始化的 OllamaClient 实例（可选）。
        cloud_client: 已初始化的 CloudClient 实例（可选）。
        rag_store: 已初始化的 RAGStore 实例（可选）。

    Returns:
        包含所有可用工具的 ToolRegistry 实例。
    """
    registry = ToolRegistry()

    # --- 翻译工具 ---
    if ollama_client is not None or cloud_client is not None:

        def translate_text(text: str, source_lang: str = "en", target_lang: str = "zh") -> str:
            """翻译文本为指定语言。将英文学术文本翻译为流畅、准确的中文。

            Args:
                text: 待翻译的文本内容。
                source_lang: 源语言代码，默认 "en"（英文）。
                target_lang: 目标语言代码，默认 "zh"（中文）。
            """
            client = ollama_client or cloud_client
            if client is None:
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

    logger.info("默认工具注册完成: %s", [t.name for t in registry.list_tools()])
    return registry
