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
    return key


def is_masked(value: str) -> bool:
    """Return True if the value looks like it has already been masked."""
    return "****" in value


def mask_bearer(text: str) -> str:
    """Replace Bearer token in a log string with Bearer ***."""
    return _BEARER_RE.sub("Bearer ***", text)


def mask_config(config: dict) -> None:
    """Mask the api_key field inside a config dict in-place."""
    cloud_cfg = config.get("translator", {}).get("cloud", {})
    api_key = cloud_cfg.get("api_key", "")
    if api_key:
        cloud_cfg["api_key"] = mask_key(api_key)
