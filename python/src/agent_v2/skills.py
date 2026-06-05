"""Skills 系统 — 从目录加载 prompt 模板注入 system prompt。

参考 claw-code:
  - skill_system.py: SkillRegistry + SOUL/AGENTS/IDENTITY layers
  - /skills slash command: list/install/help

Skill 文件格式 (Markdown with YAML frontmatter):
  ---
  name: academic_writing
  description: Professional academic writing standards
  layer: agents  # agents | soul | identity
  ---
  # Skill content (injected into system prompt)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    name: str
    description: str = ""
    layer: str = "agents"  # soul | agents | identity
    content: str = ""
    source_file: str = ""

    def inject_prompt(self) -> str:
        if not self.content.strip():
            return ""
        return f"\n<!-- SKILL: {self.name} ({self.layer}) -->\n{self.content.strip()}\n<!-- /SKILL -->\n"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "layer": self.layer, "source": self.source_file}


class SkillRegistry:
    """Skill registry — 参考 claw-code SkillRegistry。"""

    def __init__(self, skills_dir: str | Path | None = None):
        self._skills: dict[str, Skill] = {}
        self._active: set[str] = set()
        if skills_dir:
            self.load_dir(Path(skills_dir))

    def load_dir(self, directory: Path) -> int:
        """加载目录中所有 .md 文件为 skill。"""
        if not directory.is_dir():
            return 0
        count = 0
        for f in sorted(directory.glob("*.md")):
            if f.name.startswith("_") or f.name.startswith("."):
                continue  # skip helper/docs files
            try:
                skill = self._parse_skill_file(f)
                self._skills[skill.name] = skill
                self._active.add(skill.name)
                count += 1
            except Exception:
                pass
        return count

    def _parse_skill_file(self, path: Path) -> Skill:
        text = path.read_text(encoding="utf-8")
        name = path.stem
        description = ""
        layer = "agents"
        content = text

        # Parse YAML frontmatter
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
        if fm_match:
            fm = fm_match.group(1)
            content = fm_match.group(2)
            for line in fm.splitlines():
                line = line.strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k == "name":
                        name = v
                    elif k == "description":
                        description = v
                    elif k == "layer":
                        layer = v

        return Skill(name=name, description=description, layer=layer,
                     content=content.strip(), source_file=str(path))

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        self._active.add(skill.name)

    def activate(self, name: str) -> bool:
        if name in self._skills:
            self._active.add(name)
            return True
        return False

    def deactivate(self, name: str) -> bool:
        if name in self._active:
            self._active.discard(name)
            return True
        return False

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        return [{
            **s.to_dict(),
            "active": s.name in self._active,
        } for s in self._skills.values()]

    def build_prompt_injection(self, layer: str | None = None) -> str:
        """构建注入系统提示词的 skill 内容。"""
        parts = []
        for name in sorted(self._active):
            skill = self._skills.get(name)
            if skill is None:
                continue
            if layer and skill.layer != layer:
                continue
            inj = skill.inject_prompt()
            if inj:
                parts.append(inj)
        return "\n".join(parts)


# Built-in academic skills
_BUILTIN_SKILLS = [
    Skill(name="academic_writing", layer="agents",
          description="Professional academic writing standards (clarity, structure, tone)",
          content="## Academic Writing Standards\n- Use precise, formal language. Avoid colloquialisms.\n- Structure arguments with clear claims and evidence.\n- Cite relevant literature using standard formats.\n- Define technical terms on first use.\n- Use active voice where possible."),
    Skill(name="paper_review", layer="agents",
          description="Systematic paper review methodology",
          content="## Systematic Review Criteria\nWhen reviewing academic content, check:\n1. **Novelty**: Is the contribution clearly stated?\n2. **Methodology**: Are methods described in reproducible detail?\n3. **Evidence**: Do results support the claims?\n4. **Clarity**: Is the writing clear and well-structured?\n5. **Citations**: Are relevant works properly cited?"),
    Skill(name="latex_formatting", layer="agents",
          description="LaTeX formatting and best practices",
          content="## LaTeX Formatting Rules\n- Use \\section, \\subsection, \\subsubsection for hierarchy\n- Figures: \\begin{figure}[htbp] + \\includegraphics + \\caption\n- Tables: \\begin{table}[htbp] + booktabs + \\caption\n- Citations: \\cite{key} for inline, \\citep{key} for parenthetical\n- Math: \\begin{equation} for numbered, \\begin{align} for multi-line"),
    Skill(name="chinese_academic", layer="agents",
          description="中文学术写作规范",
          content="## 中文学术写作规范\n- 使用规范的学术中文，避免口语化表达\n- 段落结构：论点 → 论证 → 证据 → 小结\n- 术语首次出现需给出中英文对照（如：大语言模型（Large Language Model, LLM））\n- 引用格式遵循 GB/T 7714 标准\n- 图表标题使用中文"),
    Skill(name="methodology_critique", layer="agents",
          description="Research methodology critique guide",
          content="## Methodology Critique Guide\nWhen evaluating research methodology:\n1. **Validity**: Do the methods measure what they claim?\n2. **Reliability**: Can results be reproduced?\n3. **Generalizability**: Do findings apply beyond the sample?\n4. **Confounds**: Are alternative explanations addressed?\n5. **Ethics**: Are human/animal subjects properly protected?"),
]
