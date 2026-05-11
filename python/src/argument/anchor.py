"""Anchor — 尽力而为的正文锚点，改稿后用模糊重定位扛住漂移。"""

from __future__ import annotations

import difflib
import re
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

CONTEXT_CHARS = 48
FUZZY_THRESHOLD = 0.62


class Anchor(BaseModel):
    id: str = Field(default_factory=lambda: f"a_{uuid.uuid4().hex[:10]}")
    doc_id: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: str
    context_before: str = ""
    context_after: str = ""
    section_path: Optional[str] = None
    status: Literal["anchored", "drifted", "lost"] = "anchored"


def make_anchor(doc_id: str, text: str, char_start: int, char_end: int) -> Anchor:
    quote = text[char_start:char_end]
    cb = text[max(0, char_start - CONTEXT_CHARS):char_start]
    ca = text[char_end:char_end + CONTEXT_CHARS]
    return Anchor(
        doc_id=doc_id,
        char_start=char_start,
        char_end=char_end,
        quote=quote,
        context_before=cb,
        context_after=ca,
        section_path=section_path_at(text, char_start),
        status="anchored",
    )


def make_anchor_from_quote(doc_id: str, text: str, quote: str) -> Anchor:
    if not quote:
        return Anchor(doc_id=doc_id, quote=quote, status="lost")
    idx = text.find(quote)
    if idx >= 0:
        return make_anchor(doc_id, text, idx, idx + len(quote))
    # lost but preserve quote
    return Anchor(doc_id=doc_id, quote=quote, status="lost")


def relocate(anchor: Anchor, new_text: str) -> Anchor:
    """Pure function: relocate anchor in new_text. Returns updated copy."""
    q = anchor.quote
    if not q:
        return anchor.model_copy(update={"status": "lost", "char_start": None, "char_end": None})

    # Step 1: exact match
    idx = new_text.find(q)
    if idx >= 0:
        cb = new_text[max(0, idx - CONTEXT_CHARS):idx]
        ca = new_text[idx + len(q):idx + len(q) + CONTEXT_CHARS]
        return anchor.model_copy(update={
            "char_start": idx,
            "char_end": idx + len(q),
            "context_before": cb,
            "context_after": ca,
            "section_path": section_path_at(new_text, idx),
            "status": "anchored",
        })

    # Step 2: context window combined needle
    K = 24
    cb_tail = anchor.context_before[-K:] if anchor.context_before else ""
    ca_head = anchor.context_after[:K] if anchor.context_after else ""
    if cb_tail or ca_head:
        needle = cb_tail + q + ca_head
        idx2 = new_text.find(needle)
        if idx2 >= 0:
            real_start = idx2 + len(cb_tail)
            real_end = real_start + len(q)
            cb2 = new_text[max(0, real_start - CONTEXT_CHARS):real_start]
            ca2 = new_text[real_end:real_end + CONTEXT_CHARS]
            return anchor.model_copy(update={
                "char_start": real_start,
                "char_end": real_end,
                "context_before": cb2,
                "context_after": ca2,
                "section_path": section_path_at(new_text, real_start),
                "status": "anchored",
            })

    # Step 3: difflib fuzzy sliding window
    # Optimization: narrow search window using short prefix
    q_len = max(len(q), 1)
    prefix = q[:24]
    search_start = 0
    search_end = len(new_text)
    if len(prefix) >= 5:
        pidx = new_text.find(prefix)
        if pidx >= 0:
            search_start = max(0, pidx - 2000)
            search_end = min(len(new_text), pidx + 2000 + q_len)

    best_ratio = 0.0
    best_start: Optional[int] = None
    best_end: Optional[int] = None
    step = max(1, q_len // 3)
    for i in range(search_start, max(search_start + 1, search_end - q_len + 1), step):
        window = new_text[i:i + q_len]
        ratio = difflib.SequenceMatcher(None, q, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            best_end = i + q_len

    if best_ratio >= FUZZY_THRESHOLD and best_start is not None:
        cb3 = new_text[max(0, best_start - CONTEXT_CHARS):best_start]
        ca3 = new_text[best_end:best_end + CONTEXT_CHARS]
        return anchor.model_copy(update={
            "char_start": best_start,
            "char_end": best_end,
            "context_before": cb3,
            "context_after": ca3,
            "section_path": section_path_at(new_text, best_start),
            "status": "drifted",
        })

    # Step 4: lost
    return anchor.model_copy(update={
        "status": "lost",
        "char_start": None,
        "char_end": None,
    })


def relocate_all(anchors: list[Anchor], new_text: str) -> list[Anchor]:
    return [relocate(a, new_text) for a in anchors]


def section_path_at(text: str, char_offset: int) -> Optional[str]:
    """Scan backwards from char_offset for markdown headings; return nearest title."""
    if char_offset <= 0:
        return None
    snippet = text[:char_offset]
    headers = list(re.finditer(r'^(#{1,6})\s+(.+)', snippet, re.MULTILINE))
    if not headers:
        return None
    last = headers[-1]
    return last.group(2).strip()
