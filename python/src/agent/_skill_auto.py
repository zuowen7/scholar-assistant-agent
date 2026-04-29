"""Skill auto-generation mixin — nudge, pattern tracking, auto-generate, trajectory, context."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from src.agent._skill_model import SKILL_NUDGE_INTERVAL, Skill

logger = logging.getLogger(__name__)


class SkillAutoMixin:
    """Mixin providing auto-generation, nudge, and context for SkillRegistry."""

    # Typed stubs for attributes provided by SkillRegistry.__init__
    skills_dir: object  # Path
    _skills: dict[str, Skill]
    _iters_since_skill: int
    _patterns: dict[str, list[dict]]
    _auto_generated: set[str]

    # From other mixins
    def create_skill(self, name: str, trigger: str, description: str,
                     steps: list[str], notes: list[str] | None = None) -> Skill: ...
    def increment_use(self, name: str) -> None: ...
    def list_skills(self) -> list[Skill]: ...
    def match(self, query: str) -> Skill | None: ...

    # 同模式重复 N 次后自动生成 Skill
    _AUTO_SKILL_THRESHOLD = 3

    # ------------------------------------------------------------------
    # 催促机制
    # ------------------------------------------------------------------

    def nudge_check(self) -> str | None:
        """检查是否需要催促 Agent 整理经验为 Skill。每次对话后调用。"""
        self._iters_since_skill += 1
        if self._iters_since_skill >= SKILL_NUDGE_INTERVAL:
            self._iters_since_skill = 0
            return (
                f"你已经连续 {SKILL_NUDGE_INTERVAL} 轮对话没有创建新的 Skill。"
                "请回顾最近的对话，看看是否有值得沉淀的经验模式，"
                "使用 create_skill 工具将其固化为可复用的 Skill。"
            )
        return None

    # ------------------------------------------------------------------
    # 模式追踪与自动生成
    # ------------------------------------------------------------------

    def record_pattern(
        self,
        query: str,
        task_title: str = "",
        success: bool = True,
        tools_used: list[str] | None = None,
        error_type: str | None = None,
    ) -> Skill | None:
        """记录一次任务执行模式，若同一模式重复 ≥3 次则自动生成 Skill。"""
        key = self._pattern_key(query, task_title)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "query": query[:200],
            "task_title": task_title[:200],
            "success": success,
            "tools_used": tools_used or [],
            "error_type": error_type,
        }
        self._patterns.setdefault(key, []).append(entry)

        if key in self._auto_generated:
            return None
        if len(self._patterns[key]) < self._AUTO_SKILL_THRESHOLD:
            return None
        if self._skills.get(key):
            return None

        return self._auto_generate_skill(key)

    @staticmethod
    def _pattern_key(query: str, task_title: str = "") -> str:
        """归一化查询/任务为模式键。"""
        raw = (task_title or query).strip().lower()
        raw = re.sub(r"/[^\s]+", "", raw)
        raw = re.sub(r"\d{4}-\d{2}-\d{2}", "", raw)
        raw = re.sub(r"\d+", "", raw)
        raw = re.sub(r"[#<>:\"/\\|?*\s]+", "_", raw).strip("_")
        return f"pat_{raw[:60]}"

    def _auto_generate_skill(self, key: str) -> Skill | None:
        """根据重复模式自动生成 Skill。"""
        entries = self._patterns.get(key, [])
        if len(entries) < self._AUTO_SKILL_THRESHOLD:
            return None

        successes = sum(1 for e in entries if e["success"])
        failures = sum(1 for e in entries if not e["success"])
        all_tools: list[str] = []
        all_errors: list[str] = []
        for e in entries:
            all_tools.extend(e["tools_used"])
            if e["error_type"]:
                all_errors.append(e["error_type"])

        tool_counts: dict[str, int] = {}
        for t in all_tools:
            tool_counts[t] = tool_counts.get(t, 0) + 1
        top_tools = sorted(tool_counts, key=tool_counts.get, reverse=True)[:5]

        sample_query = entries[0]["query"][:80]
        trigger = sample_query
        description = f"自动生成的技能: {sample_query[:40]}"

        steps: list[str] = []
        if top_tools:
            steps.append(f"优先使用工具: {', '.join(top_tools)}")
        if failures > 0:
            steps.append(f"注意: {failures}/{len(entries)} 次执行失败，常见错误: {', '.join(set(all_errors[:3]))}")

        notes = [
            f"此 Skill 由系统自动生成（{len(entries)} 次重复模式触发）",
            f"{successes} 次成功, {failures} 次失败",
            "建议人工审核后更新步骤和注意事项",
        ]

        skill_name = key.replace("pat_", "auto_")[:64]
        skill_name = re.sub(r"[#<>:\"/\\|?*]+", "_", skill_name).rstrip("._")
        skill = self.create_skill(
            name=skill_name,
            trigger=trigger,
            description=description,
            steps=steps,
            notes=notes,
        )
        self._auto_generated.add(key)
        logger.info("Skill 自动生成（模式重复 %d 次）: %s → %s", len(entries), key, skill_name)
        return skill

    # ------------------------------------------------------------------
    # Skill 上下文注入
    # ------------------------------------------------------------------

    def get_skill_context(self, query: str = "") -> str:
        """构建注入到 Prompt 的 Skill 上下文。"""
        if not query:
            skills = [s for s in self.list_skills() if not s.deprecated]
            if not skills:
                return ""
            lines = ["已积累的技能:"]
            for s in skills:
                lines.append(f"- {s.name}: {s.description or s.trigger}")
            return "\n".join(lines)

        matched = self.match(query)
        if matched:
            self.increment_use(matched.name)
            parts = [f"匹配到技能「{matched.description or matched.name}」:"]
            if matched.steps:
                for i, step in enumerate(matched.steps, 1):
                    parts.append(f"  {i}. {step}")
            if matched.notes:
                parts.append("  注意:")
                for note in matched.notes:
                    parts.append(f"    - {note}")
            return "\n".join(parts)

        return ""

    # ------------------------------------------------------------------
    # 从轨迹生成 Skill（供 review_agent 调用）
    # ------------------------------------------------------------------

    def generate_from_trajectory(self, trajectory_data: dict) -> Skill | None:
        """从任务轨迹数据中生成新的 Skill。

        轨迹数据需包含 conversations 和 metadata。
        """
        metadata = trajectory_data.get("metadata", {})
        conversations = trajectory_data.get("conversations", [])

        if len(conversations) < 3:
            return None

        tool_calls: list[str] = []
        for conv in conversations:
            content = conv.get("value", "")
            if "调用工具" in content or "tool" in conv.get("from", ""):
                tool_calls.append(content[:100])

        if not tool_calls:
            return None

        query = metadata.get("query", "")
        trigger = query[:50] if query else ""

        name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return Skill(
            name=name,
            trigger=trigger,
            description=f"自动生成的技能（基于: {trigger[:30]}）",
            steps=[f"参考轨迹中的工具调用: {tc}" for tc in tool_calls[:5]],
            notes=["此 Skill 由系统自动生成，建议人工审核后更新"],
            created_at=datetime.now().strftime("%Y-%m-%d"),
            updated_at=datetime.now().strftime("%Y-%m-%d"),
        )
