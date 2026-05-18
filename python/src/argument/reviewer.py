"""Argument Companion — Reviewer-2 对抗评审（Phase 3 完整实现）。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, AsyncIterator

import yaml

from .companion_models import Ledger, ReviewPoint, ReviewSession
from .companion_store import CompanionStore
from .llm_client import call_llm_chat
from .section_utils import find_section, has_contrast_marker, split_paragraphs

logger = logging.getLogger(__name__)

_VENUE_PROFILES_PATH = Path(__file__).parent / "venue_profiles.yaml"
_venue_profiles_cache: dict[str, str] | None = None


# ── venue profiles ────────────────────────────────────────────────────────────

def _load_venue_profile(venue: str | None) -> str:
    """Return the calibration text for *venue*, falling back to generic."""
    global _venue_profiles_cache
    if _venue_profiles_cache is None:
        try:
            with open(_VENUE_PROFILES_PATH, encoding="utf-8") as f:
                _venue_profiles_cache = yaml.safe_load(f)
        except Exception:
            _venue_profiles_cache = {}

    profiles = _venue_profiles_cache or {}
    generic = profiles.get("generic", "Rigorous academic venue requiring sound methodology.")

    if venue is None:
        return generic

    # Case-insensitive lookup
    for key, val in profiles.items():
        if key.lower() == venue.lower():
            return str(val)

    # Unknown venue — generic + venue name
    return f"Venue: {venue}. " + generic


# ── deterministic checks ──────────────────────────────────────────────────────

def ledger_cross_check(ledger: "Ledger | None") -> list[ReviewPoint]:
    """确定性：把账本里 unpaid/mismatch 承诺转成 ReviewPoint。"""
    if ledger is None:
        return []
    points: list[ReviewPoint] = []
    for p in ledger.promises:
        if p.status == "unpaid":
            points.append(ReviewPoint(
                severity="major",
                category="claim_overreach",
                source="ledger_check",
                title="Claimed contribution not demonstrated",
                detail=f"承诺「{p.text}」在全文未找到对应的实验/论证。",
                anchor_id=p.source_anchor_id,
            ))
        elif p.status == "mismatch":
            points.append(ReviewPoint(
                severity="major",
                category="claim_overreach",
                source="ledger_check",
                title="Claim does not match the evidence",
                detail=f"承诺「{p.text}」兑现了但与声称不符：{p.note or ''}",
                anchor_id=p.source_anchor_id,
            ))
    return points


# ── LLM-backed checks ─────────────────────────────────────────────────────────

async def coherence_check(
    ledger: "Ledger | None",
    text: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """Check abstract↔intro↔conclusion coherence via LLM.

    Returns a list of ReviewPoint objects; empty if LLM unavailable or no issues.
    """
    abstract = find_section(text, ["abstract", "摘要"]) or ""
    intro = find_section(text, ["introduction", "引言"]) or ""
    conclusion = find_section(text, ["conclusion", "结论"]) or ""

    # Summarise promise obligations from ledger
    promise_summary = ""
    if ledger and ledger.promises:
        items = [f"- [{p.kind}] {p.text}" for p in ledger.promises[:8]]
        promise_summary = "Promised contributions:\n" + "\n".join(items)

    prompt = (
        "You are a rigorous academic reviewer. Analyse the following paper sections "
        "for internal coherence issues.\n\n"
        f"ABSTRACT:\n{abstract[:1200]}\n\n"
        f"INTRODUCTION:\n{intro[:1200]}\n\n"
        f"CONCLUSION:\n{conclusion[:1200]}\n\n"
        f"{promise_summary}\n\n"
        "Find issues in these categories (only):\n"
        "- inconsistency: abstract/intro/conclusion contradict each other\n"
        "- gap_mismatch: a stated gap is not addressed in experiments\n"
        "- term_drift: key terminology changes meaning across sections\n\n"
        "Return a JSON array (possibly empty) of objects with fields:\n"
        "  category, severity (minor/major/fatal), title, detail, verbatim_quote\n"
        "Return [] if no issues found. Return ONLY the JSON array, no prose."
    )

    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.3)
    except Exception as exc:
        logger.warning("coherence_check LLM call failed: %s", exc)
        return []

    return _parse_llm_points(raw, source="coherence_check")


async def related_work_check(
    text: str,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> list[ReviewPoint]:
    """Check related-work positioning quality.

    Deterministic: detect missing contrast markers.
    LLM: check for false comparisons and missing key works.
    """
    points: list[ReviewPoint] = []

    rw_text = find_section(text, ["related work", "related-work", "相关工作", "background"])

    if rw_text is None:
        points.append(ReviewPoint(
            severity="info" if _any_rw_elsewhere(text) else "major",
            category="missing_related_work",
            source="rw_check",
            title="No dedicated Related Work section found",
            detail="The paper lacks a clearly labelled Related Work section. "
                   "Reviewers may penalise inadequate literature coverage.",
        ))
        return points

    # Deterministic: check paragraphs for contrast markers
    paras = split_paragraphs(rw_text)
    if paras and not any(has_contrast_marker(p) for p in paras):
        points.append(ReviewPoint(
            severity="major",
            category="weak_positioning",
            source="rw_check",
            title="Related Work lacks contrast with prior art",
            detail="No paragraph in the Related Work section contains a contrast marker "
                   "(e.g. 'However', 'In contrast', '然而'). The section reads as a "
                   "summary rather than positioning your work against prior art.",
        ))

    # LLM check: deeper positioning critique
    prompt = (
        "You are a rigorous academic reviewer. Analyse this Related Work section:\n\n"
        f"{rw_text[:2000]}\n\n"
        "Check for:\n"
        "- weak_positioning: false or overstated comparisons to prior work\n"
        "- missing_related_work: obvious missing citations or sub-fields\n\n"
        "Return a JSON array (possibly empty) with fields:\n"
        "  category, severity (minor/major/fatal), title, detail, verbatim_quote\n"
        "Return ONLY the JSON array, no prose."
    )
    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=1024, temperature=0.3)
    except Exception as exc:
        logger.warning("related_work_check LLM call failed: %s", exc)
        return points

    points.extend(_parse_llm_points(raw, source="rw_check"))
    return points


def _any_rw_elsewhere(text: str) -> bool:
    """Heuristic: 'related' appears somewhere outside a section heading."""
    return bool(re.search(r"\brelated\b", text, re.IGNORECASE))


# ── LLM output parser ─────────────────────────────────────────────────────────

def _parse_llm_points(raw: str, *, source: str) -> list[ReviewPoint]:
    """Parse a JSON array of point dicts returned by the LLM."""
    if not raw or not raw.strip():
        return []
    try:
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[1:])
            cleaned = cleaned.rstrip("`").strip()
        items = json.loads(cleaned)
        if not isinstance(items, list):
            return []
    except (json.JSONDecodeError, ValueError):
        logger.debug("LLM returned non-JSON: %s…", raw[:120])
        return []

    points = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            severity = item.get("severity", "minor")
            category = item.get("category")
            if not category:
                continue  # discard items missing category
            title = item.get("title", "")
            detail = item.get("detail", "")
            if not title or not detail:
                continue  # discard malformed items
            points.append(ReviewPoint(
                severity=severity,  # type: ignore[arg-type]
                category=category,  # type: ignore[arg-type]
                source=source,
                title=title,
                detail=detail,
            ))
        except Exception:
            continue  # discard bad items silently
    return points


# ── main run_review SSE generator ────────────────────────────────────────────

async def run_review(
    doc_id: str,
    text: str,
    venue: "str | None" = None,
    persona: str = "reviewer2",
    ledger: "Ledger | None" = None,
    store: CompanionStore = None,  # type: ignore[assignment]
    *,
    doc_title: str = "",
    focus: "str | dict | None" = None,
    checks: "list[str] | None" = None,
    session_id: "str | None" = None,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: review_point* → complete.

    If *focus* is provided, only analyse the focused text (scoped review).
    Checks order: ledger_check → coherence → rw → llm.
    """
    if checks is None:
        checks = ["ledger", "coherence", "rw", "llm"]

    new_points: list[ReviewPoint] = []
    venue_profile = _load_venue_profile(venue)

    # ── scoped / focused review ───────────────────────────────────────────────
    if focus is not None:
        focus_text = focus if isinstance(focus, str) else focus.get("quote", "")
        focus_prompt = (
            f"You are a rigorous Reviewer-2. The author asks you to scrutinise "
            f"this specific sentence:\n\n\"{focus_text}\"\n\n"
            f"Venue context: {venue_profile[:400]}\n\n"
            "Identify any issues: unsupported claims, logical gaps, ambiguous language, "
            "overreach, or missing evidence. Return a JSON array (possibly empty) with:\n"
            "  category, severity (minor/major/fatal), title, detail, verbatim_quote\n"
            "Return ONLY the JSON array."
        )
        try:
            raw = await call_llm_chat(focus_prompt, cloud_client, ollama_client,
                                      max_tokens=512, temperature=0.4)
        except Exception as exc:
            logger.warning("scoped review LLM failed: %s", exc)
            raw = ""

        for rp in _parse_llm_points(raw, source="scoped"):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

        yield _build_complete_event(new_points, session_id, doc_id, doc_title, venue,
                                    persona, checks, store)
        return

    # ── full review ───────────────────────────────────────────────────────────

    # 1. Ledger cross-check (deterministic)
    if "ledger" in checks:
        for rp in ledger_cross_check(ledger):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

    # 2. Coherence check (LLM)
    if "coherence" in checks:
        for rp in await coherence_check(ledger, text, cloud_client, ollama_client):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

    # 3. Related-work check (deterministic + LLM)
    if "rw" in checks:
        for rp in await related_work_check(text, cloud_client, ollama_client):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

    # 4. General LLM review
    if "llm" in checks:
        prompt = (
            f"You are a rigorous Reviewer-2 for {venue or 'a top-tier academic venue'}.\n"
            f"Venue guidelines: {venue_profile[:600]}\n\n"
            f"Paper text (may be truncated):\n{text[:4000]}\n\n"
            "Write a thorough review. Focus on soundness, novelty, baselines, "
            "experiment design, and writing clarity. Do NOT repeat issues that are "
            "already obvious from the abstract alone.\n\n"
            "Return a JSON array (possibly empty) with fields:\n"
            "  category, severity (minor/major/fatal), title, detail, verbatim_quote\n"
            "Valid categories: motivation, novelty, baseline, ablation, soundness, "
            "claim_overreach, missing_related_work, reproducibility, experiment_design, "
            "writing_clarity, inconsistency, gap_mismatch, weak_positioning, term_drift, other\n"
            "Return ONLY the JSON array."
        )
        try:
            raw = await call_llm_chat(prompt, cloud_client, ollama_client,
                                      max_tokens=2048, temperature=0.5)
        except Exception as exc:
            logger.warning("run_review LLM call failed: %s", exc)
            raw = ""

        for rp in _parse_llm_points(raw, source="llm"):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

    yield _build_complete_event(new_points, session_id, doc_id, doc_title, venue,
                                persona, checks, store)


def _build_complete_event(
    new_points: list[ReviewPoint],
    session_id: "str | None",
    doc_id: str,
    doc_title: str,
    venue: "str | None",
    persona: str,
    checks: list[str],
    store: CompanionStore,
) -> dict:
    """Persist the session and return the complete event dict."""
    by_category: dict[str, int] = {}
    for rp in new_points:
        by_category[rp.category] = by_category.get(rp.category, 0) + 1

    if session_id:
        existing = store.get_review(session_id)
        if existing:
            existing.points.extend(new_points)
            for c in checks:
                if c not in existing.checks:
                    existing.checks.append(c)
            store.save_review(existing)
            return {"event": "complete", "data": json.dumps({
                "session_id": existing.id,
                "by_category": by_category,
                "warnings": [],
            })}

    session = ReviewSession(
        doc_id=doc_id,
        doc_title=doc_title,
        venue=venue,
        persona=persona,  # type: ignore[arg-type]
        checks=checks,
        points=new_points,
    )
    store.save_review(session)
    return {"event": "complete", "data": json.dumps({
        "session_id": session.id,
        "by_category": by_category,
        "warnings": [],
    })}


# ── rebuttal ──────────────────────────────────────────────────────────────────

async def continue_rebuttal(
    session_id: str,
    point_id: str,
    author_message: str,
    doc_text: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: reviewer_reply → status → complete."""
    from .companion_models import RebuttalTurn

    session = store.get_review(session_id)
    if session is None:
        yield {"event": "error", "data": json.dumps({"message": "Session not found"})}
        return

    point = next((p for p in session.points if p.id == point_id), None)
    if point is None:
        yield {"event": "error", "data": json.dumps({"message": "Point not found"})}
        return

    store.append_turns(session_id, point_id, [
        RebuttalTurn(role="author", text=author_message)
    ])

    thread_text = "\n".join(f"[{t.role}] {t.text}" for t in point.thread)
    context_snippet = ""
    if point.anchor_id:
        matching = next((a for a in session.anchors if a.id == point.anchor_id), None)
        if matching and matching.char_start is not None and doc_text:
            s = max(0, matching.char_start - 400)
            e = min(len(doc_text), (matching.char_end or matching.char_start) + 400)
            context_snippet = doc_text[s:e]

    prompt = (
        f"你是该论文的 reviewer（批评点：{point.title}）。\n"
        f"批评详情：{point.detail}\n"
        f"{'论文相关段落：' + context_snippet if context_snippet else ''}\n\n"
        f"对话历史：\n{thread_text}\n\n"
        "作者最新回复如上。若回复站不住——具体指出哪里还是不够（保持苛刻但讲理）；"
        "若被说服——明确说'这点可以认为已 rebutted'并简述为何。只输出你的回复文本。"
    )

    try:
        reply = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=512, temperature=0.5)
    except Exception as exc:
        reply = f"（LLM 不可用：{exc}）"

    new_status = point.status
    surrender_signals = ["已 rebutted", "撤回这条", "可以认为已 rebutted", "被说服", "认可"]
    if any(sig in reply for sig in surrender_signals):
        new_status = "rebutted"

    store.append_turns(session_id, point_id, [
        RebuttalTurn(role="reviewer", text=reply)
    ])
    if new_status != point.status:
        store.update_point(session_id, point_id, new_status)

    yield {"event": "reviewer_reply", "data": json.dumps({"text": reply})}
    yield {"event": "status", "data": json.dumps({"status": new_status})}
    yield {"event": "complete", "data": json.dumps({})}


# ── Phase 5: import real reviews ─────────────────────────────────────────────

async def import_real_reviews(
    doc_id: str,
    doc_title: str,
    text: str,
    reviews_raw: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: review_point* → complete.

    Parse pasted real reviewer comments into a persona='real' ReviewSession.
    Yields error (and saves nothing) if LLM is unavailable or JSON is malformed.
    """
    from .anchor import make_anchor_from_quote
    from .companion_models import RebuttalTurn, ReviewPoint, ReviewSession

    prompt = (
        "以下是一篇论文收到的真实审稿意见（可能来自多位 reviewer）。\n"
        f"---\n{reviews_raw[:4000]}\n---\n"
        "请将每条具体 concern 拆成结构化条目。输出严格 JSON 数组，每项：\n"
        '{"reviewer_label":"Reviewer 1","severity":"minor|major|fatal",'
        '"category":"baseline|novelty|soundness|experiment_design|writing_clarity|other",'
        '"title":"一行摘要","detail":"完整意见（可精简）",'
        '"quote_from_paper":"对应论文里的句子，找不到留空字符串"}。\n'
        "只输出 JSON，不含其它文字。"
    )

    try:
        raw = await call_llm_chat(prompt, cloud_client, ollama_client, max_tokens=2048, temperature=0.2)
    except Exception as exc:
        yield {"event": "error", "data": json.dumps({"message": f"LLM unavailable: {exc}"})}
        return

    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("expected list")
    except Exception as exc:
        yield {"event": "error", "data": json.dumps({"message": f"JSON parse failed: {exc}"})}
        return

    session = ReviewSession(
        doc_id=doc_id,
        doc_title=doc_title,
        venue=None,
        persona="real",
        checks=["imported"],
    )

    for item in items:
        try:
            severity = item.get("severity", "major")
            category = item.get("category", "other")
            title = item.get("title", "")
            detail = item.get("detail", "")
            quote = item.get("quote_from_paper", "")
            reviewer_label = item.get("reviewer_label") or None

            if not title or not detail:
                continue

            anchor_id = None
            if quote:
                anchor = make_anchor_from_quote(doc_id, text, quote)
                session.anchors.append(anchor)
                anchor_id = anchor.id

            point = ReviewPoint(
                severity=severity,
                category=category,
                title=title,
                detail=detail,
                anchor_id=anchor_id,
                source="imported",
                reviewer_label=reviewer_label,
            )
            session.points.append(point)
            yield {"event": "review_point", "data": point.model_dump_json()}
        except Exception:
            continue

    store.save_review(session)
    yield {"event": "complete", "data": json.dumps({"session_id": session.id})}


# ── parallel three-perspective review ─────────────────────────────────────────

async def run_review_parallel(
    doc_id: str,
    text: str,
    venue: "str | None" = None,
    persona: str = "reviewer2",
    ledger: "Ledger | None" = None,
    store: CompanionStore = None,  # type: ignore[assignment]
    *,
    doc_title: str = "",
    session_id: "str | None" = None,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: Parallel three-perspective review (method / experiment / writing).

    Runs three reviewer angles via asyncio.gather, then aggregates and deduplicates.
    Falls back gracefully if one perspective fails.
    """
    import asyncio as _asyncio

    from ._reviewer_perspectives import (
        aggregate_perspectives,
        run_experiment_perspective,
        run_method_perspective,
        run_writing_perspective,
    )

    venue_profile = _load_venue_profile(venue)
    new_points: list[ReviewPoint] = []

    # 1. Deterministic ledger check (fast, no LLM)
    for rp in ledger_cross_check(ledger):
        new_points.append(rp)
        yield {"event": "review_point", "data": rp.model_dump_json()}

    # 2. Three perspectives in parallel
    results = await _asyncio.gather(
        run_method_perspective(text, venue_profile, cloud_client, ollama_client),
        run_experiment_perspective(text, venue_profile, cloud_client, ollama_client),
        run_writing_perspective(text, venue_profile, cloud_client, ollama_client),
        return_exceptions=True,
    )

    method_pts = results[0] if not isinstance(results[0], Exception) else []
    experiment_pts = results[1] if not isinstance(results[1], Exception) else []
    writing_pts = results[2] if not isinstance(results[2], Exception) else []

    logger.info(
        "parallel review: method=%d experiment=%d writing=%d",
        len(method_pts), len(experiment_pts), len(writing_pts),
    )

    aggregated = aggregate_perspectives(method_pts, experiment_pts, writing_pts)

    for rp in aggregated:
        new_points.append(rp)
        yield {"event": "review_point", "data": rp.model_dump_json()}

    yield _build_complete_event(
        new_points, session_id, doc_id, doc_title, venue, persona, ["parallel"], store
    )
