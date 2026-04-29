"""LLM-driven dynamic tool generator — generates and registers new tools at runtime.

Core flow:
1. User/Agent describes a task they need a tool for
2. ToolGenerator asks the LLM to produce a tool spec (name, description, parameter schema)
3. A ToolDefinition is created whose fn body delegates to the LLM (sub-agent pattern)
4. The tool is registered into the ToolRegistry, immediately available to the Agent

Security: generated tools never exec Python code directly — they delegate to the LLM,
which stays within its own safety boundary.

版权声明: 本模块属于 Scholar Assistant Agent 子系统。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.agent.llm_client import LLMClient
from src.agent.tools.core import ToolDefinition, ToolRegistry

logger = logging.getLogger(__name__)

_GENERATION_PROMPT = """\
你是一个工具设计专家。请根据以下任务描述，生成一个工具的 JSON 定义。

任务描述: {task_description}
{extra_context}
请严格按照以下 JSON 格式输出，不要包含其他内容:
{{
  "name": "tool_name (snake_case, 简短有意义的英文名)",
  "description": "工具功能的简明描述（一句话，中文）",
  "parameters": {{
    "type": "object",
    "properties": {{
      "param1": {{"type": "string", "description": "参数1说明"}},
      "param2": {{"type": "integer", "description": "参数2说明"}}
    }},
    "required": ["param1"]
  }},
  "implementation_hint": "说明这个工具应该如何用 LLM 实现其逻辑，包括 prompt 模板和输出处理方式"
}}

要求:
1. name 必须是有效的 Python 标识符 (snake_case)
2. parameters 必须是合法的 JSON Schema
3. description 应简洁明确，便于 LLM 在推理时判断是否应调用
4. implementation_hint 应清晰描述 LLM 需要执行的具体步骤
"""

_RESOLVE_PROMPT = """\
你是一个工具执行引擎。请根据以下工具定义和参数执行任务，只输出结果文本。

工具名称: {tool_name}
工具描述: {tool_description}
执行意图: {implementation_hint}

调用参数:
{arguments}

请直接输出执行结果，不要解释过程。"""


class ToolGenerator:
    """LLM-driven dynamic tool generator.

    Generates new tools by asking the LLM to produce a tool spec (name,
    description, parameters JSON Schema), then creates a ToolDefinition whose
    fn body delegates to the LLM as a sub-agent call.

    Args:
        llm: LLMClient used for both spec generation and tool execution.
        registry: Target ToolRegistry to register generated tools into.
    """

    def __init__(self, llm: LLMClient, registry: ToolRegistry) -> None:
        self._llm = llm
        self._registry = registry

    def generate(
        self,
        task_description: str,
        llm_request: str | list[dict] | None = None,
    ) -> ToolDefinition | None:
        """Ask the LLM to generate a tool spec from a task description.

        Args:
            task_description: What the tool should do.
            llm_request: Extra context for the LLM — either a string appended
                to the generation prompt, or a list of prior message dicts
                (role/content) prepended before the generation prompt.

        Returns:
            ToolDefinition, or None if generation fails.
        """
        extra_context = ""
        if isinstance(llm_request, str) and llm_request:
            extra_context = f"\n附加上下文:\n{llm_request}\n"
        elif isinstance(llm_request, list) and llm_request:
            parts = []
            for msg in llm_request:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    parts.append(f"[{role}] {content}")
            if parts:
                extra_context = f"\n对话上下文:\n{chr(10).join(parts)}\n"

        prompt = _GENERATION_PROMPT.format(
            task_description=task_description,
            extra_context=extra_context,
        )
        raw = self._llm.call_simple_sync(prompt)
        spec = self._parse_spec(raw)
        if spec is None:
            logger.warning("工具生成失败: 无法解析 LLM 输出")
            return None

        name = spec["name"]
        description = spec["description"]
        parameters = spec["parameters"]
        hint = spec.get("implementation_hint", description)

        return self._build_tool(name, description, parameters, hint)

    def generate_and_register(
        self,
        task_description: str,
        llm_request: str | list[dict] | None = None,
    ) -> ToolDefinition | None:
        """Generate a tool and register it into the registry.

        Args:
            task_description: What the tool should do.
            llm_request: Extra context for the LLM — string or message list.

        Returns:
            Registered ToolDefinition, or None on failure.
        """
        td = self.generate(task_description, llm_request=llm_request)
        if td is not None:
            self._registry.register(td, overwrite=True)
            logger.info("动态工具已注册: %s", td.name)
        return td

    def _build_tool(
        self,
        name: str,
        description: str,
        parameters: dict,
        implementation_hint: str,
    ) -> ToolDefinition:
        """Build a ToolDefinition whose fn delegates to the LLM."""
        llm = self._llm

        def generated_fn(**kwargs: Any) -> str:
            args_str = json.dumps(kwargs, ensure_ascii=False, indent=2)
            prompt = _RESOLVE_PROMPT.format(
                tool_name=name,
                tool_description=description,
                implementation_hint=implementation_hint,
                arguments=args_str,
            )
            return llm.call_simple_sync(prompt)

        generated_fn.__name__ = name
        generated_fn.__doc__ = description

        return ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            fn=generated_fn,
        )

    @staticmethod
    def _parse_spec(raw: str) -> dict | None:
        """Extract the JSON tool spec from LLM output."""
        # Strip <think/> blocks (Qwen3 reasoning)
        cleaned = re.sub(r"<think.*?>.*?</think.*?>", "", raw, flags=re.DOTALL).strip()

        # Direct parse
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Markdown code block
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # First { ... } block
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None


__all__ = ["ToolGenerator"]
