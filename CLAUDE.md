# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scholar Assistant — privacy-first academic AI writing assistant (Tauri 0.3.1 / npm 0.2.0). Translates PDFs (parse -> clean -> chunk -> translate -> format via SSE), provides an AI editor (Monaco + Agent chat), and exports to LaTeX/Word. Runs as desktop app (Tauri manages Python + Ollama subprocesses) or standalone Python API.

## Build Commands

```bash
# Frontend
npm install
npm run dev                    # Vite dev server (proxies /api -> localhost:18088)
npm run build                  # Production build
npx vitest                     # Frontend unit tests (jsdom)
npx vitest src/__tests__/useEditor.test.ts  # Single test file

# Python backend
cd python
pip install -r requirements-lock.txt               # Locked deps (pinned, reproducible)
pip install -r requirements.txt                    # OR loose deps (flexible, >= pins)
pip install -r requirements-ocr.txt                # Optional: OCR fallback (pytesseract, pdf2image, paddleocr)
pytest tests/ -v                                   # All tests (unit + integration)
pytest tests/unit/test_parser.py                   # Single test file
pytest tests/unit/ -v                              # Unit tests only
pytest tests/integration/ -v                       # Integration tests (needs running API)
pytest tests/ -k "test_chunk"                      # By keyword

# Desktop app
npx tauri dev                  # Dev mode (auto-starts Python API on :18088)
npx tauri build                # Production build
# Windows: use start_dev.bat — clears HTTP_PROXY env vars first
# (httpx hangs on import when proxy vars are set)

# Docker
docker compose --project-name scholar-assistant build && docker compose up

# Python CLI
cd python && python main.py paper.pdf -o paper.md
```

## Architecture

### Stack

| Layer | Technology |
|-------|------------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor, Vue Flow (mind map canvas) |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE (`sse-starlette`) |
| Local LLM | Ollama + Qwen3:8b (port 11434) |
| Cloud LLM | OpenAI / Anthropic / DeepSeek / Moonshot / etc. (18 providers via `PROVIDER_PRESETS`) |
| PDF | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |
| Export | Pandoc + LaTeX templates (IEEE/ACM/NeurIPS/LNCS/Elsevier) |

### Data Flow

**Translation pipeline** (5-step SSE, `useTranslate.ts` -> `routers/translate.py`):
1. Parse -> 2. Clean -> 3. Chunk -> 4. Translate -> 5. Format
SSE events: `progress` -> `parsed` -> `cleaned` -> `chunked` -> `chunk_done`(xN) -> `complete`

**Agent chat** (ReAct loop, `useAgentChat.ts` -> `routers/agent.py` -> `agent/agent.py`):
SSE events stream tool calls and reasoning steps. Agent can use RAG, Zotero, arXiv search, file ops.

### Backend Structure (`python/`)

`api_factory.py` — `create_app()` factory: app setup, config loading, shared helpers, router registration. Routes are split into five modules under `routers/`, each exporting a `register_*` function receiving shared state (config getters, runtime dirs, RAG store):
- `routers/translate.py` — translation pipeline, config CRUD, health, Ollama/cloud status
- `routers/agent.py` — Agent chat, RAG document management
- `routers/editor.py` — AI edit, complete, export (LaTeX/PDF/Word), vision, citation, Zotero, paper scaffolding
- `routers/argument.py` — Dynamic Argument Mapping (tree CRUD, expand, review, flatten)
- `routers/mindmap.py` — Mind map CRUD, AI expand, layout

`api.py` — entry point used by Tauri and standalone. Uses **delayed imports** for optional subsystems (Agent, Plugin): they set `_AGENT_AVAILABLE = False` on ImportError, so translation works without them.

Key backend modules under `src/`:
- `parser/` — 16 format parsers, auto-detect single/dual column
- `cleaner/` — 17-stage text pipeline
- `chunker/` — 3 strategies (sentence/paragraph/fixed)
- `translator/` — `ollama_client.py` + `cloud_client.py` (`PROVIDER_PRESETS`, 18 providers)
- `formatter/` — bilingual/translated-only/parallel output + `renderer.py` (PDF/LaTeX) + `word_exporter.py`
- `agent/` — Core: `agent.py` (AgentLoop ReAct engine), `context_compressor.py`, `prompt_builder.py`, `models.py`. Memory+Evolution: `memory.py`, `skill_system.py`, `trajectory.py`, `review_agent.py`. Tools+Resources: `tools/` (core, workspace_tools, atomic_tools, builtin_tools, registry), `rag.py`, `vram_manager.py`, `tool_generator.py`. Reliability: `error_classifier.py`, `hooks.py`. Integration: `mcp_server.py`, `auto_processor.py`, `special_elements.py`.
- `plugin/` — MCP-style plugin registry + 16 built-in tools
- `argument/` — Dynamic Argument Mapping: tree store, logic checker, expander, observer, feedback generator, flattener
- `citation/`, `zotero/`, `mcp/vision_client.py` — citation indexer, Zotero API client, multi-modal image analysis
- `prompts/` — Academic writing prompt templates (polish, expand, etc.)
- `config/default.yaml` — All runtime configuration

### Frontend Structure (`src/`)

- `App.vue` — Thin shell (~680 lines): wires AppTopBar, TranslateView, AgentPanel, EditorLayout. Manages app-wide state (theme, engine settings, drag-drop, background layer, health checks).
- `composables/` — state stores; all major ones are **true singletons** (module-level state, shared app-wide):
  - `useTranslate.ts` — singleton; SSE translation pipeline state + reconnect logic
  - `useEditor.ts` — singleton; Monaco instance, tabs, AI panel, ghost text completion
  - `useFileTree.ts` — singleton; file system navigation
  - `useAgentChat.ts` — singleton (module-level refs); Agent SSE chat state + session/approval state
  - `useMindMap.ts` — singleton; mind map data (CRUD, undo/redo, flow adapters `toFlowNodes`/`toFlowEdges`)
  - `useMindMapKeyboard.ts` — keyboard handler (Tab/Enter/F2/arrows/Ctrl+Z)
  - `useMindMapLayout.ts` — dagre auto-layout
  - `useMindMapAnalysis.ts` — AI analysis integration
- `components/` — extracted from the former monolithic App.vue:
  - `AppTopBar.vue` — brand, mode switch, engine/display settings panels, health pills, window controls
  - `TranslateView.vue` — upload drop card, progress/step indicators, result views (sentence/parallel/markdown), sentence splitting, markdown rendering
  - `AgentPanel.vue` — agent chat/docs/templates/sessions side panel (self-contained via `useAgentChat()`)
  - `EditorLayout.vue` — editor mode layout (~650 lines): FileTree sidebar + MonacoEditor + AiPanel right panel + ArgumentMap, with tab management and keyboard shortcuts
  - `mindmap/` — MindMapCanvas (Vue Flow), MindNodeCard, MindEdge
  - `MindMapView.vue`, `MindMapFloatingToolbar.vue`, `MindMapAiHints.vue`
  - `ui/` — design-system primitives: UiButton, UiIconButton, UiPanel, UiInput, UiTextarea, UiSelect, UiTooltip
  - Other: MonacoEditor, AiPanel, FileTree, MarkdownPreview, ArgumentMap, EditorTabs, CommandPalette, TemplatePicker, ComplianceModal, AgentSessionList, AgentApprovalInline
- `styles/tokens.css` — Design token system (`--c-*` colors, `--space-*`, `--radius-*`, `--text-*`, `--shadow-*`, `--ease-*`) with dark/light themes. Legacy aliases (`--bg`, `--text`, `--accent`, etc.) maintained for backward compat.
- `utils/api.ts` — API base URL (auto-detects Tauri vs web)
- `utils/streamReader.ts` — shared SSE stream parser used by `useTranslate.ts`, `useAgentChat.ts`, and other SSE consumers (6 call sites)
- `types/index.ts` — Shared TypeScript types

### Tauri Layer (`src-tauri/`)

`src/main.rs` spawns Python API (port 18088) and optionally Ollama (port 11434) as child processes. On window close, kills the process tree via `ManagedProcesses` state with `Mutex<Option<Child>>`. Health-checks Python API by polling port before signaling ready.

### Cross-Cutting Patterns

- **Router registration**: `api_factory.py` calls `register_translate`, `register_agent`, `register_editor`, `register_argument`, `register_mindmap` — each receives shared closures and returns state dicts for cross-module wiring.
- **PyInstaller dual-dir**: `BUNDLED_DIR` (read-only, from `_MEIPASS`) vs `RUNTIME_DIR` (writable, beside exe). Config copied from bundle to runtime on first run.
- **Docker mode**: `DOCKER_MODE` env var switches config to `docker.yaml`.
- **SSE everywhere**: Backend uses `sse-starlette`, frontend uses shared `streamReader.ts`. `useTranslate.ts` retries SSE connections up to 3 times with 2s delay.
- **Ghost text**: `useEditor.ts` debounces 1.5s after typing, calls `/api/complete`, shows inline suggestion in Monaco.
- **Glossary extraction**: Translations extract `Chinese(English)` term pairs and inject them as context for subsequent chunks.
- **Windows proxy workaround**: `httpx` hangs on import when `HTTP_PROXY` env vars are set. `start_dev.bat` clears them before launching Tauri dev. Rust side also clears proxy vars in subprocess spawning.

## Dependency Management

Three files in `python/`:
- `requirements.txt` — 22 direct deps pinned to `==X.Y.Z`
- `requirements-lock.txt` — all 72 packages (direct + transitive) fully pinned, generated by `pip-compile`
- `requirements-ocr.txt` — optional OCR deps (pytesseract, pdf2image, paddleocr)

### How to upgrade a dependency

```bash
cd python

# Upgrade a single package (updates both requirements.txt and requirements-lock.txt):
pip-compile --upgrade-package httpx requirements.txt -o requirements-lock.txt
# Then update the == pin in requirements.txt to match the new version in requirements-lock.txt

# Upgrade ALL packages to latest compatible:
pip-compile --upgrade requirements.txt -o requirements-lock.txt

# After any lock file change, verify in a clean venv:
python -m venv /tmp/test && /tmp/test/Scripts/pip install -r requirements-lock.txt
/tmp/test/Scripts/python -m pytest tests/unit/ -q
```

## Prerequisites

- Python 3.12+
- Ollama with `ollama pull qwen3:8b` for local translation
- Node.js 18+, Rust 1.80+ for desktop development
