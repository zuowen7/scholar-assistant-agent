# CLAUDE.md

## Project Overview

Scholar Assistant — privacy-first academic AI writing assistant (v0.4.0). Core paradigm: **"Claude Code for papers"** — Agent directly reads/writes workspace files (PDF/drafts/bib/data). Translates PDFs (parse -> clean -> chunk -> translate -> format via SSE), AI editor (Monaco + Agent chat with workspace file tools), exports to LaTeX/Word. Runs as Tauri desktop app or standalone Python API. Bilingual UI (zh-CN / en-US).

## Build Commands

```bash
# Frontend
npm install && npm run dev           # Vite dev (proxies /api -> :18088)
npm run build                        # Production
npx vitest                           # Unit tests (jsdom)

# Python backend
cd python
pip install -r requirements-lock.txt  # Locked deps (pinned, reproducible)
pip install -r requirements.txt       # OR loose deps (flexible, >= pins)
pip install -r requirements-ocr.txt   # Optional: OCR fallback
pytest tests/ -v                      # All tests
pytest tests/unit/ -v                 # Unit only
pytest tests/integration/ -v          # Integration (needs running API)
pytest tests/ -k "test_chunk"         # By keyword

# Desktop
npx tauri dev                         # Dev mode (auto-starts Python on :18088)
npx tauri build                       # Production
# Windows: use start_dev.bat — clears HTTP_PROXY (httpx hangs on import when proxy vars set)

# Docker
docker compose --project-name scholar-assistant build && docker compose up

# Python CLI
cd python && python api.py            # Start API server on :18088
```

## Architecture

### Stack

| Layer | Technology |
|-------|------------|
| UI | Vue 3, TypeScript, Vite, Monaco Editor, Vue Flow |
| Desktop | Tauri 2 (Rust) |
| Backend | Python 3.12, FastAPI, SSE (`sse-starlette`) |
| Local LLM | Ollama + Qwen3:8b (:11434) |
| Cloud LLM | 21 providers via `PROVIDER_PRESETS` (OpenAI/Anthropic/DeepSeek/... ) |
| PDF | PyMuPDF, pdfplumber |
| Vector DB | ChromaDB + all-MiniLM-L6-v2 |
| Export | Pandoc + LaTeX templates (IEEE/ACM/NeurIPS/LNCS/Generic) |

### Data Flow

**Translation** (5-step SSE, `useTranslate.ts` -> `routers/translate.py`):
SSE events (all prefixed `translate.`): `progress` -> `parsed` -> `cleaned` -> `chunked` -> `block_translated`(xN) -> `complete`. Side events: `chunk_done` / `chunk_error` / `qa_warnings`; fatal: `error`. **Keep backend and frontend event names in sync.**

**Agent V2** (ConversationRuntime, `useAgentChat.ts` -> `src/agent_v2/router.py` -> `src/agent_v2/runtime/conversation.py`):
Architecture inspired by [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code). SSE events: `session_started` / `token` / `thought` / `tool_call` / `tool_result` / `await_approval` / `approval_received` / `response` / `error` / `done` / `aborted` / `checkpoint`. Agent operates on workspace folder, calling `read_file / write_file / str_replace / grep_files / glob_files / list_dir / run_command / rag_search / web_search / web_fetch / translate_document / export_document / arxiv_search / run_sub_agent`. File modifications trigger `checkpoint` SSE → frontend refreshes file tree + editor. Approval flow pauses SSE stream for user decision (accept/reject).

**Provider auto-detection**: `ANTHROPIC_API_KEY` → Anthropic, `OPENAI_API_KEY` → OpenAI-compat, config `agent.*` → any provider, `translator.cloud.*` → DeepSeek, fallback to local Ollama. Model aliases from config (`haiku`, `sonnet`, `opus`, `ds`, `4o`).

### Backend Structure (`python/`)

`api_factory.py` — `create_app()` factory registers six router modules, each receiving shared state (config, runtime dirs, RAG store):
- `routers/translate.py` — translation pipeline, config CRUD, health, export, retry
- `src/agent_v2/router.py` — Agent V2 chat (ConversationRuntime, claw-code inspired). Registered directly via `api_factory.py` at `/api/agent/v2/*`
- `routers/editor.py` — AI edit/complete/export/vision/citation/Zotero
- `routers/argument.py` — Argument Map v2 + Companion v3 (ledger, reviewer, rebuttal, import reviews). **All ledger routes use `?doc_id=` query param**.
- `routers/mindmap.py` — Mind map CRUD, AI expand, layout
- `routers/project.py` — Project management: atomic create (Markdown scaffold in `draft/main.md` + Git init), recent (LRU 20), load, detect, templates. Windows reserved names blocked, corrupt data graceful fallback.

`api.py` — entry point. Delayed imports for optional subsystems (Plugin).

Key `src/` modules:
- `parser/` (16 format parsers), `cleaner/` (17-stage pipeline), `chunker/` (3 strategies), `translator/` (ollama_client + cloud_client + block_translator), `formatter/` (PDF/LaTeX/Word)
- `agent_v2/` — Agent V2 runtime (replaces old `agent/`):
  - `runtime/conversation.py` — `ConversationRuntime` (unified agent loop, streaming + non-streaming, 3-retry error recovery)
  - `runtime/permissions.py` — `PermissionPolicy` (5-tier: ReadOnly/WorkspaceWrite/DangerFullAccess/Prompt/Allow, allow/deny/ask rule engine)
  - `runtime/permission_enforcer.py` — `PermissionEnforcer` (check_file_write/check_bash/is_read_only_command)
  - `runtime/bash_validation.py` — Bash command validation (read-only, destructive, mode, sed, path, semantics, full pipeline) — port of claw-code
  - `runtime/git_context.py` — `GitContext` (branch, commits, staged files detection for system prompt injection)
  - `runtime/lsp_client.py` — `LspRegistry` (state machine: Disconnected→Connecting→Ready→Error, 7 actions)
  - `runtime/policy_engine.py` — `PolicyEngine` (condition-driven rule evaluation, priority-ordered actions)
  - `runtime/prompt_cache.py` — `PromptCacheTracker` (hit/miss rates, token savings, summary)
  - `runtime/recovery.py` — `RecoveryContext` + `attempt_recovery` (7 failure scenarios, 1 auto-attempt before escalation)
  - `runtime/sandbox.py` — `SandboxConfig` + `SandboxResult` (Windows-adapted: CWD, output truncation, env cleanup)
  - `runtime/session.py` — `Session` (JSONL persistence, 256KB rotate, auto-save, fork with `SessionFork` metadata)
  - `runtime/session_control.py` — `SessionControl` (pause/resume/abort) + `SessionStore` (workspace-namespaced persistence)
  - `runtime/trident.py` — 3-stage context compaction (supersede → collapse → cluster)
  - `runtime/compact.py` — Context compaction (950K threshold, summary generation)
  - `runtime/usage.py` — `UsageTracker` + `ModelPricing` (Claude/GPT/DeepSeek/Ollama per-1M-token pricing)
  - `tools/registry.py` — `ToolRegistry` (read_file/write_file/str_replace/grep/glob/list_dir/run_command); run_command uses bash_validation pipeline
  - `tools/academic_tools.py` — translate_document/export_document/arxiv_search/rag_search/web_search/web_fetch
  - `tools/sub_agent.py` — `run_sub_agent` (audit/explain/implement/translate presets)
  - `providers/openai_compat.py` — `OpenAiCompatProvider` (streaming + non-streaming, 20+ providers)
  - `providers/quirks.py` — Per-provider behavioral flags (auto-detected from model/base_url)
  - `mcp/manager.py` — `McpManager` (MCP JSON-RPC stdio lifecycle)
  - `skills.py` — `SkillRegistry` (6 built-in skills, YAML frontmatter file loader)
  - `hooks.py` — `HookRunner` (5 lifecycle hook points, callable + shell hooks; HookAbortSignal, HookRunResult with updated_input + permission_override, shell hook JSON parsing with exit code conventions)
  - `plugins.py` — `PluginManager` (YAML manifest, skills + hooks + tools)
  - `sse_adapter.py` — SSE event format adapter (frontend-compatible)
- `argument/` — `ledger.py`, `reviewer.py`, `_reviewer_perspectives.py`, `anchor.py`, `graph_store.py`, `companion_store.py`
- `plugin/` — MCP-style plugin registry
- `prompts/` — 6-layer YAML frontmatter prompt templates; `src/prompts/schema.py` enforces PromptSpec

### Frontend Structure (`src/`)

- `App.vue` — Thin shell: wires AppTopBar, TranslateView, AgentPanel, EditorLayout, VoiceAssistantView
- `composables/` — All major stores are **module-level singletons** (shared app-wide):
  - `useTranslate.ts` — SSE translation pipeline + reconnect + export
  - `useEditor.ts` — Monaco instance, tabs, ghost text; delegates to `useEditorIO/Vision/Citation/State/Tabs`
  - `useAgentChat.ts` — Agent SSE chat + session/approval state (module-level refs)
  - `useFileTree.ts` — File system navigation
  - `useProject.ts` — Project management singleton (create/open/close/detect/recent, auto-sync file tree, concurrency guards)
  - `useMindMap.ts` — Mind map CRUD, undo/redo, `mindMapToMarkdown`/`markdownToMindMapNodes` bidirectional (node `body` field), `skipNextBackendLoad()`
  - `useArgumentMap.ts` — Toulmin v2 graph CRUD, SSE extraction/critique/suggest, `focusNode`/`focusSpan`
  - `useArgumentCompanion.ts` — Companion v3 state (ledger build/rebuild SSE, review objects, anchor tracking)
  - `useToast.ts` — Toast notifications + `errorLog` ring buffer (50 warn/danger entries with timestamps, consumed by DebugPanel)
  - `useSpeechRecognition.ts` — Web Speech API singleton; dedup via `utterances[]` + `commonPrefixLen()` + `processedUpTo`; `joinUtterances()` smart punctuation merge
  - `useWakeWord.ts` — Wake word detection (continuous SR, homophone variants via `buildVariants()`, 5s cooldown)
  - `useVoiceCommand.ts` — Voice command state machine (idle->activating->listening->submitting->processing), 2s silence auto-submit, 10s timeout
  - `useVoiceRouter.ts` — Keyword intent classifier + 20+ commands in 5 tiers; `classifyIntent()`/`routeCommand()`
  - `useSpeechBusy.ts` — Global speech busy flag (counting), prevents wake-word/dictation SR conflict
  - `useGlobalHotkey.ts` — Tauri system hotkey (`Alt+Shift+V`), graceful degradation in non-Tauri
  - `useAppMode.ts` — App mode singleton (extracted from App.vue)
  - `useLocale.ts` — Language preference singleton
  - Layout: `useMindMapLayout.ts`, `useArgumentLayout.ts` (dagre, dynamic node sizing, relation-aware edge minlen)
- `components/`:
  - `AppTopBar.vue` — brand, mode switch, settings panels, health pills, window controls, voice settings tab
  - `TranslateView.vue` — upload drop card, progress indicators, result views
  - `AgentPanel.vue` — agent chat/docs/templates/sessions side panel
  - `EditorLayout.vue` — FileTree + MonacoEditor + AiPanel + ArgumentMap, tab management
  - `VoiceAssistantView.vue` — Siri-style fullscreen voice UI (glassmorphism + pulse sphere + ripple animation)
  - `DebugPanel.vue` — Frontend error history + backend log viewer
  - `mindmap/` — MindMapCanvas (Vue Flow), MindNodeCard (collapsible body textarea)
  - `ui/` — Design-system primitives (UiButton, UiCard, UiDropdown, UiInput, UiPanel, UiPopover, UiSelect, UiTextarea, UiTooltip, etc.)
  - Other: MonacoEditor, AiPanel, FileTree, ArgumentMap, EditorTabs, EditorToolbar, EditorWelcome, CommandPalette, TemplatePicker, ComplianceModal, AgentSessionList, AgentApprovalInline, StatusCluster
- `utils/streamReader.ts` — Shared SSE parser (6 call sites)
- `utils/sentenceAlign.ts` — Sentence-level alignment for hover highlighting
- `styles/tokens.css` — Design tokens (`--c-*`) with dark/light themes; legacy aliases maintained

### i18n

vue-i18n v11 (Composition API). Locales in `src/i18n/locales/{zh-CN,en-US}.json` (~800 keys each, key-symmetric). Components use `useI18n()` -> `t()`; composables use `import { i18n } from '../i18n'` -> `i18n.global.t()`. Key symmetry enforced by `i18n.test.ts`. Test mock pattern: `vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: fn }) }))`.

### Tauri Layer

`src/main.rs` spawns Python API (:18088) and optionally Ollama (:11434) as child processes. Kills process tree on close via `ManagedProcesses`. Clears proxy vars before spawning subprocesses.

### Config Files

| File | Role | Git |
|------|------|-----|
| `config/default.yaml` (repo root) | Source-of-truth defaults | Yes |
| `python/config/default.yaml` | Runtime copy, auto-generated | No |
| `python/config/default.local.yaml` | User overrides (UI settings panel) | No |

### Cross-Cutting Patterns

- **Windows proxy**: `httpx` hangs on import when `HTTP_PROXY` is set. `start_dev.bat` and Rust side clear proxy vars before spawning Python.
- **SSE everywhere**: Backend `sse-starlette`, frontend shared `streamReader.ts`. `useTranslate.ts` retries up to 3x with 2s delay.
- **PyInstaller dual-dir**: `BUNDLED_DIR` (read-only, `_MEIPASS`) vs `RUNTIME_DIR` (writable, beside exe). Config copied from bundle to runtime on first run.
- **Docker mode**: `DOCKER_MODE` env var switches config to `docker.yaml`.
- **Ghost text**: `useEditor.ts` debounces 1.5s after typing, calls `/api/complete`, shows inline suggestion in Monaco.

## Subsystem Maturity

| Subsystem | Grade |
|-----------|-------|
| Agent V2 (ConversationRuntime + PermissionPolicy + ToolRegistry + Skills/Hooks/Plugins + 9 claw-code runtime modules + streaming + 700+ tests) | A+ |
| Translation pipeline (5-step SSE + multi-article + citation protect/restore + 6 continuation rules) | A |
| Argument Companion v3 (ledger + Reviewer-2 + 3-angle parallel review + rebuttal + real review import) | A |
| Mind Map (Vue Flow + AI expand + dagre + node body + editor bidirectional sync) | A |
| LaTeX/Word export (IEEE/ACM/NeurIPS/LNCS/Generic + Tectonic) | A |
| Voice Assistant (wake word + global hotkey + Siri UI + dedup + 20+ voice commands in 5 tiers) | A |
| Project management (atomic create + Markdown scaffold + Git init + recent + detect + auto-mindmap) | A- |
| AI Editor (Monaco + Ghost Text + AI Panel + mid-stream reload) | B+ |
| Cloud LLM providers (Claude/GPT/DeepSeek/Ollama, auto-detect, model aliases, provider quirks) | B+ |
| RAG / Library (on-demand `rag_search`, translation auto-ingest) | B- |
| Zotero integration | C |
| Vision / OCR | C |

## Known Defect Index

- **Monaco Range**: `useEditorState.ts` `getRange()` must use `_MonacoRange` class (properties `startLineNumber/startColumn/endLineNumber/endColumn`). Never use `{a,b,c,d}` fallback — `executeEdits` will INSERT instead of REPLACE.
- **Speech dedup**: `useSpeechRecognition.ts` `onresult` handler must do bidirectional normalized substring check before appending `finalText`. Never unconditional `+=`.
- **Wake word SR conflict**: When `pausedByDictation=true`, `onend`/`onerror` callbacks must skip `scheduleRestart()`.
- **Ledger routes use `?doc_id=` query param** (not path param) — doc_id is a full file path that may contain `/`.
- **Agent V2 streaming**: ToolUseBlock not yielded individually in streaming — must extract from ProviderResponse.blocks.
- **sudo -n/-i/-S flags**: `extract_sudo_inner()` in `bash_validation.py` — `-n`, `-i`, `-S` are sudo boolean flags (no argument). Do NOT add them to `flags_with_arg`. Adding them causes the parser to skip the actual command as if it were a flag argument.

## Dependency Management

Three files in `python/`:
- `requirements.txt` — 20 direct deps pinned to `==X.Y.Z`
- `requirements-lock.txt` — all 73 packages fully pinned (generated by `pip-compile`)
- `requirements-ocr.txt` — optional OCR deps

```bash
# Upgrade a single package:
cd python
pip-compile --upgrade-package httpx requirements.txt -o requirements-lock.txt
# Then update the == pin in requirements.txt to match

# Verify in clean venv after any lock file change:
python -m venv /tmp/test && /tmp/test/Scripts/pip install -r requirements-lock.txt
/tmp/test/Scripts/python -m pytest tests/unit/ -q
```

## Prerequisites

- Python 3.12+, Node.js 18+, Rust 1.80+
- Ollama with `ollama pull qwen3:8b` for local translation
