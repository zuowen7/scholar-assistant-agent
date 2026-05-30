"""PromptBuilder 单元测试。

覆盖范围：
- 工具描述自动提取
- 模型适配指导（qwen/gpt/gemini/未知模型）
- MEMORY.md 文件加载
- 完整 build 流程
- PromptConfig 各字段组合
- estimate_prompt_tokens
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.agent.prompt_builder import (
    PromptBuilder,
    PromptConfig,
    _AGENT_IDENTITY,
    _MODEL_TOOL_GUIDES,
    _REACT_INSTRUCTION,
)
from src.agent.tools import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _make_registry() -> ToolRegistry:
    """创建包含 2 个测试工具的注册表。"""
    registry = ToolRegistry()

    def tool_a(text: str) -> str:
        """工具A描述。"""
        return text

    tool_a._agent_tool_def = ToolDefinition(
        name="tool_a",
        description="工具A描述",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        fn=tool_a,
    )
    registry.register(tool_a)

    def tool_b(query: str, top_k: int = 5) -> str:
        """工具B描述。"""
        return query

    tool_b._agent_tool_def = ToolDefinition(
        name="tool_b",
        description="工具B描述",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        fn=tool_b,
    )
    registry.register(tool_b)

    return registry


# ---------------------------------------------------------------------------
# 工具描述自动提取
# ---------------------------------------------------------------------------

class TestBuildToolsSection:

    def test_tools_listed(self):
        registry = _make_registry()
        builder = PromptBuilder(tool_registry=registry)
        section = builder._build_tools_section()
        assert "tool_a" in section
        assert "tool_b" in section
        assert "工具A描述" in section

    def test_parameters_shown(self):
        registry = _make_registry()
        builder = PromptBuilder(tool_registry=registry)
        section = builder._build_tools_section()
        assert "text: string" in section
        assert "top_k: integer(可选)" in section

    def test_no_registry(self):
        builder = PromptBuilder()
        assert builder._build_tools_section() == ""

    def test_empty_registry(self):
        builder = PromptBuilder(tool_registry=ToolRegistry())
        assert builder._build_tools_section() == ""


# ---------------------------------------------------------------------------
# 模型适配指导
# ---------------------------------------------------------------------------

class TestGetModelGuide:

    def test_qwen_model(self):
        builder = PromptBuilder()
        guide = builder._get_model_guide("qwen3:8b")
        assert "工具使用注意事项" in guide

    def test_gpt_model(self):
        builder = PromptBuilder()
        guide = builder._get_model_guide("gpt-4o")
        assert "必须使用工具" in guide

    def test_gemini_model(self):
        builder = PromptBuilder()
        guide = builder._get_model_guide("gemini-2.0-flash")
        assert "绝对路径" in guide

    def test_unknown_model_gets_default_guide(self):
        builder = PromptBuilder()
        guide = builder._get_model_guide("unknown-model")
        assert guide != ""
        assert "工具使用注意事项" in guide

    def test_empty_model_returns_empty(self):
        builder = PromptBuilder()
        assert builder._get_model_guide("") == ""

    @pytest.mark.parametrize("model_name", [
        "moonshot-v1-8k",
        "glm-4-plus",
        "Qwen/Qwen3-235B-A22B",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "mistral-large-latest",
        "grok-2-latest",
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "sonar",
        "sonar-pro",
        "meta-llama/llama-3.1-70b-instruct",
        "doubao-pro-32k",
        "ernie-4.0-8k",
        "grok-2-vision-latest",
    ])
    def test_uncovered_provider_models_get_default_guide(self, model_name):
        builder = PromptBuilder()
        guide = builder._get_model_guide(model_name)
        assert guide != "", f"{model_name} should get a default guide, not empty"
        assert "工具使用注意事项" in guide

    def test_known_models_still_get_specific_guide(self):
        builder = PromptBuilder()
        assert "严禁在同一轮对话中多次调用同一个工具" in builder._get_model_guide("qwen3:8b")
        assert "执行后验证结果是否正确" in builder._get_model_guide("gpt-4o")
        assert "不要以" in builder._get_model_guide("deepseek-v4-pro")
        assert "绝对路径" in builder._get_model_guide("gemini-2.0-flash")


# ---------------------------------------------------------------------------
# MEMORY.md 加载
# ---------------------------------------------------------------------------

class TestLoadMemoryFile:

    def test_load_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Memory\n用户偏好中文回复")
            f.flush()
            builder = PromptBuilder(memory_file=f.name)
            content = builder._load_memory_file()
            assert "用户偏好中文回复" in content

    def test_nonexistent_file(self):
        builder = PromptBuilder(memory_file="/nonexistent/MEMORY.md")
        assert builder._load_memory_file() == ""

    def test_no_memory_file(self):
        builder = PromptBuilder()
        assert builder._load_memory_file() == ""

    def test_large_file_truncated(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("x" * 10000)
            f.flush()
            builder = PromptBuilder(memory_file=f.name)
            content = builder._load_memory_file()
            assert "截断" in content
            assert len(content) < 10000


# ---------------------------------------------------------------------------
# 完整 build 流程
# ---------------------------------------------------------------------------

class TestBuild:

    def test_minimal_config(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig())
        assert _AGENT_IDENTITY.split("\n")[0] in prompt
        assert _REACT_INSTRUCTION[:10] in prompt

    def test_with_tools(self):
        registry = _make_registry()
        builder = PromptBuilder(tool_registry=registry)
        prompt = builder.build(PromptConfig())
        assert "tool_a" in prompt
        assert "tool_b" in prompt

    def test_with_known_model(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(model_name="qwen3:8b"))
        assert "严禁在同一轮对话中多次调用同一个工具" in prompt

    def test_with_unknown_model_includes_default_guide(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(model_name="moonshot-v1-8k"))
        assert "工具使用注意事项" in prompt

    def test_with_memory(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(memory_content="用户喜欢简洁回复"))
        assert "<memory-context>" in prompt
        assert "用户喜欢简洁回复" in prompt

    def test_with_doc_context(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(doc_context="当前论文: Attention Is All You Need"))
        assert "<doc-context>" in prompt
        assert "Attention Is All You Need" in prompt

    def test_with_extra_sections(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(
            extra_sections={"安全约束": "不要执行危险命令"},
        ))
        assert "安全约束" in prompt
        assert "不要执行危险命令" in prompt

    def test_timestamp_present(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig())
        assert "当前时间:" in prompt

    def test_all_sections_combined(self):
        registry = _make_registry()
        builder = PromptBuilder(tool_registry=registry)
        prompt = builder.build(PromptConfig(
            model_name="qwen3:8b",
            memory_content="偏好中文",
            doc_context="论文上下文",
            extra_sections={"额外": "信息"},
        ))
        assert "tool_a" in prompt
        assert "工具使用注意事项" in prompt
        assert "偏好中文" in prompt
        assert "论文上下文" in prompt
        assert "额外" in prompt

    def test_custom_identity(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(identity="你是翻译专家"))
        assert "你是翻译专家" in prompt

    def test_empty_identity_skipped(self):
        builder = PromptBuilder()
        prompt = builder.build(PromptConfig(identity=""))
        # 身份为空时不应出现默认身份
        assert _AGENT_IDENTITY.split("\n")[0] not in prompt


# ---------------------------------------------------------------------------
# estimate_prompt_tokens
# ---------------------------------------------------------------------------

class TestEstimatePromptTokens:

    def test_returns_positive(self):
        builder = PromptBuilder()
        tokens = builder.estimate_prompt_tokens(PromptConfig())
        assert tokens > 0

    def test_more_content_more_tokens(self):
        builder = PromptBuilder()
        small = builder.estimate_prompt_tokens(PromptConfig())
        big = builder.estimate_prompt_tokens(PromptConfig(
            memory_content="x" * 1000,
            doc_context="y" * 1000,
        ))
        assert big > small
