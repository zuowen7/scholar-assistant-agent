"""Three-angle parallel reviewer — method / experiment / writing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.utils.json_extract import extract_json_array

from .companion_models import ReviewPoint
from .llm_client import call_llm_chat
from .reviewer import _parse_llm_points
from .section_utils import SectionExcerpt, build_section_excerpt_envelope

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts" / "tasks_review"

_METHOD_HEADINGS = (
    "method",
    "methodology",
    "approach",
    "方法",
    "研究问题",
    "技术演进",
)
_EXPERIMENT_HEADINGS = (
    "experiment",
    "result",
    "evaluation",
    "performance",
    "analysis",
    "实验",
    "结果",
    "评估",
    "性能",
    "对比",
    "讨论",
)


def _render_review_prompt(template: str, venue_profile: str, excerpt: SectionExcerpt) -> str:
    metadata = json.dumps(excerpt.metadata(), ensure_ascii=False, sort_keys=True)
    return (
        template.replace("{venue}", venue_profile[:400])
        .replace("{source_metadata}", metadata)
        .replace("{text}", excerpt.text)
    )


def _load_prompt(name: str) -> str:
    """Load a required reviewer prompt; never silently weaken review behavior."""
    p = _PROMPTS_DIR / name
    try:
        content = p.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"required review prompt unavailable: {name}: {exc}") from exc
    if not content.strip():
        raise RuntimeError(f"required review prompt is empty: {name}")
    return content


async def _call_perspective_prompt(
    prompt: str,
    cloud_client: Any,
    ollama_client: Any,
    *,
    temperature: float,
) -> list[ReviewPoint]:
    """Call one perspective and repair malformed/truncated JSON at most once."""
    raw = await call_llm_chat(
        prompt,
        cloud_client,
        ollama_client,
        max_tokens=4096,
        temperature=temperature,
        json_mode=True,
    )
    points = _parse_llm_points(raw, source="llm")
    if extract_json_array(raw) is not None:
        return points

    repair_prompt = (
        "将下面这段不完整或格式错误的审稿意见修复为严格 JSON 数组。"
        "保留已有问题，不要解释，不要添加 Markdown 代码围栏。每项必须包含 "
        "category、severity、title、detail，可选 verbatim_quote：\n\n"
        f"{raw[:12000]}"
    )
    repaired = await call_llm_chat(
        repair_prompt,
        cloud_client,
        ollama_client,
        max_tokens=4096,
        temperature=0.1,
        json_mode=True,
    )
    return _parse_llm_points(repaired, source="llm")


async def run_method_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    raise_errors: bool = False,
) -> list[ReviewPoint]:
    """LLM review focused on methodology and theoretical soundness."""
    excerpt = build_section_excerpt_envelope(
        text,
        max_chars=14000,
        preferred_headings=_METHOD_HEADINGS,
    )
    template = _load_prompt("perspective_method.md")
    if template:
        prompt = _render_review_prompt(template, venue_profile, excerpt)
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on methodology and theoretical soundness.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{excerpt.text}\n\n"
            "Focus: research design, approach validity, theoretical grounding, logical soundness of methods.\n"
            "Return 3-6 concrete issues as ONLY a JSON array: "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        return await _call_perspective_prompt(
            prompt,
            cloud_client,
            ollama_client,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("method perspective failed: %s", exc)
        if raise_errors:
            raise
        return []


async def run_experiment_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    raise_errors: bool = False,
) -> list[ReviewPoint]:
    """LLM review focused on experiments and evaluation."""
    excerpt = build_section_excerpt_envelope(
        text,
        max_chars=16000,
        preferred_headings=_EXPERIMENT_HEADINGS,
    )
    template = _load_prompt("perspective_experiment.md")
    if template:
        prompt = _render_review_prompt(template, venue_profile, excerpt)
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on experiments and evaluation.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{excerpt.text}\n\n"
            "Focus: baselines, ablation studies, experimental setup, reproducibility, statistical significance.\n"
            "Return 3-6 concrete issues as ONLY a JSON array: "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        return await _call_perspective_prompt(
            prompt,
            cloud_client,
            ollama_client,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("experiment perspective failed: %s", exc)
        if raise_errors:
            raise
        return []


async def run_writing_perspective(
    text: str,
    venue_profile: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
    *,
    raise_errors: bool = False,
) -> list[ReviewPoint]:
    """LLM review focused on writing quality and presentation."""
    excerpt = build_section_excerpt_envelope(text, max_chars=14000)
    template = _load_prompt("perspective_writing.md")
    if template:
        prompt = _render_review_prompt(template, venue_profile, excerpt)
    else:
        prompt = (
            "You are Reviewer-2 focusing ONLY on writing quality and presentation clarity.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{excerpt.text}\n\n"
            "Focus: clarity, structure, language quality, figure captions, related work positioning.\n"
            "Return 3-6 concrete issues as ONLY a JSON array: "
            '[{"category":...,"severity":"minor|major|fatal","title":...,"detail":...}]'
        )
    try:
        return await _call_perspective_prompt(
            prompt,
            cloud_client,
            ollama_client,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("writing perspective failed: %s", exc)
        if raise_errors:
            raise
        return []


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
    *,
    raise_errors: bool = False,
) -> list[ReviewPoint]:
    """LLM review from a deliberately contrarian stance."""
    excerpt = build_section_excerpt_envelope(text, max_chars=16000)
    template = _load_prompt("perspective_devils_advocate.md")
    if template:
        prompt = _render_review_prompt(template, venue_profile, excerpt)
    else:
        prompt = (
            "You are Devil's Advocate — find the strongest counter-arguments.\n"
            f"Venue: {venue_profile[:400]}\n\nPaper:\n{excerpt.text}\n\n"
            "Focus: weakest links, alternative explanations, edge cases, failing assumptions.\n"
            "Return 3-6 concrete issues as ONLY a JSON array: "
            '[{"category":"soundness|claim_overreach|experiment_design|other",'
            '"severity":"minor|major|fatal","title":...,"detail":...,'
            '"verbatim_quote":"exact paper text or empty string"}]'
        )
    try:
        return await _call_perspective_prompt(
            prompt,
            cloud_client,
            ollama_client,
            temperature=0.5,
        )
    except Exception as exc:
        logger.warning("devils_advocate perspective failed: %s", exc)
        if raise_errors:
            raise
        return []


async def synthesize_review(
    method_pts: list[ReviewPoint],
    experiment_pts: list[ReviewPoint],
    writing_pts: list[ReviewPoint],
    devils_advocate_pts: list[ReviewPoint],
    venue_profile: str = "",
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> dict | None:
    """Build a deterministic synthesis without a fifth serial model request."""
    points = aggregate_perspectives(
        method_pts,
        experiment_pts,
        writing_pts,
        devils_advocate_pts,
    )
    severity_rank = {"fatal": 0, "major": 1, "minor": 2, "info": 3}
    ranked = sorted(
        points,
        key=lambda point: (
            severity_rank.get(str(point.severity), 4),
            point.title.lower(),
        ),
    )
    fatal_count = sum(point.severity == "fatal" for point in points)
    major_count = sum(point.severity == "major" for point in points)
    if fatal_count:
        assessment = "reject"
    elif major_count:
        assessment = "major"
    elif points:
        assessment = "minor"
    else:
        assessment = "accept"
    return {
        "overall_assessment": assessment,
        "top_issues": [point.title for point in ranked[:5]],
        "actions": [point.detail for point in ranked[:5] if point.detail],
        # Strengths are not inferred from a list that contains concerns only.
        "consensus_strengths": [],
    }
