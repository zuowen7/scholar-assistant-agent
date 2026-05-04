# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scholar Assistant — privacy-first academic AI writing assistant (Tauri 0.3.1 / npm 0.2.1). Translates PDFs with DeepL-like experience (parse -> clean -> chunk -> translate -> format via SSE), provides an AI editor (Monaco + Agent chat), and exports to LaTeX/Word. Features sentence-level alignment, enhanced paragraph preservation, and flexible export options. Runs as desktop app (Tauri manages Python + Ollama subprocesses) or standalone Python API.

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
cd python && python api.py     # Start API server on :18088
``

## Architecture

### Stack

| Layer | Technology |
|-------|------------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor, Vue Flow (mind map canvas) |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE (`sse-starlette`) |
| Local LLM | Ollama + Qwen3:8b (port 11434) |
| Cloud LLM | OpenAI / Anthropic / DeepSeek / Moonshot / 智谱 / 通义千问 / Gemini / SiliconFlow / OpenRouter / Groq / Together / Mistral / xAI / Fireworks / DeepInfra / Perplexity / Novita / 火山方舟 / 百度千帆 / Azure / Custom (21 providers via `PROVIDER_PRESETS`) |
| PDF | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |
| Export | Pandoc + LaTeX templates (IEEE Conf/Journal, ACM, NeurIPS, LNCS, Generic) |

### Data Flow

**Translation pipeline** (5-step SSE, `useTranslate.ts` -> `routers/translate.py`):
1. Parse -> 2. Clean -> 3. Chunk -> 4. Translate -> 5. Format
SSE events: `progress` -> `parsed` -> `cleaned` -> `chunked` -> `block_translated`(xN) -> `complete`
- **Block-aware translation**: Sentence-level alignment with hover highlighting (`src/utils/sentenceAlign.ts`)
- **Enhanced prompts**: Paragraph structure preservation, reduced alignment failures
- **Flexible export**: 4 formats (bilingual/translated-only × Markdown/Word) via unified dropdown
- **Retry mechanism**: Failed blocks can be re-translated individually without full re-translation

**Agent chat** (ReAct loop, `useAgentChat.ts` -> `routers/agent.py` -> `agent/agent.py`):
SSE events stream tool calls and reasoning steps. Agent can use RAG, Zotero, arXiv search, file ops.

### Backend Structure (`python/`)

`api_factory.py` — `create_app()` factory: app setup, config loading, shared helpers, router registration. Routes are split into five modules under `routers/`, each exporting a `register_*` function receiving shared state (config getters, runtime dirs, RAG store):
- `routers/translate.py` — translation pipeline, config CRUD, health, Ollama/cloud status, export endpoints (bilingual/translation-only Word), retry failed blocks
- `routers/agent.py` — Agent chat, RAG document management
- `routers/editor.py` — AI edit, complete, export (LaTeX/PDF/Word), vision, citation, Zotero, paper scaffolding
- `routers/argument.py` — Dynamic Argument Mapping (tree CRUD, expand, review, flatten)
- `routers/mindmap.py` — Mind map CRUD, AI expand, layout

`api.py` — entry point used by Tauri and standalone. Uses **delayed imports** for optional subsystems (Agent, Plugin): they set `_AGENT_AVAILABLE = False` on ImportError, so translation works without them.

Key backend modules under `src/`:
- `parser/` — 16 format parsers, auto-detect single/dual column
- `cleaner/` — 17-stage text pipeline
- `chunker/` — 3 strategies (sentence/paragraph/fixed)
- `translator/` — `ollama_client.py` + `cloud_client.py` (`PROVIDER_PRESETS`, 21 providers), `block_translator.py` (block-aware translation with status tracking, retry support)
- `formatter/` — bilingual/translated-only/parallel output + `renderer.py` (PDF/LaTeX) + `word_exporter.py`
- `agent/` — Core: `agent.py` (AgentLoop ReAct engine), `session.py` (session management, checkpoint/resume/approval), `session_store.py` (JSON persistence), `context_compressor.py`, `prompt_builder.py`, `models.py`. LLM clients: `llm_client.py` (unified interface) + per-backend mixins `_llm_anthropic.py`, `_llm_ollama.py`, `_llm_openai.py`, `_llm_helpers.py`. Memory+Evolution: `memory.py`, `skill_system.py` + sub-modules `_skill_auto.py`, `_skill_matching.py`, `_skill_model.py`, `_skill_persistence.py`, `trajectory.py`, `review_agent.py`. Tools+Resources: `tools/` (core, workspace_tools, atomic_tools, builtin_tools, registry), `rag.py`, `vram_manager.py`. Special elements (split from monolith): `_elements_parser.py`, `_elements_tools.py`, `_elements_types.py`, `_elements_vision.py`. Reliability: `error_classifier.py`, `hooks.py`, `security_gate.py`. Integration: `mcp_server.py`, `auto_processor.py`. Workspace: `workspace.py`, `bash_session.py`, `change_journal.py`, `task_queue.py`.
- `plugin/` — MCP-style plugin registry (`registry.py`, `loader.py`, `builtin.py`)
- `argument/` — Dynamic Argument Mapping: tree store, logic checker, expander, observer, feedback generator, flattener
- `citation/`, `zotero/`, `mcp/vision_client.py` — citation indexer, Zotero API client, multi-modal image analysis
- `prompts/` — Academic writing prompt templates (polish, expand, etc.)
- `config/default.yaml` — All runtime configuration

### Frontend Structure (`src/`)

- `App.vue` — Thin shell (~684 lines): wires AppTopBar, TranslateView, AgentPanel, EditorLayout. Manages app-wide state (theme, engine settings, drag-drop, background layer, health checks).
- `composables/` — state stores; all major ones are **true singletons** (module-level state, shared app-wide):
  - `useTranslate.ts` — singleton; SSE translation pipeline state + reconnect logic + export functions
  - `useEditor.ts` — singleton; Monaco instance, tabs, AI panel, ghost text completion; delegates to `useEditorIO.ts` / `useEditorVision.ts` / `useEditorCitation.ts` / `useEditorState.ts` / `useEditorTabs.ts` for sub-responsibilities
  - `useAiPanelState.ts` — AI Panel independent state management
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
  - `EditorLayout.vue` — editor mode layout (~657 lines): FileTree sidebar + MonacoEditor + AiPanel right panel + ArgumentMap, with tab management and keyboard shortcuts
  - `mindmap/` — MindMapCanvas (Vue Flow), MindNodeCard, MindEdge
  - `MindMapView.vue`, `MindMapFloatingToolbar.vue`, `MindMapAiHints.vue`
  - `ui/` — design-system primitives: UiButton, UiCard, UiDropdown, UiIconButton, UiInput, UiPanel, UiPill, UiPopover, UiSegmented, UiSelect, UiTextarea, UiTooltip
  - Other: MonacoEditor, AiPanel, FileTree, FileTreeNode, MarkdownPreview, ArgumentMap, EditorTabs, EditorToolbar, EditorWelcome, EditorNewProject, EditorCompliance, CommandPalette, TemplatePicker, ComplianceModal, AgentSessionList, AgentApprovalInline, StatusCluster
- `styles/tokens.css` — Design token system (`--c-*` colors, `--space-*`, `--radius-*`, `--text-*`, `--shadow-*`, `--ease-*`) with dark/light themes. Legacy aliases (`--bg`, `--text`, `--accent`, etc.) maintained for backward compat.
- `utils/api.ts` — API base URL (auto-detects Tauri vs web)
- `utils/streamReader.ts` — shared SSE stream parser used by `useTranslate.ts`, `useAgentChat.ts`, and other SSE consumers (6 call sites)
- `utils/sentenceAlign.ts` — sentence-level alignment utilities for DeepL-like hover highlighting: `splitSentences()`, `findCorrespondingSentenceIdx()`
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

### Config Files

Three config files serve distinct roles — do not confuse them:

| File | Role | Tracked by git |
|------|------|---------------|
| `config/default.yaml` (repo root) | Source-of-truth defaults shipped with the repo. Edit here to change defaults for all environments. | Yes |
| `python/config/default.yaml` | Runtime copy used by the Python backend. Auto-generated on first run (copied from repo root or PyInstaller bundle). | No (gitignored) |
| `python/config/default.local.yaml` | User overrides merged on top of `default.yaml`. Created by the UI's Settings panel or manually. | No (gitignored) |

## Dependency Management

Three files in `python/`:
- `requirements.txt` — 20 direct deps pinned to `==X.Y.Z`
- `requirements-lock.txt` — all 73 packages (direct + transitive) fully pinned, generated by `pip-compile`
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
