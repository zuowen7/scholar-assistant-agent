# Changelog

## [0.4.0] — Agent V2: Claw-Code Architecture

### Agent V2 — Complete Rewrite

The old ReAct agent (50+ files, PPT-demo quality) has been replaced with a clean 16-file runtime inspired by [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code).

**Core components:**
- `ConversationRuntime` — unified agent loop (streaming + non-streaming, 3-retry error recovery)
- `PermissionPolicy` — 5-tier permission modes (ReadOnly/WorkspaceWrite/DangerFullAccess/Prompt/Allow) with allow/deny/ask rule engine
- `PermissionEnforcer` — check_file_write + check_bash + is_read_only_command heuristic
- `ToolRegistry` — 7 built-in tools (read/write/str_replace/grep/glob/list_dir/run_command) with ignore-aware listing
- `Session` — JSONL persistence with 256KB auto-rotate, 950K compaction threshold
- `UsageTracker` — per-session token/cost tracking with model pricing (Claude, GPT, DeepSeek, Ollama)
- `McpManager` — MCP JSON-RPC stdio lifecycle (spawn → init → call → shutdown)

**Academic tools:** translate_document, export_document, arxiv_search, rag_search, web_search, web_fetch

**Sub-agent system:** run_sub_agent with 4 presets (audit/explain/implement/translate)

**Extensibility:**
- **Skills** — YAML frontmatter prompt templates (6 built-in + file loader from `data/agent_v2/skills/`)
- **Hooks** — 5 lifecycle hook points (PreToolUse/PostToolUse/PostToolUseFailure/Init/Shutdown), callable + shell
- **Plugins** — YAML manifest system (skills + hooks + tools per plugin)

**Provider support:**
- Auto-detection: ANTHROPIC_API_KEY → Anthropic, OPENAI_API_KEY → OpenAI, config → any provider, fallback → Ollama
- Model aliases: `haiku`/`sonnet`/`opus`/`ds`/`4o` (from config `agent.model_aliases`)
- Provider quirks: per-model behavioral flags auto-detected from model name and base URL
- Real streaming (SSE token-by-token) default ON, non-streaming fallback

**Testing:** 263 agent tests (MockProvider deterministic, 100ms full suite) + 1144 non-agent = 1407 total

**Frontend integration:**
- File tree auto-refresh on agent file writes (checkpoint SSE events)
- Editor tab reload with content change detection
- Approval flow: SSE stream pause → user decision → resume
- Real-time progress display (tool calls and tokens mapped to `response` SSE type)

### Removed
- Old `src/agent/` (50+ files, 27K lines) — ReAct engine, WorkflowSession, SecurityGate, etc.
- Old agent tests (40+ files, 4K+ tests)
- `routers/agent.py` — replaced by `src/agent_v2/router.py`

### Changed
- `api_factory.py` — Agent V2 routes registered directly, `agent` config section added
- `config/default.yaml` — `agent` section with model/aliases/provider configuration
- `FileTreeNode.vue` — single-root wrapper to fix Vue fragment attrs warning
- `AgentPanel.vue` — checkpoint watcher for real-time file tree refresh

### Previous (pre-0.4.0)

### Added
- **Project management** — PyCharm-style project system: `POST /api/project/create` (atomic creation, validated templates, Git init), `GET /api/project/recent` (LRU 20, auto-filter deleted), `GET /api/project/load` + `POST /api/project/detect` + `GET /api/project/templates`
- **Markdown scaffold** — creating a project auto-generates `draft/main.md` with paper-structure outline (4 templates: Research Paper, Literature Review, Thesis, NeurIPS); frontend auto-opens the file and switches to mindmap view
- **File tree actions** — new file / new folder buttons in toolbar + right-click context menu on directories
- **`useProject.ts` composable** — singleton state (`currentProject`, `recentProjects`), `createProject`/`openProject`/`closeProject`/`detectProject`, concurrency guards (operation ID), file tree sync, robust rollback
- **`EditorNewProject.vue`** — complete project creation form: name/author/template/location picker/Git toggle, `parseResponse` content-type validation
- **`EditorWelcome.vue`** — recent projects list (max 5, click to open), `loadRecentProjects` on mount; hero card for New Project
- **`AppTopBar.vue`** — project name chip between brand and mode switcher
- **`openWorkspaceFolder` auto-detection** — opening a folder with `.yanmo/project.json` automatically loads project metadata

### Security
- Windows reserved names (CON/NUL/COM1-9/LPT1-9/AUX/PRN) rejected (422)
- Trailing dots, null bytes, path traversal, emoji/zero-width chars all rejected
- `parseResponse()` validates Content-Type before `.json()` to prevent HTML injection crashes
- `_add_recent` wrapped in try/except to prevent false 500 after successful create
- Corrupted `project.json` / `projects.json` gracefully degraded (empty lists, proper fallbacks)
- `_write_recent` handles non-dict/corrupt entries without crashing

### Project templates
- `python/templates/project_templates.json` — 5 templates (research_paper/review_paper/thesis/neurips/blank)
- Markdown scaffold generation: `_MARKDOWN_TEMPLATES` dict maps template IDs to paper outlines
- Template loading: validates JSON structure, rejects non-array, catches `json.JSONDecodeError`

### Backend
- New router `python/routers/project.py` registered in `api_factory.py`
- 64 adversarial edge case tests covering: Unicode attacks, Windows reserved names, template attacks, corrupt state, race conditions, Pydantic type validation

- **Voice command router** (`useVoiceRouter.ts`) — Siri-like intent classifier: keyword scoring matches 20+ voice commands in 5 tiers (navigation / files / editor / translation / mind map), routes to concrete actions; unmatched commands fall back to Agent chat
- **Voice command registry** (`src/voiceCommands/`) — 5 declarative tier files, each command declaring `{id, label, patterns[], handler}`; 148 new vitest tests
- **App mode singleton** (`useAppMode.ts`) — extracted from `App.vue` so router can switch modes/panels without prop drilling
- **Voice assistant demo GIF** in README (both EN/ZH) — real screen recording of wake word + dictation flow

### Changed
- **CLAUDE.md condensed** — 385 → 185 lines; removed full changelog history (redundant with git log), kept architecture, data flow, and known defect index

## [0.3.6] — 2026-06-01

### Added
- **Voice Assistant** — Siri-style hands-free control: wake word "小研" (homophone variant matching), global hotkey `Alt+Shift+V` (Tauri plugin, system-wide), voice dictation in editor/Agent/AI panel, customizable via settings
- **VoiceAssistantView** — fullscreen glass-morphism overlay with pulsing orb, ripple rings, and live transcript; 2-second silence auto-submit
- **Voice settings panel** — wake word phrase, hotkey recording, sensitivity, language toggle
- **Shared speech busy flag** — prevents wake word detection from conflicting with voice dictation (`useSpeechBusy.ts`, sync pause/resume via `flush:'sync'`)
- 115 new vitest voice-related tests (10 useWakeWord + 13 useVoiceCommand + 9 VoiceAssistantView + 7 useGlobalHotkey + 8 integration + 3 useSpeechRecognition dedup)

### Fixed
- **Voice input echo dedup** — Monaco Range fallback class with wrong property names (`{a,b,c,d}` → `{startLineNumber,...}`) caused `executeEdits` INSERT instead of REPLACE, accumulating duplicated voice text
- **Chrome re-recognition dedup** — three layers: prefix overlap detection against individual utterances (>50% match), `processedUpTo` index tracking, and internal duplication cleaning
- **Speaker punctuation auto-merge** — `joinUtterances()` converts premature Chrome-added periods to commas when the next utterance is clearly a continuation
- **Tab + voice cursor tracking** — `handleVoiceUpdate` detects cursor drift after accepting Ghost Text, resets voice insertion anchor
- **Wake word/dictation SR conflict** — wake word `onend`/`onerror` handlers now check `pausedByDictation` guard to prevent 300ms auto-restart from stealing the microphone
- CI: Ollama tests skip gracefully when service unavailable; RAG tests accept 503 when ChromaDB missing
- CI: Regenerate `requirements-lock.txt` with ChromaDB + NumPy + transitive deps
- CI: Add NumPy to requirements for test job
- CI: Opt into Node.js 24 for GitHub Actions runtime
- Build: version 0.3.3 → 0.3.6 synced across 4 files (Cargo.toml, tauri.conf.json, tauri.dev.conf.json, _version.py)

## [0.3.3] — 2026-05-31

### Added
- **Bilingual UI** (zh-CN / en-US) via vue-i18n — full coverage across 20+ components, switchable from settings panel
- **Update notifications** — checks GitHub Releases on startup, shows toast when new version available
- 149 new integration tests covering 60+ previously untested routes

### Fixed
- vue-i18n `@` linked message parsing crash (AiPanel completely broken in English mode)
- UiDropdown race condition: `close()` + `onClick()` ordering caused Vue null reference on export PDF
- Background image not working in release builds (switched from `convertFileSrc` to `readFile` + base64 data URL)
- Multiple i18n import and `t()` call omissions across components

## [0.3.2] — 2026-05-30

### Fixed
- Agent: unknown models now return default tool guidance — covers all 21 providers (previously only Qwen/GPT/DeepSeek/Gemini had guides; others returned empty string, causing Agent to refuse tool execution)
- 17 new parametrized tests for prompt builder model coverage

## [0.3.1] — 2026-05-24

### Added
- **Mind map node body** — each node has expandable body text (▸ toggle); heading = title, paragraph = body
- **Editor ↔ mind map bidirectional sync** — editor parses heading + body into nodes; mind map preserves full content on export back
- PDF export: strip `---` horizontal rules and escape bare `&` to prevent LaTeX errors

## [0.3.0] — 2026-05-23

This is a major release — the "Claude Code for Papers" pivot.

### Added
- **Agent workspace file tools** — open a project folder; Agent calls `read_file / grep_files / str_replace / write_file / git_op` directly; editor tabs reload mid-stream after each write; PDF/Word/EPUB auto-parsed
- **Document QA short-circuit** — open a document, ask questions → single-shot LLM streaming (no ReAct loop); only explicit file-modification intent triggers full Agent
- **Workspace boundary & approval** — file ops locked to project root; out-of-scope triggers approval popup (Allow once / Allow session / Deny)
- **Claim Ledger** — auto-extract promises from abstract/intro, track paid/partial/unpaid/mismatch per promise, 3-state fuzzy anchor relocation
- **Reviewer-2 adversary** — 7 conference-calibrated reviews + rebuttal mini-chat (reviewer can be persuaded) + real review import + experiment gap suggestions
- **3-angle parallel review** — method/experiment/writing perspectives reviewed concurrently with auto dedup (feature flag `parallel_review`)
- **Mind map** — Vue Flow canvas, AI expand, AI analysis, dagre auto-layout, keyboard shortcuts, undo/redo
- **Argument Map v2** — Toulmin nodes/edges on Vue Flow, AI extraction SSE, critique, suggest, flatten to draft
- **Debug panel** — frontend error history ring buffer + backend log viewer in top bar
- **File logging** — rotating 10 MB × 5 backups, trace_id per request, access logging

### Changed
- Default translation engine changed from Ollama to cloud
- Agent greeting/闲聊 no longer triggers tool loop — direct LLM response
- AI Panel polish/expand/review preset buttons now use `/api/edit` (one-shot streaming) instead of Agent ReAct loop
- RAG demoted to on-demand `search_documents` tool (no longer auto-injected per turn)

### Fixed
- Translation: block alignment failures, QA false positives (max_words 30→45), prompt leaking into output, `max_tokens` 2048→800
- Agent: infinite loops eliminated (step limits, per-tool counters, force-stop mechanism, DeepSeek 400 circuit breaker)
- Companion: ledger anchor events actually emitted (was missing), discharge fuzzy relocation, rebuttal truncation (512→2048), export download
- Argument: ledger routes use `?doc_id=` query param (was 404 on paths containing `/`)
- CSS: undefined variables in LedgerList/CompanionPanel fixed for light theme readability
- Build: PyInstaller uses `python -m PyInstaller`, packages Pandoc/Tectonic/embedding model, `start_dev.bat` clears proxy env vars

### Removed
- Deprecated tools: `polish_text`, `summarize_text`, `expand_section`, `generate_outline` (93 lines)
- Old tree-based argument map (replaced by v2 Toulmin graph)

## [0.2.x] — 2026-05

- Agent ReAct engine (Phase 0–3): streaming tool calls, context compression, Skill three-layer decomposition, Memory dedup
- SmartPause, memory time decay, session lesson learning
- Translation prompt externalization: 7 section partials + `_prompt_loader.py`
- 6-layer Prompt skeleton + eval framework (`PromptSpec`)
- Multi-provider cloud translation (21 providers)
- Zotero integration, MCP Vision, citation indexer
- Word export, PPTX export
- Docker deployment
- Dark/light theme with design token system

## [0.1.x] — 2026-04

- PDF translation pipeline (parse → clean → chunk → translate → format)
- Ollama local translation
- Bilingual side-by-side view with sentence-level hover highlighting
- Basic Monaco editor with ghost text completion
- Tauri 2 desktop shell with process management
- PyInstaller packaging for Windows installer
- NSIS installer with WebView2 bootstrapper
- GitHub Actions CI/CD
