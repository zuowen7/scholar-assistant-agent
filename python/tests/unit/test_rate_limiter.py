"""Rate limiter tests — _check_rate_limit from api_factory."""

from __future__ import annotations

import time

import pytest


class TestRateLimiter:

    def _get_checker(self):
        from api_factory import _check_rate_limit
        return _check_rate_limit

    def test_allows_requests_under_limit(self) -> None:
        check = self._get_checker()
        for _ in range(5):
            assert check("test-ip-1") is True

    def test_blocks_requests_over_limit(self) -> None:
        from api_factory import _RATE_LIMIT_RPM
        check = self._get_checker()
        ip = f"test-ip-block-{time.monotonic()}"

        # Fill up to limit
        for _ in range(_RATE_LIMIT_RPM):
            assert check(ip) is True
        # Next request should be blocked
        assert check(ip) is False

    def test_different_ips_independent(self) -> None:
        check = self._get_checker()
        ip_a = f"test-ip-a-{time.monotonic()}"
        ip_b = f"test-ip-b-{time.monotonic()}"

        assert check(ip_a) is True
        assert check(ip_b) is True

    def test_window_resets_after_time(self) -> None:
        from api_factory import _rl_windows, _rl_lock, _RATE_LIMIT_RPM
        check = self._get_checker()
        ip = f"test-ip-reset-{time.monotonic()}"

        # Fill up and block
        for _ in range(_RATE_LIMIT_RPM):
            check(ip)
        assert check(ip) is False

        # Manually age out the window entries
        with _rl_lock:
            dq = _rl_windows.get(ip)
            if dq:
                # Shift all timestamps to 120s ago (past the 60s window)
                aged = time.monotonic() - 120.0
                new_dq = type(dq)([aged] * len(dq))
                _rl_windows[ip] = new_dq

        assert check(ip) is True
