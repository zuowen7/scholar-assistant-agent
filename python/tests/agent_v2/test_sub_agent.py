"""Sub-agent 测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.agent_v2.tools.sub_agent import register_sub_agent, _PRESETS
from src.agent_v2.tools.registry import ToolRegistry
from src.agent_v2.providers.mock_provider import MockProvider


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg._provider = MockProvider()
    register_sub_agent(reg)
    return reg


class TestPresets:
    def test_all_presets_defined(self):
        assert "audit" in _PRESETS
        assert "explain" in _PRESETS
        assert "implement" in _PRESETS
        assert "translate" in _PRESETS

    def test_audit_prompt_has_checks(self):
        p = _PRESETS["audit"]
        assert "logical" in p.lower()
        assert "citation" in p.lower()

    def test_implement_prompt_is_directive(self):
        p = _PRESETS["implement"]
        assert "output" in p.lower() or "DO" in p

    def test_translate_prompt_preserves_terms(self):
        p = _PRESETS["translate"]
        assert "citation" in p.lower() or "term" in p.lower()


class TestSubAgentExecution:
    @pytest.mark.asyncio
    async def test_run_audit(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "audit",
            "content": "AI will replace all jobs.",
        })
        assert not result.is_error
        assert "[audit]" in result.output

    @pytest.mark.asyncio
    async def test_run_explain(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "explain",
            "content": "Quantum computing uses qubits.",
        })
        assert not result.is_error
        assert "[explain]" in result.output

    @pytest.mark.asyncio
    async def test_run_translate(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "translate",
            "content": "Machine learning is transforming science.",
        })
        assert not result.is_error
        assert "[translate]" in result.output

    @pytest.mark.asyncio
    async def test_with_instruction(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "implement",
            "content": "The cat sat on the mat.",
            "instruction": "Change 'cat' to 'dog'",
        })
        assert not result.is_error


class TestSubAgentEdge:
    @pytest.mark.asyncio
    async def test_unknown_preset(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "nonsense_preset_xyz",
            "content": "test",
        })
        assert result.is_error
        assert "unknown preset" in result.output.lower()

    @pytest.mark.asyncio
    async def test_empty_content(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "audit",
            "content": "",
        })
        assert result.is_error
        assert "content" in result.output.lower()

    @pytest.mark.asyncio
    async def test_no_provider(self):
        reg = ToolRegistry()
        register_sub_agent(reg)
        # No _provider set
        result = await reg.execute("run_sub_agent", {
            "preset": "audit",
            "content": "test",
        })
        assert result.is_error
        assert "provider" in result.output.lower()

    @pytest.mark.asyncio
    async def test_very_long_content(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "explain",
            "content": "test " * 5000,
        })
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_special_characters(self, registry: ToolRegistry):
        result = await registry.execute("run_sub_agent", {
            "preset": "audit",
            "content": "test \x00 null \U0001f600 中文 العربية",
        })
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_concurrent_sub_agents(self, registry: ToolRegistry):
        import asyncio
        results = await asyncio.gather(*[
            registry.execute("run_sub_agent", {"preset": "audit", "content": f"test {i}"})
            for i in range(5)
        ])
        for r in results:
            assert not r.is_error
            assert "[audit]" in r.output
