"""Agent 子系统评测基准 — 验证核心行为修复和 Agent 能力边界。

覆盖三类场景 (10 用例):
  - Memory / Skill 注入 (缺口 1 & 2 修复验证)
  - python_exec 沙盒 (安全加固验证)
  - Agent 消息构建 / 提示词组装 (整合验证)
"""

from __future__ import annotations

import asyncio
import re
import threading
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(name="test_skill", trigger="测试触发", steps=None):
    """Create a minimal Skill object without touching the filesystem."""
    from src.agent._skill_model import Skill
    return Skill(
        name=name,
        trigger=trigger,
        description="测试技能描述",
        steps=steps or ["步骤一", "步骤二"],
        notes=["注意事项一"],
        created_at="2025-01-01",
        updated_at="2025-01-01",
    )


def _make_memory_manager(memory_text="长期记忆内容"):
    """Create a MemoryManager with mocked DB (in-memory) and preset MEMORY.md."""
    import tempfile, os
    tmp = tempfile.mkdtemp()
    from src.agent.memory import MemoryManager
    mm = MemoryManager(data_dir=tmp)
    mm.memory_file.write_text(memory_text, encoding="utf-8")
    return mm


def _make_skill_registry(skill=None):
    """Create a SkillRegistry backed by a temp dir, optionally pre-populated."""
    import tempfile
    tmp = tempfile.mkdtemp()
    from src.agent.skill_system import SkillRegistry
    sr = SkillRegistry(skills_dir=tmp)
    if skill is not None:
        # Directly inject without file I/O for speed
        sr._skills[skill.name] = skill
    return sr


def _make_agent_loop(memory_manager=None, skill_registry=None):
    """Create a minimal AgentLoop with mocked LLM."""
    from src.agent.agent import AgentLoop
    from src.agent.prompt_builder import PromptBuilder
    from src.agent.tools import ToolRegistry

    loop = AgentLoop.__new__(AgentLoop)
    loop.model = "test-model"
    loop.system_prompt = ""
    loop.tool_registry = ToolRegistry()
    loop.prompt_builder = PromptBuilder(tool_registry=loop.tool_registry)
    loop.memory = memory_manager
    loop.skills = skill_registry
    loop.rag_store = None
    loop.rag_top_k = 3
    loop._scratchpad = {}
    loop._scratchpad_step = 0
    return loop


# ===========================================================================
# 1. Memory injection
# ===========================================================================

class TestMemoryInjection:
    """缺口 2 修复: memory_content 正确注入 system prompt。"""

    def test_memory_injected_when_present(self):
        mm = _make_memory_manager("用户偏好中文回复，重视简洁")
        agent = _make_agent_loop(memory_manager=mm)
        msgs = agent._build_messages("帮我翻译")
        system_content = msgs[0].content
        assert "用户偏好中文回复" in system_content, "长期记忆应被注入 system prompt"

    def test_memory_not_crashes_on_empty_file(self):
        mm = _make_memory_manager("")
        agent = _make_agent_loop(memory_manager=mm)
        msgs = agent._build_messages("任意查询")
        # No exception → pass
        assert msgs[0].role == "system"

    def test_no_memory_manager_still_works(self):
        agent = _make_agent_loop(memory_manager=None)
        msgs = agent._build_messages("查询")
        assert msgs[0].role == "system"

    def test_memory_section_wrapped_in_tag(self):
        mm = _make_memory_manager("关键背景知识")
        agent = _make_agent_loop(memory_manager=mm)
        msgs = agent._build_messages("查询")
        assert "<memory-context>" in msgs[0].content


# ===========================================================================
# 2. Skill injection
# ===========================================================================

class TestSkillInjection:
    """缺口 1 修复: 匹配到 Skill 时注入 active-skill 段落，并递增使用计数。"""

    def test_skill_injected_on_match(self):
        skill = _make_skill(trigger="翻译,translate,学术")
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        msgs = agent._build_messages("帮我翻译这篇学术论文")
        assert "可用技能指导" in msgs[0].content, "Skill 应被注入 system prompt"
        assert "步骤一" in msgs[0].content

    def test_skill_use_count_incremented(self):
        skill = _make_skill(trigger="翻译")
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        agent._build_messages("翻译这段内容")
        assert sr._skills[skill.name].use_count == 1

    def test_no_skill_match_no_injection(self):
        skill = _make_skill(trigger="图表,matplotlib")
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        msgs = agent._build_messages("帮我润色文字")
        assert "可用技能指导" not in msgs[0].content

    def test_no_skill_registry_still_works(self):
        agent = _make_agent_loop(skill_registry=None)
        msgs = agent._build_messages("查询")
        assert msgs[0].role == "system"

    def test_deprecated_skill_not_injected(self):
        skill = _make_skill(trigger="翻译")
        skill.deprecated = True
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        msgs = agent._build_messages("帮我翻译")
        assert "可用技能指导" not in msgs[0].content


# ===========================================================================
# 3. python_exec sandbox
# ===========================================================================

class TestPythonExecSandbox:
    """安全加固: 沙盒拦截 dunder 属性逃逸和 import 攻击。"""

    def _exec(self, code: str) -> str:
        from src.agent.tools.atomic_tools import _python_exec
        return _python_exec(code)

    def test_normal_code_runs(self):
        result = self._exec("print(sum([1, 2, 3]))")
        assert "6" in result

    def test_import_os_blocked(self):
        result = self._exec("import os; print(os.getcwd())")
        assert "禁止" in result

    def test_dunder_class_blocked(self):
        result = self._exec("x = []; print(x.__class__)")
        assert "禁止" in result

    def test_dunder_subclasses_blocked(self):
        result = self._exec("print(().__class__.__bases__[0].__subclasses__())")
        assert "禁止" in result

    def test_dunder_import_blocked(self):
        result = self._exec("__import__('os').system('whoami')")
        assert "禁止" in result

    def test_dunder_globals_blocked(self):
        result = self._exec("print(__globals__)")
        assert "禁止" in result


# ===========================================================================
# 4. SkillRegistry thread safety
# ===========================================================================

class TestSkillRegistryConcurrency:
    """并发安全: 多线程同时 create_skill 不崩溃，结果一致。"""

    def test_concurrent_create_skill(self):
        import tempfile
        from src.agent.skill_system import SkillRegistry

        sr = SkillRegistry(skills_dir=tempfile.mkdtemp())
        errors: list[Exception] = []

        def create(i: int):
            try:
                sr.create_skill(
                    name=f"skill_{i}",
                    trigger=f"触发{i}",
                    description=f"描述{i}",
                    steps=[f"步骤{i}"],
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发创建 Skill 出错: {errors}"
        assert len(sr._skills) == 10


# ===========================================================================
# 5. ReviewAgent event loop fix
# ===========================================================================

class TestReviewAgentEventLoop:
    """get_running_loop() 修复: spawn_review 在有运行循环时返回 Task，无循环时返回 None。"""

    def test_spawn_review_returns_none_outside_loop(self):
        from src.agent.review_agent import ReviewAgent
        ra = ReviewAgent()
        result = ra.spawn_review({"conversations": []})
        assert result is None

    def test_spawn_review_returns_task_inside_loop(self):
        from src.agent.review_agent import ReviewAgent
        ra = ReviewAgent()

        async def _run():
            task = ra.spawn_review({"conversations": []})
            assert task is not None
            assert asyncio.isfuture(task) or hasattr(task, "cancel")
            task.cancel()

        asyncio.run(_run())
