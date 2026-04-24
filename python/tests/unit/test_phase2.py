"""Phase 2 单元测试 — memory, trajectory, skill_system, review_agent。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.memory import MemoryManager, MemoryEntry
from src.agent.skill_system import Skill, SkillRegistry, SKILL_NUDGE_INTERVAL
from src.agent.trajectory import Trajectory, TrajectoryRecorder, TrajectoryTurn


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

class TestMemoryManager:

    def _tmpdir(self):
        return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def test_init_creates_db(self):
        with self._tmpdir() as tmp:
            mgr = MemoryManager(data_dir=tmp)
            assert (Path(tmp) / "memory.db").exists()
            assert (Path(tmp) / "MEMORY.md").parent == Path(tmp)

    def test_memory_file_roundtrip(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.save_memory_file("用户偏好中文")
            assert mgr.load_memory_file() == "用户偏好中文"

    def test_memory_file_nonexistent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            assert mgr.load_memory_file() == ""

    def test_memory_file_truncation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.save_memory_file("x" * 10000)
            content = mgr.load_memory_file()
            assert "截断" in content
            assert len(content) < 10000

    def test_append_to_memory_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.save_memory_file("第一行")
            mgr.append_to_memory_file("第二行")
            content = mgr.load_memory_file()
            assert "第一行" in content
            assert "第二行" in content

    def test_add_and_search_memory(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.add_memory("翻译学术论文时保留 LaTeX 公式", category="experience")
            mgr.add_memory("用户偏好使用 Qwen3 模型", category="preference")
            results = mgr.search_memories("翻译")
            assert len(results) == 1
            assert "LaTeX" in results[0].content

    def test_search_no_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.add_memory("测试记忆")
            results = mgr.search_memories("不存在的关键词")
            assert len(results) == 0

    def test_get_recent_memories(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.add_memory("记忆1")
            mgr.add_memory("记忆2")
            results = mgr.get_recent_memories(limit=1)
            assert len(results) == 1
            assert results[0].content == "记忆2"

    def test_get_memory_context_with_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.save_memory_file("长期记忆内容")
            ctx = mgr.get_memory_context()
            assert "长期记忆" in ctx

    def test_get_memory_context_with_query(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.add_memory("翻译相关经验")
            ctx = mgr.get_memory_context(query="翻译")
            assert "翻译相关经验" in ctx

    def test_save_and_get_conversations(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.save_conversation("帮我翻译", "翻译结果", success=True)
            convs = mgr.get_recent_conversations(limit=1)
            assert len(convs) == 1
            assert convs[0]["query"] == "帮我翻译"
            assert convs[0]["success"] is True

    def test_get_stats(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            mgr = MemoryManager(data_dir=tmp)
            mgr.add_memory("test")
            mgr.save_conversation("q", "a")
            stats = mgr.get_stats()
            assert stats["memories_count"] == 1
            assert stats["conversations_count"] == 1


# ---------------------------------------------------------------------------
# TrajectoryRecorder
# ---------------------------------------------------------------------------

class TestTrajectoryRecorder:

    def test_start_and_finish(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            recorder = TrajectoryRecorder(data_dir=tmp)
            traj = recorder.start("测试查询", model="test")
            recorder.add_turn("user", "测试查询")
            recorder.add_turn("tool", "结果", tool_name="test_tool", duration_ms=100)
            result = recorder.finish("最终回答", success=True)
            assert result is not None
            assert result.success is True
            assert result.query == "测试查询"
            assert len(result.turns) == 2

    def test_finish_without_start(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            recorder = TrajectoryRecorder(data_dir=tmp)
            result = recorder.finish("回答", success=True)
            assert result is None

    def test_jsonl_saved(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            recorder = TrajectoryRecorder(data_dir=tmp)
            recorder.start("查询")
            recorder.add_turn("user", "查询")
            recorder.finish("回答", success=True)
            success_file = Path(tmp) / "success.jsonl"
            assert success_file.exists()
            line = success_file.read_text(encoding="utf-8").strip()
            data = json.loads(line)
            assert "conversations" in data
            assert "metadata" in data

    def test_failed_trajectory(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            recorder = TrajectoryRecorder(data_dir=tmp)
            recorder.start("失败查询")
            recorder.finish("", success=False)
            failed_file = Path(tmp) / "failed.jsonl"
            assert failed_file.exists()

    def test_sharegpt_format(self):
        traj = Trajectory(
            query="test",
            turns=[
                TrajectoryTurn(role="user", content="hello"),
                TrajectoryTurn(role="assistant", content="hi"),
            ],
            final_answer="done",
        )
        sg = traj.to_sharegpt()
        assert len(sg) == 3
        assert sg[0]["from"] == "human"
        assert sg[1]["from"] == "gpt"
        assert sg[2]["from"] == "gpt"
        assert sg[2]["value"] == "done"

    def test_get_recent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            recorder = TrajectoryRecorder(data_dir=tmp)
            recorder.start("查询1")
            recorder.finish("回答1", success=True)
            recorder.start("查询2")
            recorder.finish("", success=False)
            recent = recorder.get_recent(limit=5)
            assert len(recent) == 2


# ---------------------------------------------------------------------------
# SkillRegistry
# ---------------------------------------------------------------------------

class TestSkill:

    def test_to_markdown(self):
        skill = Skill(
            name="test_skill",
            trigger="测试触发",
            description="测试技能",
            steps=["步骤1", "步骤2"],
            notes=["注意1"],
            created_at="2026-04-24",
        )
        md = skill.to_markdown()
        assert "name: test_skill" in md
        assert "步骤1" in md
        assert "注意1" in md
        assert "# 测试技能" in md


class TestSkillRegistry:

    def test_create_and_get(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill(
                name="translate_paper",
                trigger="翻译论文, 学术翻译",
                description="翻译学术论文",
                steps=["解析文档", "逐段翻译", "合并结果"],
            )
            skill = registry.get("translate_paper")
            assert skill is not None
            assert skill.name == "translate_paper"
            assert len(skill.steps) == 3

    def test_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill(
                name="translate_paper",
                trigger="翻译论文, 学术翻译",
                description="翻译学术论文",
                steps=["步骤1"],
            )
            matched = registry.match("帮我翻译这篇学术论文")
            assert matched is not None
            assert matched.name == "translate_paper"

    def test_no_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            assert registry.match("随机查询") is None

    def test_nudge_check(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            # 前 N-1 次不应催促
            for _ in range(SKILL_NUDGE_INTERVAL - 1):
                assert registry.nudge_check() is None
            # 第 N 次应催促
            result = registry.nudge_check()
            assert result is not None
            assert "Skill" in result

    def test_skill_context_with_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill(
                name="test",
                trigger="测试",
                description="测试技能",
                steps=["步骤1"],
            )
            ctx = registry.get_skill_context("帮我测试一下")
            assert "测试技能" in ctx
            assert "步骤1" in ctx

    def test_skill_context_no_match(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill(
                name="test",
                trigger="测试",
                description="测试技能",
                steps=["步骤1"],
            )
            ctx = registry.get_skill_context("完全不相关的查询")
            assert ctx == ""

    def test_load_from_disk(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            # 创建第一个 registry 并保存 skill
            r1 = SkillRegistry(skills_dir=tmp)
            r1.create_skill("test_skill", "触发", "描述", ["步骤1"])

            # 创建第二个 registry 从磁盘加载
            r2 = SkillRegistry(skills_dir=tmp)
            skill = r2.get("test_skill")
            assert skill is not None
            assert skill.name == "test_skill"

    def test_generate_from_trajectory(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            traj = {
                "conversations": [
                    {"from": "human", "value": "翻译论文"},
                    {"from": "gpt", "value": "调用工具 translate_text"},
                    {"from": "tool", "value": "翻译结果"},
                ],
                "metadata": {"query": "翻译论文"},
            }
            skill = registry.generate_from_trajectory(traj)
            assert skill is not None

    def test_generate_from_short_trajectory(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            traj = {"conversations": [{"from": "human", "value": "hi"}], "metadata": {}}
            assert registry.generate_from_trajectory(traj) is None

    def test_update_skill(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill("test", "触发", "描述", ["步骤1"])
            updated = registry.update_skill("test", description="新描述", steps=["新步骤"])
            assert updated is not None
            assert updated.description == "新描述"

    def test_update_nonexistent(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            assert registry.update_skill("不存在") is None

    def test_increment_use(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            registry = SkillRegistry(skills_dir=tmp)
            registry.create_skill("test", "触发", "描述", ["步骤1"])
            registry.increment_use("test")
            skill = registry.get("test")
            assert skill.use_count == 1
