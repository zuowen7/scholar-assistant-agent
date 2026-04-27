"""Config validation tests — _validate_config and _load_config from api_factory."""

from __future__ import annotations

import pytest


class TestValidateConfig:

    def _call(self, cfg: dict) -> None:
        from api_factory import _validate_config
        _validate_config(cfg)

    def test_valid_config_passes(self) -> None:
        self._call({
            "translator": {"temperature": 0.3},
            "agent": {"temperature": 0.5, "max_steps": 20},
        })

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
        self._call({
            "translator": {"temperature": 0},
            "agent": {"temperature": 2, "max_steps": 1},
        })

    def test_translator_temperature_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="translator.temperature"):
            self._call({"translator": {"temperature": "hot"}})
