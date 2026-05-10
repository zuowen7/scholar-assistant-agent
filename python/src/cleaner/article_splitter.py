"""Inline reference detector for Perspectives-style multi-article PDFs.

Note: the *actual* multi-article splitter lives in `src.parser.article_detector`
(`extract_articles`) and is wired into `routers/translate.py`. This module's
sole remaining purpose is `detect_inline_refs`, which `cleaner/pipeline.py`
calls as a fallback when no `REFERENCES` header is found.
"""

from __future__ import annotations

import re


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