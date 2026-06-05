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
    except Exception as e:
        logger.warning("failed to load review prompt template %s: %s", name, e)
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
    devils_advocate_pts: list[ReviewPoint] | None = None,
) -> list[ReviewPoint]:
    """Merge perspective lists. Deduplicate by (title.lower(), category).
    Preserve stable order: method -> experiment -> writing -> DA.
    """
    result: list[ReviewPoint] = []
    seen: set[tuple[str, str]] = set()
    all_pts = method_pts + experiment_pts + writing_pts
    if devils_advocate_pts:
        all_pts += devils_advocate_pts
    for pt in all_pts:
        key = (pt.title.strip().lower(), pt.category)
        if key not in seen:
            seen.add(key)
            result.append(pt)
    return result


async def run_devils_advocate_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """LLM review from a deliberately contrarian stance."""
    template = _load_prompt("perspective_devils_advocate.md")
    if template:
        prompt = template.replace("{venue}", venue_profile[:400]).replace("{text}", text[:3000])
    else:
        prompt = (
            "You are Devil's Advocate — find the strongest counter-arguments.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{text[:3000]}\n\n"
            "Focus: weakest links, alternative explanations, edge cases, failing assumptions.\n"
            "Return ONLY a JSON array (possibly []): "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.5)
    except Exception as exc:
        logger.warning("devils_advocate perspective failed: %s", exc)
        return []
    return _parse_llm_points(raw, source="llm")


async def synthesize_review(
    method_pts: list[ReviewPoint],
    experiment_pts: list[ReviewPoint],
    writing_pts: list[ReviewPoint],
    devils_advocate_pts: list[ReviewPoint],
    venue_profile: str = "",
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> dict | None:
    """Run editorial synthesis across all 4 perspectives. Returns dict or None."""
    template = _load_prompt("synthesizer.md")

    def _format_pts(pts: list[ReviewPoint]) -> str:
        if not pts:
            return "No issues found."
        return "; ".join(f"[{pt.severity or '?'}] {pt.title}: {pt.detail or ''}" for pt in pts)

    method_str = _format_pts(method_pts)
    experiment_str = _format_pts(experiment_pts)
    writing_str = _format_pts(writing_pts)
    da_str = _format_pts(devils_advocate_pts)

    if template:
        prompt = (template
                  .replace("{method_points}", method_str[:2000])
                  .replace("{experiment_points}", experiment_str[:2000])
                  .replace("{writing_points}", writing_str[:2000])
                  .replace("{devils_advocate_points}", da_str[:2000]))
    else:
        prompt = (
            "You are an editorial synthesizer. Summarize these 4 reviews:\n"
            f"Methodology: {method_str[:1000]}\n"
            f"Experiment: {experiment_str[:1000]}\n"
            f"Writing: {writing_str[:1000]}\n"
            f"Devil's Advocate: {da_str[:1000]}\n\n"
            'Return ONLY a JSON object: '
            '{"overall_assessment":"accept|minor|major|reject",'
            '"top_issues":["..."],"actions":["..."],"consensus_strengths":["..."]}'
        )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.4)
    except Exception as exc:
        logger.warning("synthesize_review failed: %s", exc)
        return None

    import json as _json
    import re as _re
    cleaned = _re.sub(r"<think[^>]*>.*?</think\s*>", "", raw, flags=_re.DOTALL).strip()
    try:
        match = _re.search(r"\{[^}]+\}", cleaned)
        if match:
            return _json.loads(match.group())
    except (_json.JSONDecodeError, TypeError):
        pass
    return {"overall_assessment": "minor", "top_issues": [], "actions": [], "consensus_strengths": []}
