"""Shared JSON extraction utilities for LLM output parsing.

Extracts valid JSON objects or arrays from LLM responses that may contain
markdown fences, preamble/postamble text, or multiple JSON structures.

Algorithm:
1. Try json.loads directly (handles clean JSON)
2. Strip markdown fences and retry
3. Balanced-brace scan from first open char to its match (handles preamble)
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(
    r"```(?:[a-zA-Z]*)\s*\n(.*?)\n\s*```", re.DOTALL
)


def extract_json_object(text: str) -> dict | None:
    """Extract the first valid JSON object from LLM output."""
    result = _extract(text, "{", "}")
    if isinstance(result, dict):
        return result
    return None


def extract_json_array(text: str) -> list | None:
    """Extract the first valid JSON array from LLM output."""
    result = _extract(text, "[", "]")
    if isinstance(result, list):
        return result
    return None


def _extract(text: str, open_ch: str, close_ch: str) -> Any | None:
    if not text or not text.strip():
        return None

    # 1. Direct parse
    parsed = _try_loads(text.strip())
    if parsed is not None and _is_type(parsed, open_ch):
        return parsed

    # 2. Strip markdown fences
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        parsed = _try_loads(fence_match.group(1).strip())
        if parsed is not None and _is_type(parsed, open_ch):
            return parsed

    # 3. Balanced-brace scan from first open char
    start = text.find(open_ch)
    if start == -1:
        return None
    end = _balanced_scan(text, start, open_ch, close_ch)
    if end is not None:
        parsed = _try_loads(text[start : end + 1])
        if parsed is not None and _is_type(parsed, open_ch):
            return parsed

    return None


def _try_loads(s: str) -> Any | None:
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return None


def _is_type(value: Any, open_ch: str) -> bool:
    if open_ch == "{":
        return isinstance(value, dict)
    return isinstance(value, list)


def _balanced_scan(text: str, start: int, open_ch: str, close_ch: str) -> int | None:
    """Find the closing index matching the open char at *start*.

    Tracks brace depth while skipping characters inside JSON strings
    (double-quoted or single-quoted) to avoid false matches.
    """
    depth = 0
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            i = _skip_string(text, i + 1, '"')
            continue
        if ch == "'":
            i = _skip_string(text, i + 1, "'")
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _skip_string(text: str, start: int, quote: str) -> int:
    """Skip past the closing quote of a JSON-style string, handling escapes."""
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2  # skip escaped char
            continue
        if ch == quote:
            return i + 1  # past closing quote
        i += 1
    return n
