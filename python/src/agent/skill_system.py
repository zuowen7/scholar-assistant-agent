"""动态 Skill 系统 — 从任务轨迹中沉淀可复用经验。

Skill 是将 Agent 的"一次性执行"转化为"经验沉淀"的核心机制：
- 自动生成：从成功的任务轨迹中提取经验，抽象为结构化的 Skill
- 持续优化：发现更好的路径或新的边界情况时更新已有 Skill
- 持续积累：随使用增长，Agent 能力库越来越丰富
- 催促机制：连续 N 轮未创建 Skill 时提醒 Agent 整理经验

Internal structure (split since v0.3):
- _skill_model.py       — Skill dataclass, _tokenize(), constants
- _skill_persistence.py — load/parse/save/prune mixin
- _skill_matching.py    — query/match/score mixin
- _skill_auto.py        — nudge, pattern tracking, auto-generate, trajectory, context mixin
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent._skill_auto import SkillAutoMixin
from src.agent._skill_matching import SkillMatchingMixin
from src.agent._skill_model import SKILL_DECAY_DAYS, SKILL_NUDGE_INTERVAL, Skill
from src.agent._skill_persistence import SkillPersistenceMixin

logger = logging.getLogger(__name__)

# Re-export for backward compatibility.
__all__ = [
    "Skill",
    "SkillRegistry",
    "SKILL_NUDGE_INTERVAL",
    "SKILL_DECAY_DAYS",
]


class SkillRegistry(SkillPersistenceMixin, SkillMatchingMixin, SkillAutoMixin):
    """Skill 注册表 — 管理技能的加载、查询、生成和催促。

    Composes four mixins:
    - SkillPersistenceMixin  — I/O (load, parse, save, prune)
    - SkillMatchingMixin     — query and match
    - SkillAutoMixin         — nudge, pattern tracking, auto-generate, trajectory, context
    """

    def __init__(self, skills_dir: str | Path = "data/agent/skills") -> None:
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._iters_since_skill = 0
        self._patterns: dict[str, list[dict]] = {}
        self._auto_generated: set[str] = set()
        self._lock = threading.RLock()
        self._load_all()

    # ------------------------------------------------------------------
    # 创建和更新
    # ------------------------------------------------------------------

    def create_skill(
        self,
        name: str,
        trigger: str,
        description: str,
        steps: list[str],
        notes: list[str] | None = None,
    ) -> Skill:
        """创建新的 Skill 并保存到文件。"""
        with self._lock:
            now = datetime.now().strftime("%Y-%m-%d")
            skill = Skill(
                name=name,
                trigger=trigger,
                description=description,
                steps=steps,
                notes=notes or [],
                created_at=now,
                updated_at=now,
            )
            self._save_skill(skill)
            self._skills[name] = skill
            self._iters_since_skill = 0
            logger.info("新 Skill 已创建: %s", name)
            return skill

    def update_skill(self, name: str, **kwargs: Any) -> Skill | None:
        """更新已有 Skill。"""
        with self._lock:
            skill = self._skills.get(name)
            if skill is None:
                return None

            for key, value in kwargs.items():
                if hasattr(skill, key):
                    setattr(skill, key, value)

            skill.updated_at = datetime.now().strftime("%Y-%m-%d")
            self._save_skill(skill)
            self._iters_since_skill = 0
            logger.info("Skill 已更新: %s", name)
            return skill

    def increment_use(self, name: str) -> None:
        """增加 Skill 的使用计数，同时更新 last_used_at 并恢复 deprecated 状态。"""
        with self._lock:
            skill = self._skills.get(name)
            if skill:
                skill.use_count += 1
                skill.last_used_at = datetime.now().strftime("%Y-%m-%d")
                if skill.deprecated:
                    skill.deprecated = False
                    logger.info("Skill 因使用而从过期状态恢复: %s", name)
                self._save_skill(skill)
