"""Anchor — 尽力而为的正文锚点，改稿后用模糊重定位扛住漂移。"""

from __future__ import annotations

import difflib
import re
import sys
import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

CONTEXT_CHARS = 48
FUZZY_THRESHOLD = 0.62
FUZZY_CONTEXT_THRESHOLD = 0.40


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    quote_ratio: float
    context_ratio: float
    section_match: int
    position_distance: int

    @property
    def rank(self) -> tuple[float, float, float, int, int, int]:
        """Stable quality-first ordering independent of discovery order."""

        combined = 0.68 * self.quote_ratio + 0.27 * self.context_ratio + 0.05 * self.section_match
        return (
            -combined,
            -self.context_ratio,
            -self.quote_ratio,
            self.position_distance,
            self.start,
            self.end,
        )


class Anchor(BaseModel):
    id: str = Field(default_factory=lambda: f"a_{uuid.uuid4().hex[:10]}")
    doc_id: str
    char_start: int | None = None
    char_end: int | None = None
    quote: str
    context_before: str = ""
    context_after: str = ""
    section_path: str | None = None
    status: Literal["anchored", "drifted", "lost"] = "anchored"


def make_anchor(doc_id: str, text: str, char_start: int, char_end: int) -> Anchor:
    quote = text[char_start:char_end]
    cb = text[max(0, char_start - CONTEXT_CHARS) : char_start]
    ca = text[char_end : char_end + CONTEXT_CHARS]
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

    # Exact quotes can repeat. Rank every occurrence against the stored context
    # instead of accepting str.find()'s first occurrence.
    exact_spans = [(start, start + len(q)) for start in _find_all(new_text, q)]
    if exact_spans:
        best = _rank_candidates(anchor, new_text, exact_spans, exact=True)[0]
        return _updated_anchor(anchor, new_text, best.start, best.end, "anchored")

    fuzzy = _rank_candidates(anchor, new_text, _fuzzy_spans(q, new_text), exact=False)
    if fuzzy and _accept_fuzzy(anchor, fuzzy[0]):
        best = fuzzy[0]
        return _updated_anchor(anchor, new_text, best.start, best.end, "drifted")

    return anchor.model_copy(update={"status": "lost", "char_start": None, "char_end": None})


def _find_all(text: str, needle: str) -> list[int]:
    starts: list[int] = []
    offset = 0
    while True:
        found = text.find(needle, offset)
        if found < 0:
            return starts
        starts.append(found)
        offset = found + 1


def _similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


def _context_similarity(anchor: Anchor, text: str, start: int, end: int) -> float:
    before = text[max(0, start - CONTEXT_CHARS) : start]
    after = text[end : end + CONTEXT_CHARS]
    scores: list[float] = []
    if anchor.context_before:
        scores.append(_similarity(anchor.context_before[-CONTEXT_CHARS:], before[-CONTEXT_CHARS:]))
    if anchor.context_after:
        scores.append(_similarity(anchor.context_after[:CONTEXT_CHARS], after[:CONTEXT_CHARS]))
    return sum(scores) / len(scores) if scores else 1.0


def _rank_candidates(
    anchor: Anchor,
    text: str,
    spans: list[tuple[int, int]],
    *,
    exact: bool,
) -> list[_Candidate]:
    unique = sorted(set(spans))
    candidates: list[_Candidate] = []
    for start, end in unique:
        if not (0 <= start < end <= len(text)):
            continue
        section = section_path_at(text, start)
        section_match = int(bool(anchor.section_path) and section == anchor.section_path)
        old_start = anchor.char_start
        distance = abs(start - old_start) if old_start is not None else sys.maxsize
        candidates.append(
            _Candidate(
                start=start,
                end=end,
                quote_ratio=1.0 if exact else _similarity(anchor.quote, text[start:end]),
                context_ratio=_context_similarity(anchor, text, start, end),
                section_match=section_match,
                position_distance=distance,
            )
        )
    return sorted(candidates, key=lambda item: item.rank)


def _fuzzy_spans(quote: str, text: str) -> list[tuple[int, int]]:
    """Return bounded, deterministic phrase candidates without copying relocate semantics."""

    if not text:
        return []
    tokens = list(re.finditer(r"\S+", text))
    quote_tokens = max(1, len(re.findall(r"\S+", quote)))
    widths = range(max(1, quote_tokens - 1), quote_tokens + 2)
    spans: set[tuple[int, int]] = set()
    for index, token in enumerate(tokens):
        for width in widths:
            last = index + width - 1
            if last < len(tokens):
                spans.add((token.start(), tokens[last].end()))

    # Quotes without useful token boundaries still receive candidates around
    # their longest common block. The proposal set is small and deterministic.
    match = difflib.SequenceMatcher(None, quote, text, autojunk=False).find_longest_match()
    if match.size:
        estimated_start = max(0, match.b - match.a)
        delta = max(2, min(12, len(quote) // 3))
        for start_shift in range(-delta, delta + 1):
            start = estimated_start + start_shift
            if start < 0 or start >= len(text):
                continue
            for length_shift in range(-delta, delta + 1):
                end = start + max(1, len(quote) + length_shift)
                if end <= len(text):
                    spans.add((start, end))
    return sorted(spans)


def _accept_fuzzy(anchor: Anchor, candidate: _Candidate) -> bool:
    if candidate.quote_ratio < FUZZY_THRESHOLD:
        return False
    has_context = bool(anchor.context_before or anchor.context_after)
    if has_context and candidate.context_ratio < FUZZY_CONTEXT_THRESHOLD:
        return False
    combined = (
        0.68 * candidate.quote_ratio
        + 0.27 * candidate.context_ratio
        + 0.05 * candidate.section_match
    )
    return combined >= 0.68


def _updated_anchor(
    anchor: Anchor,
    text: str,
    start: int,
    end: int,
    status: Literal["anchored", "drifted"],
) -> Anchor:
    return anchor.model_copy(
        update={
            "char_start": start,
            "char_end": end,
            "context_before": text[max(0, start - CONTEXT_CHARS) : start],
            "context_after": text[end : end + CONTEXT_CHARS],
            "section_path": section_path_at(text, start),
            "status": status,
        }
    )


def relocate_all(anchors: list[Anchor], new_text: str) -> list[Anchor]:
    return [relocate(a, new_text) for a in anchors]


def section_path_at(text: str, char_offset: int) -> str | None:
    """Scan backwards from char_offset for markdown headings; return nearest title."""
    if char_offset <= 0:
        return None
    snippet = text[:char_offset]
    headers = list(re.finditer(r"^(#{1,6})\s+(.+)", snippet, re.MULTILINE))
    if not headers:
        return None
    last = headers[-1]
    return last.group(2).strip()
