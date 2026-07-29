"""Config validation tests — _validate_config and _load_config from api_factory."""

from __future__ import annotations

import pytest


class TestValidateConfig:
    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config

        _validate_config(cfg)

    def test_valid_config_passes(self) -> None:
        self._call(
            {
                "translator": {"temperature": 0.3},
                "agent": {"temperature": 0.5, "max_steps": 20},
            }
        )

    def test_empty_config_passes(self) -> None:
        self._call({})

    def test_translator_temperature_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="translator.temperature"):
            self._call({"translator": {"temperature": -0.1}})

    def test_translator_temperature_above_2_rejected(self) -> None:
        with pytest.raises(ValueError, match="translator.temperature"):
            self._call({"translator": {"temperature": 2.5}})

    def test_agent_temperature_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent.temperature"):
            self._call({"agent": {"temperature": -1}})

    def test_agent_temperature_above_2_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent.temperature"):
            self._call({"agent": {"temperature": 3.0}})

    def test_agent_max_steps_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent.max_steps"):
            self._call({"agent": {"max_steps": 0}})

    def test_agent_max_steps_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent.max_steps"):
            self._call({"agent": {"max_steps": -5}})

    def test_agent_max_steps_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent.max_steps"):
            self._call({"agent": {"max_steps": 3.5}})

    def test_boundary_values_accepted(self) -> None:
        self._call(
            {
                "translator": {"temperature": 0},
                "agent": {"temperature": 2, "max_steps": 1},
            }
        )

    def test_translator_temperature_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="translator.temperature"):
            self._call({"translator": {"temperature": "hot"}})


class TestEngineValidation:
    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config

        _validate_config(cfg)

    def test_ollama_engine_accepted(self):
        self._call({"translator": {"engine": "ollama"}})

    def test_cloud_engine_accepted(self):
        self._call({"translator": {"engine": "cloud"}})

    def test_invalid_engine_rejected(self):
        with pytest.raises(ValueError, match="translator.engine"):
            self._call({"translator": {"engine": "gpt4"}})

    def test_empty_engine_string_rejected(self):
        with pytest.raises(ValueError, match="translator.engine"):
            self._call({"translator": {"engine": ""}})

    def test_missing_engine_passes(self):
        self._call({"translator": {}})


class TestTimeoutValidation:
    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config

        _validate_config(cfg)

    def test_positive_timeout_accepted(self):
        self._call({"translator": {"timeout": 300.0}})

    def test_zero_timeout_rejected(self):
        with pytest.raises(ValueError, match="translator.timeout"):
            self._call({"translator": {"timeout": 0}})

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValueError, match="translator.timeout"):
            self._call({"translator": {"timeout": -1}})

    def test_missing_timeout_passes(self):
        self._call({"translator": {}})


class TestChunkerValidation:
    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config

        _validate_config(cfg)

    def test_valid_max_tokens_accepted(self):
        self._call({"chunker": {"max_tokens": 2048}})

    def test_zero_max_tokens_rejected(self):
        with pytest.raises(ValueError, match="chunker.max_tokens"):
            self._call({"chunker": {"max_tokens": 0}})

    def test_float_max_tokens_rejected(self):
        with pytest.raises(ValueError, match="chunker.max_tokens"):
            self._call({"chunker": {"max_tokens": 512.5}})

    def test_missing_max_tokens_passes(self):
        self._call({"chunker": {}})


class TestAgentModelValidation:
    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config

        _validate_config(cfg)

    def test_valid_model_string_accepted(self):
        self._call({"agent": {"model": "qwen3:8b"}})

    def test_empty_model_string_allowed(self):
        """Empty model string is valid — means auto-detect."""
        self._call({"agent": {"model": ""}})  # should not raise

    def test_whitespace_model_rejected(self):
        with pytest.raises(ValueError, match="whitespace"):
            self._call({"agent": {"model": "   "}})

    def test_missing_model_passes(self):
        self._call({"agent": {}})


def test_rejects_invalid_agent_thinking_mode():
    from api_factory import _validate_config

    with pytest.raises(ValueError, match="thinking_mode"):
        _validate_config({"agent": {"thinking_mode": "maximum"}})


def test_rejects_unbounded_agent_request_timeout():
    from api_factory import _validate_config

    with pytest.raises(ValueError, match="request_timeout"):
        _validate_config({"agent": {"request_timeout": 301}})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_steps", 257),
        ("max_tool_calls", 129),
        ("soft_tool_calls", -1),
        ("max_model_calls", 65),
        ("max_mutation_attempts", 0),
        ("max_active_seconds", 3601),
    ],
)
def test_rejects_agent_budget_outside_safe_operating_range(field, value):
    from api_factory import _validate_config

    with pytest.raises(ValueError, match=field):
        _validate_config({"agent": {field: value}})


def test_rejects_soft_tool_budget_at_or_above_hard_limit():
    from api_factory import _validate_config

    with pytest.raises(ValueError, match="soft_tool_calls"):
        _validate_config(
            {
                "agent": {
                    "max_tool_calls": 64,
                    "soft_tool_calls": 64,
                }
            }
        )


def test_accepts_hardened_agent_budget_defaults():
    from api_factory import _validate_config

    _validate_config(
        {
            "agent": {
                "max_steps": 96,
                "max_tool_calls": 64,
                "soft_tool_calls": 56,
                "max_model_calls": 32,
                "max_mutation_attempts": 20,
                "max_active_seconds": 600,
                "request_timeout": 120,
            }
        }
    )
