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
    │                  │ LLM 推理  │ ← LLMClient   │
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

LLM 通信委托给 llm_client.LLMClient，支持:
- Ollama 本地推理 (原生 tool calling)
- OpenAI 兼容云端 API (18 providers)
- Anthropic Messages API
- 流式/非流式双模式

错误恢复策略:
- 工具参数解析失败 → 将错误信息作为 Observation 反馈给 LLM，继续推理。
- LLM 调用不存在的工具 → 反馈工具不存在信息，引导 LLM 选择正确的工具。
- 超过最大推理步数 (MAX_STEPS) → 终止循环，返回错误事件。
- Ollama 连接失败 → 不可恢复错误，终止循环。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator

from src.agent.context_compressor import ContextCompressor
from src.agent.error_classifier import ErrorType, classify_error, get_recovery, RetryManager
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.llm_client import LLMClient, TokenUsage, extract_text_content, extract_tool_calls
from src.agent.memory import MemoryManager
from src.agent.models import AgentEvent, Message, ToolCall, message_to_ollama_dict
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.review_agent import ReviewAgent
from src.agent.skill_system import SkillRegistry
from src.agent.tool_generator import ToolGenerator, create_tool_generator
from src.agent.tools import ToolRegistry
from src.agent.trajectory import TrajectoryRecorder

logger = logging.getLogger(__name__)

MAX_STEPS = 10
TASK_MAX_STEPS = 50
GLOBAL_MAX_STEPS = 200
_MAX_HISTORY_TURNS = 10
_TOOL_RESULT_MAX_CHARS = 4000

_PLAN_TRIGGER_KEYWORDS = frozenset({
    "研究", "对比", "分析", "写", "撰写", "搜索", "查", "找",
    "总结", "概括", "整理", "归纳", "综述", "论文", "报告",
    "compare", "analyze", "research", "write", "search", "summarize",
})


def _is_simple_query(query: str) -> bool:
    q = query.strip()
    for kw in _PLAN_TRIGGER_KEYWORDS:
        if kw in q:
            return False
    if len(q) < 80:
        return True
    return False


class AgentLoop:
    """ReAct 模式 Agent 推理循环引擎。

    LLM 通信委托给 LLMClient，本类专注 ReAct 编排:
    消息构建 → LLM 调用 → 工具执行 → 上下文压缩 → 循环。
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        tool_registry: ToolRegistry | None = None,
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
        rag_store: Any | None = None,
        cloud_base_url: str = "",
        cloud_api_key: str = "",
        cloud_model: str = "",
        api_format: str = "openai",
        memory_dir: str = "",
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.num_predict = num_predict
        self.timeout = timeout

        # LLM client
        self.llm = LLMClient(
            ollama_base_url=ollama_base_url,
            model=model,
            temperature=temperature,
            num_predict=num_predict,
            timeout=timeout,
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
            api_format=api_format,
            system_prompt=system_prompt,
        )

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

        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format

        self.rag_store = rag_store
        self._tool_generator = create_tool_generator(self.tool_registry)
        self._auto_processor: Any | None = None

        self._format_error_retry = False

    async def close(self) -> None:
        await self.llm.close()
        await self.compressor.close()
        await self.reviewer.close()

    # ------------------------------------------------------------------
    # v2: Stateless single-step executor
    # ------------------------------------------------------------------

    @dataclass
    class StepResult:
        """单步执行结果。"""
        events: list[AgentEvent]
        tool_calls: list[ToolCall]
        tool_results: list[tuple[str, str, str]]  # (name, id, result)
        is_final: bool = False
        final_answer: str = ""
        error: str = ""

    async def step(
        self,
        messages: list[Message],
        *,
        step_num: int = 1,
        max_steps: int = TASK_MAX_STEPS,
        execute_tools: bool = True,
    ) -> AgentLoop.StepResult:
        """执行单个 ReAct 步骤，返回结构化结果。

        AgentSession.drive() 反复调用此方法驱动循环。
        不修改 self 实例状态（除了 token_usage 累积），
        所有可变状态由 AgentSession 管理。

        Args:
            messages: 当前消息列表（会被原地追加 assistant + tool 消息）。
            step_num: 当前步骤编号（用于日志）。
            max_steps: 最大步骤数上限（用于日志，不做判断）。
            execute_tools: 若为 False，只推理不执行工具，由调用方门控后执行。

        Returns:
            StepResult 包含本轮事件、工具调用和结果。
        """
        result = self.StepResult(events=[], tool_calls=[], tool_results=[])
        logger.info("ReAct step %d (session-driven)", step_num)

        # 上下文压缩
        ollama_dicts = [message_to_ollama_dict(m) for m in messages]
        try:
            compression = await self.compressor.compress(ollama_dicts)
            if compression.was_compressed:
                messages[:] = self._rebuild_messages_from_dicts(compression.messages)
                result.events.append(AgentEvent(
                    type="thinking",
                    content=f"上下文已压缩: {compression.original_tokens} → {compression.compressed_tokens} tokens",
                ))
        except Exception as e:
            logger.warning("上下文压缩失败（继续）: %s", e)

        # LLM 调用
        try:
            tools = self.tool_registry.to_ollama_tools() or None
            response = None
            token_events: list[AgentEvent] = []
            async for token_event, full_response in self.llm.stream(messages, tools=tools):
                if token_event is not None:
                    ev = AgentEvent(type="token", content=token_event.get("content", ""))
                    token_events.append(ev)
                    result.events.append(ev)
                if full_response is not None:
                    response = full_response
            if response is None:
                raise ValueError("LLM 流式响应未返回完整结果")
            self.llm.token_usage.accumulate(response)
        except Exception as e:
            logger.error("LLM 调用异常: %s", e, exc_info=True)
            result.error = str(e)
            result.events.append(AgentEvent(type="error", content=f"LLM 调用失败: {e}"))
            return result

        # 解析工具调用
        tool_calls = extract_tool_calls(response)
        if not tool_calls:
            tool_calls = self._parse_text_react(extract_text_content(response))

        if not tool_calls:
            answer = extract_text_content(response)
            result.is_final = True
            result.final_answer = answer
            result.events.append(AgentEvent(
                type="response",
                content=answer,
                metadata={"token_usage": self.llm.token_usage.to_dict()},
            ))
            return result

        # 记录 assistant 消息
        assistant_content = extract_text_content(response)
        reasoning = (response.get("message") or {}).get("reasoning_content") or None
        messages.append(Message(
            role="assistant",
            content=assistant_content,
            tool_calls=tool_calls,
            reasoning_content=reasoning,
        ))

        result.tool_calls = tool_calls

        # 发出 tool_call 事件
        for tc in tool_calls:
            result.events.append(AgentEvent(
                type="tool_call",
                content="",
                metadata={"tool": tc.name, "args": tc.arguments},
            ))

        # Phase 3: 若调用方要求不执行，则由 AgentSession 门控后再执行
        if not execute_tools:
            return result

        # 执行工具
        if len(tool_calls) > 1:
            parallel_results = await self._execute_tools_parallel(tool_calls, "")
            for tc_name, tc_id, tc_result in parallel_results:
                result.tool_results.append((tc_name, tc_id, tc_result))
        else:
            for tc in tool_calls:
                tc_result = await self._execute_single_tool(tc, "")
                result.tool_results.append((tc.name, tc.id, tc_result))

        # 追加 tool 消息 + tool_result 事件
        for tc_name, tc_id, tc_result in result.tool_results:
            truncated = tc_result[:_TOOL_RESULT_MAX_CHARS]
            messages.append(Message(role="tool", content=truncated, tool_call_id=tc_id))
            result.events.append(AgentEvent(
                type="tool_result",
                content=tc_result[:500] + ("..." if len(tc_result) > 500 else ""),
                metadata={"tool_name": tc_name},
            ))

        return result

    async def run(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行 ReAct 推理循环，流式返回事件。"""
        self.retry_manager.reset()
        self._format_error_retry = False
        self.llm.token_usage = TokenUsage()

        self.trajectory_recorder.start(query, model=self.model)

        # 特殊元素自动检测和处理
        auto_result = await self._auto_process_special_elements(query, history)
        if auto_result and auto_result.has_special_elements:
            logger.info("自动检测到特殊元素: %s", auto_result.detected_elements)
            yield AgentEvent(
                type="thinking",
                content=f"检测到特殊元素: {', '.join(auto_result.detected_elements)}，正在分析..."
            )
            query = auto_result.enhanced_query

        messages = self._build_messages(query, history)

        # Plan-and-Execute
        plan = await self._generate_plan(query, messages)
        if plan:
            yield AgentEvent(type="thinking", content=f"执行计划:\n{plan}")
            plan_text = f"\n\n## 执行计划\n请按以下步骤执行：\n{plan}"
            if messages and messages[0].role == "system":
                messages[0] = Message(role="system", content=messages[0].content + plan_text)
            else:
                messages.insert(0, Message(role="system", content=plan_text))

        try:
            for step in range(1, self.max_steps + 1):
                logger.info("ReAct 步骤 %d/%d", step, self.max_steps)

                # 主动上下文压缩
                ollama_dicts = [message_to_ollama_dict(m) for m in messages]
                await self.hooks.trigger(HookContext(
                    point=HookPoint.ON_PRE_COMPRESS,
                    data={"message_count": len(ollama_dicts), "step": step},
                ))
                compression = await self.compressor.compress(ollama_dicts)
                if compression.was_compressed:
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
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_CALL,
                        data={"step": step, "message_count": len(messages)},
                    ))

                    tools = None if self._format_error_retry else self.tool_registry.to_ollama_tools() or None
                    response = None
                    async for token_event, full_response in self.llm.stream(messages, tools=tools):
                        if token_event is not None:
                            yield AgentEvent(type="token", content=token_event.get("content", ""))
                        if full_response is not None:
                            response = full_response
                    if response is None:
                        raise ValueError("LLM 流式响应未返回完整结果")
                    self.llm.token_usage.accumulate(response)
                    if self._format_error_retry:
                        self._format_error_retry = False
                        logger.info("工具调用已恢复（上一步无工具重试成功）")
                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_LLM_RESPONSE,
                        data={"step": step},
                    ))
                except Exception as e:
                    logger.error("LLM 调用异常 [%s]: %s", type(e).__name__, e, exc_info=True)
                    error_type = classify_error(e)
                    recovery = get_recovery(error_type)

                    await self.hooks.trigger(HookContext(
                        point=HookPoint.ON_ERROR,
                        data={"error_type": error_type.value, "error": str(e), "step": step},
                    ))

                    if error_type == ErrorType.CONTEXT_OVERFLOW:
                        logger.warning("上下文溢出，触发主动压缩...")
                        try:
                            ollama_dicts = [message_to_ollama_dict(m) for m in messages]
                            compression = await self.compressor.compress(ollama_dicts)
                            if compression.was_compressed:
                                messages = self._rebuild_messages_from_dicts(compression.messages)
                                logger.info("上下文压缩后重试: %d → %d 条消息",
                                            compression.original_count, compression.compressed_count)
                                continue
                            else:
                                yield AgentEvent(type="error", content="上下文过长，无法处理，请简化问题。")
                                return
                        except Exception as compress_err:
                            logger.error("压缩重试也失败: %s", compress_err)
                            yield AgentEvent(type="error", content="上下文过长，无法处理，请简化问题。")
                            return

                    if error_type == ErrorType.FORMAT_ERROR and self.retry_manager.can_retry(error_type):
                        delay = self.retry_manager.get_delay(error_type)
                        feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                        self.retry_manager.record_attempt(error_type)
                        logger.warning(
                            "LLM 错误 [%s]: %s → %s (去掉工具后重试, 第 %d 次)",
                            error_type.value, e, feedback,
                            self.retry_manager._attempt_counts.get(error_type, 0),
                        )
                        yield AgentEvent(
                            type="thinking",
                            content=f"请求格式错误，尝试去掉工具后重新调用...",
                        )
                        await asyncio.sleep(delay)
                        self._format_error_retry = True
                        continue

                    if recovery.action == "retry" and self.retry_manager.can_retry(error_type):
                        delay = self.retry_manager.get_delay(error_type)
                        feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                        self.retry_manager.record_attempt(error_type)
                        logger.warning(
                            "LLM 错误 [%s]: %s → %s (将在 %.1fs 后重试, 第 %d 次)",
                            error_type.value, e, feedback, delay,
                            self.retry_manager._attempt_counts.get(error_type, 0),
                        )
                        yield AgentEvent(
                            type="thinking",
                            content=f"遇到错误 ({feedback})，正在重试...",
                        )
                        await asyncio.sleep(delay)
                        continue

                    feedback = self.retry_manager.get_feedback_message(error_type, str(e))
                    raw = str(e)
                    logger.warning("LLM 错误 [%s]: %s → %s (终止)", error_type.value, e, feedback)
                    display_msg = f"LLM 调用失败: {feedback}"
                    if raw and raw not in display_msg:
                        display_msg += f"\n详情: {raw[:300]}"
                    yield AgentEvent(type="error", content=display_msg, metadata={"raw_error": raw, "error_type": error_type.value})
                    return

                # 解析 LLM 响应中的工具调用
                tool_calls = extract_tool_calls(response)
                if not tool_calls:
                    tool_calls = self._parse_text_react(extract_text_content(response))

                if not tool_calls:
                    answer = extract_text_content(response)
                    self._finalize_trajectory(query, answer, success=True)
                    if answer:
                        try:
                            self.memory.add_memory(
                                content=f"Q: {query}\nA: {answer[:2000]}",
                                category="conversation",
                                source="conversation",
                                importance=0.5,
                            )
                        except Exception as e:
                            logger.warning("长期记忆存储失败（不影响推理）: %s", e)
                    yield AgentEvent(
                        type="response",
                        content=answer,
                        metadata={"token_usage": self.llm.token_usage.to_dict()},
                    )
                    return

                assistant_content = extract_text_content(response)
                reasoning = (response.get("message") or {}).get("reasoning_content") or None
                messages.append(Message(
                    role="assistant",
                    content=assistant_content,
                    tool_calls=tool_calls,
                    reasoning_content=reasoning,
                ))

                tool_results: list[tuple[str, str, str]] = []
                if len(tool_calls) > 1:
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

                for tc_name, tc_id, tc_result in tool_results:
                    truncated = tc_result[:_TOOL_RESULT_MAX_CHARS]
                    messages.append(Message(
                        role="tool",
                        content=truncated,
                        tool_call_id=tc_id,
                    ))

            self._finalize_trajectory(query, "", success=False)
            yield AgentEvent(
                type="error",
                content=f"推理步数超过上限 ({self.max_steps})，请简化问题或分步提问。",
            )
        except GeneratorExit:
            raise

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _finalize_trajectory(self, query: str, answer: str, success: bool) -> None:
        trajectory = self.trajectory_recorder.finish(answer, success=success)
        self.memory.save_conversation(query, answer, success=success)
        nudge = self.skills.nudge_check()
        if nudge:
            logger.info("Skill 催促: %s", nudge)
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
        messages: list[Message] = []
        for d in dicts:
            role = d.get("role", "user")
            content = d.get("content", "")
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
    # 特殊元素自动处理
    # ------------------------------------------------------------------

    async def _auto_process_special_elements(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> Any | None:
        try:
            from src.agent.auto_processor import AutoElementProcessor
        except ImportError:
            return None

        if self._auto_processor is None:
            self._auto_processor = AutoElementProcessor()

        context_text = None
        if history:
            for msg in reversed(history):
                if msg.role == "user" and msg.content:
                    context_text = msg.content
                    break

        try:
            return await self._auto_processor.process_async(query, context_text)
        except Exception as e:
            logger.warning("特殊元素自动处理失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 消息构建
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        query: str,
        history: list[Message] | None = None,
    ) -> list[Message]:
        messages: list[Message] = []

        if self.prompt_builder and not self.system_prompt:
            memory_ctx = self.memory.get_memory_context(query)
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

        if history:
            recent = history[-(_MAX_HISTORY_TURNS * 2):]
            messages.extend(recent)

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
        if _is_simple_query(query):
            return ""
        tool_names = [t.name for t in self.tool_registry.list_tools()]
        prompt = self._PLAN_PROMPT.format(
            query=query[:500],
            tools=", ".join(tool_names) if tool_names else "无",
        )
        try:
            plan_messages = [Message(role="user", content=prompt)]
            response = await self.llm.call_simple(plan_messages)
            if response and response.strip().upper().startswith("SKIP"):
                return ""
            if response and response.strip():
                cleaned = re.sub(r"<think.*?>.*?</think.*?>", "", response, flags=re.DOTALL).strip()
                return cleaned
        except Exception as e:
            logger.warning("规划生成失败 (将跳过): %s", e)
        return ""

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def _execute_single_tool(self, tc: ToolCall, query: str) -> str:
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

            if self.memory:
                self.memory.add_memory(
                    content=f"工具 {tc.name} 执行失败: {error_msg}\n参数: {tc.arguments}",
                    category="tool_knowledge",
                    source="agent",
                    importance=0.6,
                )
            return result
        except Exception as e:
            error_str = str(e)
            if self.memory:
                self.memory.add_memory(
                    content=f"工具 {tc.name} 执行异常: {error_str}\n参数: {tc.arguments}",
                    category="tool_knowledge",
                    source="agent",
                    importance=0.7,
                )
            return f"工具执行错误 ({tc.name}): {error_str}"

    async def _execute_tools_parallel(
        self, tool_calls: list[ToolCall], query: str
    ) -> list[tuple[str, str, str]]:
        async def _run(tc: ToolCall) -> tuple[str, str, str]:
            result = await self._execute_single_tool(tc, query)
            return (tc.name, tc.id, result)

        results = await asyncio.gather(*[_run(tc) for tc in tool_calls])
        return list(results)

    # ------------------------------------------------------------------
    # 文本 ReAct 解析（降级策略）
    # ------------------------------------------------------------------

    def _parse_text_react(self, content: str) -> list[ToolCall]:
        """从文本输出中解析 ReAct 格式的工具调用 (Action/Action Input)。"""
        tool_calls: list[ToolCall] = []

        action_match = re.search(
            r"Action\s*:\s*(\w+)\s*\n\s*Action\s*Input\s*:\s*(.+?)(?:\n|$)",
            content,
            re.IGNORECASE | re.DOTALL,
        )

        if action_match:
            tool_name = action_match.group(1).strip()
            raw_args = action_match.group(2).strip()
            arguments: dict = {}
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    arguments = parsed
                else:
                    arguments = {"input": str(parsed)}
            except json.JSONDecodeError:
                arguments = {"input": raw_args}

            if self.tool_registry.get(tool_name):
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4())[:8],
                    name=tool_name,
                    arguments=arguments,
                ))
            else:
                logger.warning("文本 ReAct 解析: 工具 '%s' 未注册", tool_name)

        return tool_calls
