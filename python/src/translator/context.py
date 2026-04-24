"""Lightweight document context extraction for cross-chunk translation."""

from __future__ import annotations

import re


def extract_document_context(text: str, max_chars: int = 1200) -> str:
    """Return a compact document-level context snippet.

    The translator uses this to keep terminology and style consistent across
    chunks. We keep the implementation conservative so it is safe for any
    supported input format.
    """
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    title = lines[0][:200]
    abstract = ""
    joined = "\n".join(lines[:80])
    match = re.search(
        r"(?is)\babstract\b\s*[:.\-]?\s*(.+?)(?:\n\s*(?:keywords|introduction|1[.\s]+introduction)\b|$)",
        joined,
    )
    if match:
        abstract = re.sub(r"\s+", " ", match.group(1)).strip()[:800]

    parts = [f"Title: {title}"]
    if abstract:
        parts.append(f"Abstract: {abstract}")
    else:
        parts.append("Preview: " + re.sub(r"\s+", " ", " ".join(lines[:8]))[:900])

    return "\n".join(parts)[:max_chars]
