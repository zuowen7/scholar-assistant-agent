"""LSP Client Registry — Language Server Protocol client management.

Port of claw-code rust/crates/runtime/src/lsp_client.rs.

Manages LSP server connections with state machine: Disconnected→Connecting→Ready→Error.
Supports 7 actions: diagnostics, hover, definition, references, completion, symbols, format.
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class LspAction(Enum):
    DIAGNOSTICS = "diagnostics"
    HOVER = "hover"
    DEFINITION = "definition"
    REFERENCES = "references"
    COMPLETION = "completion"
    SYMBOLS = "symbols"
    FORMAT = "format"

    @staticmethod
    def from_str(s: str) -> LspAction | None:
        mapping = {
            "diagnostics": LspAction.DIAGNOSTICS,
            "hover": LspAction.HOVER,
            "definition": LspAction.DEFINITION,
            "goto_definition": LspAction.DEFINITION,
            "references": LspAction.REFERENCES,
            "find_references": LspAction.REFERENCES,
            "completion": LspAction.COMPLETION,
            "completions": LspAction.COMPLETION,
            "symbols": LspAction.SYMBOLS,
            "document_symbols": LspAction.SYMBOLS,
            "format": LspAction.FORMAT,
            "formatting": LspAction.FORMAT,
        }
        return mapping.get(s)

    from_string = from_str


class LspClientState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    ERROR = "error"


class LspRegistry:
    """In-memory LSP client registry with state machine."""

    def __init__(self):
        self._servers: dict[str, dict[str, Any]] = {}
        self._states: dict[str, LspClientState] = {}
        self._errors: dict[str, str] = {}

    def register(self, language: str, config: dict[str, Any]) -> None:
        self._servers[language] = config
        self._states[language] = LspClientState.DISCONNECTED

    def unregister(self, language: str) -> None:
        self._servers.pop(language, None)
        self._states.pop(language, None)
        self._errors.pop(language, None)

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def get_state(self, language: str) -> LspClientState:
        return self._states.get(language, LspClientState.DISCONNECTED)

    def connect(self, language: str) -> None:
        if language in self._servers:
            self._states[language] = LspClientState.CONNECTING

    def mark_ready(self, language: str) -> None:
        if language in self._servers:
            self._states[language] = LspClientState.READY
            self._errors.pop(language, None)

    def mark_error(self, language: str, error: str) -> None:
        if language in self._servers:
            self._states[language] = LspClientState.ERROR
            self._errors[language] = error

    def get_last_error(self, language: str) -> str | None:
        return self._errors.get(language)

    def dispatch(self, language: str, action: LspAction, **kwargs) -> dict[str, Any] | None:
        state = self.get_state(language)
        if state != LspClientState.READY:
            return {"action": action.value, "error": f"server not ready (state={state.value})",
                    "language": language}
        return {"action": action.value, "language": language, "status": "dispatched", **kwargs}
