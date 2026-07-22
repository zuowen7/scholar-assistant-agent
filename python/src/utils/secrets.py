"""Utilities for masking sensitive credential values in logs and API responses."""

from __future__ import annotations

import re

_BEARER_RE = re.compile(r'Bearer\s+\S+', re.IGNORECASE)


def mask_key(key: str) -> str:
    """Return a partially-redacted version of an API key string."""
    if not key:
        return key
    if len(key) > 12:
        return key[:8] + "****" + key[-4:]
    if len(key) > 8:
        return key[:4] + "****" + key[-4:]
    return "****"


def is_masked(value: str) -> bool:
    """Return True if the value looks like it has already been masked."""
    return "****" in value


def mask_bearer(text: str) -> str:
    """Replace Bearer token in a log string with Bearer ***."""
    return _BEARER_RE.sub("Bearer ***", text)


def mask_config(config: dict) -> None:
    """Mask every ``api_key`` field inside a config dict in-place.

    Config sections are extended independently (cloud translation, Agent,
    Zotero, Vision, and future providers). Traversing the config prevents a new
    section from accidentally exposing its credential through ``/api/config``.
    """
    for key, value in config.items():
        if key == "api_key" and isinstance(value, str):
            config[key] = mask_key(value)
        elif isinstance(value, dict):
            mask_config(value)
