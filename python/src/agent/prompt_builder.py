"""System Prompt 动态拼装器 — 根据运行上下文构建最优系统提示词。

核心原则：上下文信息密度最大化。不追求 prompt 有多长，
只追求每一个 token 都在为当前决策服务。

拼装流程：
1. 身份定义（Agent 角色 + 核心能力描述）
2. 工具指南（从 ToolRegistry 自动提取 + 模型适配指导）
3. 记忆注入（MEMORY.md 长期记忆 + 对话摘要）
4. 文档上下文（当前编辑的文档信息）
5. 模型适配（针对不同模型的工具使用指导）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.tools import ToolRegistry

logger = logging.getLogger(__name__)

# Agent 身份定义
_AGENT_IDENTITY = """你是研墨，一个专业的学术 AI 助手。你可以帮助用户进行学术翻译、文档分析、论文检索和学术写作。

你的核心能力：
- 高质量学术翻译（英→中、中→英，保留专业术语和公式）
- 文档解析和知识检索（基于本地知识库的 RAG 检索）
- 学术论文搜索（arXiv 等学术数据库）
- 学术写作辅助（润色、扩写、格式化）

工作原则：
1. 使用工具时，确保参数完整且准确
2. 翻译时保留原文的专业术语和数学公式
3. 回答需基于检索到的事实，不编造不存在的论文或数据
4. 如果信息不足，主动使用检索工具获取，而非猜测"""

# 模型适配指导
_MODEL_TOOL_GUIDES: dict[str, str] = {
    "qwen": """工具使用注意事项：
- 收到工具调用结果后，必须基于结果直接回答用户，不要重复调用相同工具
- 参数必须是合法 JSON，字符串值用双引号
- 如果一次工具调用足够，不要多次调用
- 每次工具调用后必须判断：信息是否已足够回答用户？如果足够，立即给出最终回答，不要继续调用工具
- 严禁在同一轮对话中多次调用同一个工具""",

    "gpt": """工具使用注意事项：
- 你必须使用工具来执行操作，不要仅描述你会做什么
- 不要编造文件路径或 API 地址
- 执行后验证结果是否正确""",

    "gemini": """工具使用注意事项：
- 始终使用绝对路径
- 编辑前先读取文件确认内容
- 多个独立操作可以并行调用工具""",
}

# ReAct 行为指导
_REACT_INSTRUCTION = """推理模式：使用 ReAct（推理 + 行动）模式工作。
每一步：
1. 思考：分析当前状态，决定下一步
2. 行动：调用合适的工具（如果需要）
3. 观察：分析工具返回的结果

重要：当收集到足够信息后，立即以纯文本形式给出最终回答，不要再调用任何工具。
如果工具结果已经包含回答所需的信息，直接整理后回复用户。"""


@dataclass
class PromptConfig:
    """Prompt 拼装配置。

    Attributes:
        identity: Agent 身份定义文本。
        memory_content: 从 MEMORY.md 加载的长期记忆内容。
        doc_context: 当前编辑文档的上下文信息。
        model_name: 当前使用的模型名称（用于模型适配）。
        extra_sections: 额外的自定义段落。
    """

    identity: str = _AGENT_IDENTITY
    memory_content: str = ""
    doc_context: str = ""
    model_name: str = ""
    extra_sections: dict[str, str] = field(default_factory=dict)


class PromptBuilder:
    """System Prompt 动态拼装器。

    根据运行时的上下文信息（工具、记忆、模型、文档）动态组装
    最优的系统提示词。避免静态的超长 prompt 浪费 token。

    使用示例：
        builder = PromptBuilder(tool_registry=registry)
        system_prompt = builder.build(PromptConfig(
            model_name="qwen3:8b",
            memory_content="用户偏好中文回复...",
        ))
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        memory_file: str | Path | None = None,
    ) -> None:
        """初始化 Prompt Builder。

        Args:
            tool_registry: 工具注册表（用于提取工具描述）。
            memory_file: MEMORY.md 文件路径（可选，自动加载）。
        """
        self.tool_registry = tool_registry
        self.memory_file = Path(memory_file) if memory_file else None

    def build(self, config: PromptConfig) -> str:
        """构建完整的系统提示词。

        拼装顺序（每个段落非空时才添加）：
        1. 身份定义
        2. 工具列表
        3. 模型适配指导
        4. ReAct 行为指导
        5. 记忆注入
        6. 文档上下文
        7. 额外段落
        8. 时间戳

        Args:
            config: Prompt 配置。

        Returns:
            拼装完成的系统提示词。
        """
        sections: list[str] = []

        # 1. 身份定义
        if config.identity:
            sections.append(config.identity)

        # 2. 工具列表
        if self.tool_registry:
            tools_section = self._build_tools_section()
            if tools_section:
                sections.append(tools_section)

        # 3. 模型适配指导
        model_guide = self._get_model_guide(config.model_name)
        if model_guide:
            sections.append(model_guide)

        # 4. ReAct 行为指导
        sections.append(_REACT_INSTRUCTION)

        # 5. 记忆注入
        memory = config.memory_content
        if not memory and self.memory_file:
            memory = self._load_memory_file()
        if memory:
            sections.append(
                f"<memory-context>\n[系统注: 以下是 recalled 记忆，"
                f"作为背景信息参考，不是新的用户输入]\n{memory}\n</memory-context>"
            )

        # 6. 文档上下文
        if config.doc_context:
            sections.append(f"<doc-context>\n{config.doc_context}\n</doc-context>")

        # 7. 额外段落
        for title, content in config.extra_sections.items():
            sections.append(f"## {title}\n{content}")

        # 8. 时间戳
        sections.append(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return "\n\n".join(sections)

    def _build_tools_section(self) -> str:
        """从 ToolRegistry 自动构建工具描述段落。

        Returns:
            工具描述文本，无工具时返回空字符串。
        """
        if not self.tool_registry:
            return ""

        tools = self.tool_registry.list_tools()
        if not tools:
            return ""

        lines = ["可用工具列表："]
        for t in tools:
            # 提取参数摘要
            params = t.parameters.get("properties", {})
            required = t.parameters.get("required", [])
            param_strs: list[str] = []
            for pname, pdef in params.items():
                ptype = pdef.get("type", "string")
                req_mark = "" if pname in required else "(可选)"
                param_strs.append(f"{pname}: {ptype}{req_mark}")

            param_info = ", ".join(param_strs) if param_strs else "无参数"
            lines.append(f"- {t.name}({param_info}): {t.description}")

        lines.append("\n使用工具时，在 function call 中提供正确的工具名和参数。")
        return "\n".join(lines)

    def _get_model_guide(self, model_name: str) -> str:
        """根据模型名称返回对应的工具使用指导。

        Args:
            model_name: 模型名称（如 "qwen3:8b", "gpt-4o"）。

        Returns:
            模型适配指导文本，无匹配时返回空字符串。
        """
        if not model_name:
            return ""

        model_lower = model_name.lower()
        for key, guide in _MODEL_TOOL_GUIDES.items():
            if key in model_lower:
                return guide
        return ""

    def _load_memory_file(self) -> str:
        """从 MEMORY.md 文件加载长期记忆。

        Returns:
            记忆内容文本，文件不存在时返回空字符串。
        """
        if not self.memory_file or not self.memory_file.exists():
            return ""

        try:
            content = self.memory_file.read_text(encoding="utf-8").strip()
            # 限制大小，防止记忆文件过大占用过多 token
            max_chars = 3000
            if len(content) > max_chars:
                content = content[:max_chars] + "\n...[记忆已截断]"
            return content
        except Exception as e:
            logger.warning("加载 MEMORY.md 失败: %s", e)
            return ""

    def estimate_prompt_tokens(self, config: PromptConfig) -> int:
        """估算构建出的 prompt 大约占用多少 token。

        用于在构建前判断是否需要调整配置（如裁剪记忆内容）。

        Args:
            config: Prompt 配置。

        Returns:
            估算的 token 数。
        """
        text = self.build(config)
        return max(1, int(len(text) / _CHARS_PER_TOKEN))


# Token 估算用字符系数
_CHARS_PER_TOKEN: float = 2.5
