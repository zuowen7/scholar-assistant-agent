"""Agent 子系统评测基准 — 验证核心行为修复和 Agent 能力边界。

覆盖:
  - Memory / Skill 注入 (缺口 1 & 2 修复验证)
  - python_exec 沙盒 (安全加固 + subprocess 隔离验证)
  - Memory 模糊去重 + 上限修剪
  - Skill 质量门槛
  - SkillRegistry 并发安全
  - ReviewAgent 事件循环
  - Task 分解
  - Shell git 子命令白名单
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(name="test_skill", trigger="测试触发", steps=None):
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
    tmp = tempfile.mkdtemp()
    from src.agent.memory import MemoryManager
    mm = MemoryManager(data_dir=tmp)
    mm.memory_file.write_text(memory_text, encoding="utf-8")
    return mm


def _make_skill_registry(skill=None):
    tmp = tempfile.mkdtemp()
    from src.agent.skill_system import SkillRegistry
    sr = SkillRegistry(skills_dir=tmp)
    if skill is not None:
        sr._skills[skill.name] = skill
    return sr


def _make_agent_loop(memory_manager=None, skill_registry=None):
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
    def test_memory_injected_when_present(self):
        mm = _make_memory_manager("用户偏好中文回复，重视简洁")
        agent = _make_agent_loop(memory_manager=mm)
        msgs = agent._build_messages("帮我翻译")
        assert "用户偏好中文回复" in msgs[0].content

    def test_memory_not_crashes_on_empty_file(self):
        mm = _make_memory_manager("")
        agent = _make_agent_loop(memory_manager=mm)
        msgs = agent._build_messages("任意查询")
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
    def test_skill_injected_on_match(self):
        skill = _make_skill(trigger="翻译,translate,学术")
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        msgs = agent._build_messages("帮我翻译这篇学术论文")
        assert "可用技能指导" in msgs[0].content
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

    def test_deprecated_skill_not_injected(self):
        skill = _make_skill(trigger="翻译")
        skill.deprecated = True
        sr = _make_skill_registry(skill=skill)
        agent = _make_agent_loop(skill_registry=sr)
        msgs = agent._build_messages("帮我翻译")
        assert "可用技能指导" not in msgs[0].content


# ===========================================================================
# 3. python_exec sandbox (subprocess-isolated)
# ===========================================================================

class TestPythonExecSandbox:
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

    def test_timeout_actually_kills(self):
        """Verify subprocess-based timeout truly terminates the process."""
        from src.agent.tools.atomic_tools import _python_exec
        result = _python_exec("while True: pass", timeout=2)
        assert "超时" in result

    def test_output_truncated(self):
        result = self._exec("print('x' * 100000)")
        assert "截断" in result or len(result) < 100000


# ===========================================================================
# 4. Memory fuzzy dedup + pruning
# ===========================================================================

class TestMemoryDedupAndPruning:
    def test_exact_duplicate_rejected(self):
        mm = _make_memory_manager()
        id1 = mm.add_memory("完全相同的内容条目", category="fact", importance=0.7)
        id2 = mm.add_memory("完全相同的内容条目", category="fact", importance=0.7)
        assert id1 > 0
        assert id2 == 0

    def test_fuzzy_duplicate_rejected(self):
        mm = _make_memory_manager()
        mm.add_memory("用户偏好使用中文回复，要求简洁明了", category="experience", source="review", importance=0.8)
        id2 = mm.add_memory("用户偏好使用中文回复，要求简洁明了，不要啰嗦", category="experience", source="review", importance=0.8)
        assert id2 == 0, "高度相似的条目应被模糊去重拒绝"

    def test_different_content_accepted(self):
        mm = _make_memory_manager()
        id1 = mm.add_memory("用户偏好中文回复", category="preference", importance=0.8)
        id2 = mm.add_memory("工具 python_exec 需要超时保护", category="fact", importance=0.6)
        assert id1 > 0
        assert id2 > 0

    def test_auto_prune_triggers_on_overflow(self):
        mm = _make_memory_manager()
        from src.agent.memory import _MEMORY_MAX_ROWS
        # Insert more than max rows with low importance
        for i in range(_MEMORY_MAX_ROWS + 10):
            mm.add_memory(f"低重要性记忆条目编号{i:04d}内容是关于一些不重要的事情", category="fact", importance=0.2)
        stats = mm.get_stats()
        assert stats["memories_count"] <= _MEMORY_MAX_ROWS, "应自动修剪低重要性记忆"


# ===========================================================================
# 5. SkillRegistry thread safety
# ===========================================================================

class TestSkillRegistryConcurrency:
    def test_concurrent_create_skill(self):
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
# 6. ReviewAgent event loop
# ===========================================================================

class TestReviewAgentEventLoop:
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
            task.cancel()

        asyncio.run(_run())


# ===========================================================================
# 7. Task decomposition
# ===========================================================================

class TestTaskDecomposition:
    def _decompose(self, query: str):
        from src.agent.session import AgentSession
        return AgentSession._decompose_query(query)

    def test_numbered_list_decomposition(self):
        result = self._decompose("1. 翻译论文 2. 润色文字 3. 导出PDF")
        assert result is not None
        assert len(result) >= 2

    def test_semicolon_decomposition(self):
        result = self._decompose("翻译论文；润色文字；导出PDF")
        assert result is not None
        assert len(result) >= 2

    def test_connector_decomposition(self):
        result = self._decompose("翻译论文然后润色文字接着导出PDF最后检查格式")
        assert result is not None
        assert len(result) >= 3

    def test_simple_query_no_decomposition(self):
        result = self._decompose("帮我翻译这段文字")
        assert result is None

    def test_short_query_no_decomposition(self):
        result = self._decompose("翻译")
        assert result is None


# ===========================================================================
# 8. Shell git subcommand restriction
# ===========================================================================

class TestShellGitRestriction:
    def _exec(self, command: str) -> str:
        from src.agent.tools.atomic_tools import _shell_exec
        return _shell_exec(command)

    def test_git_status_allowed(self):
        result = self._exec("git status")
        # May fail if not in a git repo, but should NOT say "不在白名单中"
        assert "不在白名单中" not in result
        assert "子命令" not in result

    def test_git_log_allowed(self):
        result = self._exec("git log --oneline -5")
        assert "子命令" not in result

    def test_git_push_blocked(self):
        result = self._exec("git push origin main")
        assert "子命令" in result or "不在白名单中" in result

    def test_git_reset_blocked(self):
        result = self._exec("git reset --hard HEAD~1")
        assert "子命令" in result or "不在白名单中" in result

    def test_git_clean_blocked(self):
        result = self._exec("git clean -fdx")
        assert "子命令" in result or "不在白名单中" in result
