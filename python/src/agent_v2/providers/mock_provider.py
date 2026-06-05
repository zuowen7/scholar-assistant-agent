"""确定性 Mock LLM Provider。

参考 claw-code crates/mock-anthropic-service：
  预设场景 → 根据 messages 内容匹配 → 返回固定的 ProviderResponse。
不依赖任何网络，毫秒级响应，100% 可复现。
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from src.agent_v2.types import (
    ApiError,
    ContentBlock,
    InputMessage,
    Message,
    MessageRole,
    ProviderResponse,
    TextBlock,
    ThinkingBlock,
    TokenUsage,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
)


class Scenario:
    """一个预设的 LLM 响应场景。"""

    def __init__(
        self,
        name: str,
        trigger_patterns: list[str] | None = None,
        turn_index: int | None = None,
        response_factory: Any = None,
    ):
        self.name = name
        self.trigger_patterns = trigger_patterns or []
        self.turn_index = turn_index
        self.response_factory = response_factory

    def matches(self, messages: list[Message], turn_index: int) -> bool:
        if self.turn_index is not None and self.turn_index != turn_index:
            return False
        if not self.trigger_patterns:
            return True
        last_user = ""
        for m in reversed(messages):
            if m.role == MessageRole.USER:
                last_user = m.text_content()
                break
        return any(p.lower() in last_user.lower() for p in self.trigger_patterns)


def _text_response(text: str, usage: TokenUsage | None = None) -> ProviderResponse:
    return ProviderResponse(
        blocks=[TextBlock(text=text)],
        usage=usage or TokenUsage(input_tokens=50, output_tokens=len(text) // 4),
        stop_reason="end_turn",
    )


def _tool_response(tool_name: str, tool_input: dict[str, Any], usage: TokenUsage | None = None) -> ProviderResponse:
    return ProviderResponse(
        blocks=[ToolUseBlock(id=f"tu_{uuid.uuid4().hex[:8]}", name=tool_name, input=json.dumps(tool_input))],
        usage=usage or TokenUsage(input_tokens=50, output_tokens=30),
        stop_reason="tool_use",
    )


def _thinking_then_text(thinking: str, text: str) -> ProviderResponse:
    return ProviderResponse(
        blocks=[
            ThinkingBlock(thinking=thinking),
            TextBlock(text=text),
        ],
        usage=TokenUsage(input_tokens=50, output_tokens=40),
        stop_reason="end_turn",
    )


def _thinking_then_tool(thinking: str, tool_name: str, tool_input: dict[str, Any]) -> ProviderResponse:
    return ProviderResponse(
        blocks=[
            ThinkingBlock(thinking=thinking),
            ToolUseBlock(id=f"tu_{uuid.uuid4().hex[:8]}", name=tool_name, input=json.dumps(tool_input)),
        ],
        usage=TokenUsage(input_tokens=50, output_tokens=30),
        stop_reason="tool_use",
    )


# ---------------------------------------------------------------------------
# Built-in scenarios
# ---------------------------------------------------------------------------

BUILTIN_SCENARIOS: list[Scenario] = [
    # ---- MP-001: 纯文本回复 ----
    Scenario(name="greeting", trigger_patterns=["hello", "你好", "hi"],
             response_factory=lambda msgs, turn: _text_response("Hello! How can I help you today?")),

    Scenario(name="summarize", trigger_patterns=["summarize", "总结", "摘要"],
             response_factory=lambda msgs, turn: _text_response("Here is a summary of the content.")),

    # ---- MP-002: 单工具调用 ----
    Scenario(name="read_request", trigger_patterns=["read", "读取", "查看"],
             response_factory=lambda msgs, turn: _tool_response("read_file", {"file_path": "main.md"})),

    Scenario(name="write_request", trigger_patterns=["write", "写入", "创建"],
             response_factory=lambda msgs, turn: _tool_response("write_file", {"file_path": "output.txt", "content": "hello"})),

    # ---- MP-003: 多工具并行调用 ----
    Scenario(name="multi_read", trigger_patterns=["read both", "读取两个", "compare"],
             response_factory=lambda msgs, turn: ProviderResponse(
                 blocks=[
                     ToolUseBlock(id=f"tu_{uuid.uuid4().hex[:8]}", name="read_file", input=json.dumps({"file_path": "a.md"})),
                     ToolUseBlock(id=f"tu_{uuid.uuid4().hex[:8]}", name="read_file", input=json.dumps({"file_path": "b.md"})),
                 ],
                 usage=TokenUsage(input_tokens=50, output_tokens=50),
                 stop_reason="tool_use",
             )),

    # ---- MP-004: 思考 + 文本 ----
    Scenario(name="think_then_text", trigger_patterns=["explain", "解释", "why"],
             response_factory=lambda msgs, turn: _thinking_then_text(
                 "Let me think about this carefully...",
                 "The reason is that the implementation follows the standard pattern.",
             )),

    # ---- MP-005: 思考 + 工具调用 ----
    Scenario(name="think_then_read", trigger_patterns=["analyze", "分析"],
             response_factory=lambda msgs, turn: _thinking_then_tool(
                 "I need to read the file first to understand the context.",
                 "read_file", {"file_path": "main.md"},
             )),

    # ---- 多轮场景 (turn_index 匹配) ----
    Scenario(name="read_then_summarize_turn0", turn_index=0,
             trigger_patterns=["read and summarize", "读取并总结"],
             response_factory=lambda msgs, turn: _tool_response("read_file", {"file_path": "main.md"})),

    Scenario(name="read_then_summarize_turn1", turn_index=1,
             trigger_patterns=["read and summarize", "读取并总结"],
             response_factory=lambda msgs, turn: _text_response(
                 "Based on the file content, here is the summary: The document discusses the architecture of the system.",
             )),

    # 3 轮工具链
    Scenario(name="chain_turn0", turn_index=0,
             trigger_patterns=["find and fix", "查找并修复"],
             response_factory=lambda msgs, turn: _tool_response("read_file", {"file_path": "main.py"})),

    Scenario(name="chain_turn1", turn_index=1,
             trigger_patterns=["find and fix", "查找并修复"],
             response_factory=lambda msgs, turn: _tool_response("grep_files", {"pattern": "TODO", "path": "."})),

    Scenario(name="chain_turn2", turn_index=2,
             trigger_patterns=["find and fix", "查找并修复"],
             response_factory=lambda msgs, turn: _tool_response("str_replace", {
                 "file_path": "main.py", "old_string": "TODO: fix", "new_string": "# fixed",
             })),
]


class MockProvider:
    """确定性 Mock LLM Provider。

    用法:
        provider = MockProvider()
        # 默认使用 BUILTIN_SCENARIOS
        response = await provider.chat(messages=[...], tools=[...])

        # 自定义场景
        provider = MockProvider(scenarios=[...])
    """

    def __init__(
        self,
        scenarios: list[Scenario] | None = None,
        default_response: str = "I understand. Let me help you with that.",
        error_on_turn: dict[int, Exception] | None = None,
        delay_seconds: float = 0.0,
    ):
        self.scenarios = scenarios or list(BUILTIN_SCENARIOS)
        self.default_response = default_response
        self.error_on_turn = error_on_turn or {}
        self.delay_seconds = delay_seconds
        self._turn_counter = 0
        self._call_log: list[list[Message]] = []

    def _find_scenario(self, messages: list[Message], turn_index: int) -> Scenario | None:
        # Sort by specificity: scenarios with turn_index or longer trigger patterns first
        def specificity(s: Scenario) -> tuple[int, int]:
            has_turn = 1 if s.turn_index is not None else 0
            max_pat = max((len(p) for p in s.trigger_patterns), default=0)
            return (has_turn, max_pat)
        ranked = sorted(self.scenarios, key=specificity, reverse=True)
        for scenario in ranked:
            if scenario.matches(messages, turn_index):
                return scenario
        return None

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        tool_choice: str = "auto",
    ) -> ProviderResponse:
        """模拟 LLM 调用，返回预设响应。"""
        import asyncio

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self._turn_counter in self.error_on_turn:
            raise self.error_on_turn[self._turn_counter]

        self._call_log.append(messages)

        scenario = self._find_scenario(messages, self._turn_counter)
        turn = self._turn_counter
        self._turn_counter += 1

        if scenario is not None:
            return scenario.response_factory(messages, turn)

        return _text_response(self.default_response)

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> AsyncGenerator:
        """模拟流式 — 逐 token 产出。"""
        import asyncio
        from src.agent_v2.types import TextBlock as _TB, ThinkingBlock as _THB, ToolUseBlock as _TUB
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self._turn_counter in self.error_on_turn:
            raise self.error_on_turn[self._turn_counter]

        self._call_log.append(messages)
        scenario = self._find_scenario(messages, self._turn_counter)
        turn = self._turn_counter
        self._turn_counter += 1

        response = scenario.response_factory(messages, turn) if scenario is not None else _text_response(self.default_response)

        # Emit each content block as a stream event
        for block in response.blocks:
            if isinstance(block, _TB):
                # Simulate token-by-token streaming: split text into word tokens
                words = block.text.split(" ")
                for i, w in enumerate(words):
                    token = w + (" " if i < len(words) - 1 else "")
                    yield _TB(text=token)
                    await asyncio.sleep(0.001)
            elif isinstance(block, _THB):
                yield block
            elif isinstance(block, _TUB):
                yield block

        if response.usage.total() > 0:
            yield response.usage

        # Final assembled response
        yield response

    @property
    def turn_counter(self) -> int:
        return self._turn_counter

    @property
    def call_log(self) -> list[list[Message]]:
        return list(self._call_log)

    def reset(self) -> None:
        self._turn_counter = 0
        self._call_log.clear()
