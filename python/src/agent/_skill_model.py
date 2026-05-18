"""Skill data model, tokenizer, and constants."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Skill 催促间隔（连续 N 轮对话未创建/更新 Skill 时提醒）
SKILL_NUDGE_INTERVAL = 10
# Skill 衰减阈值：超过此天数未使用则标记为 deprecated，不再注入 prompt
SKILL_DECAY_DAYS = 30


def _tokenize(text: str) -> list[str]:
    r"""中英文混合分词 — 英文按 \w+，中文按字符分词。"""
    tokens: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        code = ord(c)
        if 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            tokens.append(c)
            i += 1
        elif c.isalnum() or c == "_":
            j = i
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(text[i:j])
            i = j
        else:
            i += 1
    return tokens


@dataclass
class Skill:
    """一个可复用的技能。"""

    name: str
    trigger: str = ""
    description: str = ""
    steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_used_at: str = ""
    use_count: int = 0
    deprecated: bool = False
    soul_path: str = ""      # absolute path to SOUL.md (empty = not three-layer)
    agents_path: str = ""    # absolute path to AGENTS.md
    identity_path: str = ""  # absolute path to IDENTITY.md

    def to_markdown(self) -> str:
        """序列化为 SKILL.md 格式。"""
        frontmatter = [
            f"name: {self.name}",
            f"trigger: {self.trigger}",
            f"created: {self.created_at}",
            f"updated: {self.updated_at}",
            f"last_used: {self.last_used_at}",
            f"use_count: {self.use_count}",
            f"deprecated: {str(self.deprecated).lower()}",
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
