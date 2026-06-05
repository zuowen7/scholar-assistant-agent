"""Sandbox — Windows-adapted process isolation.

Adapted from claw-code rust/crates/runtime/src/sandbox.rs.

Windows doesn't have Linux namespaces, so we provide:
  - CWD restriction
  - Output truncation
  - Environment variable cleanup
  - Timeout enforcement
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SandboxConfig:
    restrict_cwd: bool = True
    timeout_seconds: int = 30
    max_output_bytes: int = 16384
    clear_env_vars: bool = False
    blocked_env_vars: tuple[str, ...] = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")

    def truncate_output(self, output: str) -> str:
        if len(output.encode("utf-8", errors="replace")) <= self.max_output_bytes:
            return output
        # Find safe UTF-8 boundary
        truncated = output[:self.max_output_bytes]
        return truncated + "\n[output truncated]"

    def clean_env(self, env: dict[str, str]) -> dict[str, str]:
        if not self.clear_env_vars:
            return env
        cleaned = dict(env)
        for key in self.blocked_env_vars:
            cleaned.pop(key, None)
            cleaned.pop(key.upper(), None)
        return cleaned


@dataclass
class SandboxResult:
    allowed: bool
    reason: str = ""
    output: str = ""
    truncated: bool = False

    @property
    def blocked(self) -> bool:
        return not self.allowed
