"""Unit tests for version module — _version.py exports valid semver."""

from __future__ import annotations

import re


class TestVersionModule:
    """src._version.__version__ is a valid semver string used by /api/health
    and the frontend update checker."""

    def test_version_is_string(self) -> None:
        from src._version import __version__

        assert isinstance(__version__, str)

    def test_version_is_semver_three_parts(self) -> None:
        from src._version import __version__

        assert re.match(r"^\d+\.\d+\.\d+$", __version__), (
            f"Version '{__version__}' must be X.Y.Z format"
        )

    def test_version_parseable_as_ints(self) -> None:
        from src._version import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        for p in parts:
            assert int(p) >= 0
