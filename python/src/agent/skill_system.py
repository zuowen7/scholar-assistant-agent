"""动态 Skill 系统 — 从任务轨迹中沉淀可复用经验。

Skill 是将 Agent 的"一次性执行"转化为"经验沉淀"的核心机制：
- 自动生成：从成功的任务轨迹中提取经验，抽象为结构化的 Skill
- 持续优化：发现更好的路径或新的边界情况时更新已有 Skill
- 持续积累：随使用增长，Agent 能力库越来越丰富
- 催促机制：连续 N 轮未创建 Skill 时提醒 Agent 整理经验

Skill 文件格式（SKILL.md）：
```markdown
---
name: translate_academic_paper
trigger: 翻译学术论文、学术文本翻译
created: 2026-04-24
---

# 翻译学术论文

## 步骤
1. 使用 parse_document 提取论文全文
2. 按段落切块，每块不超过 2000 token
3. 逐块调用 translate_text，保留 LaTeX 公式
4. 合并翻译结果

## 注意事项
- 数学公式 ($...$) 必须原样保留
- 专有名词首次出现时标注英文原文
```
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Skill 催促间隔（连续 N 轮对话未创建/更新 Skill 时提醒）
SKILL_NUDGE_INTERVAL = 10


@dataclass
class Skill:
    """一个可复用的技能。

    Attributes:
        name: 技能名称（英文 snake_case，对应目录名）。
        trigger: 触发条件描述。
        description: 技能简述。
        steps: 执行步骤列表。
        notes: 注意事项列表。
        created_at: 创建时间。
        updated_at: 最后更新时间。
        use_count: 累计使用次数。
    """

    name: str
    trigger: str = ""
    description: str = ""
    steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    use_count: int = 0

    def to_markdown(self) -> str:
        """序列化为 SKILL.md 格式。

        Returns:
            Markdown 格式的 Skill 描述。
        """
        frontmatter = [
            f"name: {self.name}",
            f"trigger: {self.trigger}",
            f"created: {self.created_at}",
            f"updated: {self.updated_at}",
            f"use_count: {self.use_count}",
        ]

        lines = [
            "---",
            "\n".join(frontmatter),
            "---",
            "",
            f"# {self.description or self.name}",
            "",
        ]

        if self.steps:
            lines.append("## 步骤")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        if self.notes:
            lines.append("## 注意事项")
            for note in self.notes:
                lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines)


class SkillRegistry:
    """Skill 注册表 — 管理技能的加载、查询、生成和催促。

    Attributes:
        skills_dir: Skill 文件目录。
    """

    def __init__(self, skills_dir: str | Path = "data/agent/skills") -> None:
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._iters_since_skill = 0
        self._load_all()

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """从 skills/ 目录加载所有 Skill。"""
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skill = self._parse_skill_file(skill_file)
                if skill:
                    self._skills[skill.name] = skill

        if self._skills:
            logger.info("已加载 %d 个 Skill: %s", len(self._skills), list(self._skills.keys()))

    def _parse_skill_file(self, filepath: Path) -> Skill | None:
        """解析 SKILL.md 文件。

        Args:
            filepath: SKILL.md 文件路径。

        Returns:
            Skill 实例，解析失败返回 None。
        """
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 Skill 文件失败 %s: %s", filepath, e)
            return None

        # 解析 frontmatter
        fm_match = re.match(r"---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return None

        fm_text = fm_match.group(1)
        body = content[fm_match.end():].strip()

        # 简易 frontmatter 解析
        fm: dict[str, str] = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fm[key.strip()] = value.strip()

        # 解析 body 中的步骤和注意事项
        steps = self._extract_list_section(body, "步骤")
        notes = self._extract_list_section(body, "注意事项")
        description = self._extract_title(body)

        return Skill(
            name=fm.get("name", filepath.parent.name),
            trigger=fm.get("trigger", ""),
            description=description,
            steps=steps,
            notes=notes,
            created_at=fm.get("created", ""),
            updated_at=fm.get("updated", ""),
            use_count=int(fm.get("use_count", "0")),
        )

    @staticmethod
    def _extract_list_section(text: str, header: str) -> list[str]:
        """从 Markdown 中提取指定标题下的列表项。

        Args:
            text: Markdown 文本。
            header: 标题文本。

        Returns:
            列表项内容列表。
        """
        items: list[str] = []
        in_section = False
        for line in text.split("\n"):
            if line.strip().startswith(f"## {header}"):
                in_section = True
                continue
            if in_section:
                if line.strip().startswith("## "):
                    break
                # 匹配有序/无序列表
                m = re.match(r"\s*(?:\d+\.\s*|-)\s*(.+)", line)
                if m:
                    items.append(m.group(1).strip())
        return items

    @staticmethod
    def _extract_title(text: str) -> str:
        """从 Markdown body 中提取一级标题。

        Args:
            text: Markdown 文本。

        Returns:
            标题文本。
        """
        m = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, name: str) -> Skill | None:
        """按名称查询 Skill。

        Args:
            name: Skill 名称。

        Returns:
            Skill 实例或 None。
        """
        return self._skills.get(name)

    def match(self, query: str) -> Skill | None:
        """根据用户查询匹配最相关的 Skill。

        匹配策略：将 trigger 按逗号分割为短语，每个短语中的字符
        在 query 中出现的比例作为匹配分数。

        Args:
            query: 用户查询文本。

        Returns:
            匹配的 Skill 或 None。
        """
        query_lower = query.lower()
        best_match: Skill | None = None
        best_score = 0

        for skill in self._skills.values():
            score = 0
            trigger_phrases = skill.trigger.lower().split(",")
            for phrase in trigger_phrases:
                phrase = phrase.strip()
                if not phrase:
                    continue
                # 子串匹配
                if phrase in query_lower:
                    score += len(phrase) * 2
                else:
                    # 字符级匹配：短语中有多少字符出现在 query 中
                    matched_chars = sum(1 for ch in phrase if ch in query_lower)
                    ratio = matched_chars / len(phrase) if phrase else 0
                    if ratio >= 0.6:
                        score += int(matched_chars)
            if score > best_score:
                best_score = score
                best_match = skill

        return best_match

    def list_skills(self) -> list[Skill]:
        """返回所有已加载的 Skill 列表。"""
        return list(self._skills.values())

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
        """创建新的 Skill 并保存到文件。

        Args:
            name: Skill 名称。
            trigger: 触发条件。
            description: 描述。
            steps: 步骤列表。
            notes: 注意事项。

        Returns:
            创建的 Skill 实例。
        """
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
        """更新已有 Skill。

        Args:
            name: Skill 名称。
            **kwargs: 要更新的字段。

        Returns:
            更新后的 Skill 或 None。
        """
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
        """增加 Skill 的使用计数。

        Args:
            name: Skill 名称。
        """
        skill = self._skills.get(name)
        if skill:
            skill.use_count += 1
            self._save_skill(skill)

    def _save_skill(self, skill: Skill) -> None:
        """将 Skill 保存为文件。

        Args:
            skill: 要保存的 Skill。
        """
        skill_dir = self.skills_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        filepath = skill_dir / "SKILL.md"

        try:
            filepath.write_text(skill.to_markdown(), encoding="utf-8")
        except Exception as e:
            logger.error("保存 Skill 文件失败: %s", e)

    # ------------------------------------------------------------------
    # 催促机制
    # ------------------------------------------------------------------

    def nudge_check(self) -> str | None:
        """检查是否需要催促 Agent 整理经验为 Skill。

        每次对话后调用，返回催促提示或 None。

        Returns:
            催促提示文本，不需要催促时返回 None。
        """
        self._iters_since_skill += 1
        if self._iters_since_skill >= SKILL_NUDGE_INTERVAL:
            self._iters_since_skill = 0
            return (
                f"你已经连续 {SKILL_NUDGE_INTERVAL} 轮对话没有创建新的 Skill。"
                "请回顾最近的对话，看看是否有值得沉淀的经验模式，"
                "使用 create_skill 工具将其固化为可复用的 Skill。"
            )
        return None

    def get_skill_context(self, query: str = "") -> str:
        """构建注入到 Prompt 的 Skill 上下文。

        当匹配到相关 Skill 时，返回其步骤描述供 Agent 参考。

        Args:
            query: 用户查询（用于匹配）。

        Returns:
            Skill 上下文文本，无匹配时返回空字符串。
        """
        if not query:
            skills = self.list_skills()
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

        这是由 review_agent 在后台调用的高层接口。
        轨迹数据需包含 conversations 和 metadata。

        Args:
            trajectory_data: 轨迹数据（ShareGPT 格式 + metadata）。

        Returns:
            生成的 Skill 或 None（不适合生成时）。
        """
        metadata = trajectory_data.get("metadata", {})
        conversations = trajectory_data.get("conversations", [])

        # 至少需要 3 轮对话才有价值生成 Skill
        if len(conversations) < 3:
            return None

        # 提取工具调用信息
        tool_calls: list[str] = []
        for conv in conversations:
            content = conv.get("value", "")
            if "调用工具" in content or "tool" in conv.get("from", ""):
                tool_calls.append(content[:100])

        if not tool_calls:
            return None

        # 用查询的前 30 字符作为触发条件
        query = metadata.get("query", "")
        trigger = query[:50] if query else ""

        # 生成 Skill（简化版，实际由 review_agent 的 LLM 做更好的提取）
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
