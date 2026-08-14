# Changelog

## [0.5.2] — Vision, agent polish, and reliability fixes

### Vision / OCR

- **Vision settings UI** — 设置 → 集成 now includes a 识图 Vision API card to configure base URL, vision model, and API key; `/api/config` accepts and masks the `vision` section.
- **Local OCR fallback** — image OCR now falls back to local engines (Tesseract → PaddleOCR) when no vision key is configured or the cloud call fails, so text-only models can still transcribe images; results report the `engine` used and never write error text into the document.
- **Real OCR endpoint + formula route** — `/api/vision/ocr` transcribes line by line and `/api/vision/formula` converts formulas to LaTeX; scanned PDFs get an actionable hint about optional OCR dependencies.
- **Zhipu vision compatibility** — GLM-4V-Flash fixes (removed OpenAI-only `detail` field, configurable `max_tokens`).

### Agent V2

- **DeepSeek provider conformance** — `reasoning_content` echo-back on tool turns, prompt-cache hit/miss usage reporting, `thinking` params, and `response_format` JSON mode for structured calls.
- **todo_write planning tool** — structured task plan tool with a frontend checklist; updates replace the plan in place instead of stacking duplicate cards.
- **openclaw-style message dedup** — duplicate sends (double-click) compare raw user text and replace the previous answer instead of re-running the turn.
- **Provider quirk gating** — reasoning echo is enabled only for providers that tolerate it, protecting strict providers.
- **Approval diffs jump to the edit location** — accepting/rejecting a diff scrolls to the changed region.

### Zotero / RAG

- **Keyless local Zotero fallback** — local Zotero mode works without an API key with a clear hint; RAG ingest deduplicates translation chunks and search hits.

### UI / Editor

- Fixed header overflow, session-list 403 handling, missing i18n keys; argument-map split overflow; sources navigation no longer jumps to standalone translation without a project.
- **Real auto-save** — removed the always-on "已自动保存" badge; the save state now reflects actual writes.

### Update Checker

- **Backend-proxied GitHub Releases check** — new `GET /api/version/latest` (web redirect first, REST API fallback, 5-minute cache); the frontend no longer calls `api.github.com` directly, fixing the Tauri CSP block and anonymous API rate limiting that made "check for updates" always fail.

### Packaging & Privacy

- **Frozen-build config parity** — `VisionClient` resolves its config from the runtime config directory inside PyInstaller bundles (PYZ modules have no real `__file__`), so vision settings saved in the installed app actually take effect.
- **Privacy cleanup** — removed hardcoded local username / Desktop paths from tests and scripts.

## [0.5.1] — Agent V2 reliability hardening

### Agent Runtime

- **Progressing turns** — removed blocking gates so agent turns keep progressing through real multi-step workflows instead of stalling.
- **Capability-wide reliability** — hardened execution and recovery across Agent V2 capabilities: blocked-write recovery, session reliability gaps, approval routing and feedback.
- **Runtime identity** — runtime identity stays local to its workspace (config fix) instead of leaking between contexts.
- **Zotero credentials** — API calls now use the merged runtime credentials instead of falling back to stale ones.

### Build

- **Bundle matplotlib** — the Agent V2 `nature_figure` skill renders figure scripts with the backend Python via `run_command`. matplotlib is now a production dependency (requirements.txt + lock) and included in the PyInstaller build (removed from `api.spec` excludes), so figure rendering works in the packaged app instead of failing on import.
- Version bumped to 0.5.1 across package.json, Cargo.toml, tauri.conf.json, `_version.py`, and Docker image labels.

## [0.5.0] — Agent execution redesign & build chain hardening

### Agent Execution UI

- **AgentExecutionGroup** — unified execution display component replacing fragmented tool-call cards; groups related tool calls with status, duration, and result previews.
- **Inline diff overlay** — approval diff card now renders as a Vue overlay outside Monaco's DOM, completely bypassing Monaco's internal event interception that blocked clicks and scroll.
- **Selection editing interaction** — inline diff accept/reject flows directly through the overlay with proper event handling.

### Session Lifecycle

- **Pause / Resume / Abort** — `SessionControl` + `SessionStore` provide workspace-namespaced session persistence with full lifecycle management.
- **Scope breaker reset** — consecutive tool errors now trigger proper session reset instead of silent retry loops.
- **Isolated selection sessions** — selection-scoped agent runs no longer leak context between sessions.

### Build Chain

- **PyInstaller PIL inclusion** — removed `PIL` from excludes to fix PPTX import/export in packaged builds.
- **pylatexenc dependency** — added and locked to requirements for LaTeX `.tex` file support.
- **External tool build gating** — missing Pandoc / Tectonic / ONNX model now fails the build instead of silently producing incomplete packages.
- **Release workflow** — switched `npm install` to `npm ci` for reproducible release builds.

### arxiv_search Fix

- Fixed URL encoding: switched from raw f-string to `httpx` params dict so queries containing spaces, quotes, and operators are properly encoded.

## [0.4.2] — Stability, quality baseline & security hardening

### Agent V2 Stability

- **Session pool memory leak** — `_SESSION_POOL` cleanup was a no-op stub; implemented real TTL-based eviction with a background sweep task.
- **Approval scope** — file-edit approvals now honor the user's accept/reject decision per-file instead of applying blanket scope; rejected edits are properly rolled back.
- **Dirty editor protection** — agent writes no longer silently overwrite unsaved Monaco tabs; editor state is checked before checkpoint refresh.
- **Streaming token accumulation** — SSE tokens now append correctly in the UI instead of overwriting the previous chunk.
- **Inline diff approval** — str_replace/write_file diffs render inline for review; checkpoint SSE handler added to AiPanel.
- **History restore** — session history reload works reliably across resume/abort cycles.
- **max_steps** — agent loop limit raised 24 → 48 (configurable from `default.yaml`).
- **Sub-agent reliability** — prefer `write_file` over `str_replace` for large edits to reduce partial-write failures.

### Frontend Refactor

- **App.vue decomposition** — extracted 5 composables from the 1200-line god component (`useAppInit`, `useAppShortcuts`, `useAppTheme`, `useAppVoice`, `useAppProject`).
- **Reference-driven UI** — Markdown and translation blocks rewritten as focused components with consistent rendering.
- **Design token unification** — replaced ad-hoc alias bridges with canonical CSS custom properties; resolved 15 post-refactor visual regressions.
- **Workspace navigation** — hardened browser startup and cross-platform file-tree navigation.
- **Voice assistant** — restored reliable wake-word and command routing after refactor regressions.

### Code Quality Baseline

- **Python lint** — Ruff 622 violations → 0; established format baseline (`ruff format`).
- **TypeScript** — production code `any` count 35 → 0; all replaced with concrete types.
- **Prettier** — full format pass establishing the frontend formatting baseline.
- **CI gates** — quality checks upgraded from advisory to blocking; added `.gitattributes` for cross-platform line-ending consistency.
- **Vitest 4** — test runner upgraded to 4.1.10.
- **Git hooks** — pre-commit hook via `.githooks/pre-commit` (enabled with `npm run setup`).

### Security

- **Secret scanning** — CI gate rejects commits containing API keys or tokens; purged historical runtime data from tracking.
- **Cross-platform path validation** — sensitive-path checks now work correctly on Windows (drive letters, UNC paths).
- **LLM log leak** — agent debug logging no longer prints full API keys or conversation payloads.
- **Shadow backend removed** — eliminated a vestigial duplicate backend entry that bypassed permission checks.

### Build & Packaging

- **PyInstaller** — excluded unused ML/CV/DL packages; kept OCR dependencies.
- **Console window** — Python backend no longer spawns a visible console on Windows.
- **PDF/LaTeX export** — fixed export pipeline errors and editor live-reload after export.

---

## [0.4.1] — Agent connection fix

### Bug Fixes

- **Agent: PyInstaller config path** — agent router used `Path(__file__)` to locate config files, which resolves to `_MEIPASS` in packaged builds. User settings (API keys, proxy) in `default.local.yaml` are stored in `RUNTIME_DIR`, so agent couldn't find them and fell back to Ollama → "All connection attempts failed". Fixed by using `api_factory.RUNTIME_DIR`.
- **Agent: proxy-aware connection fallback** — connection strategy now tries system proxy settings first (`trust_env=True`), then falls back to direct connection (`trust_env=False`). Works whether VPN/proxy is on, off, or misconfigured.
- **Config: proxy settings not saved** — `ConfigUpdate` model was missing `network` and `agent` fields, so proxy settings from the UI were silently discarded. Fixed.
- **Agent: ConnectError error messages** — `httpx.ConnectError` and `HTTPStatusError` are now wrapped in `ApiError` with the endpoint URL, instead of showing raw "unexpected error: All connection attempts failed".

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

**Testing:** 700+ agent tests (MockProvider deterministic) + 1000+ non-agent = 1700+ total; 105 edge/stress tests in 0.97s

**Frontend integration:**
- File tree auto-refresh on agent file writes (checkpoint SSE events)
- Editor tab reload with content change detection
- Approval flow: SSE stream pause → user decision → resume
- Real-time progress display (tool calls and tokens mapped to `response` SSE type)

### 9 Claw-Code Runtime Modules (2026-06-06)

Ported from [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code) `rust/crates/runtime/src/`:

- **`bash_validation.py`** — 6-submodule bash command validation pipeline: readOnlyValidation, destructiveCommandWarning, modeValidation, sedValidation, pathValidation, commandSemantics. Exposed via `validate_command()` and `is_read_only_command()`. Supports sudo wrapping detection (`extract_sudo_inner`), git subcommand classification, env var stripping (`extract_first_command`).
- **`git_context.py`** — `GitContext.detect()` scans workspace git state (branch, recent 5 commits, staged files) for system prompt injection. Returns `None` gracefully for non-git directories.
- **`lsp_client.py`** — `LspRegistry` with state machine (Disconnected→Connecting→Ready→Error). Supports 7 LSP actions with alias resolution (e.g. `goto_definition`→`DEFINITION`). Dispatch gated on READY state.
- **`policy_engine.py`** — Declarative `PolicyCondition(key=value|threshold)` → `PolicyAction(RETRY|ESCALATE|LOG|ABORT)` rule engine. Priority-ordered evaluation against context dicts.
- **`prompt_cache.py`** — `PromptCacheTracker` with hit/miss rates, token savings, cache writes, event log, and `summary()` method.
- **`recovery.py`** — 7 `FailureScenario` enum values with `recipe_for()` lookup. `RecoveryContext` tracks attempt counts + ledger entries. `attempt_recovery()` enforces max attempts with escalation (one auto-attempt before alerting human).
- **`sandbox.py`** — Windows-adapted `SandboxConfig` (CWD restriction, output truncation at UTF-8 safe boundaries, env var cleanup for proxy vars). `SandboxResult.allowed/blocked` convenience.
- **`session_control.py`** — `SessionControl` (Active/Paused/Aborted state machine) + `SessionStore` (workspace-fingerprinted `sessions/<hash>/<id>.jsonl` persistence with list/latest/delete).
- **`trident.py`** — 3-stage context compaction: Stage 1 supersede (remove obsolete file ops, keep only latest write per file), Stage 2 collapse (summarize chatty non-tool exchanges), Stage 3 cluster (Jaccard-similarity semantic grouping). `TridentConfig` + `TridentStats.format_report()`.

### Enhanced Hooks

- **HookAbortSignal** — thread-safe `threading.Event` for async hook cancellation
- **HookRunResult** — enriched result with `updated_input` (hook can modify tool parameters), `permission_override` + `permission_reason` (hook provides permission context), `messages` accumulation, `cancelled` flag
- **Shell hook JSON parsing** — exit code conventions (0=allow, 2=deny, 3=ask); JSON stdout fields: `decision`, `continue`, `reason`, `hookSpecificOutput.updatedInput`, `hookSpecificOutput.permissionDecision`
- **Shell hook non-JSON stdout** — treated as plain message, appended to `HookRunResult.messages`

### Session Fork

- `Session.fork(branch_name)` creates independent copy with new `session_id`, preserving message history
- `SessionFork` dataclass captures `parent_session_id` + `branch_name`
- Fork metadata persisted in JSONL header (`"fork": {"parent_session_id": ..., "branch_name": ...}`)
- `Session.load()` restores `fork_meta` from saved sessions

### Bash Validation Pipeline Integration

- `ToolRegistry._permission_policy_check()` derives effective `PermissionMode` for `run_command`
- Replaced hardcoded dangerous-command blocking with `validate_command()` pipeline
- `run_command` now outputs `[WARNING: ...]` prefix for destructive commands (instead of blocking)
- `set_permission_mode()` for dynamic mode switching

### Testing (2026-06-06)

- **test_bash_validation.py** — 650+ lines, 6 submodule test classes (readOnlyValidation, destructiveCommandWarning, modeValidation, sedValidation, pathValidation, commandSemantics) + full pipeline + types
- **test_edge_and_stress.py** — 920+ lines, 105 edge/stress tests across 15 test classes covering all 9 new modules + enhanced hooks + session fork + registry integration
- **test_hooks_advanced.py** — 391 lines: HookAbortSignal, HookProgressReporter, HookRunResult (updated_input, permission_override), shell JSON parsing (exit codes 0/2/3, continue:false, permissionDecision), payload structure
- **test_session_fork.py** — 246 lines: fork creation/copy/independence/parent tracking/double-fork chain, SessionFork dataclass, SessionControl state machine, SessionStore save/load/delete/list/latest
- **test_recovery_recipes.py** — 274 lines: FailureScenario enum, recipe_for, RecoveryContext (attempt tracking, event log, ledger, status report), attempt_recovery outcomes (success/partial/escalation), RecoveryResult types
- **test_trident_compact.py** — 362 lines: stage1 supersede (no-ops, single write, read→write supersede, edit supersede, mixed files, user message preservation), stage2 collapse (below threshold, chatty→collapse, tool passthrough), stage3 cluster (too few, identical, different), TridentConfig/TridentStats, full pipeline
- **test_lsp_prompt_cache_sandbox_policy.py** — 260 lines: LspRegistry (register/list/state transitions/error/unregister/dispatch), PromptCacheTracker (hit/miss/rate/events/summary), SandboxConfig/Result (defaults/custom/truncate), PolicyEngine (empty/match/no-match/priority/threshold)
- **test_git_context.py** — dedicated tests for GitContext.detect() and render()
- **test_e2e_new_modules.py** — integration tests for end-to-end module interaction
- Total: 105 edge/stress tests all passing in 0.97s

### Bug Fixes

- **`extract_sudo_inner`** — `-n`, `-i`, `-S` are sudo boolean flags (no argument), removed from `flags_with_arg`. Offset calculation replaced with `" ".join(parts[i:])` for correctness.
- **TypeScript** — all TypeScript errors resolved (0 remaining)

### Removed
- Old `src/agent/` (50+ files, 27K lines) — ReAct engine, WorkflowSession, SecurityGate, etc.
- Old agent tests (40+ files, 4K+ tests)
- `routers/agent.py` — replaced by `src/agent_v2/router.py`

### Changed
- `api_factory.py` — Agent V2 routes registered directly, `agent` config section added
- `config/default.yaml` — `agent` section with model/aliases/provider configuration
- `FileTreeNode.vue` — single-root wrapper to fix Vue fragment attrs warning
- `AgentPanel.vue` — checkpoint watcher for real-time file tree refresh

### Previous (pre-0.4.1)

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
