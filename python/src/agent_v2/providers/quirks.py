"""Provider quirks — 每个 provider 的特殊行为配置。

参考 claw-code:
  - detect_provider_kind() / model_family_identity_for()
  - model_rejects_is_error_field() / model_requires_reasoning_content_in_history()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderQuirks:
    """Provider-specific behavioral flags."""

    # Content handling
    omit_content_with_tool_calls: bool = True   # Don't send content:null with tool_calls
    include_name_in_tool_def: bool = False      # Duplicate function name in tool def

    # History handling
    requires_thinking_with_tool_use: bool = False  # Anthropic-format: thinking blocks required
    strip_reasoning_from_history: bool = False     # Don't include reasoning in history

    # Request tuning
    supports_stream_options: bool = False       # stream_options parameter
    max_tool_output_chars: int = 4000           # Truncate tool outputs
    prefer_temperature_zero: bool = False       # Use temperature=0 for tool calling

    # Response quirks
    choices_can_be_empty: bool = False          # Streaming chunks may have empty choices
    usage_in_stream_chunks: bool = False        # Usage stats in streaming chunks
    wraps_tool_calls_in_extra_json: bool = False  # Tool args need double-JSON parsing


# ── Provider registry ──

_PROVIDER_QUIRKS: dict[str, ProviderQuirks] = {}


def _register(pattern: str, **kwargs: Any) -> None:
    _PROVIDER_QUIRKS[pattern] = ProviderQuirks(**kwargs)


# DeepSeek: strict about tool history format, empty choices in streaming
_register("deepseek",
          omit_content_with_tool_calls=True,
          choices_can_be_empty=True,
          supports_stream_options=False)

# Claude (Anthropic): Anthropic-format, requires thinking with tool_use
_register("claude",
          omit_content_with_tool_calls=False,
          requires_thinking_with_tool_use=True)

# GPT-4o/OpenAI: standard OpenAI, supports stream_options
_register("gpt-4o",
          supports_stream_options=True)

_register("gpt-4",
          supports_stream_options=True)

# Ollama/Qwen: local, may need temperature tweaks
_register("qwen",
          prefer_temperature_zero=True,
          choices_can_be_empty=True)

_register("llama",
          prefer_temperature_zero=True,
          choices_can_be_empty=True)

# Generic OpenAI-compatible: safest defaults
_register("openai",
          supports_stream_options=False)


def detect_quirks(model: str, base_url: str = "") -> ProviderQuirks:
    """检测 provider 并返回对应的 quirks 配置。参考 claw-code detect_provider_kind。"""
    model_lower = model.lower()
    url_lower = base_url.lower()

    # Exact/substring match
    for pattern, quirks in _PROVIDER_QUIRKS.items():
        if pattern in model_lower or pattern in url_lower:
            return quirks

    # Heuristic: if URL contains "anthropic", it's Claude-family
    if "anthropic" in url_lower:
        return _PROVIDER_QUIRKS.get("claude", ProviderQuirks())

    # Heuristic: if URL contains "ollama" or "localhost", it's local
    if "ollama" in url_lower or "localhost" in url_lower or "127.0.0.1" in url_lower:
        return _PROVIDER_QUIRKS.get("qwen", ProviderQuirks())

    # Default: safest possible (OpenAI-compatible generic)
    return ProviderQuirks(omit_content_with_tool_calls=True,
                          choices_can_be_empty=True,
                          supports_stream_options=False)
