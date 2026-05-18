"""Skill migration — legacy SKILL.md → three-layer {IDENTITY,SOUL,AGENTS}.md."""
from __future__ import annotations

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FM_RE = re.compile(r"---\s*\n(.*?)\n---", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+)", re.MULTILINE)


def _parse_legacy(filepath: Path) -> dict:
    """Parse a legacy SKILL.md, return dict with keys: fm, description, steps, notes."""
    content = filepath.read_text(encoding="utf-8")
    fm: dict[str, str] = {}
    body = content
    m = _FM_RE.match(content)
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip()
        body = content[m.end():].strip()

    steps: list[str] = []
    notes: list[str] = []
    description = ""
    current_section = None

    for line in body.split("\n"):
        if line.strip().startswith("# "):
            description = line.strip("# ").strip()
        elif line.strip().startswith("## 步骤"):
            current_section = "steps"
        elif line.strip().startswith("## 注意事项"):
            current_section = "notes"
        elif line.strip().startswith("## "):
            current_section = None
        elif current_section == "steps":
            m2 = re.match(r"\s*(?:\d+\.\s*|-)\s*(.+)", line)
            if m2:
                steps.append(m2.group(1).strip())
        elif current_section == "notes":
            m2 = re.match(r"\s*-\s*(.+)", line)
            if m2:
                notes.append(m2.group(1).strip())

    return {"fm": fm, "description": description, "steps": steps, "notes": notes}


def migrate_skills_dir(skills_dir: Path, dry_run: bool = False) -> dict:
    """Migrate legacy SKILL.md files to three-layer format.

    Returns: {"migrated": int, "skipped": int, "errors": list[str]}
    dry_run=True: report only, do not write files.
    For each skill_dir/SKILL.md:
      1. Parse existing SKILL.md (reuse frontmatter + body parsing logic)
      2. Create IDENTITY.md (frontmatter with all metadata + description as body, truncated to 200 chars)
      3. Create SOUL.md (skill steps as numbered list, or "# Core\\n" if no steps)
      4. Create AGENTS.md (skill notes as bullet list, or "# Extended\\n" if no notes)
      5. Rename SKILL.md -> SKILL.md.bak (backup)
    """
    result: dict = {"migrated": 0, "skipped": 0, "errors": []}

    if not skills_dir.exists():
        result["errors"].append(f"skills_dir does not exist: {skills_dir}")
        return result

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            result["skipped"] += 1
            continue
        # Already migrated?
        if (skill_dir / "IDENTITY.md").exists():
            result["skipped"] += 1
            continue

        try:
            parsed = _parse_legacy(skill_md)
            fm = parsed["fm"]
            name = fm.get("name") or skill_dir.name
            description = (parsed["description"] or name)[:200]

            # Build IDENTITY.md
            identity_fm_lines = [
                f"name: {name}",
                f"trigger: {fm.get('trigger', '')}",
                f"created: {fm.get('created', '')}",
                f"updated: {fm.get('updated', '')}",
                f"last_used: {fm.get('last_used', '')}",
                f"use_count: {fm.get('use_count', '0')}",
                f"deprecated: {fm.get('deprecated', 'false')}",
            ]
            identity_content = "---\n" + "\n".join(identity_fm_lines) + "\n---\n" + description

            # Build SOUL.md
            if parsed["steps"]:
                soul_lines = ["# Core\n"]
                for i, step in enumerate(parsed["steps"], 1):
                    soul_lines.append(f"{i}. {step}")
                soul_content = "\n".join(soul_lines)
            else:
                soul_content = "# Core\n"

            # Build AGENTS.md
            if parsed["notes"]:
                agents_lines = ["# Extended\n"]
                for note in parsed["notes"]:
                    agents_lines.append(f"- {note}")
                agents_content = "\n".join(agents_lines)
            else:
                agents_content = "# Extended\n"

            if not dry_run:
                (skill_dir / "IDENTITY.md").write_text(identity_content, encoding="utf-8")
                (skill_dir / "SOUL.md").write_text(soul_content, encoding="utf-8")
                (skill_dir / "AGENTS.md").write_text(agents_content, encoding="utf-8")
                skill_md.rename(skill_dir / "SKILL.md.bak")

            result["migrated"] += 1
            logger.info("Migrated skill: %s (dry_run=%s)", name, dry_run)

        except Exception as e:
            err = f"Error migrating {skill_dir.name}: {e}"
            result["errors"].append(err)
            logger.warning(err)

    return result
