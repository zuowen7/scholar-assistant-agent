# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scholar Assistant is a privacy-first academic AI writing assistant platform (Tauri 0.3.1 / npm 0.2.0). It starts with translation and covers the full workflow of reading, writing, and formatting academic papers. Users drag in a PDF to automatically parse, clean, and translate it; switch to Editor mode for AI polishing/expanding/outline generation; export LaTeX templates directly for submission.

## Build Commands

### Frontend (npm)
```bash
npm install
npm run dev          # Vite dev server
npm run build        # Production build
npx tauri dev        # Tauri development mode
npx tauri build      # Tauri production build
npm test             # Run vitest unit tests
```

### Python
```bash
cd python
pip install -r requirements.txt
pytest tests/ -v                 # Run all tests
pytest tests/unit/test_parser.py # Run single test file
```

### Docker
```bash
docker compose --project-name scholar-assistant build
docker compose up    # Start Ollama + app service
```

## Architecture

### Stack
| Layer | Technology |
|-------|------------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE |
| Translation (local) | Ollama + Qwen3:8b |
| Translation (cloud) | OpenAI / Anthropic / DeepSeek / Moonshot / etc. |
| PDF Processing | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |

### Translation Pipeline (5-step SSE flow)
1. **Parse** — 16 format support, auto-detect single/dual column
2. **Clean** — 17-stage pipeline (fix line breaks, remove watermarks/headers/footers, hyphenation)
3. **Chunk** — 3 strategies (sentence/paragraph/fixed)
4. **Translate** — Ollama (local) or Cloud API
5. **Format** — Bilingual, translated-only, or parallel

SSE events: `progress` → `parsed` → `cleaned` → `chunked` → `chunk_done` (xN) → `complete`

### Agent System (ReAct loop)
- **Tool System**: File ops, RAG queries, Zotero integration, arXiv search, template handling
- **RAG**: ChromaDB + local embeddings for document retrieval
- **Skill System**: Reusable experience from task trajectories, multi-signal matching
- **Memory**: Conversation history and context management

### Plugin System (MCP-style)
- **Registry**: `python/src/plugin/registry.py` — `PluginRegistry`, `PluginServer`, `ToolSpec`
- **Built-in**: `python/src/plugin/builtin.py` — 16 tools (translate, parse, search, arxiv, polish, summarize, outline, expand, bibliography, markdown elements, table, formula, vision)
- **Loader**: `python/src/plugin/loader.py` — Dynamic plugin discovery from `plugins/` directory
- **MCP Server**: `python/src/agent/mcp_server.py` — stdio MCP server for Claude Code/Cursor integration
- **Vision**: `python/src/mcp/vision_client.py` — Multi-modal image understanding (OpenAI/Claude Vision)

### Tauri Backend (Rust)
`src-tauri/src/main.rs` manages Python API subprocess (port 18088) and optionally Ollama subprocess (port 11434). It monitors backend health and cleans up child processes on window close.

### Key Directories
- `src-tauri/` — Rust + Tauri desktop wrapper, capabilities config
- `src/` — Vue 3 frontend (App.vue, composables/, components/)
- `python/` — Python backend (~10k lines): FastAPI, parsers, cleaners, translators, agent
- `python/src/agent/` — ReAct agent: agent.py, rag.py, skill_system.py, tools.py, memory.py
- `python/src/plugin/` — Plugin registry system: registry.py, builtin.py, loader.py
- `python/src/mcp/` — MCP components: vision_client.py for image understanding
- `python/prompts/` — Academic writing prompt system (tasks_polish/, tasks_expand/, etc.)
- `python/data/paper_assets/` — LaTeX templates (IEEE, ACM, NeurIPS, LNCS, Elsevier)

### Key Files
- `python/api_factory.py` — FastAPI app factory, main API implementation
- `python/api.py` — API entry point (used by Tauri in dev mode)
- `python/src/translator/ollama_client.py` — Local Ollama translation client
- `python/src/translator/cloud_client.py` — Cloud API translation client
- `python/src/agent/agent.py` — ReAct inference loop engine
- `src/composables/useTranslate.ts` — SSE translation pipeline state
- `src/composables/useAgentChat.ts` — Agent SSE chat state
- `src/utils/api.ts` — API base URL configuration
- `python/config/default.yaml` — Default config (parser, chunker, translator, formatter, agent)

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/ollama/status` | Ollama status |
| POST | `/api/translate` | Upload document, returns task_id |
| GET | `/api/translate/{id}/stream` | SSE translation progress stream |
| GET | `/api/download/{id}` | Download translation result |
| GET/PUT | `/api/config` | Read/write config |
| POST | `/api/chat` | Agent SSE chat (ReAct loop) |
| POST | `/api/agent/task` | Execute specific Agent task |
| GET | `/api/plugins` | List registered plugin tools |
| POST | `/api/vision/analyze` | MCP Vision image analysis |

## Prerequisites
- Ollama must be installed with `ollama pull qwen3:8b` for local translation
- Python 3.12+ for backend development
