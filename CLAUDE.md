# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scholar Assistant is a privacy-first academic AI writing assistant (Tauri 0.3.1 / npm 0.2.0). It translates PDFs (parse → clean → chunk → translate → format via SSE), provides an AI editor (Monaco + Agent chat), and exports to LaTeX/Word. Runs as a desktop app (Tauri manages Python + Ollama subprocesses) or standalone Python API.

## Build Commands

```bash
# Frontend
npm install
npm run dev                    # Vite dev server (proxies /api → localhost:18088)
npm run build                  # Production build
npx vitest                     # Frontend unit tests (jsdom)
npx vitest src/__tests__/useEditor.test.ts  # Single test file

# Python backend
cd python
pip install -r requirements.txt
pytest tests/ -v               # All tests
pytest tests/unit/test_parser.py  # Single test file
pytest tests/ -k "test_chunk"  # By keyword

# Desktop app
npx tauri dev                  # Dev mode (auto-starts Python API on :18088)
npx tauri build                # Production build

# Docker
docker compose --project-name scholar-assistant build && docker compose up

# Python CLI
cd python && python main.py paper.pdf -o paper.md
```

## Architecture

### Stack

| Layer | Technology |
|-------|------------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE (`sse-starlette`) |
| Local translation | Ollama + Qwen3:8b (port 11434) |
| Cloud translation | OpenAI / Anthropic / DeepSeek / Moonshot / etc. |
| PDF | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |
| Export | Pandoc + LaTeX templates (IEEE/ACM/NeurIPS/LNCS/Elsevier) |

### Data Flow

**Translation pipeline** (5-step SSE, `useTranslate.ts` → `api_factory.py`):
1. Parse → 2. Clean → 3. Chunk → 4. Translate → 5. Format
SSE events: `progress` → `parsed` → `cleaned` → `chunked` → `chunk_done`(×N) → `complete`

**Agent chat** (ReAct loop, `useAgentChat.ts` → `agent.py`):
SSE events stream tool calls and reasoning steps. Agent can use RAG, Zotero, arXiv search, file ops.

### Backend Structure (`python/`)

All API routes live in a single file — `api_factory.py` (~2300 lines) — returned by `create_app()` factory. `api.py` is the entry point used by Tauri. The app uses **delayed imports** for optional subsystems (Agent, Plugin, Argument Mapping): they set a flag like `_AGENT_AVAILABLE = False` on ImportError, so the translation pipeline works without them.

Key backend modules:
- `src/parser/` — 16 format parsers, auto-detect single/dual column
- `src/cleaner/` — 17-stage text pipeline
- `src/chunker/` — 3 strategies (sentence/paragraph/fixed)
- `src/translator/` — `ollama_client.py` + `cloud_client.py` (provider presets in `PROVIDER_PRESETS`)
- `src/formatter/` — bilingual/translated-only/parallel output + `renderer.py` (PDF/LaTeX) + `word_exporter.py`
- `src/agent/` — ReAct loop (`agent.py`), RAG (`rag.py`), tools (`tools.py`), skill system (`skill_system.py`), memory, VRAM manager, context compressor, trajectory recorder, MCP server
- `src/plugin/` — MCP-style plugin registry + 16 built-in tools
- `src/argument/` — Dynamic Argument Mapping: tree store, logic checker, expander, observer, feedback generator, flattener
- `src/citation/` — Citation indexer
- `src/zotero/` — Zotero API client
- `src/mcp/vision_client.py` — Multi-modal image analysis
- `prompts/` — Academic writing prompt templates (polish, expand, etc.)
- `config/default.yaml` — All runtime configuration

### Frontend Structure (`src/`)

- `App.vue` — Main layout, toggles between Translate Mode and Editor Mode
- `composables/` — **Singleton state stores** (module-level `ref`/`reactive`, not composable functions):
  - `useTranslate.ts` — SSE translation pipeline state + reconnect logic
  - `useAgentChat.ts` — Agent SSE chat state
  - `useEditor.ts` — Monaco instance, tabs, AI panel, file tree, ghost text completion
  - `useFileTree.ts` — File system navigation
- `components/` — `MonacoEditor.vue`, `AiPanel.vue`, `FileTree.vue`, `MarkdownPreview.vue`, `ArgumentMap.vue`, etc.
- `utils/api.ts` — API base URL (auto-detects Tauri vs web)
- `types/index.ts` — Shared TypeScript types

### Tauri Layer (`src-tauri/`)

`src/main.rs` spawns and manages Python API (port 18088) and optionally Ollama (port 11434) as child processes. On window close, it kills the process tree. Uses `ManagedProcesses` state with `Mutex<Option<Child>>`. Health-checks the Python API by polling the port before signaling ready.

### Cross-Cutting Patterns

- **PyInstaller dual-dir**: `BUNDLED_DIR` (read-only, from `_MEIPASS`) vs `RUNTIME_DIR` (writable, beside exe). Config is copied from bundle to runtime on first run.
- **Docker mode**: `DOCKER_MODE` env var switches config to `docker.yaml`.
- **SSE reconnect**: `useTranslate.ts` retries SSE connections up to 3 times with 2s delay.
- **Ghost text**: `useEditor.ts` debounces 1.5s after typing, calls `/api/complete`, shows inline suggestion in Monaco.
- **Cloud translator**: `cloud_client.py` defines `PROVIDER_PRESETS` dict for each provider's model list, base URL, and default params.
- **Glossary extraction**: Translations extract `中文(English)` term pairs and inject them as context for subsequent chunks.

## Prerequisites

- Python 3.12+
- Ollama with `ollama pull qwen3:8b` for local translation
- Node.js 18+, Rust 1.80+ for desktop development
