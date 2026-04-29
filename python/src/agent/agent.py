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
from dataclasses import dataclass
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator

from src.agent.error_classifier import ErrorType, classify_error, get_recovery, RetryManager
from src.agent.hooks import HookContext, HookManager, HookPoint
from src.agent.llm_client import LLMClient, TokenUsage, extract_text_content, extract_tool_calls
from src.agent.memory import MemoryManager
from src.agent.models import AgentEvent, Message, ToolCall
from src.agent.prompt_builder import PromptBuilder, PromptConfig
from src.agent.skill_system import SkillRegistry
from src.agent.tools import ToolRegistry
from src.agent.trajectory import TrajectoryRecorder

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """单步执行结果。"""
    events: list[AgentEvent]
    tool_calls: list[ToolCall]
    tool_results: list[tuple[str, str, str]]  # (name, id, result)
    is_final: bool = False
    final_answer: str = ""
    error: str = ""


MAX_STEPS = 6
TASK_MAX_STEPS = 50
GLOBAL_MAX_STEPS = 200
_MAX_HISTORY_TURNS = 10
_TOOL_RESULT_MAX_CHARS = 4000
_TOOL_RESULT_RECENT = 2
_TOOL_RESULT_SHORT = 800
_SLIDING_WINDOW_TAIL = 16
_SLIDING_WINDOW_THRESHOLD = 22


def _trim_messages(messages: list[Message]) -> list[Message]:
    """滑动窗口裁剪，保证 tool/assistant 消息配对完整，旧工具结果截断。"""
    if len(messages) <= _SLIDING_WINDOW_THRESHOLD:
        return messages
    head = messages[:2]
    tail = messages[-_SLIDING_WINDOW_TAIL:]
    # 从 head 末端收集已有的 tool_call_id
    valid_ids: set[str] = set()
    for m in head:
        if m.tool_calls:
            valid_ids.update(tc.id for tc in m.tool_calls)
    # 从 tail 头部丢掉孤立的 tool 或引用不全的 assistant
    while tail:
        m = tail[0]
        if m.role == "tool" and m.tool_call_id and m.tool_call_id not in valid_ids:
            tail.pop(0)
            continue
        if m.role == "assistant" and m.tool_calls:
            need = {tc.id for tc in m.tool_calls}
            have = {x.tool_call_id for x in tail[1:] if x.role == "tool"}
            if not need.issubset(have):
                tail.pop(0)
                continue
            valid_ids.update(need)
        elif m.role == "tool" and m.tool_call_id:
            pass  # already covered by valid_ids check above
        break
    # 截断旧工具结果：最近 2 条保持原样，更早的截到 _TOOL_RESULT_SHORT
    tool_msg_indices = [i for i, m in enumerate(tail) if m.role == "tool"]
    recent_tool_count = 0
    for i in reversed(tool_msg_indices):
        recent_tool_count += 1
        if recent_tool_count > _TOOL_RESULT_RECENT and len(tail[i].content) > _TOOL_RESULT_SHORT:
            tail[i] = Message(
                role="tool",
                content=tail[i].content[:_TOOL_RESULT_SHORT],
                tool_call_id=tail[i].tool_call_id,
            )
    result = head + tail
    # 安全检查：确保 assistant(tool_calls) 后紧跟对应的 tool 消息
    # 如果序列不合法，去掉末尾不完整的消息块
    i = 0
    while i < len(result):
        m = result[i]
        if m.role == "assistant" and m.tool_calls:
            tc_ids = {tc.id for tc in m.tool_calls}
            # 检查紧随其后的 tool 消息是否覆盖所有 tool_call_id
            j = i + 1
            found_ids: set[str] = set()
            while j < len(result) and result[j].role == "tool":
                if result[j].tool_call_id:
                    found_ids.add(result[j].tool_call_id)
                j += 1
            if not tc_ids.issubset(found_ids):
                # 去掉这个不完整的 assistant 块及其后续 tool 消息
                result = result[:i]
                break
            i = j
        else:
            i += 1
    return result


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
        context_compressor: Any | None = None,
        prompt_builder: PromptBuilder | None = None,
        memory_manager: MemoryManager | None = None,
        skill_registry: SkillRegistry | None = None,
        trajectory_recorder: TrajectoryRecorder | None = None,
        rag_store: Any | None = None,
        rag_top_k: int = 3,
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

        self.prompt_builder = prompt_builder or PromptBuilder(
            tool_registry=self.tool_registry,
        )

        self.memory = memory_manager or MemoryManager()
        self.skills = skill_registry or SkillRegistry()
        self.trajectory_recorder = trajectory_recorder or TrajectoryRecorder()

        self.retry_manager = RetryManager()
        self.hooks = HookManager()

        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format

        self.rag_store = rag_store
        self.rag_top_k = rag_top_k

    async def close(self) -> None:
        await self.llm.close()

    # ------------------------------------------------------------------
    # v2: Stateless single-step executor
    # ------------------------------------------------------------------

    async def step(
        self,
        messages: list[Message],
        *,
        step_num: int = 1,
        max_steps: int = TASK_MAX_STEPS,
        execute_tools: bool = True,
    ) -> StepResult:
        """执行单个 ReAct 步骤，返回结构化结果。

        这是 AgentLoop 的**核心执行方法**，由 AgentSession.drive() 反复调用
        来驱动完整的推理循环。

        设计原则：
        - 无状态执行：不修改 self 实例状态（除了 token_usage 累积）
        - 消息原地更新：直接在 messages 列表上追加 assistant/tool 消息
        - 灵活工具执行：execute_tools=False 允许调用方先门控再执行

        Args:
            messages: 当前消息列表（会被原地追加 assistant + tool 消息）。
            step_num: 当前步骤编号（用于日志）。
            max_steps: 最大步骤数上限（用于日志，不做判断）。
            execute_tools: 若为 False，只推理不执行工具，由调用方门控后执行。

        Returns:
            StepResult 包含本轮事件、工具调用和结果。
        """
        result = StepResult(events=[], tool_calls=[], tool_results=[])
        logger.info("ReAct step %d (session-driven)", step_num)

        # 滑动窗口上下文管理
        messages[:] = _trim_messages(messages)

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


    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _finalize_trajectory(self, query: str, answer: str, success: bool) -> None:
        self.trajectory_recorder.finish(answer, success=success)
        self.memory.save_conversation(query, answer, success=success)

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
                reasoning_content=d.get("reasoning_content"),
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
        messages: list[Message] = []

        if self.prompt_builder and not self.system_prompt:
            config = PromptConfig(model_name=self.model)
            system = self.prompt_builder.build(config)
        else:
            system = self.system_prompt
            if self.tool_registry.list_tools():
                tool_names = [t.name for t in self.tool_registry.list_tools()]
                system += f"\n\n可用工具: {', '.join(tool_names)}"
        messages.append(Message(role="system", content=system))

        if self.rag_store is not None:
            try:
                rag_results = self.rag_store.retrieve_context(query, top_k=self.rag_top_k)
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
                available = [t.name for t in self.tool_registry.list_tools()]
                result = f"错误: 工具 '{tc.name}' 不存在。可用工具: {', '.join(available)}"
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
