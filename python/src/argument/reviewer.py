"""Argument Companion — Reviewer-2 对抗评审（Phase 3 实现，Phase 1 桩）。"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from .companion_models import Ledger, ReviewPoint, ReviewSession
from .companion_store import CompanionStore

logger = logging.getLogger(__name__)


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


async def run_review(
    doc_id: str,
    doc_title: str,
    text: str,
    venue: "str | None",
    persona: str,
    ledger: "Ledger | None",
    store: CompanionStore,
    *,
    focus: "dict | None" = None,
    checks: "list[str] | None" = None,
    session_id: "str | None" = None,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: review_point* → complete。Phase 1 桩：只跑确定性 ledger_cross_check。"""
    if checks is None:
        checks = ["llm"]

    new_points: list[ReviewPoint] = []

    # Deterministic ledger check
    if "ledger" in checks or checks == ["llm"]:
        for rp in ledger_cross_check(ledger):
            new_points.append(rp)
            yield {"event": "review_point", "data": rp.model_dump_json()}

    # Build / append session
    if session_id:
        existing = store.get_review(session_id)
        if existing:
            existing.points.extend(new_points)
            existing.anchors.extend([])
            for c in checks:
                if c not in existing.checks:
                    existing.checks.append(c)
            store.save_review(existing)
            yield {"event": "complete", "data": json.dumps({
                "session_id": existing.id,
                "by_category": {},
                "warnings": [],
            })}
            return

    session = ReviewSession(
        doc_id=doc_id,
        doc_title=doc_title,
        venue=venue,
        persona=persona,  # type: ignore[arg-type]
        checks=checks,
        points=new_points,
    )
    store.save_review(session)
    yield {"event": "complete", "data": json.dumps({
        "session_id": session.id,
        "by_category": {},
        "warnings": [],
    })}


async def continue_rebuttal(
    session_id: str,
    point_id: str,
    author_message: str,
    doc_text: str,
    store: CompanionStore,
    cloud_client: Any = None,
    ollama_client: Any = None,
) -> AsyncIterator[dict]:
    """SSE: reviewer_reply → status → complete。Phase 1 桩。"""
    from .companion_models import RebuttalTurn
    from .llm_client import call_llm_chat

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

    # Build context
    thread_text = "\n".join(
        f"[{t.role}] {t.text}" for t in point.thread
    )
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
        reply = await call_llm_chat(
            prompt, cloud_client, ollama_client, max_tokens=512, temperature=0.5
        )
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
