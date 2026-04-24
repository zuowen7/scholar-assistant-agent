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
    │    [Execute]              [Yield Response]   │
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

版权声明: 本模块属于 Scholar Translate Agent 子系统，
ReAct 推理循环与双策略工具调用机制受软件著作权和发明专利保护。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import AsyncGenerator

import httpx

from src.agent.context_compressor import ContextCompressor
from src.agent.error_classifier import ErrorType, classify_error, get_recovery, RetryManager
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.memory import MemoryManager
from src.agent.models import AgentEvent, Message, ToolCall, message_to_ollama_dict
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.review_agent import ReviewAgent
from src.agent.skill_system import SkillRegistry
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
        context_compressor: ContextCompressor | None = None,
        prompt_builder: PromptBuilder | None = None,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
        trajectory_recorder: TrajectoryRecorder | None = None,
        cloud_client: Any | None = None,
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
        )

        # Phase 3: 错误恢复 + Hook
        self.retry_manager = RetryManager()
        self.hooks = HookManager()

        # 双引擎: cloud_client 非空时走云端 API, 否则走 Ollama
        self.cloud_client = cloud_client
        self._use_cloud = cloud_client is not None

        self._http_client: httpx.AsyncClient | None = None

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
           a. 调用 Ollama Chat API (附带工具定义)。
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
        # 开始轨迹记录
        self.trajectory_recorder.start(query, model=self.model)

        # 构建消息列表
        messages = self._build_messages(query, history)

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

                # 调用 LLM
                try:
                    # Hook: on_llm_call
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_CALL,
                        data={"step": step, "message_count": len(messages)},
                    ))
                    response = await self._call_llm(messages)
                    # Hook: on_llm_response
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_RESPONSE,
                        data={"step": step},
                    ))
                except Exception as e:
                    error_type = classify_error(e)
                    recovery = get_recovery(error_type)
                    feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                    # Hook: on_error
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_ERROR,
                        data={"error_type": error_type.value, "error": str(e), "step": step},
                    ))
                    logger.warning("LLM 错误 [%s]: %s → %s", error_type.value, e, feedback)
                    yield AgentEvent(type="error", content=f"LLM 调用失败: {feedback}")
                    return

                # 解析 LLM 响应中的工具调用
                tool_calls = self._extract_tool_calls(response)

                if not tool_calls:
                    # 无工具调用 → 这是最终回答
                    answer = self._extract_text_content(response)
                    self._finalize_trajectory(query, answer, success=True)
                    yield AgentEvent(type="response", content=answer)
                    return

                # 将 LLM 的 assistant 消息（含工具调用）加入历史
                assistant_content = self._extract_text_content(response)

                # ── 判断本轮是否需要上下文隔离 ──
                # 只要有一个 heavy tool 就整轮隔离，避免多工具调用的消息链断裂。
                # 整轮隔离意味着 snapshot 在 append assistant 消息之前完成，
                # 恢复后 messages 不包含 assistant(tool_calls) 消息，
                # 避免 Ollama 报 "assistant with tool_calls but no tool response" 格式错误。
                has_heavy = (
                    self.scheduler is not None
                    and any(self.scheduler.is_heavy_tool(tc.name) for tc in tool_calls)
                )

                if has_heavy:
                    # 在 append assistant 消息之前保存快照（不含 tool_calls 格式）
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
                tool_results: list[tuple[str, str]] = []
                for tc in tool_calls:
                    # Hook: on_tool_call
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_TOOL_CALL,
                        data={"tool_name": tc.name, "arguments": tc.arguments},
                    ))
                    yield AgentEvent(
                        type="tool_call",
                        content=f"调用工具: {tc.name}",
                        metadata={"tool_name": tc.name, "arguments": tc.arguments},
                    )

                    start_time = time.monotonic()
                    try:
                        result = await self.tool_registry.execute(tc.name, tc.arguments)
                        duration_ms = int((time.monotonic() - start_time) * 1000)
                        self.trajectory_recorder.add_turn(
                            role="tool", content=result[:500],
                            tool_name=tc.name, tool_args=tc.arguments,
                            duration_ms=duration_ms,
                        )
                        # Hook: on_tool_result
                        await self.hooks.trigger(HookContext(
                            point=HookPoint.ON_TOOL_RESULT,
                            data={"tool_name": tc.name, "duration_ms": duration_ms, "success": True},
                        ))
                        yield AgentEvent(
                            type="tool_result",
                            content=result[:500] + ("..." if len(result) > 500 else ""),
                            metadata={"tool_name": tc.name, "duration_ms": duration_ms},
                        )
                    except ValueError as e:
                        result = f"错误: {e}"
                        # Hook: on_tool_result (error)
                        await self.hooks.trigger(HookContext(
                            point=HookPoint.ON_TOOL_RESULT,
                            data={"tool_name": tc.name, "success": False, "error": str(e)},
                        ))
                        yield AgentEvent(
                            type="tool_result",
                            content=result,
                            metadata={"tool_name": tc.name, "error": True},
                        )

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

        # 历史对话（截断保护）
        if history:
            recent = history[-(_MAX_HISTORY_TURNS * 2):]
            messages.extend(recent)

        # 当前查询
        messages.append(Message(role="user", content=query))

        return messages

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: list[Message]) -> dict:
        """调用 LLM — 云端 API 或本地 Ollama。

        根据用户设置自动路由：
        - cloud_client 非空 → OpenAI 兼容 API (/v1/chat/completions)
        - 否则 → Ollama API (/api/chat)

        两种格式的 tool_calls 响应在 _extract_tool_calls 中统一处理。

        Args:
            messages: 消息列表。

        Returns:
            统一格式的响应 dict，包含 message.content 和 message.tool_calls。

        Raises:
            ConnectionError: 无法连接 LLM 服务。
            ValueError: API 返回错误。
        """
        if self._use_cloud:
            return await self._call_cloud(messages)
        return await self._call_ollama(messages)

    async def _call_ollama(self, messages: list[Message]) -> dict:
        """调用 Ollama Chat API。"""
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
            raise ConnectionError(f"无法连接 Ollama 服务 ({self.ollama_base_url})") from e
        except httpx.HTTPStatusError as e:
            raise ValueError(f"Ollama API 错误 (HTTP {e.response.status_code}): {e.response.text[:200]}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Ollama 请求超时 ({self.timeout}s)") from e

        return resp.json()

    async def _call_cloud(self, messages: list[Message]) -> dict:
        """调用 OpenAI 兼容 Chat API，返回统一格式。"""
        client = await self._get_http_client()
        cloud = self.cloud_client

        # 将 Message 列表转为 OpenAI 格式
        api_messages = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content or ""}
            if m.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)},
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
                d["content"] = m.content or ""
            api_messages.append(d)

        payload: dict = {
            "model": cloud.model,
            "messages": api_messages,
            "temperature": self.temperature,
            "max_tokens": self.num_predict,
        }

        tools = self.tool_registry.to_ollama_tools()
        if tools:
            payload["tools"] = tools

        url = f"{cloud.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cloud.api_key}",
        }

        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        except httpx.ConnectError as e:
            raise ConnectionError(f"无法连接云端 API ({cloud.base_url})") from e
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                body = e.response.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                detail = e.response.text[:200]
            raise ValueError(f"云端 API 错误 (HTTP {e.response.status_code}): {detail}") from e
        except httpx.TimeoutException as e:
            raise ConnectionError(f"云端 API 请求超时 ({self.timeout}s)") from e

        data = resp.json()
        # 统一为 Ollama 格式，方便下游 _extract_tool_calls 处理
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})

        unified_tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            func = tc.get("function", {})
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"raw_input": args}
            unified_tool_calls.append({
                "function": {
                    "name": func.get("name", ""),
                    "arguments": args if isinstance(args, dict) else {},
                },
            })

        return {
            "message": {
                "role": "assistant",
                "content": msg.get("content", ""),
                "tool_calls": unified_tool_calls,
            },
        }

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
                id=str(uuid.uuid4())[:8],
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
