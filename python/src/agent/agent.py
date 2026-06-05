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

from src.agent.context_compressor import ContextCompressor
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
TASK_MAX_STEPS = 20
GLOBAL_MAX_STEPS = 60
_MAX_HISTORY_TURNS = 10
_TOOL_RESULT_MAX_CHARS = 4000


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
        workspace_root: str = "",
        lesson_store: Any | None = None,
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

        self.workspace_root = workspace_root.strip()
        self.memory = memory_manager or MemoryManager()
        self.skills = skill_registry or SkillRegistry()
        self.trajectory_recorder = trajectory_recorder or TrajectoryRecorder()

        self.retry_manager = RetryManager()
        self.hooks = HookManager()
        self.lesson_store = lesson_store

        # 比例阈值上下文压缩器，替代旧的滑动窗口 _trim_messages
        _window = 32_000
        self.compressor = ContextCompressor(
            max_window_tokens=_window,
            threshold_percent=0.60,
            protect_head_count=1,
            protect_tail_turns=4,
            summary_max_tokens=500,
            ollama_base_url=ollama_base_url,
            summary_model=model if not cloud_base_url else None,
            cloud_base_url=cloud_base_url,
            cloud_api_key=cloud_api_key,
            cloud_model=cloud_model,
        )

        self.cloud_base_url = cloud_base_url.rstrip("/") if cloud_base_url else ""
        self.cloud_api_key = cloud_api_key
        self.cloud_model = cloud_model
        self.api_format = api_format

        self.rag_store = rag_store
        self.rag_top_k = rag_top_k

        # Scratchpad: stores full tool results when output exceeds SCRATCHPAD_THRESHOLD
        self._scratchpad: dict[str, str] = {}
        self._scratchpad_step = 0

    async def close(self) -> None:
        await self.llm.close()
        await self.compressor.close()

    # ------------------------------------------------------------------
    # Planning step: pre-execution reasoning without tools
    # ------------------------------------------------------------------

    _PLAN_PROMPT = (
        "你是一个任务分析器。分析用户的请求，判断是否需要调用工具来完成。\n"
        "只需要回答一个 JSON 对象，不要有其他文字：\n"
        '{"needs_tools": true/false, "plan": "简短规划", "tools": ["tool_name1", ...]}\n\n'
        "规则：\n"
        '- 如果用户要求读写文件、执行代码、搜索文献、翻译长文本 → needs_tools=true\n'
        "- 如果用户只是闲聊、问概念性问题、打招呼 → needs_tools=false\n"
        "- 拿不准时，宁可 needs_tools=true"
    )

    _SCRATCHPAD_MAX_ENTRIES = 32

    async def plan(self, messages: list[Message]) -> "PlanResult":
        """规划步骤：LLM 不调工具，仅判断是否需要工具。

        Returns:
            PlanResult with needs_tools, plan_text, estimated_tools.
        """
        from src.agent.models import PlanResult

        if not messages:
            return PlanResult(needs_tools=False, plan_text="empty input")

        last_user = ""
        for m in reversed(messages):
            if m.role == "user" and m.content:
                last_user = m.content
                break

        if not last_user:
            return PlanResult(needs_tools=False, plan_text="no user input")

        plan_msgs = [
            Message(role="system", content=self._PLAN_PROMPT),
            Message(role="user", content=last_user[:2000]),
        ]

        try:
            raw = await asyncio.to_thread(
                self.llm.call_simple_sync,
                "\n".join(f"{m.role}: {m.content}" for m in plan_msgs),
            )
        except Exception as exc:
            logger.warning("plan() LLM call failed: %s", exc)
            return PlanResult(needs_tools=True, plan_text="plan failed, defaulting to tools")

        return self._parse_plan_result(raw)

    def _parse_plan_result(self, raw: str) -> "PlanResult":
        """Parse LLM plan response into PlanResult."""
        from src.agent.models import PlanResult

        # Strip <think/> tags
        cleaned = re.sub(r"<think[^>]*>.*?</think\s*>", "", raw, flags=re.DOTALL).strip()

        # Try to extract JSON
        json_match = re.search(r"\{[^}]+\}", cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return PlanResult(
                    needs_tools=bool(data.get("needs_tools", True)),
                    plan_text=str(data.get("plan", "")),
                    estimated_tools=list(data.get("tools", [])),
                )
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback: check for true/false keywords
        lower = cleaned.lower()
        if "false" in lower or "不需要" in lower or "no tool" in lower:
            return PlanResult(needs_tools=False, plan_text=cleaned[:200])

        return PlanResult(needs_tools=True, plan_text=cleaned[:200])

    def scratchpad_read(self, key: str) -> str | None:
        """Read a stored scratchpad entry. Returns None if key not found."""
        return self._scratchpad.get(key)

    def _scratchpad_store(self, key: str, value: str) -> None:
        """Store value in scratchpad with LRU eviction."""
        if len(self._scratchpad) >= self._SCRATCHPAD_MAX_ENTRIES:
            oldest_key = next(iter(self._scratchpad))
            del self._scratchpad[oldest_key]
        self._scratchpad[key] = value

    async def _verify_answer(self, query: str, answer: str) -> "VerificationResult":
        """Post-execution answer quality check."""
        from src.agent.models import VerificationResult

        if not answer or not answer.strip():
            return VerificationResult(
                confidence=0.0, should_retry=True, reason="empty answer"
            )

        query_len = len(query)
        answer_len = len(answer)
        ratio = answer_len / max(query_len, 1)

        if ratio < 0.1 and query_len > 20:
            return VerificationResult(
                confidence=0.2,
                should_retry=True,
                reason=f"answer too short ({answer_len} chars for {query_len} char query)",
            )

        confidence = min(1.0, ratio / 0.5)
        return VerificationResult(
            confidence=confidence,
            should_retry=confidence < 0.3,
            reason="ok" if confidence >= 0.3 else "low confidence",
        )

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

        # 比例阈值上下文压缩（替代旧的滑动窗口 _trim_messages）
        try:
            messages[:] = await self.compressor.compress_messages(messages)
        except Exception as _ce:
            logger.warning("上下文压缩失败，跳过: %s", _ce)

        # LLM 调用（含错误分类 + 指数退避重试）
        # 每步重置重试预算：否则上一步耗尽某错误类型的配额后，本步同类错误会
        # 直接不重试（跨步预算泄漏）。
        self.retry_manager.reset()
        tools = self.tool_registry.to_ollama_tools() or None
        response = None
        _llm_call_done = False
        for _attempt in range(3):
            try:
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
                self.retry_manager.reset()
                _llm_call_done = True
                break
            except Exception as e:
                err_type = classify_error(e)
                if not self.retry_manager.can_retry(err_type):
                    logger.error("LLM 不可恢复错误 [%s]: %s", err_type.value, e)
                    result.error = str(e)
                    result.events.append(AgentEvent(
                        type="error",
                        content=self.retry_manager.get_feedback_message(err_type, str(e)),
                    ))
                    return result
                delay = self.retry_manager.get_delay(err_type)
                self.retry_manager.record_attempt(err_type)
                logger.warning(
                    "LLM 错误 [%s], %.1fs 后重试 (attempt %d/3): %s",
                    err_type.value, delay, _attempt + 1, e,
                )
                result.events.append(AgentEvent(
                    type="warning",
                    content=self.retry_manager.get_feedback_message(err_type, str(e)),
                ))
                await asyncio.sleep(delay)

        if not _llm_call_done:
            result.error = "LLM 调用多次重试后仍失败"
            result.events.append(AgentEvent(type="error", content=result.error))
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
                metadata={"tool_name": tc.name, "args": tc.arguments},
            ))

        # 若调用方要求不执行，则由 AgentSession 门控后再执行
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

        # 追加 tool 消息 + tool_result 事件（超长结果存入 scratchpad）
        _SCRATCHPAD_THRESHOLD = 2000
        for tc_name, tc_id, tc_result in result.tool_results:
            self._scratchpad_step += 1
            if len(tc_result) > _SCRATCHPAD_THRESHOLD:
                sp_key = f"{tc_name}_{self._scratchpad_step}"
                self._scratchpad_store(sp_key, tc_result)
                truncated = (
                    tc_result[:_SCRATCHPAD_THRESHOLD]
                    + f"\n...[输出过长已截断。完整结果已存入临时缓存 scratchpad[{sp_key}]，"
                    "如需完整内容可重新调用该工具或使用 offset 参数]"
                )
            else:
                truncated = tc_result
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
            # Inject memory context
            memory_ctx = ""
            if self.memory:
                try:
                    memory_ctx = self.memory.get_memory_context(query)
                except Exception as _me:
                    logger.warning("记忆上下文获取失败: %s", _me)

            # Inject matched skill as extra section
            extra: dict[str, str] = {}
            if self.skills:
                try:
                    matched_skill = self.skills.match(query)
                    if matched_skill:
                        self.skills.increment_use(matched_skill.name)
                        skill_lines = [
                            f"触发条件: {matched_skill.trigger}",
                            f"描述: {matched_skill.description}",
                            "执行步骤:",
                            *[f"  {i + 1}. {s}" for i, s in enumerate(matched_skill.steps)],
                        ]
                        if matched_skill.notes:
                            skill_lines += ["注意事项:", *[f"  - {n}" for n in matched_skill.notes]]
                        extra["可用技能指导"] = "\n".join(skill_lines)
                        logger.info("注入 Skill: %s", matched_skill.name)
                except Exception as _se:
                    logger.warning("Skill 匹配失败: %s", _se)

            # Inject lesson overlay from prior sessions
            if self.lesson_store:
                try:
                    overlay = self.lesson_store.build_overlay(query)
                    if overlay:
                        extra["过往经验教训"] = overlay
                except Exception as _le:
                    logger.warning("Lesson overlay 注入失败: %s", _le)

            doc_ctx = ""
            if self.workspace_root:
                doc_ctx = (
                    f"当前工作区根目录: {self.workspace_root}\n"
                    "读取工作区文件用 read_file（支持 PDF/Word/Markdown 等，会自动提取正文），"
                    "列目录用 list_directory，路径均为绝对路径。\n"
                    "重要：若用户消息中已带 [参考文本] 或 [当前编辑文件] 的内容，那就是当前文档本身，"
                    "直接据此回答，不要再 read_file 重复读取同一文件。\n"
                    "read_argument_graph / read_argument_ledger 仅在用户明确询问"
                    "“论证结构/逻辑漏洞/摘要承诺是否兑付”时才用；它们需要用户先在论证面板里构建，"
                    "若返回“暂无/未找到”，不要反复重试，改用 read_file 读原文后直接回答。"
                )

            config = PromptConfig(
                model_name=self.model,
                memory_content=memory_ctx,
                doc_context=doc_ctx,
                extra_sections=extra,
            )
            system = self.prompt_builder.build(config)
        else:
            system = self.system_prompt
            if self.tool_registry.list_tools():
                tool_names = [t.name for t in self.tool_registry.list_tools()]
                system += f"\n\n可用工具: {', '.join(tool_names)}"
        messages.append(Message(role="system", content=system))
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
                if len(raw_args) > 1_000_000:
                    raise ValueError("tool args too large")
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    arguments = parsed
                else:
                    arguments = {"input": str(parsed)}
            except (json.JSONDecodeError, ValueError):
                arguments = {"input": raw_args[:4096]}

            if self.tool_registry.get(tool_name):
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4())[:8],
                    name=tool_name,
                    arguments=arguments,
                ))
            else:
                logger.warning("文本 ReAct 解析: 工具 '%s' 未注册", tool_name)

        return tool_calls
