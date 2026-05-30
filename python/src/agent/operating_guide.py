"""Machine-readable Agent operating guide.

This is the compact runtime counterpart of AGENTS.md. It exposes the stable
agent contract to UI/debug surfaces and external assistants without requiring
them to parse a long project document.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_GUIDE: dict[str, Any] = {
    "name": "Scholar Assistant Agent Operating Guide",
    "version": 1,
    "role": (
        "Scholar Assistant is Codex for papers: a privacy-first academic "
        "workspace agent that reads and edits PDFs, drafts, bibliographies, "
        "data, and export artifacts inside the user's selected workspace."
    ),
    "gates": [
        {
            "name": "SmartPause",
            "trigger": "Large deletes, file overwrites, large file creation, or git state changes.",
            "action": "Force await_approval even when auto_approve is enabled.",
        },
        {
            "name": "WorkspaceBoundary",
            "trigger": "A file tool targets a path outside workspace_root.",
            "action": "Force await_approval and temporarily enable escape only after approval.",
        },
        {
            "name": "DocQAShortCircuit",
            "trigger": "The user asks about the open document without mutation intent.",
            "action": "Use oneshot_doc_qa and do not enter ReAct or call tools.",
        },
        {
            "name": "ProtocolContract",
            "trigger": "SSE payloads, tool metadata, or ledger routes change.",
            "action": "Update backend models, frontend consumers, and protocol tests together.",
        },
    ],
    "decision_guide": [
        {
            "intent": "translation",
            "signals": "PDF upload or translation request.",
            "path": "translate_sse_pipeline",
            "primary_files": ["src/composables/useTranslate.ts", "python/routers/translate.py"],
        },
        {
            "intent": "document_qa",
            "signals": "Summarize, critique, or ask about the currently open document.",
            "path": "oneshot_doc_qa",
            "primary_files": ["python/routers/agent.py"],
        },
        {
            "intent": "file_mutation",
            "signals": "Write, save, create, edit, replace, run, execute, or commit.",
            "path": "agent_react_with_approval",
            "primary_files": ["python/src/agent/session.py", "python/src/agent/security_gate.py"],
        },
        {
            "intent": "ai_panel_preset_edit",
            "signals": "Polish, expand, review, or translate from editor preset buttons.",
            "path": "api_edit_oneshot",
            "primary_files": ["src/components/AiPanel.vue", "python/routers/editor.py"],
        },
        {
            "intent": "argument_companion",
            "signals": "Build ledger, review, rebuttal, or import real reviews.",
            "path": "argument_companion_routes",
            "primary_files": ["python/routers/argument.py", "src/composables/useArgumentCompanion.ts"],
        },
    ],
    "invariants": [
        "Agent event metadata uses tool_name, not bare tool.",
        "Translation SSE events keep the translate.* prefix.",
        "Ledger routes pass doc_id as a query parameter.",
        "Runtime MEMORY.md must not overwrite user-edited memory.",
        "Unsaved Monaco tabs must not be overwritten by agent writes.",
    ],
    "verification": [
        "npx vitest",
        "cd python && pytest tests/unit/ -q",
        "cd python && pytest tests/ -v",
    ],
}


def build_agent_operating_guide() -> dict[str, Any]:
    """Return a JSON-safe copy of the current Agent operating guide."""
    return deepcopy(_GUIDE)
