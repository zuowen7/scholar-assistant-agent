"""后台审查 Agent — 任务完成后异步审查对话，沉淀记忆和 Skill。

设计参考 Hermes Agent 的"前台即时响应、后台异步进化"模式：
- 用户看到 Agent 秒回，背后审查 Agent 慢慢整理经验
- 三个维度审查：记忆审查、Skill 审查、综合审查
- 审查结果写入 MemoryManager 和 SkillRegistry
"""

from __future__ import annotations

import asyncio
import logging
import json
import re
from typing import Any

from src.agent.llm_client import LLMClient
from src.agent.models import Message

logger = logging.getLogger(__name__)

_MEMORY_REVIEW_PROMPT = """分析以下对话，提取值得长期记住的关键经验或事实。
只提取具有长期价值的通用性经验，不要提取临时性信息。
每条经验必须满足以下条件之一：
- 涉及工具使用技巧或常见陷阱
- 涉及用户偏好或项目约束
- 涉及特定领域的通用方法论
不要提取任务本身的细节、临时数值、或任何仅对本次任务有意义的内容。
每条经验用一行表示，格式为: - 经验内容

对话内容:
{conversation}

值得记住的经验:"""

_SKILL_REVIEW_PROMPT = """分析以下任务执行过程，判断是否值得固化为一个可复用的 Skill。

严格判断标准（必须全部满足）：
1. 任务涉及 3 个以上明确的步骤（不是简单的单步操作）
2. 步骤有固定的执行顺序，且每步的结果对下一步有依赖
3. 触发条件清晰可描述，不是泛化的"帮助用户"
4. 未来很可能遇到高度类似的任务

如果全部满足，输出以下格式的 JSON：
{{"should_create": true, "name": "skill_name", "trigger": "触发条件（含具体关键词）", "description": "描述（一句话概括做什么）", "steps": ["步骤1", "步骤2"], "notes": ["注意事项"]}}

如果不满足任一条件，输出：
{{"should_create": false}}

任务过程:
{conversation}"""

_COMBINED_REVIEW_PROMPT = """回顾以下任务执行过程，仅提取一个最重要的改进建议。
格式：一句话，以"改进:"开头。不要罗列多条，不要复述任务内容。
如果任务执行顺利无明显改进空间，直接输出"无"。

任务过程:
{conversation}

反思:"""


class ReviewAgent:
    """后台审查 Agent。

    在主 Agent 完成任务后异步启动，对对话进行三个维度的审查。
    不阻塞前台响应，不影响用户体验。

    Attributes:
        ollama_base_url: Ollama API 地址。
        model: 使用的模型名称。
        memory_manager: 记忆管理器。
        skill_registry: Skill 注册表。
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        memory_manager: Any | None = None,
        skill_registry: Any | None = None,
        cloud_base_url: str = "",
        cloud_api_key: str = "",
        cloud_model: str = "",
        api_format: str = "openai",
    ) -> None:
        self.memory_manager = memory_manager
        self.skill_registry = skill_registry
        self.llm = LLMClient(
            ollama_base_url=ollama_base_url,
            model=model,
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
            api_format=api_format,
            temperature=0.1,
            num_predict=1024,
        )

    async def close(self) -> None:
        await self.llm.close()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def spawn_review(self, trajectory_data: dict) -> asyncio.Task | None:
        """异步启动后台审查（不阻塞前台）。

        Args:
            trajectory_data: 任务轨迹数据。

        Returns:
            asyncio.Task 或 None（无运行中的事件循环时）。
        """
        try:
            loop = asyncio.get_running_loop()
            return loop.create_task(self._review(trajectory_data))
        except RuntimeError:
            logger.warning("无法获取事件循环，跳过后台审查")
            return None

    async def _review(self, trajectory_data: dict) -> None:
        """执行三维度审查。

        Args:
            trajectory_data: 任务轨迹数据。
        """
        conversations = trajectory_data.get("conversations", [])
        conv_text = self._format_conversations(conversations)

        if not conv_text:
            return

        # 1. 记忆审查
        await self._memory_review(conv_text)

        # 2. Skill 审查
        await self._skill_review(conv_text, trajectory_data)

        # 3. 综合审查
        await self._combined_review(conv_text)

        logger.info("后台审查完成")

    # ------------------------------------------------------------------
    # 三维度审查
    # ------------------------------------------------------------------

    async def _memory_review(self, conv_text: str) -> None:
        """记忆审查：提取值得记住的经验。

        Args:
            conv_text: 格式化的对话文本。
        """
        if not self.memory_manager:
            return

        prompt = _MEMORY_REVIEW_PROMPT.format(conversation=conv_text)
        result = await self.llm.call_simple([Message(role="user", content=prompt)])

        if result:
            experiences = [line.strip().lstrip("- ") for line in result.split("\n") if line.strip().startswith("-")]
            # Quality gate: skip short, vague, or overly generic entries
            _vague_patterns = {"无", "不适用", "none", "n/a", "暂无", "无特别"}
            added = 0
            for exp in experiences:
                if len(exp) < 15 or len(exp) > 500:
                    continue
                if exp.lower().strip() in _vague_patterns:
                    continue
                self.memory_manager.add_memory(
                    content=exp,
                    category="experience",
                    source="review",
                    importance=0.6,
                )
                added += 1
                if added >= 3:  # cap per review to prevent memory flooding
                    break
            logger.info("记忆审查: 提取了 %d/%d 条经验", added, len(experiences))

    async def _skill_review(self, conv_text: str, trajectory_data: dict) -> None:
        """Skill 审查：判断任务模式是否值得固化为 Skill。

        Args:
            conv_text: 格式化的对话文本。
            trajectory_data: 原始轨迹数据。
        """
        if not self.skill_registry:
            return

        prompt = _SKILL_REVIEW_PROMPT.format(conversation=conv_text)
        result = await self.llm.call_simple([Message(role="user", content=prompt)])

        if result:
            try:
                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    if data.get("should_create") and self.skill_registry:
                        # Quality gate: validate minimum field quality
                        name = data.get("name", "").strip()
                        trigger = data.get("trigger", "").strip()
                        steps = data.get("steps", [])
                        if not name or not trigger or len(steps) < 2:
                            logger.info("Skill 审查: 质量不足，跳过 (name=%s, trigger=%s, steps=%d)",
                                        name[:20], trigger[:20], len(steps))
                            return
                        # Prevent duplicate skill names
                        if self.skill_registry.get(name):
                            logger.info("Skill 审查: 同名 Skill 已存在，跳过: %s", name)
                            return
                        self.skill_registry.create_skill(
                            name=name,
                            trigger=trigger,
                            description=data.get("description", ""),
                            steps=steps,
                            notes=data.get("notes", []),
                        )
                        logger.info("Skill 审查: 创建了新 Skill: %s", name)
            except Exception as e:
                logger.warning("Skill 审查解析失败: %s", e)

    async def _combined_review(self, conv_text: str) -> None:
        """综合审查：提取一条最重要的改进建议。

        Args:
            conv_text: 格式化的对话文本。
        """
        if not self.memory_manager:
            return

        prompt = _COMBINED_REVIEW_PROMPT.format(conversation=conv_text)
        result = await self.llm.call_simple([Message(role="user", content=prompt)])

        if result and result.strip() != "无" and len(result) > 10:
            self.memory_manager.add_memory(
                content=f"[改进建议] {result[:300]}",
                category="experience",
                source="review",
                importance=0.4,
            )
            logger.info("综合审查: 保存了改进建议")

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _format_conversations(self, conversations: list[dict]) -> str:
        """将 ShareGPT 格式的对话列表格式化为文本。

        Args:
            conversations: ShareGPT 格式对话列表。

        Returns:
            格式化后的文本。
        """
        role_names = {
            "system": "系统",
            "human": "用户",
            "gpt": "助手",
            "tool": "工具",
        }
        parts: list[str] = []
        for conv in conversations:
            role = role_names.get(conv.get("from", ""), conv.get("from", ""))
            value = conv.get("value", "")
            if value:
                parts.append(f"{role}: {value[:500]}")
        return "\n".join(parts)

