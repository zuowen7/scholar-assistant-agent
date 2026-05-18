"""Skill persistence mixin — load, parse, save, prune."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from src.agent._skill_model import SKILL_DECAY_DAYS, Skill

logger = logging.getLogger(__name__)


class SkillPersistenceMixin:
    """Mixin providing Skill I/O operations for SkillRegistry."""

    # Typed stubs for attributes provided by SkillRegistry.__init__
    skills_dir: Path
    _skills: dict[str, Skill]

    def _load_all(self) -> None:
        """从 skills/ 目录加载所有 Skill。"""
        if not self.skills_dir.exists():
            return

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            if (skill_dir / "IDENTITY.md").exists():
                skill = self._load_three_layer_skill(skill_dir)
            elif (skill_dir / "SKILL.md").exists():
                skill = self._parse_skill_file(skill_dir / "SKILL.md")
            else:
                continue
            if skill:
                self._skills[skill.name] = skill

        if self._skills:
            logger.info("已加载 %d 个 Skill: %s", len(self._skills), list(self._skills.keys()))
        self._prune_stale()

    def _load_three_layer_skill(self, skill_dir: Path) -> Skill | None:
        """Load a three-layer skill from IDENTITY.md (SOUL/AGENTS read lazily)."""
        identity_path = skill_dir / "IDENTITY.md"
        try:
            content = identity_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 IDENTITY.md 失败 %s: %s", identity_path, e)
            return None

        # Parse optional frontmatter using simple key: value parsing (not YAML)
        # to avoid crashing on invalid YAML (C11 requirement)
        fm: dict[str, str] = {}
        body = content
        fm_match = re.match(r"---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            body = content[fm_match.end():].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    fm[key.strip()] = value.strip()

        name = fm.get("name", skill_dir.name)
        description = body[:200] if body else ""

        return Skill(
            name=name,
            trigger=fm.get("trigger", ""),
            description=description,
            created_at=fm.get("created", ""),
            updated_at=fm.get("updated", ""),
            last_used_at=fm.get("last_used", ""),
            use_count=int(fm.get("use_count", "0") or "0"),
            deprecated=fm.get("deprecated", "false").lower() == "true",
            soul_path=str(skill_dir / "SOUL.md"),
            agents_path=str(skill_dir / "AGENTS.md"),
            identity_path=str(identity_path),
        )

    def _prune_stale(self) -> None:
        """将超过 SKILL_DECAY_DAYS 天未使用的 skill 标记为 deprecated。"""
        today = datetime.now()
        for skill in self._skills.values():
            date_str = skill.last_used_at or skill.updated_at or skill.created_at
            if not date_str:
                continue
            try:
                last = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            stale = (today - last).days > SKILL_DECAY_DAYS
            if stale and not skill.deprecated:
                skill.deprecated = True
                self._save_skill(skill)
                logger.info("Skill 已标记为过期（%d 天未使用）: %s", SKILL_DECAY_DAYS, skill.name)
            elif not stale and skill.deprecated:
                skill.deprecated = False
                self._save_skill(skill)
                logger.info("Skill 已从过期状态恢复: %s", skill.name)

    def _parse_skill_file(self, filepath: Path) -> Skill | None:
        """解析 SKILL.md 文件。"""
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("读取 Skill 文件失败 %s: %s", filepath, e)
            return None

        fm_match = re.match(r"---\s*\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return None

        fm_text = fm_match.group(1)
        body = content[fm_match.end():].strip()

        fm: dict[str, str] = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fm[key.strip()] = value.strip()

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
            last_used_at=fm.get("last_used", ""),
            use_count=int(fm.get("use_count", "0")),
            deprecated=fm.get("deprecated", "false").lower() == "true",
        )

    @staticmethod
    def _extract_list_section(text: str, header: str) -> list[str]:
        """从 Markdown 中提取指定标题下的列表项。"""
        items: list[str] = []
        in_section = False
        for line in text.split("\n"):
            if line.strip().startswith(f"## {header}"):
                in_section = True
                continue
            if in_section:
                if line.strip().startswith("## "):
                    break
                m = re.match(r"\s*(?:\d+\.\s*|-)\s*(.+)", line)
                if m:
                    items.append(m.group(1).strip())
        return items

    @staticmethod
    def _extract_title(text: str) -> str:
        """从 Markdown body 中提取一级标题。"""
        m = re.search(r"^#\s+(.+)", text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    def _save_skill(self, skill: Skill) -> None:
        """将 Skill 保存为文件。

        三层 Skill（identity_path 已设且文件存在）→ 仅更新 IDENTITY.md frontmatter。
        传统 Skill → 写 SKILL.md（原有逻辑不变）。
        """
        # Three-layer skill: update IDENTITY.md frontmatter only
        if skill.identity_path and Path(skill.identity_path).exists():
            try:
                content = Path(skill.identity_path).read_text(encoding="utf-8")
                fm_match = re.match(r"---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
                if fm_match:
                    body = content[fm_match.end():]
                    new_fm = (
                        f"name: {skill.name}\n"
                        f"trigger: {skill.trigger}\n"
                        f"created: {skill.created_at}\n"
                        f"updated: {skill.updated_at}\n"
                        f"last_used: {skill.last_used_at}\n"
                        f"use_count: {skill.use_count}\n"
                        f"deprecated: {str(skill.deprecated).lower()}"
                    )
                    Path(skill.identity_path).write_text(
                        f"---\n{new_fm}\n---\n{body}", encoding="utf-8"
                    )
                    return
            except Exception as e:
                logger.warning("更新 IDENTITY.md 失败，回退到 SKILL.md: %s", e)

        # Legacy skill: write SKILL.md
        skill_dir = self.skills_dir / skill.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        filepath = skill_dir / "SKILL.md"
        try:
            filepath.write_text(skill.to_markdown(), encoding="utf-8")
        except Exception as e:
            logger.error("保存 Skill 文件失败: %s", e)
