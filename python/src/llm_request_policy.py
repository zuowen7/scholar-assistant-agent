"""Shared request policy for provider-specific LLM controls."""

from __future__ import annotations

from typing import Any

VALID_THINKING_MODES = frozenset({"auto", "enabled", "disabled"})
VALID_REASONING_EFFORTS = frozenset({"low", "high", "max"})


def normalize_thinking_mode(value: Any) -> str:
    """Return a supported thinking mode, falling back to automatic policy."""
    mode = str(value or "auto").strip().lower()
    return mode if mode in VALID_THINKING_MODES else "auto"


def normalize_reasoning_effort(value: Any) -> str | None:
    """Return an explicit supported effort, or ``None`` when unset.

    Unlike thinking mode, an invalid explicit effort is rejected instead of
    silently changing an experiment's effective request controls.
    """
    if value is None or str(value).strip() == "":
        return None
    effort = str(value).strip().lower()
    if effort not in VALID_REASONING_EFFORTS:
        allowed = ", ".join(sorted(VALID_REASONING_EFFORTS))
        raise ValueError(f"reasoning_effort must be one of: {allowed}")
    return effort


def resolve_thinking_mode(base_url: str, model: str, configured: Any = "auto") -> str | None:
    """Resolve request-level thinking control.

    DeepSeek V4 defaults to thinking mode. Scholar Assistant's translation,
    structured extraction, and tool loop need bounded latency, so automatic
    policy explicitly selects non-thinking mode on the official endpoint.
    Other providers receive no vendor-specific parameter.
    """
    mode = normalize_thinking_mode(configured)
    normalized_url = base_url.rstrip("/").lower()
    normalized_model = model.strip().lower()
    is_official_deepseek = "api.deepseek.com" in normalized_url and normalized_model.startswith(
        "deepseek-"
    )
    if not is_official_deepseek:
        return None

    if mode != "auto":
        return mode

    if normalized_model.startswith("deepseek-v4-"):
        return "disabled"
    return None


def apply_thinking_policy(
    payload: dict[str, Any],
    *,
    base_url: str,
    model: str,
    configured: Any = "auto",
) -> str | None:
    """Apply a compatible ``thinking`` field when the provider supports it."""
    resolved = resolve_thinking_mode(base_url, model, configured)
    if resolved is not None:
        payload["thinking"] = {"type": resolved}
    return resolved


def apply_reasoning_effort_policy(
    payload: dict[str, Any],
    *,
    base_url: str,
    model: str,
    configured: Any = None,
) -> str | None:
    """Apply DeepSeek V4 ``reasoning_effort`` only when explicitly configured."""
    effort = normalize_reasoning_effort(configured)
    normalized_url = base_url.rstrip("/").lower()
    normalized_model = model.strip().lower()
    if (
        effort is not None
        and "api.deepseek.com" in normalized_url
        and normalized_model.startswith("deepseek-v4-")
    ):
        payload["reasoning_effort"] = effort
        return effort
    return None
