"""Read-only tools for progressive Skill discovery and loading."""

from __future__ import annotations

import json

from src.agent_v2.skills import SkillRegistry
from src.agent_v2.tools.registry import ToolRegistry, ToolResult


def register_skill_tools(registry: ToolRegistry, skills: SkillRegistry) -> None:
    async def skills_list(args: dict) -> ToolResult:
        del args
        payload = [
            {
                "name": item["name"],
                "description": item["description"],
                "category": item["category"],
                "active": item["active"],
            }
            for item in skills.list_all()
        ]
        return ToolResult(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    async def skill_view(args: dict) -> ToolResult:
        name = str(args.get("name", "")).strip()
        skill = skills.get(name)
        if skill is None:
            return ToolResult(
                f"Unknown skill: {name}",
                is_error=True,
                status="error",
            )
        payload = {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "layer": skill.layer,
            "content": skill.content,
        }
        return ToolResult(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    registry.register(
        "skills_list",
        "List available reusable skills with compact metadata. Use this only when the system "
        "skill index is insufficient.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        skills_list,
        permission="read-only",
    )
    registry.register(
        "skill_view",
        "Load the full instructions for one available skill by exact name before applying it.",
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact skill name from the available-skills index.",
                }
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        skill_view,
        permission="read-only",
    )
