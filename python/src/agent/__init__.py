"""Agent 子系统 — ReAct 推理循环 + RAG 检索 + 显存动态调度 + 上下文压缩。

本包实现了将 Scholar Translate 从单一翻译工具升级为
轻量级 ReAct 架构智能体的全部核心组件:

- **AgentLoop** (agent.py): ReAct 模式推理循环引擎，
  支持 Ollama 原生 tool calling 和文本 ReAct 双策略。
- **ContextCompressor** (context_compressor.py): 比例阈值上下文压缩器，
  头尾保护 + 中间 LLM 摘要，自适应不同模型窗口。
- **PromptBuilder** (prompt_builder.py): System Prompt 动态拼装器，
  根据工具/记忆/模型自动组装最优提示词。
- **ToolRegistry** (tools.py): 工具注册表与 @tool 装饰器，
  将翻译、解析、检索等能力封装为 LLM 可调用的工具。
- **RAGStore** (rag.py): 基于 ChromaDB 的本地文档检索存储，
  提供文档入库和语义检索能力（零配置，CPU 嵌入）。
- **VRAMResourceManager** (vram_manager.py): 端侧显存动态调度器，
  管理消费级 GPU 上多模型的加载与卸载生命周期。

所有 Agent 逻辑均为手写实现，不依赖 LangChain/LlamaIndex 等重量级框架。
"""

from src.agent.context_compressor import CompressionResult, ContextCompressor
from src.agent.models import AgentEvent, DocumentInfo, Message, ToolCall
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.rag import RAGStore
from src.agent.tools import ToolRegistry, create_default_registry
from src.agent.vram_manager import ContextRole, MultiplexingScheduler, VRAMResourceManager

# AgentLoop 延迟导入，避免循环依赖和未安装 chromadb 时的导入错误
try:
    from src.agent.agent import AgentLoop
except ImportError:
    pass

__all__ = [
    "AgentEvent",
    "CompressionResult",
    "ContextCompressor",
    "ContextRole",
    "DocumentInfo",
    "Message",
    "MultiplexingScheduler",
    "PromptBuilder",
    "PromptConfig",
    "ToolCall",
    "ToolRegistry",
    "create_default_registry",
    "RAGStore",
    "VRAMResourceManager",
    "AgentLoop",
]
