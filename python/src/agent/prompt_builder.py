"""System Prompt 动态拼装器 — 根据运行上下文构建最优系统提示词。

核心原则：上下文信息密度最大化。不追求 prompt 有多长，
只追求每一个 token 都在为当前决策服务。

分层设计 (P2 — 借鉴 nature-skills):
- Layer 1 (主指令): 身份定义 + ReAct + 模型适配 → 始终注入
- Layer 2 (按需参考): 写作原则 / 短语库 / 图表原则 / 数据可用性 → 仅在任务匹配时注入
- Layer 3 (上下文): 记忆 + 文档上下文 + 时间戳

拼装流程：
1. 身份定义（Agent 角色 + 核心能力描述）
2. 工具指南（从 ToolRegistry 自动提取 + 模型适配指导）
3. 记忆注入（MEMORY.md 长期记忆 + 对话摘要）
4. 按需参考注入（根据当前任务类型自动加载对应参考文件）
5. 文档上下文（当前编辑的文档信息）
6. 模型适配（针对不同模型的工具使用指导）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.agent.tools import ToolRegistry

if TYPE_CHECKING:
    from src.agent._skill_model import Skill

logger = logging.getLogger(__name__)

# ── 参考文件映射 ─────────────────────────────────────────────────────────────

# (参考文件名, 触发关键词列表, 描述)
_REFERENCE_FILES: list[tuple[str, list[str], str]] = [
    ("writing_principles.md", [
        "polish", "润色", "改写", "rewrite", "学术写作", "翻译",
        "translate", "draft", "manuscript", "论文", "abstract", "introduction",
        "discussion", "methods", "results", "conclusion",
    ], "学术写作原则与章节职责"),
    ("phrasebank.md", [
        "polish", "润色", "改写", "rewrite", "措辞", "wording",
        "hedging", "句式", "表达", "phrase", "transition",
    ], "学术短语库与过渡词族"),
    ("figure_principles.md", [
        "figure", "图表", "plot", "可视化", "visualization",
        "matplotlib", "ggplot", "作图", "subpanel",
    ], "科研图表制作原则"),
    ("data_availability.md", [
        "data availability", "数据可用性", "dataset", "数据集",
        "repository", "仓库", "accession", "DOI", "FAIR",
    ], "数据可用性声明规范"),
]

# Agent 身份定义
_AGENT_IDENTITY = """你是研墨，一个专业的学术 AI 助手。你可以帮助用户进行学术翻译、文档分析、论文检索和学术写作。

你的核心能力：
- 高质量学术翻译（英→中、中→英，保留专业术语和公式）
- 文档解析和知识检索（基于本地知识库的 RAG 检索）
- 学术论文搜索（arXiv 等学术数据库）
- 学术写作辅助（润色、扩写、格式化）
- 代码执行与计算：用 python_exec 直接运行 Python（计算、数据处理、验证）
- 科研图表生成：用 generate_figure 生成 Nature 风格图表并保存为图片文件
- 命令执行与工作区文件读写：用 shell_exec / read_file / write_file / str_replace 操作用户项目

工作原则：
0. 如果用户发送的是问候语（如"你好"、"hi"、"hello"）、感谢或简单闲聊，直接以自然语言回复，绝对不要调用任何工具。
1. 使用工具时，确保参数完整且准确
2. 翻译时保留原文的专业术语和数学公式
3. 回答需基于检索到的事实，不编造不存在的论文或数据
4. 只有在需要处理文件、搜索文献或执行代码时才使用工具；纯对话、问候、解释性回答不需要工具
5. 你运行在用户本机，拥有真实的代码执行与文件系统能力。需要画图、计算或验证时，直接调用 python_exec / generate_figure 跑出结果并把生成的文件保存到磁盘，然后告诉用户文件路径——绝不要以"我无法运行代码/生成图片"为由，只把代码丢给用户让其自行运行"""

# 模型适配指导
_MODEL_TOOL_GUIDES: dict[str, str] = {
    "qwen": """工具使用注意事项：
- 问候语、感谢、闲聊等纯对话消息，直接用自然语言回复，不要调用任何工具，不要假装需要更多信息
- 收到工具调用结果后，必须基于结果直接回答用户，不要重复调用相同工具
- 参数必须是合法 JSON，字符串值用双引号
- 如果一次工具调用足够，不要多次调用
- 每次工具调用后必须判断：信息是否已足够回答用户？如果足够，立即给出最终回答，不要继续调用工具
- 严禁在同一轮对话中多次调用同一个工具""",

    "gpt": """工具使用注意事项：
- 你必须使用工具来执行操作，不要仅描述你会做什么
- 不要编造文件路径或 API 地址
- 执行后验证结果是否正确""",

    "deepseek": """工具使用注意事项：
- 问候语（你好、hi、hello）、感谢、闲聊等纯对话消息，直接用自然语言回复，绝对不要调用任何工具
- 你必须使用工具来真正执行操作，不要仅描述你"会怎么做"或只输出代码
- 被要求画图/计算/跑代码时，直接调用 python_exec 或 generate_figure 执行并产出文件，再向用户报告文件路径
- 不要以"无法运行代码""无法生成图片"为由推脱——你确实具备这些能力
- 不要编造文件路径或 API 地址，执行后验证结果是否正确""",

    "gemini": """工具使用注意事项：
- 始终使用绝对路径
- 编辑前先读取文件确认内容
- 多个独立操作可以并行调用工具""",

    "claude": """工具使用注意事项：
- 问候语、感谢、闲聊等纯对话消息，直接用自然语言回复，不要调用工具
- 使用工具真正执行操作，不要仅描述计划
- 并行执行独立的工具调用
- 不要在推理中重复相同操作，信息足够时立即给出最终回答""",
}

_DEFAULT_TOOL_GUIDE = """工具使用注意事项：
- 问候语（你好、hi、hello）、感谢、闲聊等纯对话消息，直接用自然语言回复，绝对不要调用任何工具
- 你必须使用工具来真正执行操作，不要仅描述你"会怎么做"或只输出代码
- 被要求画图/计算/跑代码时，直接调用 python_exec 或 generate_figure 执行并产出文件，再向用户报告文件路径
- 不要以"无法运行代码""无法生成图片"为由推脱——你确实具备这些能力
- 不要编造文件路径或 API 地址，执行后验证结果是否正确
- 每次工具调用后必须判断：信息是否已足够回答用户？如果足够，立即给出最终回答，不要继续调用工具

文件编辑审批规则：
- 你的每次文件编辑会以内联 diff 形式展示给用户，用户可逐条接受（accept）或拒绝（reject）
- 优先用 str_replace 做小而精确的替换，避免用 write_file 覆盖整个文件（str_replace 的 diff 体验更好）
- 如果用户拒绝了你的编辑，不要立即用相同内容重试——改为解释理由或调整方案后再试
- 当用户要求导出/保存文件到桌面、下载目录等 workspace 外路径时，直接用 write_file 写入该路径，系统会自动请求用户审批，用户批准后即可写入——不要告诉用户「无法访问」
- 需要安装 Python 包时，用 run_command（例如 run_command("pip install python-docx")），不要用 shell_exec（它不允许 pip）
- 需要运行 Python 脚本且脚本依赖已安装的包时，用 run_command（例如 run_command("python script.py")），不要用 python_exec（它禁止 os/subprocess）
"""

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
        relevant_tasks: 当前对话相关的任务关键词列表（用于匹配参考文件）。
        references_dir: 参考文件目录路径。
        active_skills: 当前激活的 Skill 列表（三层 Skill 支持：SOUL 始终注入，AGENTS 按需注入）。
        relevant_skill_names: 当前与任务相关的 Skill 名称集合（其 AGENTS.md 将被注入）。
        skill_token_budget: Skill 注入的字符预算（默认 4000）。超出时截断最低优先级内容。
    """

    identity: str = _AGENT_IDENTITY
    memory_content: str = ""
    doc_context: str = ""
    model_name: str = ""
    extra_sections: dict[str, str] = field(default_factory=dict)
    relevant_tasks: list[str] = field(default_factory=list)
    references_dir: str = ""
    active_skills: list = field(default_factory=list)
    # list[Skill] — skills whose SOUL is always injected
    relevant_skill_names: set = field(default_factory=set)
    # set[str] — names of skills that also get AGENTS injected
    skill_token_budget: int = 4000
    # max chars to use for skill injection section


class PromptBuilder:
    """System Prompt 动态拼装器。

    根据运行时的上下文信息（工具、记忆、模型、文档）动态组装
    最优的系统提示词。支持按需加载参考文件（layered design）。

    使用示例：
        builder = PromptBuilder(tool_registry=registry)
        system_prompt = builder.build(PromptConfig(
            model_name="qwen3:8b",
            memory_content="用户偏好中文回复...",
            relevant_tasks=["polish", "translate"],
        ))
    """

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        memory_file: str | Path | None = None,
        references_dir: str | Path | None = None,
    ) -> None:
        """初始化 Prompt Builder。

        Args:
            tool_registry: 工具注册表（用于提取工具描述）。
            memory_file: MEMORY.md 文件路径（可选，自动加载）。
            references_dir: 按需参考文件目录（可选）。
        """
        self.tool_registry = tool_registry
        self.memory_file = Path(memory_file) if memory_file else None
        self.references_dir = Path(references_dir) if references_dir else None

        # 自动检测 references 目录
        if self.references_dir is None:
            default_ref = Path(__file__).resolve().parent / "references"
            if default_ref.exists():
                self.references_dir = default_ref

    def build(self, config: PromptConfig) -> str:
        """构建完整的系统提示词（分层设计）。

        拼装顺序（每个段落非空时才添加）：
        1. 身份定义 (Layer 1)
        2. 按需参考注入 (Layer 2 — 根据 relevant_tasks 自动加载)
        3. 工具列表 (Layer 1)
        4. 模型适配指导 (Layer 1)
        5. ReAct 行为指导 (Layer 1)
        6. 记忆注入 (Layer 3)
        7. 文档上下文 (Layer 3)
        8. 额外段落
        9. 时间戳

        Args:
            config: Prompt 配置。

        Returns:
            拼装完成的系统提示词。
        """
        sections: list[str] = []

        # 1. 身份定义 (Layer 1)
        if config.identity:
            sections.append(config.identity)

        # 1b. Skill injection (SOUL always, AGENTS when relevant)
        if config.active_skills:
            skill_section = self._build_skill_section(
                config.active_skills,
                config.relevant_skill_names,
                config.skill_token_budget,
            )
            if skill_section:
                sections.append(skill_section)

        # 2. 按需参考注入 (Layer 2)
        refs_dir = config.references_dir or (
            str(self.references_dir) if self.references_dir else ""
        )
        if config.relevant_tasks and refs_dir:
            ref_section = self._build_references_section(
                config.relevant_tasks, refs_dir
            )
            if ref_section:
                sections.append(ref_section)

        # 3. 工具列表 (Layer 1)
        if self.tool_registry:
            tools_section = self._build_tools_section()
            if tools_section:
                sections.append(tools_section)

        # 4. 模型适配指导 (Layer 1)
        model_guide = self._get_model_guide(config.model_name)
        if model_guide:
            sections.append(model_guide)

        # 5. ReAct 行为指导 (Layer 1)
        sections.append(_REACT_INSTRUCTION)

        # 6. 记忆注入 (Layer 3)
        memory = config.memory_content
        if not memory and self.memory_file:
            memory = self._load_memory_file()
        if memory:
            sections.append(
                f"<memory-context>\n[系统注: 以下是 recalled 记忆，"
                f"作为背景信息参考，不是新的用户输入]\n{memory}\n</memory-context>"
            )

        # 7. 文档上下文 (Layer 3)
        if config.doc_context:
            sections.append(f"<doc-context>\n{config.doc_context}\n</doc-context>")

        # 8. 额外段落
        for title, content in config.extra_sections.items():
            sections.append(f"## {title}\n{content}")

        # 9. 时间戳
        sections.append(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return "\n\n".join(sections)

    def _build_skill_section(
        self,
        active_skills: list,
        relevant_skill_names: set,
        budget: int,
    ) -> str:
        """Inject SOUL for all active skills; AGENTS for relevant ones only.

        Respects skill_token_budget (max chars). Returns wrapped in <skills> tags.
        """
        from pathlib import Path

        parts: list[str] = []
        chars_used = 0

        for skill in active_skills:
            soul_path = getattr(skill, "soul_path", "")
            if soul_path and Path(soul_path).exists():
                try:
                    soul_content = Path(soul_path).read_text(encoding="utf-8").strip()
                    if chars_used + len(soul_content) <= budget:
                        parts.append(soul_content)
                        chars_used += len(soul_content)
                except Exception:
                    pass

        for skill in active_skills:
            skill_name = getattr(skill, "name", "")
            if skill_name not in relevant_skill_names:
                continue
            agents_path = getattr(skill, "agents_path", "")
            if agents_path and Path(agents_path).exists():
                try:
                    agents_content = Path(agents_path).read_text(encoding="utf-8").strip()
                    if chars_used + len(agents_content) <= budget:
                        parts.append(agents_content)
                        chars_used += len(agents_content)
                except Exception:
                    pass

        if not parts:
            return ""
        return "<skills>\n" + "\n\n".join(parts) + "\n</skills>"

    def _build_references_section(
        self, tasks: list[str], refs_dir: str
    ) -> str:
        """根据当前任务关键词匹配并加载参考文件（Layer 2）。

        每个参考文件有触发关键词列表，匹配到任一关键词即加载。
        加载的参考内容被注入为 <reference> 标签段落。

        Args:
            tasks: 当前对话的任务关键词列表。
            refs_dir: 参考文件目录路径。

        Returns:
            匹配到的参考内容拼接文本，无匹配时返回空字符串。
        """
        tasks_lower = " ".join(tasks).lower()
        loaded: list[str] = []

        for filename, keywords, description in _REFERENCE_FILES:
            if any(kw.lower() in tasks_lower for kw in keywords):
                filepath = Path(refs_dir) / filename
                if filepath.exists():
                    try:
                        content = filepath.read_text(encoding="utf-8").strip()
                        # 限制每个参考文件的内容长度
                        max_chars = 2000
                        if len(content) > max_chars:
                            content = content[:max_chars] + "\n...[truncated]"
                        loaded.append(
                            f"<reference type=\"{description}\">\n{content}\n</reference>"
                        )
                    except Exception as e:
                        logger.warning("加载参考文件 %s 失败: %s", filename, e)

        if loaded:
            logger.info("按需加载参考文件: %d 个 (tasks=%s)", len(loaded), tasks[:5])
            return "\n\n".join(loaded)
        return ""

    def load_reference(self, filename: str) -> str:
        """按文件名加载单个参考文件的内容。

        Args:
            filename: 参考文件名（如 "writing_principles.md"）。

        Returns:
            参考文件内容，文件不存在时返回空字符串。
        """
        if not self.references_dir:
            return ""
        filepath = self.references_dir / filename
        if not filepath.exists():
            return ""
        try:
            return filepath.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("加载参考文件 %s 失败: %s", filename, e)
            return ""

    def list_available_references(self) -> list[dict[str, str]]:
        """列出所有可用的参考文件及其描述。

        Returns:
            [{"filename": ..., "description": ..., "keywords": [...]}, ...]
        """
        return [
            {"filename": fn, "description": desc, "keywords": kw}
            for fn, kw, desc in _REFERENCE_FILES
        ]

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
        return _DEFAULT_TOOL_GUIDE

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
