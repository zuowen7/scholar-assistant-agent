"""Three-angle parallel reviewer — method / experiment / writing."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .companion_models import ReviewPoint
from .llm_client import call_llm_chat
from .reviewer import _parse_llm_points

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "tasks_review"


def _load_prompt(name: str) -> str:
    """Load a prompt template from tasks_review/; return '' if missing."""
    p = _PROMPTS_DIR / name
    try:
        return p.read_text(encoding="utf-8") if p.exists() else ""
    except Exception:
        return ""


async def run_method_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """LLM review focused on methodology and theoretical soundness."""
    template = _load_prompt("perspective_method.md")
    if template:
        prompt = template.replace("{venue}", venue_profile[:400]).replace("{text}", text[:3000])
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on methodology and theoretical soundness.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{text[:3000]}\n\n"
            "Focus: research design, approach validity, theoretical grounding, logical soundness of methods.\n"
            "Return ONLY a JSON array (possibly []): "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.4)
    except Exception as exc:
        logger.warning("method perspective failed: %s", exc)
        return []
    return _parse_llm_points(raw, source="llm")


async def run_experiment_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """LLM review focused on experiments and evaluation."""
    template = _load_prompt("perspective_experiment.md")
    if template:
        prompt = template.replace("{venue}", venue_profile[:400]).replace("{text}", text[:3000])
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on experiments and evaluation.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{text[:3000]}\n\n"
            "Focus: baselines, ablation studies, experimental setup, reproducibility, statistical significance.\n"
            "Return ONLY a JSON array (possibly []): "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.4)
    except Exception as exc:
        logger.warning("experiment perspective failed: %s", exc)
        return []
    return _parse_llm_points(raw, source="llm")


async def run_writing_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """LLM review focused on writing quality and presentation."""
    template = _load_prompt("perspective_writing.md")
    if template:
        prompt = template.replace("{venue}", venue_profile[:400]).replace("{text}", text[:3000])
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on writing quality and presentation clarity.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{text[:3000]}\n\n"
            "Focus: clarity, structure, language quality, figure captions, related work positioning.\n"
            "Return ONLY a JSON array (possibly []): "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.4)
    except Exception as exc:
        logger.warning("writing perspective failed: %s", exc)
        return []
    return _parse_llm_points(raw, source="llm")


def aggregate_perspectives(
    method_pts: list[ReviewPoint],
    experiment_pts: list[ReviewPoint],
    writing_pts: list[ReviewPoint],
) -> list[ReviewPoint]:
    """Merge three perspective lists. Deduplicate by (title.lower(), category).
    Preserve stable order: method -> experiment -> writing.
    """
    result: list[ReviewPoint] = []
    seen: set[tuple[str, str]] = set()
    for pt in method_pts + experiment_pts + writing_pts:
        key = (pt.title.strip().lower(), pt.category)
        if key not in seen:
            seen.add(key)
            result.append(pt)
    return result
