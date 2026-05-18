"""Translation system prompt loader — assembles prompt from template + section partials.

Design:
- Reads prompts/tasks_translate/academic_translate.md as the base template
- Optionally appends a section-specific partial from prompts/tasks_translate/_partials/
- Optionally appends an injected glossary block
- Template file content is cached with lru_cache to avoid repeated disk IO
"""

from __future__ import annotations

import functools
from pathlib import Path

# prompts/ directory is at python/prompts/, relative to this file at
# python/src/translator/_prompt_loader.py → go up 3 levels
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_TASKS_TRANSLATE_DIR = _PROMPTS_DIR / "tasks_translate"
_PARTIALS_DIR = _TASKS_TRANSLATE_DIR / "_partials"


@functools.lru_cache(maxsize=32)
def _read_file(path: str) -> str:
    """Read a file and cache its contents. Uses str path as cache key."""
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def load_translate_prompt(section: str = "unknown", glossary_text: str = "") -> str:
    """Load and assemble the translation system prompt from template + partials.

    Args:
        section: section type string, e.g. "abstract", "methods", "unknown"
        glossary_text: pre-built glossary string to inject (or empty string)
    Returns:
        Assembled system prompt string
    """
    # Step 1: Load base template
    template_path = _TASKS_TRANSLATE_DIR / "academic_translate.md"
    content = _read_file(str(template_path))

    if not content:
        # Minimal fallback — should not happen if file is present
        content = "You are a professional academic translator."

    # Step 2: Append section-specific partial (only for known sections)
    section_lower = section.lower().strip()
    if section_lower and section_lower != "unknown":
        partial_path = _PARTIALS_DIR / f"section_{section_lower}.md"
        partial_content = _read_file(str(partial_path))
        if partial_content:
            content = content.rstrip() + "\n\n" + partial_content

    # Step 3: Append glossary block if provided
    if glossary_text:
        content = content.rstrip() + "\n\n## 已确定的术语翻译（请严格沿用以下译法）\n" + glossary_text

    return content
