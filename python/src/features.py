"""Centralized optional-dependency detection.

Each flag is computed once at import time.  Import and check ``features.X``
instead of scattering try/except ImportError across the codebase.

Available flags:
    agent                — Agent subsystem (ReAct loop, RAG, skills, sessions)
    plugin               — Plugin system (MCP-style tool registry)
    argument             — Advanced argument mapping (tree, logic checker, expander)
    mcp                  — MCP protocol server (stdio transport)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _probe(label: str, *modules: str) -> bool:
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            logger.debug("feature %s: %s not available", label, mod)
            return False
    return True


# ── Subsystem gates ──────────────────────────────────────────────────

agent: bool = _probe("agent", "src.agent")
plugin: bool = _probe("plugin", "src.plugin")
argument: bool = _probe("argument", "src.argument.models")
mcp: bool = _probe("mcp", "mcp.server", "mcp.server.stdio")
