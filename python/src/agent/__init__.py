"""Agent 子系统 — ReAct 推理循环 + 上下文工程 + 记忆 + Skill 自进化 + RAG。

核心推理:
- **AgentLoop** (agent.py): ReAct 推理循环，双策略工具调用，轨迹记录
- **ContextCompressor** (context_compressor.py): 比例阈值压缩器
- **PromptBuilder** (prompt_builder.py): System Prompt 动态拼装

记忆与自进化:
- **MemoryManager** (memory.py): MEMORY.md + SQLite 双层持久化记忆
- **SkillRegistry** (skill_system.py): 动态 Skill 系统，经验沉淀与复用
- **TrajectoryRecorder** (trajectory.py): ReAct 轨迹记录器
- **ReviewAgent** (review_agent.py): 后台审查 Agent，记忆+Skill 异步沉淀

工具与资源:
- **ToolRegistry** (tools.py): 工具注册表与 @tool 装饰器
- **RAGStore** (rag.py): ChromaDB 文档检索存储

所有 Agent 逻辑均为手写实现，不依赖 LangChain/LlamaIndex 等重量级框架。
"""

from src.agent.context_compressor import CompressionResult, ContextCompressor
from src.agent.error_classifier import ErrorType, RecoveryAction, RetryManager, classify_error, get_recovery
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.llm_client import LLMClient, TokenUsage
from src.agent.memory import MemoryManager, MemoryEntry
from src.agent.models import AgentEvent, DocumentInfo, Message, ToolCall
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.rag import RAGStore
from src.agent.review_agent import ReviewAgent
from src.agent.skill_system import Skill, SkillRegistry
from src.agent.tools import ToolRegistry, create_default_registry
from src.agent.trajectory import Trajectory, TrajectoryRecorder, TrajectoryTurn

# AgentLoop 延迟导入，避免循环依赖
try:
    from src.agent.agent import AgentLoop
except ImportError:
    pass

__all__ = [
    "AgentEvent",
    "AgentLoop",
    "CompressionResult",
    "ContextCompressor",
    "DocumentInfo",
    "ErrorType",
    "HookContext",
    "HookManager",
    "HookPoint",
    "LLMClient",
    "MemoryEntry",
    "MemoryManager",
    "Message",
    "PromptBuilder",
    "PromptConfig",
    "RAGStore",
    "RecoveryAction",
    "ReviewAgent",
    "RetryManager",
    "Skill",
    "SkillRegistry",
    "TokenUsage",
    "ToolCall",
    "ToolRegistry",
    "Trajectory",
    "TrajectoryRecorder",
    "TrajectoryTurn",
    "create_default_registry",
]
