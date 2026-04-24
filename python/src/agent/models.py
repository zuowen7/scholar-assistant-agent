"""Agent 子系统数据模型 — 定义消息、工具调用、事件、文档信息等跨模块共享的数据结构。

本模块作为 Agent 子系统的「类型字典」，被 tools.py / rag.py / agent.py / vram_manager.py
共同引用。所有数据结构使用纯 dataclass 定义（不依赖 Pydantic），与项目现有的
TranslationResult / Chunk 等数据类保持风格一致。

设计原则:
- Message 对齐 Ollama Chat API 的消息格式，避免序列化时的转换开销。
- AgentEvent 采用字符串类型标识符（非 Enum），与 api_factory.py 中 SSE 事件
  的命名风格（"progress", "chunk_done", "error"）保持一致。
- 所有字段使用 Python 3.10+ 联合类型语法 (X | None) 而非 Optional[X]。

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
调度策略与数据隐私保护机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """LLM 发起的工具调用请求。

    当 Agent 的推理模型决定调用某个工具时，会生成一个 ToolCall 实例。
    该结构同时兼容 Ollama 原生 tool calling 的响应格式和文本 ReAct 的解析结果。

    Attributes:
        id: 工具调用的唯一标识符，用于将 tool_result 消息与对应的 tool_call 关联。
        name: 待调用的工具名称，必须在 ToolRegistry 中已注册。
        arguments: 解析后的工具参数字典，键名与 @tool 装饰器函数的形参名一致。
    """

    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class Message:
    """Agent 对话消息 — 与 Ollama Chat API 消息格式对齐。

    支持四种角色:
    - system: 系统提示词，定义 Agent 的行为约束和可用能力。
    - user:   用户输入的查询或指令。
    - assistant: 模型的回复，可能包含文本内容或工具调用请求。
    - tool: 工具执行结果，通过 tool_call_id 与对应的 ToolCall 关联。

    Attributes:
        role: 消息角色 (system | user | assistant | tool)。
        content: 消息的文本内容。assistant 角色在发起工具调用时 content 可为空串。
        tool_calls: assistant 消息中包含的工具调用列表。仅 role="assistant" 时有效。
        tool_call_id: tool 消息关联的工具调用 ID。仅 role="tool" 时有效。
    """

    role: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


@dataclass
class AgentEvent:
    """Agent SSE 事件 — ReAct 推理过程中流式返回的中间状态或最终结果。

    事件类型说明:
    - thinking:    Agent 正在推理（可选择性地展示思考过程）。
    - tool_call:   Agent 决定调用某个工具，携带工具名和参数。
    - tool_result: 工具执行完毕，携带返回值或错误信息。
    - response:    Agent 的最终回答（ReAct 循环终止）。
    - error:       不可恢复的错误（如连接失败、超过最大步数）。

    该数据结构与 api_factory.py 中 SSE EventSourceResponse 的事件格式兼容，
    未来接入 FastAPI 路由时可直接映射为 {"event": type, "data": json.dumps(...)}。

    Attributes:
        type: 事件类型标识符。
        content: 事件的文本内容（思考过程、工具参数、最终回答等）。
        metadata: 附加元数据，如工具名称、执行耗时、token 用量等。
    """

    type: str
    content: str = ""
    metadata: dict | None = None


@dataclass
class DocumentInfo:
    """RAG 文档元信息 — 描述已入库文档的概要信息。

    用于 list_documents() 接口的返回值，让用户了解当前向量库中
    存储了哪些文档及其入库状态。

    Attributes:
        id: 文档唯一标识符（入库时由调用方指定）。
        title: 文档标题或文件名。
        chunk_count: 该文档被切分后存入向量库的文本块数量。
        metadata: 入库时附加的元数据（如来源路径、入库时间等）。
    """

    id: str
    title: str = ""
    chunk_count: int = 0
    metadata: dict = field(default_factory=dict)


def message_to_ollama_dict(msg: Message) -> dict:
    """将 Message 转换为 Ollama Chat API 所需的消息字典格式。

    该函数是 Agent 与 Ollama 之间的序列化桥梁，确保 Message dataclass
    可以无损转换为 Ollama /api/chat 接口接受的 messages 数组元素。

    Args:
        msg: Agent 内部的 Message 实例。

    Returns:
        符合 Ollama Chat API 格式的字典，包含 role、content 等字段。
        当 msg.tool_calls 非空时，字典中还包含 tool_calls 数组。
    """
    d: dict = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments,
                }
            }
            for tc in msg.tool_calls
        ]
    if msg.tool_call_id:
        d["tool_call_id"] = msg.tool_call_id
    return d
