"""PromptSpec — 6-layer schema validator for prompt .md files.

Layers: role, task, constraints, format, examples, fallback
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class PromptSchemaError(ValueError):
    """Raised when a required schema layer is missing."""


REQUIRED_LAYERS = ("role", "task", "constraints", "format", "fallback")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract and parse YAML between the first pair of --- markers."""
    if yaml is None:
        raise ImportError("pyyaml is required for schema validation")
    # Match ---\n...\n--- at start of file (with optional leading whitespace)
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        raise PromptSchemaError("No YAML frontmatter found (expected --- ... --- block at top of file)")
    return yaml.safe_load(m.group(1)) or {}


@dataclass
class PromptSpec:
    role: str
    task: str
    constraints: list[str]
    format: str
    examples: list = field(default_factory=list)
    fallback: str = ""

    @classmethod
    def from_yaml_frontmatter(cls, text: str) -> "PromptSpec":
        """Parse and validate a PromptSpec from a .md file's YAML frontmatter."""
        data = _parse_frontmatter(text)
        # Check required layers
        for layer in REQUIRED_LAYERS:
            val = data.get(layer)
            if val is None or val == "None":
                raise PromptSchemaError(f"Missing required layer: '{layer}'")
        return cls(
            role=str(data["role"]),
            task=str(data["task"]),
            constraints=list(data["constraints"]),
            format=str(data["format"]),
            examples=list(data.get("examples") or []),
            fallback=str(data["fallback"]),
        )

    def validate(self) -> list[str]:
        """Return list of warning strings (non-fatal issues)."""
        warnings = []
        if not self.role.strip().startswith("You are"):
            warnings.append("role layer should start with 'You are'")
        # B9: at least 1 constraint must contain a digit
        has_number = any(re.search(r"\d", c) for c in self.constraints)
        if not has_number:
            warnings.append("constraints layer should contain at least 1 quantified constraint (with a number)")
        # B10: fallback should mention empty input
        if not re.search(r"empty|fewer than|no input|short|zero|blank", self.fallback, re.IGNORECASE):
            warnings.append("fallback layer should describe handling of empty or very short input")
        return warnings
