"""Argument Companion — section extraction utilities (Phase 3)."""

from __future__ import annotations

import re

# Markdown heading pattern: # … or ## … (levels 1–6)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

_CONTRAST_MARKERS = [
    # English
    r"\bhowever\b",
    r"\bin contrast\b",
    r"\bunlike\b",
    r"\bwhereas\b",
    r"\bwhile\b",
    r"\bnevertheless\b",
    r"\byet\b",
    r"\bon the other hand\b",
    r"\balthough\b",
    r"\bnonetheless\b",
    r"\bbut\b",
    # Chinese
    r"然而",
    r"与此不同",
    r"相比之下",
    r"但(?:是)?",
    r"而本文",
    r"而我们",
    r"前人.*而本",
    r"而(?:本文|本方法|本工作)",
]

_CONTRAST_RE = re.compile(
    "|".join(_CONTRAST_MARKERS),
    re.IGNORECASE,
)


def find_section(text: str, names: list[str]) -> str | None:
    """Return the body text of the first section whose heading matches any of *names*.

    Matching is case-insensitive. The returned text excludes the heading line
    itself and stops before the next heading of equal or higher level.
    Returns ``None`` when no matching heading is found.
    """
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return None

    lower_names = [n.lower() for n in names]

    for i, m in enumerate(headings):
        heading_text = m.group(2).strip().lower()
        if any(name in heading_text or heading_text in name for name in lower_names):
            start = m.end()
            # Find the end: next heading at same level or shallower
            level = len(m.group(1))
            end = len(text)
            for j in range(i + 1, len(headings)):
                next_level = len(headings[j].group(1))
                if next_level <= level:
                    end = headings[j].start()
                    break
            return text[start:end].strip()

    return None


def split_paragraphs(text: str) -> list[str]:
    """Split *text* on blank lines, returning non-empty paragraph strings."""
    if not text:
        return []
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def has_contrast_marker(text: str) -> bool:
    """Return True if *text* contains a contrast/counterpoint marker."""
    if not text:
        return False
    return bool(_CONTRAST_RE.search(text))


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown into ``(heading, full_section_text)`` chunks."""
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return [("", text)] if text else []

    sections: list[tuple[str, str]] = []
    if headings[0].start() > 0:
        sections.append(("", text[: headings[0].start()]))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append((heading.group(2).strip(), text[heading.start() : end]))
    return sections


def build_section_excerpt(
    text: str,
    *,
    max_chars: int,
    preferred_headings: tuple[str, ...] = (),
) -> str:
    """Build a bounded excerpt without silently dropping all late sections.

    When preferred headings are supplied, matching sections are used first.
    Otherwise the character budget is distributed across every Markdown
    section, preserving document order.
    """
    if max_chars <= 0 or not text:
        return ""
    if len(text) <= max_chars and not preferred_headings:
        return text

    sections = split_markdown_sections(text)
    preferred = tuple(term.lower() for term in preferred_headings)
    selected = [
        (heading, body)
        for heading, body in sections
        if preferred and any(term in heading.lower() for term in preferred)
    ]
    if not selected:
        selected = sections

    joined = "\n\n".join(body for _, body in selected)
    if len(joined) <= max_chars:
        return joined

    # Give every selected section representation instead of taking a prefix.
    separator_budget = max(0, 2 * (len(selected) - 1))
    quota = max(160, (max_chars - separator_budget) // max(1, len(selected)))
    excerpt = "\n\n".join(body[:quota] for _, body in selected)
    return excerpt[:max_chars]
