"""Skill matching mixin — query and match skills."""

from __future__ import annotations

from src.agent._skill_model import Skill, _tokenize


class SkillMatchingMixin:
    """Mixin providing Skill query/match operations for SkillRegistry."""

    _skills: dict[str, Skill]

    def get(self, name: str) -> Skill | None:
        """按名称查询 Skill。"""
        return self._skills.get(name)

    def match(self, query: str) -> Skill | None:
        """根据用户查询匹配最相关的 Skill。

        匹配策略：
        1. 关键词精确匹配：trigger 短语直接出现在 query 中
        2. 关键词重合度：query 和 trigger 共享关键词的比例
        3. 语义扩展：检查 description 和 name 是否匹配
        """
        if not self._skills:
            return None

        query_lower = query.lower()
        query_tokens = set(_tokenize(query_lower))

        best_match: Skill | None = None
        best_score = 0.0

        for skill in self._skills.values():
            if skill.deprecated:
                continue
            score = self._compute_match_score(query_lower, query_tokens, skill)
            if score > best_score:
                best_score = score
                best_match = skill

        return best_match if best_score >= 1.0 else None

    @staticmethod
    def _compute_match_score(
        query_lower: str, query_tokens: set[str], skill: Skill
    ) -> float:
        """计算查询与 Skill 的匹配分数（>= 1.0 为有效匹配）。"""
        score = 0.0

        trigger_phrases = [p.strip() for p in skill.trigger.lower().split(",") if p.strip()]
        for phrase in trigger_phrases:
            if phrase in query_lower:
                score += len(phrase) * 0.5

        trigger_tokens = set(_tokenize(skill.trigger.lower()))
        if query_tokens and trigger_tokens:
            overlap = query_tokens & trigger_tokens
            jaccard = len(overlap) / len(query_tokens | trigger_tokens)
            score += jaccard * 10

        if skill.description:
            desc_tokens = set(_tokenize(skill.description.lower()))
            if query_tokens and desc_tokens:
                desc_overlap = query_tokens & desc_tokens
                score += len(desc_overlap) * 0.3

        name_tokens = set(_tokenize(skill.name.lower()))
        if query_tokens and name_tokens:
            name_overlap = query_tokens & name_tokens
            score += len(name_overlap) * 0.5

        return score

    def list_skills(self) -> list[Skill]:
        """返回所有已加载的 Skill 列表。"""
        return list(self._skills.values())
