"""ReAct 推理循环引擎 — Agent 子系统的核心决策模块。

本模块实现了基于 ReAct (Reasoning + Acting) 模式的 Agent 推理循环，
是连接 LLM 推理能力与工具执行能力的核心调度器。

架构设计:

    ┌──────────────────────────────────────────────┐
    │               AgentLoop                      │
    │                                              │
    │  User Query ──▶ [System Prompt]              │
    │                  [History Messages]           │
    │                  [Tool Definitions]           │
    │                       │                      │
    │                  ┌────▼─────┐                │
    │                  │ LLM 推理  │ ← Ollama API   │
    │                  └────┬─────┘                │
    │                       │                      │
    │            ┌──────────┼──────────┐           │
    │            ▼                     ▼           │
    │    [Tool Calls]           [Final Answer]     │
    │    [Execute]              [Yield Response]  │
    │    [Observation]                             │
    │         │                                    │
    │         └──▶ 回到 LLM 推理 ◀──┘              │
    └──────────────────────────────────────────────┘

双策略工具调用机制:
1. **主策略 (Native Tool Calling)**: 利用 Ollama /api/chat 的 tools 参数，
   由 LLM 原生生成结构化的工具调用请求。Qwen3 系列模型已支持此功能。
2. **降级策略 (Text ReAct)**: 通过文本模式匹配解析 LLM 输出中的
   Thought / Action / Action Input 标记。适用于不支持原生 tool calling 的模型。

错误恢复策略:
- 工具参数解析失败 → 将错误信息作为 Observation 反馈给 LLM，继续推理。
- LLM 调用不存在的工具 → 反馈工具不存在信息，引导 LLM 选择正确的工具。
- 超过最大推理步数 (MAX_STEPS) → 终止循环，返回错误事件。
- Ollama 连接失败 → 不可恢复错误，终止循环。

SSE 流式事件:
Agent 的 run() 方法返回 AsyncGenerator[AgentEvent]，每个事件对应推理过程的
一个阶段 (thinking / tool_call / tool_result / response / error)。
该格式与 api_factory.py 的 EventSourceResponse 完全兼容。

版权声明: 本模块属于 Scholar Assistant Agent 子系统，
ReAct 推理循环与双策略工具调用机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator

import httpx

from src.agent.context_compressor import ContextCompressor
from src.agent.error_classifier import ErrorType, classify_error, get_recovery, RetryManager
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.memory import AgentMemory, MemoryManager
from src.agent.models import AgentEvent, Message, ToolCall, message_to_ollama_dict
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.review_agent import ReviewAgent
from src.agent.skill_system import SkillRegistry
from src.agent.tool_generator import ToolGenerator, create_tool_generator
from src.agent.tools import ToolRegistry
from src.agent.trajectory import TrajectoryRecorder
from src.agent.vram_manager import ContextRole, MultiplexingScheduler

logger = logging.getLogger(__name__)

# 最大 ReAct 推理步数，防止无限循环
MAX_STEPS = 10

# 对话历史中保留的最大轮数（超出截断最旧的轮次）
_MAX_HISTORY_TURNS = 10

# 工具执行结果的最大字符长度
_TOOL_RESULT_MAX_CHARS = 4000


class AgentLoop:
    """ReAct 模式 Agent 推理循环引擎。

    双策略工具调用:
    1. 主策略: Ollama 原生 tool calling (/api/chat + tools 参数)
    2. 降级策略: 文本 ReAct (Thought/Action/Observation 解析)

    适用于 Qwen3:8B 等支持 tool calling 的模型，
    以及未来可能接入的不支持 tool calling 的模型。

    Attributes:
        ollama_base_url: Ollama REST API 地址。
        model: 使用的 LLM 模型名称。
        tool_registry: 工具注册表，提供可用工具定义和执行能力。
        scheduler: 时分复用调度器（可选），管理模型加载/卸载和角色切换。
        max_steps: 单次推理的最大 ReAct 循环步数。
        system_prompt: 系统提示词，定义 Agent 的行为约束和可用能力。
        temperature: LLM 生成温度。
        num_predict: 最大生成 token 数。
        timeout: HTTP 请求超时秒数。
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        tool_registry: ToolRegistry | None = None,
        scheduler: MultiplexingScheduler | None = None,
        max_steps: int = MAX_STEPS,
        system_prompt: str = "",
        temperature: float = 0.3,
        num_predict: int = 4096,
        timeout: float = 300.0,
        # Phase 1/2/3 模块
        context_compressor: ContextCompressor | None = None,
        prompt_builder: PromptBuilder | None = None,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
        trajectory_recorder: TrajectoryRecorder | None = None,
        rag_store: Any | None = None,
        # 云端 API 配置（可选）
        cloud_base_url: str = "",
        cloud_api_key: str = "",
        cloud_model: str = "",
        api_format: str = "openai",
        # 长期记忆持久化目录（可选）
        memory_dir: str = "",
    ) -> None:
        """初始化 Agent 推理循环引擎。

        Args:
            ollama_base_url: Ollama 服务地址。
            model: LLM 模型名称。
            tool_registry: 工具注册表实例。
            scheduler: 时分复用调度器实例（可选）。
            max_steps: 最大推理步数。
            system_prompt: 系统提示词（向后兼容，优先级低于 PromptBuilder）。
            temperature: 生成温度。
            num_predict: 最大生成 token 数。
            timeout: HTTP 超时秒数。
            context_compressor: 上下文压缩器（可选，默认自动创建）。
            prompt_builder: Prompt 拼装器（可选，默认自动创建）。
            memory_manager: 记忆管理器（可选，默认自动创建）。
            skill_registry: Skill 注册表（可选，默认自动创建）。
            trajectory_recorder: 轨迹记录器（可选，默认自动创建）。
            rag_store: RAG 向量存储实例（可选，启用自动上下文注入）。
            cloud_base_url: 云端 API 地址。
            cloud_api_key: 云端 API Key。
            cloud_model: 云端模型名称。
            api_format: 云端 API 格式，"openai" 或 "anthropic"。
            memory_dir: 记忆持久化目录。
        """
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.tool_registry = tool_registry or ToolRegistry()
        self.scheduler = scheduler
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout = timeout

        # Phase 1: 上下文工程
        self.compressor = context_compressor or ContextCompressor(
            ollama_base_url=self.ollama_base_url,
            summary_model=model,
        )
        self.prompt_builder = prompt_builder or PromptBuilder(
            tool_registry=self.tool_registry,
        )

        # Phase 2: 记忆 + Skill + 轨迹
        self.memory = memory_manager or MemoryManager()
        self.skills = skill_registry or SkillRegistry()
        self.trajectory_recorder = trajectory_recorder or TrajectoryRecorder()
        self.reviewer = ReviewAgent(
            ollama_base_url=self.ollama_base_url,
            model=model,
            memory_manager=self.memory,
            skill_registry=self.skills,
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
            api_format=api_format,
        )

        # Phase 3: 错误恢复 + Hook
        self.retry_manager = RetryManager()
        self.hooks = HookManager()

        # 云端 API 配置（提供后优先使用云端）
        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format  # "openai" or "anthropic"

        # 长期记忆管理器（文件持久化）
        self._memory = AgentMemory(persist_dir=memory_dir) if memory_dir else None

        # RAG 自动注入
        self.rag_store = rag_store

        # 自适应工具生成器
        self._tool_generator = create_tool_generator(self.tool_registry)

        # Token 用量追踪
        self._token_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_calls": 0,
        }

        self._http_client: httpx.AsyncClient | None = None

    @property
    def _use_cloud(self) -> bool:
        """是否使用云端 API。"""
        return bool(self.cloud_api_key and self.cloud_base_url)

    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取异步 HTTP 客户端（懒加载复用）。"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        """关闭底层资源。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
        if self.scheduler is not None:
            await self.scheduler.close()
        await self.compressor.close()
        await self.reviewer.close()

    async def run(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行 ReAct 推理循环，流式返回事件。

        推理流程:
        1. 构建初始消息列表 (system + history + user query)。
        2. 如果配置了调度器，确保 Agent 模型已加载到显存。
        3. 进入 ReAct 循环:
           a. 调用 LLM API (附带工具定义)。
           b. 解析响应:
              - 包含 tool_calls → 执行工具 → yield 事件 → 回到步骤 a。
              - 无 tool_calls → 最终回答 → yield response 事件 → 结束。
        4. 对于重 IO 工具 (translate_text, parse_document)，执行上下文隔离:
           a. 保存规划者上下文快照。
           b. 切换到 ACTOR 角色 (flush KV Cache)。
           c. 执行工具。
           d. 切换回 PLANNER 角色 (flush KV Cache)。
           e. 恢复规划者上下文 + 注入压缩后的观测值。
        5. 每次调用 LLM 前主动裁剪上下文，防止超出 token 预算。
        6. 超过 max_steps → yield error 事件 → 结束。

        Args:
            query: 用户输入的查询或指令。
            history: 之前的对话历史（用于多轮对话上下文）。

        Yields:
            AgentEvent 实例，包含推理过程的中间状态或最终结果。
        """
        # 重试计数器 per-session 重置
        self.retry_manager.reset()

        # 重置 token 用量追踪
        self._token_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_calls": 0,
        }

        # 开始轨迹记录
        self.trajectory_recorder.start(query, model=self.model)

        # 构建消息列表
        messages = self._build_messages(query, history)

        # Plan-and-Execute: 对复杂查询先生成执行计划
        plan = await self._generate_plan(query, messages)
        if plan:
            yield AgentEvent(type="thinking", content=f"执行计划:\n{plan}")
            messages.append(Message(
                role="system",
                content=f"以下是为你制定的执行计划，请按步骤执行:\n\n{plan}",
            ))

        # 调度器: 确保 Agent 模型已加载到显存
        if self.scheduler is not None:
            yield AgentEvent(type="thinking", content="正在加载推理模型...")
            try:
                await self.scheduler.ensure_model()
                self.scheduler.enter_role(ContextRole.PLANNER)
            except Exception as e:
                yield AgentEvent(type="error", content=f"模型加载失败: {e}")
                return

        try:
            # ReAct 主循环
            for step in range(1, self.max_steps + 1):
                logger.info("ReAct 步骤 %d/%d", step, self.max_steps)

                # 主动上下文压缩：比例阈值 + 头尾保护 + 中间摘要
                ollama_dicts = [message_to_ollama_dict(m) for m in messages]
                # Hook: on_pre_compress
                await self.hooks.trigger(HookContext(
                    point=HookPoint.ON_PRE_COMPRESS,
                    data={"message_count": len(ollama_dicts), "step": step},
                ))
                compression = await self.compressor.compress(ollama_dicts)
                if compression.was_compressed:
                    # Hook: on_post_compress
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_POST_COMPRESS,
                        data={
                            "original_tokens": compression.original_tokens,
                            "compressed_tokens": compression.compressed_tokens,
                        },
                    ))
                    messages = self._rebuild_messages_from_dicts(compression.messages)
                    logger.info(
                        "上下文已压缩: %d → %d 条消息, %d → %d tokens",
                        compression.original_count, compression.compressed_count,
                        compression.original_tokens, compression.compressed_tokens,
                    )

                # 调用 LLM（流式输出）
                try:
                    # Hook: on_llm_call
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_CALL,
                        data={"step": step, "message_count": len(messages)},
                    ))
                    response = None
                    async for token_event, full_response in self._call_llm_streaming(messages):
                        if token_event is not None:
                            yield token_event
                        if full_response is not None:
                            response = full_response
                    if response is None:
                        raise ValueError("LLM 流式响应未返回完整结果")
                    self._accumulate_token_usage(response)
                    # Hook: on_llm_response
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_RESPONSE,
                        data={"step": step},
                    ))
                except Exception as e:
                    error_type = classify_error(e)
                    recovery = get_recovery(error_type)

                    # Hook: on_error
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_ERROR,
                        data={"error_type": error_type.value, "error": str(e), "step": step},
                    ))

                    # CONTEXT_OVERFLOW: 触发主动压缩，尝试继续推理循环
                    if error_type == ErrorType.CONTEXT_OVERFLOW:
                        logger.warning("上下文溢出，触发主动压缩...")
                        try:
                            ollama_dicts = [message_to_ollama_dict(m) for m in messages]
                            compression = await self.compressor.compress(ollama_dicts)
                            if compression.was_compressed:
                                messages = self._rebuild_messages_from_dicts(compression.messages)
                                logger.info("上下文压缩后重试: %d → %d 条消息",
                                            compression.original_count, compression.compressed_count)
                                continue  # 继续 ReAct 循环，不 abort
                            else:
                                feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                                yield AgentEvent(type="error", content=f"上下文过长: {feedback}")
                                return
                        except Exception as compress_err:
                            logger.error("压缩重试也失败: %s", compress_err)
                            yield AgentEvent(type="error", content="上下文过长，无法处理，请简化问题。")
                            return

                    feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                    logger.warning("LLM 错误 [%s]: %s → %s", error_type.value, e, feedback)
                    yield AgentEvent(type="error", content=f"LLM 调用失败: {feedback}")
                    return

                # 解析 LLM 响应中的工具调用
                tool_calls = self._extract_tool_calls(response)

                if not tool_calls:
                    # 无工具调用 → 这是最终回答
                    answer = self._extract_text_content(response)
                    self._finalize_trajectory(query, answer, success=True)
                    # 存储对话到长期记忆
                    if self._memory and answer:
                        self._memory.add(
                            content=f"Q: {query}\nA: {answer[:2000]}",
                            category="conversation",
                            importance=0.5,
                            tags=["conversation"],
                        )
                    yield AgentEvent(
                        type="response",
                        content=answer,
                        metadata={"token_usage": dict(self._token_usage)},
                    )
                    return

                # 将 LLM 的 assistant 消息（含工具调用）加入历史
                assistant_content = self._extract_text_content(response)

                # ── 判断本轮是否需要上下文隔离 ──
                has_heavy = (
                    self.scheduler is not None
                    and any(self.scheduler.is_heavy_tool(tc.name) for tc in tool_calls)
                )

                if has_heavy:
                    ollama_msgs = [message_to_ollama_dict(m) for m in messages]
                    self.scheduler.snapshot_context(ollama_msgs)
                    yield AgentEvent(
                        type="thinking",
                        content="正在隔离上下文以执行重 IO 工具...",
                    )
                    await self.scheduler.switch_role(ContextRole.ACTOR)

                # 追加 assistant 消息（含工具调用）到消息列表
                messages.append(Message(
                    role="assistant",
                    content=assistant_content,
                    tool_calls=tool_calls,
                ))

                # 执行所有工具，收集结果
                # 并行执行: 多个非重 IO 工具可同时运行
                tool_results: list[tuple[str, str, str]] = []
                if len(tool_calls) > 1 and not has_heavy:
                    # 并行执行独立工具
                    parallel_results = await self._execute_tools_parallel(tool_calls, query)
                    for tc_name, tc_id, result in parallel_results:
                        tool_results.append((tc_name, tc_id, result))
                        yield AgentEvent(
                            type="tool_result",
                            content=result[:500] + ("..." if len(result) > 500 else ""),
                            metadata={"tool_name": tc_name},
                        )
                else:
                    for tc in tool_calls:
                        result = await self._execute_single_tool(tc, query)
                        tool_results.append((tc.name, tc.id, result))

                if has_heavy:
                    # ── 隔离恢复: 切回 PLANNER，用快照 + 观测值替换消息列表 ──
                    await self.scheduler.switch_role(ContextRole.PLANNER)

                    # 合并所有工具结果为一条观测值
                    if len(tool_results) == 1:
                        tc_name, _, tc_result = tool_results[0]
                        observation = self.scheduler.condense_observation(tc_name, tc_result)
                    else:
                        parts = [
                            self.scheduler.condense_observation(name, result)
                            for name, _, result in tool_results
                        ]
                        observation = "\n\n".join(parts)

                    restored_dicts = self.scheduler.restore_context(observation)
                    messages = self._rebuild_messages_from_dicts(restored_dicts)

                    logger.info(
                        "上下文已恢复: %d 条消息, 观测值 %d 字符",
                        len(messages), len(observation),
                    )
                else:
                    # ── 非隔离: 正常追加 tool result 消息（Ollama 标准格式）──
                    for tc_name, tc_id, tc_result in tool_results:
                        truncated = tc_result[:_TOOL_RESULT_MAX_CHARS]
                        messages.append(Message(
                            role="tool",
                            content=truncated,
                            tool_call_id=tc_id,
                        ))

            # 超过最大步数
            self._finalize_trajectory(query, "", success=False)
            yield AgentEvent(
                type="error",
                content=f"推理步数超过上限 ({self.max_steps})，请简化问题或分步提问。",
            )

        finally:
            # 调度器: 推理完成后释放显存
            if self.scheduler is not None:
                try:
                    await self.scheduler.release_model()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _finalize_trajectory(self, query: str, answer: str, success: bool) -> None:
        """完成轨迹记录，保存对话，并触发后台审查。

        Args:
            query: 原始用户查询。
            answer: 最终回答。
            success: 是否成功完成。
        """
        trajectory = self.trajectory_recorder.finish(answer, success=success)

        # 保存对话到记忆系统
        self.memory.save_conversation(query, answer, success=success)

        # Skill 催促检查
        nudge = self.skills.nudge_check()
        if nudge:
            logger.info("Skill 催促: %s", nudge)

        # 异步触发后台审查
        if trajectory:
            traj_data = {
                "conversations": trajectory.to_sharegpt(),
                "metadata": {
                    "query": query,
                    "model": self.model,
                    "success": success,
                    "total_duration_ms": trajectory.total_duration_ms,
                    "created_at": trajectory.created_at,
                },
            }
            self.reviewer.spawn_review(traj_data)

    def _rebuild_messages_from_dicts(self, dicts: list[dict]) -> list[Message]:
        """将 Ollama 格式的 dict 列表转换回 Message 对象列表。

        用于调度器裁剪或恢复上下文后，将 dict 格式的消息重建为
        Message 对象，以便后续的 _call_llm 可以重新序列化。

        Args:
            dicts: Ollama 格式的消息字典列表。

        Returns:
            Message 对象列表。
        """
        messages: list[Message] = []
        for d in dicts:
            role = d.get("role", "user")
            content = d.get("content", "")

            # 检查是否有 tool_calls
            tool_calls = None
            raw_calls = d.get("tool_calls")
            if raw_calls:
                tool_calls = []
                for call in raw_calls:
                    func = call.get("function", {})
                    tool_calls.append(ToolCall(
                        id=call.get("id", str(uuid.uuid4())[:8]),
                        name=func.get("name", ""),
                        arguments=func.get("arguments", {}),
                    ))

            messages.append(Message(
                role=role,
                content=content,
                tool_calls=tool_calls,
                tool_call_id=d.get("tool_call_id"),
            ))
        return messages

    # ------------------------------------------------------------------
    # 消息构建
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> list[Message]:
        """构建 LLM 调用的完整消息列表。

        使用 PromptBuilder 动态拼装系统提示词（身份+工具+记忆+模型适配）。
        若 prompt_builder 未配置或 system_prompt 已手动指定，回退到静态拼接。

        Args:
            query: 当前用户查询。
            history: 历史对话消息。

        Returns:
            完整的消息列表，可直接序列化为 Ollama API 的 messages 参数。
        """
        messages: list[Message] = []

        # 系统提示词：优先使用 PromptBuilder，回退到静态拼接
        if self.prompt_builder and not self.system_prompt:
            # 注入记忆上下文
            memory_ctx = self.memory.get_memory_context(query)
            # 注入 Skill 上下文
            skill_ctx = self.skills.get_skill_context(query)
            extra: dict[str, str] = {}
            if skill_ctx:
                extra["技能库"] = skill_ctx

            config = PromptConfig(
                model_name=self.model,
                memory_content=memory_ctx,
                extra_sections=extra,
            )
            system = self.prompt_builder.build(config)
        else:
            system = self.system_prompt
            if self.tool_registry.list_tools():
                tool_names = [t.name for t in self.tool_registry.list_tools()]
                system += f"\n\n可用工具: {', '.join(tool_names)}"
        messages.append(Message(role="system", content=system))

        # RAG 自动注入：查询相关文档片段并作为上下文插入
        if self.rag_store is not None:
            try:
                rag_results = self.rag_store.retrieve_context(query, top_k=3)
                if rag_results:
                    rag_parts: list[str] = []
                    for i, r in enumerate(rag_results):
                        rag_parts.append(f"[文档片段 {i + 1}]\n{r['text']}")
                    rag_context = "\n\n---\n\n".join(rag_parts)
                    messages.append(Message(
                        role="system",
                        content=f"以下是从知识库检索到的相关文档片段，可作为回答参考:\n\n{rag_context}",
                    ))
                    logger.info("RAG 自动注入: %d 个片段", len(rag_results))
            except Exception as e:
                logger.warning("RAG 自动注入失败: %s", e)

        # 历史对话（截断保护）
        if history:
            recent = history[-(_MAX_HISTORY_TURNS * 2):]
            messages.extend(recent)

        # 当前查询
        messages.append(Message(role="user", content=query))

        return messages

    # ------------------------------------------------------------------
    # Plan-and-Execute 规划
    # ------------------------------------------------------------------

    _PLAN_PROMPT = """分析以下用户请求，判断是否需要多步骤执行计划。

如果请求比较简单（单步即可完成，如简单翻译、单个问题回答），输出: SKIP
如果请求需要多个步骤（如研究某个主题、对比多篇论文、分步骤处理文档），输出执行计划。

执行计划格式:
1. [步骤描述]
2. [步骤描述]
...

用户请求: {query}

可用的工具: {tools}

执行计划（或 SKIP）:"""

    async def _generate_plan(self, query: str, messages: list[Message]) -> str:
        """为复杂查询生成执行计划。

        使用 LLM 判断查询是否需要多步骤规划，若需要则生成计划。
        简单查询返回空字符串，不注入计划。

        Args:
            query: 用户查询。
            messages: 已构建的消息列表（用于可选的上下文参考）。

        Returns:
            执行计划文本，或空字符串（简单查询时）。
        """
        tool_names = [t.name for t in self.tool_registry.list_tools()]
        prompt = self._PLAN_PROMPT.format(
            query=query[:500],
            tools=", ".join(tool_names) if tool_names else "无",
        )
        try:
            plan_messages = [Message(role="user", content=prompt)]
            response = await self._call_llm_simple(plan_messages)
            if response and response.strip().upper().startswith("SKIP"):
                return ""
            if response and response.strip():
                cleaned = re.sub(r"<think.*?>.*?</think.*?>", "", response, flags=re.DOTALL).strip()
                return cleaned
        except Exception as e:
            logger.warning("规划生成失败 (将跳过): %s", e)
        return ""

    async def _call_llm_simple(self, messages: list[Message]) -> str | None:
        """轻量级 LLM 调用（无工具定义），用于规划等辅助推理。

        Args:
            messages: 消息列表。

        Returns:
            LLM 文本响应，失败时返回 None。
        """
        try:
            client = await self._get_http_client()
            ollama_dicts = [message_to_ollama_dict(m) for m in messages]

            if self._use_cloud:
                if self.api_format == "anthropic":
                    # Anthropic simple call
                    system_text = ""
                    anthropic_msgs = []
                    for d in ollama_dicts:
                        if d["role"] == "system":
                            system_text += d.get("content", "")
                            continue
                        anthropic_msgs.append({"role": d["role"], "content": d.get("content", "")})
                    payload: dict = {
                        "model": self.cloud_model or self.model,
                        "max_tokens": 1024,
                        "messages": anthropic_msgs,
                    }
                    if system_text:
                        payload["system"] = system_text
                    headers = {
                        "Content-Type": "application/json",
                        "x-api-key": self.cloud_api_key,
                        "anthropic-version": "2023-06-01",
                    }
                    resp = await client.post(
                        f"{self.cloud_base_url}/v1/messages",
                        json=payload, headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return "".join(
                        b.get("text", "") for b in data.get("content", [])
                        if b.get("type") == "text"
                    ).strip() or None
                else:
                    # OpenAI simple call
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.cloud_api_key}",
                    }
                    resp = await client.post(
                        f"{self.cloud_base_url}/chat/completions",
                        json={
                            "model": self.cloud_model or self.model,
                            "messages": ollama_dicts,
                            "temperature": 0.1,
                            "max_tokens": 1024,
                            "stream": False,
                        },
                        headers=headers,
                    )
                    resp.raise_for_status()
                    return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip() or None
            else:
                # Ollama simple call
                resp = await client.post(
                    f"{self.ollama_base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": ollama_dicts,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 1024},
                    },
                )
                resp.raise_for_status()
                return resp.json().get("message", {}).get("content", "").strip() or None
        except Exception as e:
            logger.warning("LLM 辅助调用失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[Message]) -> dict:
        """调用 LLM（非流式），自动选择 Ollama / OpenAI / Anthropic。

        返回值统一为 Ollama 格式: {"message": {"role", "content", "tool_calls"?}}
        """
        if not self._use_cloud:
            return await self._call_llm_ollama(messages)
        if self.api_format == "anthropic":
            return await self._call_llm_anthropic(messages)
        return await self._call_llm_cloud(messages)

    async def _call_llm_streaming(
        self, messages: list[Message]
    ) -> AsyncGenerator[tuple[AgentEvent | None, dict | None], None]:
        """流式调用 LLM，逐 token 输出，最终返回完整响应。

        Yields:
            (token_event, None) — 每个 token 输出
            (None, full_response) — 最终完整响应（一次）
        """
        if not self._use_cloud:
            async for item in self._stream_ollama(messages):
                yield item
        elif self.api_format == "anthropic":
            async for item in self._stream_anthropic(messages):
                yield item
        else:
            async for item in self._stream_cloud(messages):
                yield item

    async def _call_llm_ollama(self, messages: list[Message]) -> dict:
        """调用 Ollama Chat API，支持原生工具调用。

        请求格式:
        - endpoint: POST {base_url}/api/chat
        - payload: {
            "model": "...",
            "messages": [...],
            "tools": [...],  // 工具定义
            "stream": false,
            "options": { temperature, num_predict, ... }
          }

        Args:
            messages: 消息列表。

        Returns:
            Ollama Chat API 的完整 JSON 响应。

        Raises:
            ConnectionError: 无法连接 Ollama。
            ValueError: API 返回错误。
        """
        client = await self._get_http_client()
        ollama_messages = [message_to_ollama_dict(m) for m in messages]

        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }

        # 附带工具定义（Ollama 原生 tool calling）
        tools = self.tool_registry.to_ollama_tools()
        if tools:
            payload["tools"] = tools

        try:
            resp = await client.post(
                f"{self.ollama_base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.ollama_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ollama API 错误 (HTTP {e.response.status_code}): "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Ollama 请求超时 ({self.timeout}s)"
            ) from e

        return resp.json()

    async def _call_llm_cloud(self, messages: list[Message]) -> dict:
        """调用 OpenAI 兼容的云端 Chat API。

        将 OpenAI 响应格式归一化为 Ollama 格式，下游代码无需修改。

        Args:
            messages: 消息列表。

        Returns:
            归一化为 Ollama 格式的响应: {"message": {"role", "content", "tool_calls"?}}
        """
        client = await self._get_http_client()

        # 序列化消息为 OpenAI 兼容格式
        # 关键: tool_calls[].function.arguments 必须是 JSON 字符串
        openai_messages: list[dict] = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            openai_messages.append(d)

        # 构建 endpoint
        endpoint = f"{self.cloud_base_url}/chat/completions"

        payload: dict = {
            "model": self.cloud_model or self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.num_predict,
            "stream": False,
        }

        tools = self.tool_registry.to_ollama_tools()
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",
        }

        try:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接云端 API ({self.cloud_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                body = e.response.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                detail = e.response.text[:300]
            raise ValueError(
                f"云端 API 错误 (HTTP {e.response.status_code}): {detail}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"云端 API 请求超时 ({self.timeout}s)"
            ) from e

        data = resp.json()

        # 归一化: OpenAI → Ollama 格式
        choice = data.get("choices", [{}])[0]
        openai_msg = choice.get("message", {})

        normalized_tool_calls = []
        for tc in (openai_msg.get("tool_calls") or []):
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}")
            # OpenAI 返回 arguments 为 JSON 字符串，需要解析为 dict
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {"raw_input": raw_args}
            else:
                args = raw_args if isinstance(raw_args, dict) else {}

            normalized_tool_calls.append({
                "id": tc.get("id", str(uuid.uuid4())[:8]),
                "function": {
                    "name": func.get("name", ""),
                    "arguments": args,
                },
            })

        return {
            "message": {
                "role": openai_msg.get("role", "assistant"),
                "content": openai_msg.get("content", ""),
                **({"tool_calls": normalized_tool_calls} if normalized_tool_calls else {}),
            }
        }

    # ------------------------------------------------------------------
    # 流式 LLM 调用
    # ------------------------------------------------------------------

    async def _stream_ollama(
        self, messages: list[Message]
    ) -> AsyncGenerator[tuple[AgentEvent | None, dict | None], None]:
        """Ollama 流式输出，逐 token yield。

        Ollama NDJSON 流格式: 每行 {"message":{"content":"..."}, "done": false/true}
        最终 done=true 的行包含完整统计信息。
        """
        client = await self._get_http_client()
        ollama_messages = [message_to_ollama_dict(m) for m in messages]

        payload: dict = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.num_predict,
            },
        }
        tools = self.tool_registry.to_ollama_tools()
        if tools:
            payload["tools"] = tools

        try:
            async with client.stream(
                "POST",
                f"{self.ollama_base_url}/api/chat",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                full_content = ""
                tool_calls_acc: list[dict] = []

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = chunk.get("message", {})
                    token = msg.get("content", "")

                    # 收集流式 tool_calls
                    tc_chunk = msg.get("tool_calls")
                    if tc_chunk:
                        tool_calls_acc.extend(tc_chunk)

                    if token:
                        full_content += token
                        yield AgentEvent(type="token", content=token), None

                    if chunk.get("done"):
                        # 流结束，组装完整响应
                        result: dict = {
                            "message": {
                                "role": "assistant",
                                "content": full_content,
                            }
                        }
                        if tool_calls_acc:
                            result["message"]["tool_calls"] = tool_calls_acc
                        yield None, result
                        return

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Ollama 服务 ({self.ollama_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Ollama API 错误 (HTTP {e.response.status_code}): "
                f"{e.response.text[:200]}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Ollama 请求超时 ({self.timeout}s)"
            ) from e

        # 流结束但未收到 done=true，返回已积累的内容
        result = {"message": {"role": "assistant", "content": full_content}}
        if tool_calls_acc:
            result["message"]["tool_calls"] = tool_calls_acc
        yield None, result

    async def _stream_cloud(
        self, messages: list[Message]
    ) -> AsyncGenerator[tuple[AgentEvent | None, dict | None], None]:
        """OpenAI 兼容云端 API 流式输出。

        SSE 格式: data: {"choices":[{"delta":{"content":"..."}}]}
        工具调用: data: {"choices":[{"delta":{"tool_calls":[...]}}]}
        结束标记: data: [DONE]
        """
        client = await self._get_http_client()
        openai_messages: list[dict] = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            openai_messages.append(d)

        endpoint = f"{self.cloud_base_url}/chat/completions"
        payload: dict = {
            "model": self.cloud_model or self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.num_predict,
            "stream": True,
        }
        tools = self.tool_registry.to_ollama_tools()
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cloud_api_key}",
        }

        try:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                resp.raise_for_status()

                full_content = ""
                tc_accumulator: dict[str, dict] = {}  # index -> {id, name, arguments_str}

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})

                    token = delta.get("content", "")
                    if token:
                        full_content += token
                        yield AgentEvent(type="token", content=token), None

                    # 流式 tool_calls 增量拼接
                    tc_deltas = delta.get("tool_calls")
                    if tc_deltas:
                        for tc_d in tc_deltas:
                            idx = str(tc_d.get("index", 0))
                            if idx not in tc_accumulator:
                                tc_accumulator[idx] = {
                                    "id": tc_d.get("id", ""),
                                    "name": "",
                                    "arguments_str": "",
                                }
                            acc = tc_accumulator[idx]
                            if tc_d.get("id"):
                                acc["id"] = tc_d["id"]
                            func = tc_d.get("function", {})
                            if func.get("name"):
                                acc["name"] = func["name"]
                            if func.get("arguments"):
                                acc["arguments_str"] += func["arguments"]

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接云端 API ({self.cloud_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"云端 API 错误 (HTTP {e.response.status_code})"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"云端 API 请求超时 ({self.timeout}s)"
            ) from e

        # 归一化 tool_calls 为 Ollama 格式
        normalized_tool_calls = []
        for acc in tc_accumulator.values():
            raw_args = acc["arguments_str"] or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"raw_input": raw_args}
            normalized_tool_calls.append({
                "id": acc["id"] or str(uuid.uuid4())[:8],
                "function": {"name": acc["name"], "arguments": args},
            })

        result: dict = {
            "message": {
                "role": "assistant",
                "content": full_content,
            }
        }
        if normalized_tool_calls:
            result["message"]["tool_calls"] = normalized_tool_calls
        yield None, result

    async def _stream_anthropic(
        self, messages: list[Message]
    ) -> AsyncGenerator[tuple[AgentEvent | None, dict | None], None]:
        """Anthropic Messages API 流式输出。

        SSE 格式:
        event: content_block_delta, data: {"delta":{"text":"..."}}
        event: content_block_start, data: {"content_block":{"type":"tool_use",...}}
        event: message_stop
        """
        client = await self._get_http_client()
        endpoint = f"{self.cloud_base_url}/v1/messages"

        system_text = self.system_prompt
        anthropic_messages: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                if msg.content:
                    system_text = (system_text + "\n\n" + msg.content).strip() if system_text else msg.content
                continue
            if msg.role == "tool" and msg.tool_call_id:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
                continue
            if msg.role == "assistant" and msg.tool_calls:
                blocks: list[dict] = []
                if msg.content:
                    blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
                continue
            if msg.content:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        payload: dict = {
            "model": self.cloud_model or self.model,
            "max_tokens": self.num_predict,
            "messages": anthropic_messages,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text

        ollama_tools = self.tool_registry.to_ollama_tools()
        if ollama_tools:
            anthropic_tools = []
            for t in ollama_tools:
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = anthropic_tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,
            "anthropic-version": "2023-06-01",
        }

        full_content = ""
        tool_use_blocks: dict[int, dict] = {}  # index -> {id, name, input_json_str}

        try:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = chunk.get("type", "")

                    if event_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                full_content += token
                                yield AgentEvent(type="token", content=token), None
                        elif delta.get("type") == "input_json_delta":
                            idx = chunk.get("index", 0)
                            if idx in tool_use_blocks:
                                tool_use_blocks[idx]["input_str"] += delta.get("partial_json", "")

                    elif event_type == "content_block_start":
                        block = chunk.get("content_block", {})
                        if block.get("type") == "tool_use":
                            idx = chunk.get("index", 0)
                            tool_use_blocks[idx] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input_str": "",
                            }

                    elif event_type == "message_stop":
                        break

        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Anthropic API ({self.cloud_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"Anthropic API 错误 (HTTP {e.response.status_code})"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Anthropic API 请求超时 ({self.timeout}s)"
            ) from e

        normalized_tool_calls = []
        for blk in tool_use_blocks.values():
            raw = blk.get("input_str") or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"raw_input": raw}
            normalized_tool_calls.append({
                "id": blk.get("id") or str(uuid.uuid4())[:8],
                "function": {"name": blk.get("name", ""), "arguments": args},
            })

        result: dict = {
            "message": {
                "role": "assistant",
                "content": full_content,
            }
        }
        if normalized_tool_calls:
            result["message"]["tool_calls"] = normalized_tool_calls
        yield None, result

    async def _call_llm_anthropic(self, messages: list[Message]) -> dict:
        """调用 Anthropic Messages API，归一化为 Ollama 格式。

        Anthropic 与 OpenAI 的关键差异:
        - endpoint: {base_url}/v1/messages
        - auth: x-api-key + anthropic-version header
        - system prompt 是顶层字段，不在 messages 数组中
        - 工具定义用 input_schema 而非 parameters
        - 响应 content 是 blocks 数组: [{"type": "text"}, {"type": "tool_use"}]
        - tool result 消息用 {"type": "tool_result", "tool_use_id": ...}
        """
        client = await self._get_http_client()
        endpoint = f"{self.cloud_base_url}/v1/messages"

        # 分离 system prompt 和其他消息
        system_text = self.system_prompt
        anthropic_messages: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                # 系统消息合并到顶层 system 字段
                if msg.content:
                    system_text = (system_text + "\n\n" + msg.content).strip() if system_text else msg.content
                continue

            # tool result 消息 → Anthropic 的 user + tool_result 格式
            if msg.role == "tool" and msg.tool_call_id:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
                continue

            # assistant 消息带 tool_calls → Anthropic 的 content blocks 格式
            if msg.role == "assistant" and msg.tool_calls:
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                anthropic_messages.append({"role": "assistant", "content": content_blocks})
                continue

            # 普通 user / assistant 消息
            if msg.content:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        payload: dict = {
            "model": self.cloud_model or self.model,
            "max_tokens": self.num_predict,
            "messages": anthropic_messages,
        }
        if system_text:
            payload["system"] = system_text

        # Anthropic 工具定义格式: {name, description, input_schema}
        ollama_tools = self.tool_registry.to_ollama_tools()
        if ollama_tools:
            anthropic_tools = []
            for t in ollama_tools:
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            payload["tools"] = anthropic_tools

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.cloud_api_key,
            "anthropic-version": "2023-06-01",
        }

        try:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接 Anthropic API ({self.cloud_base_url})"
            ) from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                body = e.response.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                detail = e.response.text[:300]
            raise ValueError(
                f"Anthropic API 错误 (HTTP {e.response.status_code}): {detail}"
            ) from e
        except httpx.TimeoutException as e:
            raise ConnectionError(
                f"Anthropic API 请求超时 ({self.timeout}s)"
            ) from e

        # 归一化: Anthropic → Ollama 格式
        # Anthropic: {"content": [{"type": "text", "text": "..."}, {"type": "tool_use", "id": "...", "name": "...", "input": {...}}]}
        # Ollama:    {"message": {"role": "assistant", "content": "...", "tool_calls": [...]}}
        data = resp.json()
        text_parts: list[str] = []
        normalized_tool_calls = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                normalized_tool_calls.append({
                    "id": block.get("id", str(uuid.uuid4())[:8]),
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input", {}),
                    },
                })

        return {
            "message": {
                "role": "assistant",
                "content": "".join(text_parts),
                **({"tool_calls": normalized_tool_calls} if normalized_tool_calls else {}),
            }
        }

    # ------------------------------------------------------------------
    # 工具执行辅助
    # ------------------------------------------------------------------

    async def _execute_single_tool(self, tc: ToolCall, query: str) -> str:
        """执行单个工具调用，返回结果字符串。

        Args:
            tc: 工具调用描述。
            query: 原始用户查询（用于动态工具生成）。

        Returns:
            工具执行结果字符串。
        """
        await self.hooks.trigger(HookContext(
            point=HookPoint.ON_TOOL_CALL,
            data={"tool_name": tc.name, "arguments": tc.arguments},
        ))

        start_time = time.monotonic()
        try:
            result = await self.tool_registry.execute(tc.name, tc.arguments)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.trajectory_recorder.add_turn(
                role="tool", content=result[:500],
                tool_name=tc.name, tool_args=tc.arguments,
                duration_ms=duration_ms,
            )
            await self.hooks.trigger(HookContext(
                point=HookPoint.ON_TOOL_RESULT,
                data={"tool_name": tc.name, "duration_ms": duration_ms, "success": True},
            ))
            return result
        except ValueError as e:
            error_msg = str(e)
            if "未注册的工具" in error_msg or "not found" in error_msg.lower():
                tool_spec = self._tool_generator.generate_from_llm_request(
                    llm_request=f"{tc.name}: {tc.arguments}",
                    task_description=query,
                )
                if tool_spec and self._tool_generator.generate_tool(tool_spec):
                    try:
                        result = await self.tool_registry.execute(tc.name, tc.arguments)
                        return result
                    except Exception:
                        pass
                result = f"错误: 工具 '{tc.name}' 不存在且自动生成失败"
            else:
                result = f"错误: {e}"

            if self._memory:
                self._memory.add(
                    content=f"工具 {tc.name} 执行失败: {error_msg}\n参数: {tc.arguments}",
                    category="tool_knowledge",
                    importance=0.6,
                    tags=["tool_error", tc.name],
                )
            return result
        except Exception as e:
            error_str = str(e)
            if self._memory:
                self._memory.add(
                    content=f"工具 {tc.name} 执行异常: {error_str}\n参数: {tc.arguments}",
                    category="tool_knowledge",
                    importance=0.7,
                    tags=["tool_error", tc.name],
                )
            return f"工具执行错误 ({tc.name}): {error_str}"

    async def _execute_tools_parallel(
        self, tool_calls: list[ToolCall], query: str
    ) -> list[tuple[str, str, str]]:
        """并行执行多个独立工具调用。

        Args:
            tool_calls: 工具调用列表。
            query: 原始用户查询。

        Returns:
            (tool_name, tool_call_id, result) 元组列表。
        """
        async def _run(tc: ToolCall) -> tuple[str, str, str]:
            result = await self._execute_single_tool(tc, query)
            return (tc.name, tc.id, result)

        results = await asyncio.gather(*[_run(tc) for tc in tool_calls])
        return list(results)

    # ------------------------------------------------------------------
    # 工具调用解析
    # ------------------------------------------------------------------

    def _extract_tool_calls(self, response: dict) -> list[ToolCall]:
        """从 LLM 响应中提取工具调用请求。

        双策略解析:
        1. **原生解析**: Ollama 响应中 message.tool_calls 字段。
        2. **文本降级**: 解析 message.content 中的 Action/Action Input 标记。

        Args:
            response: Ollama Chat API 的完整 JSON 响应。

        Returns:
            ToolCall 列表（空列表表示 LLM 未请求调用工具）。
        """
        tool_calls: list[ToolCall] = []

        # 策略 1: 原生 tool calling
        message = response.get("message", {})
        native_calls = message.get("tool_calls", [])

        for call in native_calls:
            func = call.get("function", {})
            name = func.get("name", "")
            arguments = func.get("arguments", {})

            if not name:
                continue

            # arguments 可能是字符串（需要 JSON 解析）
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw_input": arguments}

            tool_calls.append(ToolCall(
                id=call.get("id") or str(uuid.uuid4())[:8],
                name=name,
                arguments=arguments if isinstance(arguments, dict) else {},
            ))

        # 策略 2: 文本 ReAct 解析（仅在原生解析无结果时启用）
        if not tool_calls:
            content = message.get("content", "")
            tool_calls = self._parse_text_react(content)

        return tool_calls

    def _parse_text_react(self, content: str) -> list[ToolCall]:
        """从文本输出中解析 ReAct 格式的工具调用。

        解析模式:
            Action: tool_name
            Action Input: {"param": "value"}

        该降级策略确保即使模型不支持原生 tool calling，
        也能通过文本指令完成工具调用。

        Args:
            content: LLM 的文本输出。

        Returns:
            解析得到的 ToolCall 列表（可能为空）。
        """
        tool_calls: list[ToolCall] = []

        # 匹配 Action: xxx 和 Action Input: xxx
        action_match = re.search(
            r"Action\s*:\s*(\w+)\s*\n\s*Action\s*Input\s*:\s*(.+?)(?:\n|$)",
            content,
            re.IGNORECASE | re.DOTALL,
        )

        if action_match:
            tool_name = action_match.group(1).strip()
            raw_args = action_match.group(2).strip()

            # 尝试解析 JSON 参数
            arguments: dict = {}
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    arguments = parsed
                else:
                    arguments = {"input": str(parsed)}
            except json.JSONDecodeError:
                # 非 JSON 格式，尝试 key: value 解析
                arguments = {"input": raw_args}

            # 验证工具名是否已注册
            if self.tool_registry.get(tool_name):
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4())[:8],
                    name=tool_name,
                    arguments=arguments,
                ))
            else:
                logger.warning("文本 ReAct 解析: 工具 '%s' 未注册", tool_name)

        return tool_calls

    def _extract_text_content(self, response: dict) -> str:
        """从 LLM 响应中提取纯文本内容。

        Args:
            response: Ollama Chat API 的完整 JSON 响应。

        Returns:
            响应中的文本内容（已清理前后空白）。
        """
        message = response.get("message", {})
        content = message.get("content", "")
        return content.strip()

    def _accumulate_token_usage(self, response: dict) -> None:
        """从 LLM 响应中提取 token 用量并累加。

        支持多种 API 格式:
        - Ollama: eval_count, prompt_eval_count
        - OpenAI: usage.prompt_tokens, usage.completion_tokens
        - Anthropic: usage.input_tokens, usage.output_tokens

        Args:
            response: LLM 响应字典。
        """
        # Ollama 格式
        eval_count = response.get("eval_count") or response.get("eval_count")
        prompt_eval = response.get("prompt_eval_count")
        if eval_count:
            self._token_usage["completion_tokens"] += eval_count
        if prompt_eval:
            self._token_usage["prompt_tokens"] += prompt_eval

        # OpenAI 格式
        usage = response.get("usage")
        if isinstance(usage, dict):
            self._token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self._token_usage["completion_tokens"] += usage.get("completion_tokens", 0)

        # Anthropic 格式
        anthropic_usage = response.get("usage")
        if isinstance(anthropic_usage, dict):
            self._token_usage["prompt_tokens"] += anthropic_usage.get("input_tokens", 0)
            self._token_usage["completion_tokens"] += anthropic_usage.get("output_tokens", 0)

        self._token_usage["total_tokens"] = (
            self._token_usage["prompt_tokens"] + self._token_usage["completion_tokens"]
        )
        self._token_usage["llm_calls"] += 1
