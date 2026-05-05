"""Multi-article splitter — detect and split bundled PDFs containing multiple articles.

Science Perspectives, Nature News & Views, and similar journal formats often
bundle 3-5 short articles in a single PDF.  Without splitting, the translation
pipeline merges them into one document, causing glossary pollution, chunk
boundary errors, and broken paragraph alignment.
"""

from __future__ import annotations

import re


# Author name pattern: "First M. Last" or "First Last and First Last"
_AUTHOR_RE = (
    r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+"
    r"(?:\s+(?:and|&|,)\s+[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)*"
)


def split_articles(text: str) -> list[str]:
    """Split cleaned text into independent articles.

    Detection strategy: find interstitial blocks consisting of a short
    title-like line followed by an author-byline line.  These appear between
    bundled Perspectives articles (the original "Downloaded from" footer was
    already stripped by the cleaner, so we match the title + author pattern
    that remains).

    Returns:
        List of article texts.  If only one article is detected, returns [text].
    """
    # Strategy 1: title + author pattern (after watermark removal)
    boundary = re.compile(
        r"\n\n"
        r"(?="
        r"[A-Z][^\n]{10,80}\n+"          # Title line (10-80 chars, Title Case)
        + _AUTHOR_RE +
        r"\s*\n+"                         # Author byline
        r")",
    )
    parts = boundary.split(text)
    articles = [p.strip() for p in parts if p.strip()]

    if len(articles) > 1:
        return articles

    # Strategy 2: if no split found, look for title + author at line start
    # preceded by empty line (looser boundary)
    boundary2 = re.compile(
        r"\n\n"
        r"(?="
        r"[A-Z][^\n]{10,80}\n+"          # Title line
        + _AUTHOR_RE +
        r"\s*$"                           # End of author line
        r")",
        re.MULTILINE,
    )
    parts2 = boundary2.split(text)
    articles2 = [p.strip() for p in parts2 if p.strip()]
    return articles2 if len(articles2) > 1 else [text]


def detect_inline_refs(article_text: str) -> tuple[str, str]:
    """Detect trailing numbered reference entries (Perspectives style).

    Perspectives articles list references as bare numbered entries:
        1. Author, Title, Journal (Year) ...
        2. ...

    These lack a "REFERENCES" header, so the standard reference detector misses them.

    Returns:
        (body_text, references_text) — references_text is empty if not found.
    """
    lines = article_text.rstrip().split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if re.match(r"^\s*1\.\s+[A-Z]", lines[i]):
            seen = {1}
            for j in range(i + 1, len(lines)):
                m = re.match(r"^\s*(\d+)\.\s+[A-Z]", lines[j])
                if m:
                    seen.add(int(m.group(1)))
            if len(seen) >= 3:
                return (
                    "\n".join(lines[:i]).rstrip(),
                    "\n".join(lines[i:]),
                )
    return article_text, ""
