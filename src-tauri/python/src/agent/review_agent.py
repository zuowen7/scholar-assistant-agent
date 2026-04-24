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

import httpx

logger = logging.getLogger(__name__)

_MEMORY_REVIEW_PROMPT = """分析以下对话，提取值得长期记住的关键经验或事实。
只提取具有长期价值的通用性经验，不要提取临时性信息。
每条经验用一行表示，格式为: - 经验内容

对话内容:
{conversation}

值得记住的经验:"""

_SKILL_REVIEW_PROMPT = """分析以下任务执行过程，判断是否值得固化为一个可复用的 Skill。

判断标准：
1. 任务涉及 2 个以上步骤
2. 步骤有固定的执行顺序
3. 未来可能遇到类似的任务

如果值得创建 Skill，输出以下格式的 JSON（不要其他内容）：
{{"should_create": true, "name": "skill_name", "trigger": "触发条件", "description": "描述", "steps": ["步骤1", "步骤2"], "notes": ["注意事项"]}}

如果不值得创建，输出：
{{"should_create": false}}

任务过程:
{conversation}"""

_COMBINED_REVIEW_PROMPT = """请用简洁的中文回顾以下任务执行过程，回答两个问题：
1. 有什么可以改进的地方？
2. 有什么错误需要避免？

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
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.memory_manager = memory_manager
        self.skill_registry = skill_registry
        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format
        self._http_client: httpx.AsyncClient | None = None

    @property
    def _use_cloud(self) -> bool:
        return bool(self.cloud_api_key and self.cloud_base_url)

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0))
        return self._http_client

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def spawn_review(self, trajectory_data: dict) -> asyncio.Task | None:
        """异步启动后台审查（不阻塞前台）。

        Args:
            trajectory_data: 任务轨迹数据。

        Returns:
            asyncio.Task 或 None（无事件循环时）。
        """
        try:
            loop = asyncio.get_event_loop()
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
        result = await self._call_llm(prompt)

        if result:
            # 解析提取的经验
            experiences = [line.strip().lstrip("- ") for line in result.split("\n") if line.strip().startswith("-")]
            for exp in experiences:
                if len(exp) > 10:  # 过滤过短的
                    self.memory_manager.add_memory(
                        content=exp,
                        category="experience",
                        source="review",
                        importance=0.6,
                    )
            logger.info("记忆审查: 提取了 %d 条经验", len(experiences))

    async def _skill_review(self, conv_text: str, trajectory_data: dict) -> None:
        """Skill 审查：判断任务模式是否值得固化为 Skill。

        Args:
            conv_text: 格式化的对话文本。
            trajectory_data: 原始轨迹数据。
        """
        if not self.skill_registry:
            return

        prompt = _SKILL_REVIEW_PROMPT.format(conversation=conv_text)
        result = await self._call_llm(prompt)

        if result:
            try:
                # 尝试解析 JSON
                json_match = re.search(r"\{.*\}", result, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    if data.get("should_create") and self.skill_registry:
                        self.skill_registry.create_skill(
                            name=data.get("name", f"skill_{hash(conv_text) % 10000}"),
                            trigger=data.get("trigger", ""),
                            description=data.get("description", ""),
                            steps=data.get("steps", []),
                            notes=data.get("notes", []),
                        )
                        logger.info("Skill 审查: 创建了新 Skill")
            except Exception as e:
                logger.warning("Skill 审查解析失败: %s", e)

    async def _combined_review(self, conv_text: str) -> None:
        """综合审查：反思优化空间。

        Args:
            conv_text: 格式化的对话文本。
        """
        if not self.memory_manager:
            return

        prompt = _COMBINED_REVIEW_PROMPT.format(conversation=conv_text)
        result = await self._call_llm(prompt)

        if result and len(result) > 20:
            self.memory_manager.add_memory(
                content=f"[反思] {result[:300]}",
                category="experience",
                source="review",
                importance=0.4,
            )
            logger.info("综合审查: 保存了反思记录")

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

    async def _call_llm(self, prompt: str) -> str | None:
        """调用 LLM 生成审查结果，支持 Ollama 和云端 API。

        Args:
            prompt: 审查提示词。

        Returns:
            LLM 响应文本，失败时返回 None。
        """
        try:
            client = await self._get_http_client()
            messages = [{"role": "user", "content": prompt}]

            if self._use_cloud:
                openai_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.cloud_api_key}"}
                endpoint = f"{self.cloud_base_url}/chat/completions"
                resp = await client.post(
                    endpoint,
                    json={
                        "model": self.cloud_model or self.model,
                        "messages": openai_messages,
                        "temperature": 0.1,
                        "max_tokens": 1024,
                        "stream": False,
                    },
                    headers=headers,
                )
            else:
                resp = await client.post(
                    f"{self.ollama_base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 1024},
                    },
                )

            resp.raise_for_status()
            data = resp.json()

            if self._use_cloud:
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            else:
                content = data.get("message", {}).get("content", "").strip()

            content = re.sub(r"<think?>.*?</think?>", "", content, flags=re.DOTALL).strip()
            return content if content else None
        except Exception as e:
            logger.warning("审查 LLM 调用失败: %s", e)
            return None
