# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Scholar Assistant — privacy-first academic AI writing assistant (v0.3.2, single source `python/src/_version.py`). Core paradigm: **"Claude Code for papers"** — Agent directly reads/writes workspace files (PDF/drafts/bib/data) like Claude Code edits source code. Translates PDFs with DeepL-like experience (parse -> clean -> chunk -> translate -> format via SSE), provides an AI editor (Monaco + Agent chat with workspace file tools), and exports to LaTeX/Word. Runs as desktop app (Tauri manages Python + Ollama subprocesses) or standalone Python API.

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
SSE events (all prefixed `translate.`): `translate.progress` -> `translate.parsed` -> `translate.cleaned` -> `translate.chunked` -> `translate.block_translated`(xN) -> `translate.complete`. Per-block side events: `translate.chunk_done` / `translate.chunk_error` / `translate.qa_warnings`; fatal: `translate.error`. `useTranslate.ts` switches on these exact prefixed names — keep backend (`routers/translate.py`) and frontend in sync.
- **Block-aware translation**: Sentence-level alignment with hover highlighting (`src/utils/sentenceAlign.ts`)
- **Enhanced prompts**: Paragraph structure preservation, reduced alignment failures
- **Flexible export**: 4 formats (bilingual/translated-only × Markdown/Word) via unified dropdown
- **Retry mechanism**: Failed blocks can be re-translated individually without full re-translation

**Agent chat** (ReAct loop, `useAgentChat.ts` -> `routers/agent.py` -> `agent/agent.py`):
SSE event types (defined in `agent/models.py`): `session_started` (metadata.session_id) / `task_started` / `token` / `thought` / `tool_call` / `tool_result` / `await_approval` / `approval_received` / `task_done` / `response` / `warning` / `error` / `done` / `aborted`. **Tool-name metadata key is canonical `tool_name`** across `tool_call` / `tool_result` / `await_approval` (do not reintroduce a bare `tool` key). SSE events stream tool calls and reasoning steps. Agent operates on the user's open project folder (`workspace_root` from `useFileTree.rootDir`), calling `read_file / grep_files / str_replace / write_file / git_op` directly. Workspace boundary enforced by `WorkspaceEnv.resolve()`; out-of-workspace paths trigger `force_approval=True` in `SecurityGate` → `await_approval` SSE event → user approves via `AgentApprovalInline`. RAG (`search_documents`) is on-demand for long-term literature library, not auto-injected per turn. Monaco editor reloads open tabs mid-stream on each `write_file`/`str_replace` tool result.

### Backend Structure (`python/`)

`api_factory.py` — `create_app()` factory: app setup, config loading, shared helpers, router registration. Routes are split into five modules under `routers/`, each exporting a `register_*` function receiving shared state (config getters, runtime dirs, RAG store):
- `routers/translate.py` — translation pipeline, config CRUD, health, Ollama/cloud status, export endpoints (bilingual/translation-only Word), retry failed blocks
- `routers/agent.py` — Agent chat, RAG document management. **三态路由**：trivial 问候直接回复 / 打开文档的纯问答（`_has_mutation_intent`=false）走 `_oneshot_doc_qa_stream` 一次性 LLM 流式（不进 ReAct）/ 明确改文件·跑命令才走完整 Agent 循环
- `routers/editor.py` — AI edit, complete, export (LaTeX/PDF/Word), vision, citation, Zotero, paper scaffolding
- `routers/argument.py` — Argument Map v2 graph CRUD (node/edge/span) + Toulmin extraction SSE + critique + suggest + flatten/export + Companion v3 (ledger SSE, reviewer, rebuttal, import reviews). **Ledger routes use `?doc_id=` query param** (not path param).
- `routers/mindmap.py` — Mind map CRUD, AI expand, layout

`api.py` — entry point used by Tauri and standalone. Uses **delayed imports** for optional subsystems (Agent, Plugin): they set `_AGENT_AVAILABLE = False` on ImportError, so translation works without them.

Key backend modules under `src/`:
- `parser/` — 16 format parsers, auto-detect single/dual column
- `cleaner/` — 17-stage text pipeline
- `chunker/` — 3 strategies (sentence/paragraph/fixed)
- `translator/` — `ollama_client.py` + `cloud_client.py` (`PROVIDER_PRESETS`, 21 providers), `block_translator.py` (block-aware translation with status tracking, retry support), `_prompt_loader.py` (template + partial assembly)
- `formatter/` — bilingual/translated-only/parallel output + `renderer.py` (PDF/LaTeX) + `word_exporter.py`
- `agent/` — Core: `agent.py` (AgentLoop ReAct engine), `session.py` (session management, checkpoint/resume/approval), `session_store.py` (JSON persistence), `context_compressor.py`, `prompt_builder.py` (Skill SOUL/AGENTS injection), `models.py`. LLM clients: `llm_client.py` (unified interface) + per-backend mixins `_llm_anthropic.py`, `_llm_ollama.py`, `_llm_openai.py`, `_llm_helpers.py`. Memory+Evolution: `memory.py`, `skill_system.py` + sub-modules `_skill_auto.py`, `_skill_matching.py`, `_skill_model.py` (three-layer paths), `_skill_persistence.py` (IDENTITY.md/SKILL.md detection), `_skill_migrate.py` (legacy→three-layer), `trajectory.py`, `review_agent.py`. Tools+Resources: `tools/` (core, workspace_tools, atomic_tools, builtin_tools, registry), `rag.py`, `vram_manager.py`. Special elements (split from monolith): `_elements_parser.py`, `_elements_tools.py`, `_elements_types.py`, `_elements_vision.py`. Reliability: `error_classifier.py`, `hooks.py`, `security_gate.py`. Integration: `mcp_server.py`, `auto_processor.py`. Workspace: `workspace.py`, `bash_session.py`, `change_journal.py`, `task_queue.py`.
- `plugin/` — MCP-style plugin registry (`registry.py`, `loader.py`, `builtin.py`)
- `argument/` — Argument Map v2 + Companion v3: `llm_client.py` (cloud/Ollama with reasoning-model auto-retry), `ai_ops.py` (Toulmin extraction SSE + element suggestion), `ledger.py` (promise ledger SSE — yields anchor events before each promise), `reviewer.py` (Reviewer-2 serial + parallel review, rebuttal, import_real_reviews), `_reviewer_perspectives.py` (method/experiment/writing + aggregate), `anchor.py` (3-state fuzzy relocation), `companion_store.py`, `graph_store.py`, `models_v2.py`. **All ledger routes use `?doc_id=` query param** (not path param) because doc_id is a full file path that may contain `/`.
- `citation/`, `zotero/`, `mcp/vision_client.py` — citation indexer, Zotero API client, multi-modal image analysis
- `prompts/` — Academic writing prompt templates with 6-layer YAML frontmatter schema (polish, expand, coherence, edit, compliance, translate, review); `src/prompts/schema.py` enforces PromptSpec
- `config/default.yaml` — All runtime configuration

### Frontend Structure (`src/`)

- `App.vue` — Thin shell (~684 lines): wires AppTopBar, TranslateView, AgentPanel, EditorLayout. Manages app-wide state (theme, engine settings, drag-drop, background layer, health checks).
- `composables/` — state stores; all major ones are **true singletons** (module-level state, shared app-wide):
  - `useTranslate.ts` — singleton; SSE translation pipeline state + reconnect logic + export functions
  - `useEditor.ts` — singleton; Monaco instance, tabs, AI panel, ghost text completion; delegates to `useEditorIO.ts` / `useEditorVision.ts` / `useEditorCitation.ts` / `useEditorState.ts` / `useEditorTabs.ts` for sub-responsibilities
  - `useAiPanelState.ts` — AI Panel independent state management
  - `useFileTree.ts` — singleton; file system navigation
  - `useAgentChat.ts` — singleton (module-level refs); Agent SSE chat state + session/approval state
  - `useMindMap.ts` — singleton; mind map data (CRUD, undo/redo, flow adapters `toFlowNodes`/`toFlowEdges`, `mindMapToMarkdown`/`markdownToMindMapNodes` bidirectional sync with `body` field per node)
  - `useMindMapKeyboard.ts` — keyboard handler (Tab/Enter/F2/arrows/Ctrl+Z)
  - `useMindMapLayout.ts` — dagre auto-layout
  - `useMindMapAnalysis.ts` — AI analysis integration
  - `useArgumentMap.ts` — singleton; Toulmin v2 graph state (CRUD, undo/redo, flow adapters, SSE extraction, critique, suggest); spans `focusNode`/`focusSpan` for source-pane highlighting
  - `useArgumentCompanion.ts` — singleton; companion state (docId auto-assign, ledger build/rebuild SSE)
  - `useArgumentLayout.ts` — dagre auto-layout with dynamic node sizing and relation-aware edge minlen (Toulmin hierarchy)
  - `useToast.ts` — singleton; toast 通知 + `errorLog` ring buffer (最近 50 条 warn/danger，带时间戳，供 DebugPanel 消费)
- `components/` — extracted from the former monolithic App.vue:
  - `AppTopBar.vue` — brand, mode switch, engine/display settings panels, health pills, window controls
  - `TranslateView.vue` — upload drop card, progress/step indicators, result views (sentence/parallel/markdown), sentence splitting, markdown rendering
  - `AgentPanel.vue` — agent chat/docs/templates/sessions side panel (self-contained via `useAgentChat()`)
  - `EditorLayout.vue` — editor mode layout (~657 lines): FileTree sidebar + MonacoEditor + AiPanel right panel + ArgumentMap, with tab management and keyboard shortcuts
  - `mindmap/` — MindMapCanvas (Vue Flow), MindNodeCard (collapsible body textarea), MindEdge
  - `MindMapView.vue`, `MindMapFloatingToolbar.vue`, `MindMapAiHints.vue`
  - `ui/` — design-system primitives: UiButton, UiCard, UiDropdown, UiIconButton, UiInput, UiPanel, UiPill, UiPopover, UiSegmented, UiSelect, UiTextarea, UiTooltip
  - `DebugPanel.vue` — 独立调试面板组件（前端错误历史 + 后端日志，在 AppTopBar 中以 `<DebugPanel />` 引入）
  - Other: MonacoEditor, AiPanel, FileTree, FileTreeNode, MarkdownPreview, ArgumentMap, EditorTabs, EditorToolbar, EditorWelcome, EditorNewProject, EditorCompliance, CommandPalette, TemplatePicker, ComplianceModal, AgentSessionList, AgentApprovalInline, StatusCluster
- `styles/tokens.css` — Design token system (`--c-*` colors, `--space-*`, `--radius-*`, `--text-*`, `--shadow-*`, `--ease-*`) with dark/light themes. Legacy aliases (`--bg`, `--text`, `--accent`, etc.) maintained for backward compat.
- `utils/api.ts` — API base URL (auto-detects Tauri vs web)
- `utils/streamReader.ts` — shared SSE stream parser used by `useTranslate.ts`, `useAgentChat.ts`, and other SSE consumers (6 call sites)
- `utils/sentenceAlign.ts` — sentence-level alignment utilities for DeepL-like hover highlighting: `splitSentences()`, `findCorrespondingSentenceIdx()`
- `types/index.ts` — Shared TypeScript types

### Tauri Layer (`src-tauri/`)

`src/main.rs` spawns Python API (port 18088) and optionally Ollama (port 11434) as child processes. On window close, kills the process tree via `ManagedProcesses` state with `Mutex<Option<Child>>`. Health-checks Python API by polling port before signaling ready.

### i18n / Internationalization (`src/i18n/`)

**Bilingual UI**: zh-CN / en-US, powered by vue-i18n v11 (Composition API, `legacy: false`).

| File | Role |
|------|------|
| `src/i18n/index.ts` | `createAppI18n()` factory + singleton `i18n` instance (registered in `main.ts` via `app.use(i18n)`) |
| `src/i18n/locales/zh-CN.json` | Chinese locale (~770 keys, nested by feature: mode/settings/translate/editor/agent/argument/mindmap/errors) |
| `src/i18n/locales/en-US.json` | English locale — symmetric with zh-CN (same keys, English values) |
| `src/composables/useLocale.ts` | Language preference singleton: detects `navigator.language`, persists to `localStorage`, syncs `document.documentElement.lang` + `i18n.global.locale.value` |
| `src/__tests__/helpers/i18n.ts` | `createTestI18n()` — shared test helper providing full locale messages for component tests |

**Key patterns**:
- **Components** use `useI18n()` → `const { t } = useI18n()` → `{{ t('key') }}` in templates
- **Composables** use `import { i18n } from '../i18n'` → `i18n.global.t('key')` (no reactive context needed)
- **Language switcher** in `AppTopBar.vue` settings popover (below tabs, uses `UiSelect` with `currentLocale`/`setLocale`)
- **Locale key symmetry** is enforced: every key in zh-CN must have a counterpart in en-US; `i18n.test.ts` verifies this
- **Brand strings** (研墨/研/墨) are hardcoded in components — never in locale files
- **LLM prompts** (in AiPanel.vue, agent prompts) are intentionally NOT i18n'd — they are sent to models, not displayed to users

**Testing**: Components that use `t()` must mock `vue-i18n` via `vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: fn }) }))`. See `AgentApprovalInline.test.ts` for the canonical pattern. 8 test files have this mock.

**Adding a new locale**:
1. Create `src/i18n/locales/{locale}.json` with all keys
2. Add the locale to `SUPPORTED_LOCALES` in `src/i18n/index.ts`
3. Add an `<option>` in `AppTopBar.vue` language selector
4. Run `npx vitest` to verify key symmetry

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
### Subsystem Maturity Matrix

Use this as the canonical "what works / what's polished / what's a stub" map. Updated 2026-05-30.

| # | Subsystem | Grade | Key evidence |
|---|-----------|-------|--------------|
| 1 | Translation pipeline (5-step SSE + multi-article split + citation placeholders + continuation rules + UTF-8 fix) | A | `routers/translate.py:295` multi-article via `parser/article_detector.extract_articles`; `block_translator.py:289,326` citation protect/restore; `cleaner/pipeline.py:258` pdfplumber encoding fix; `cleaner/pipeline.py:894-979` 6 continuation rules |
| 2 | 论证陪练 v3（账本 + Reviewer‑2 对抗 + 三角度并行评审 + Toulmin X 光 / 真实评审导入）| A | `argument/ledger.py` SSE 账本（anchor SSE 事件修复）; `argument/reviewer.py` run_review/run_review_parallel/continue_rebuttal/import_real_reviews; `argument/_reviewer_perspectives.py` method/experiment/writing 三角度 asyncio.gather; `argument/anchor.py` 三态锚定; `components/argument/CompanionPanel + LedgerList + ReviewerThread.vue` + 完整 rebuttal mini-chat; features.argument_companion=true; features.parallel_review 灰度开关; **ledger 路由全部用 `?doc_id=` query param** |
| 3 | Mind Map (Vue Flow + AI expand + dagre layout + node body + editor sync) | A | `MindMapNode.body` field; `mindMapToMarkdown`/`markdownToMindMapNodes` round-trip with body; `MindNodeCard` collapsible body textarea; `skipNextBackendLoad` prevents `loadFromBackend` overwriting editor→mindmap data |
| 4 | LaTeX/Word export (IEEE Conf/Journal, ACM, NeurIPS, LNCS, Generic + Tectonic) | A | `word_exporter.py`, `pandoc_templates`, `pptx_exporter` |
| 5 | AI editor (Monaco + Ghost Text + AI Panel + mid-stream reload) | B+ | `useEditorTabs.reloadOpenTabs()` refreshes open tabs after each Agent write; completion quality average |
| 6 | Agent ReAct engine (ContextCompressor + SessionStore tool_calls + Skill 三层分解 + review + Memory dedup + greeting guard + _DEFAULT_TOOL_GUIDE fallback) | A- | `agent.py:149,176,214` ContextCompressor wired into `step()`; `session_store.py:199-225` tool_calls round-trip; `review_agent.py` skill quality gate; `agent/_skill_model.py` SOUL/AGENTS/IDENTITY 三层; `prompt_builder.py` skill injection + 原则 #0 问候不调工具 + `_DEFAULT_TOOL_GUIDE` 自动覆盖所有未匹配 provider（moonshot/llama/grok/mistral 等不再返回空指导） |
| 7 | 21 cloud LLM providers | B | Only OpenAI-compatible path tested end-to-end |
| 8 | RAG / 文献库 | B- | Demoted to on-demand `search_documents` tool (no longer auto-injected); translation auto-ingest intact; `tools/registry.py` full impl when `rag_store` injected |
| 9 | Zotero integration | C | Requires user API key |
| 10 | Vision / OCR | C | Depends on external MCP server |
| 11 | Agent workspace file tools (read/write/grep/str_replace/git_op + boundary approval) | B | E2E verified: workspace_root wired from `useFileTree.rootDir`; `SecurityGate.force_approval` + `WorkspaceEnv` ContextVar; `await_approval` SSE → frontend `AgentApprovalInline` → `POST /approve` → ContextVar bypass; 1815 pytest passed |

### Known Defect Index

Single-pointer index — do not duplicate the long lists.

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

### 论证陪练 v3（已完成 — 见 docs/argument-map-v3-spec.md）

5 个 Phase（Phase 0–5）全部完成。功能包括：论证账本（承诺 ↔ 兑付，三态锚定）、Reviewer‑2 对抗（会议校准评审 + rebuttal mini-chat，reviewer 会被说服）、质疑这句/一致性/gap/RW 检查、真实评审导入（import_real_reviews）、实验缺口建议（suggest_experiment）、rebuttal 包导出（/download）。Toulmin v2 图（ArgGraph/Vue Flow）保留并复用为"审稿模式"可视化（ArgSourcePane 已有"从编辑器载入"入口）。features.argument_companion=true（已发布）。E2E 集成测试：`python/tests/integration/test_companion_e2e.py` 27 个测试覆盖全部 `/api/companion/*` 端点（pytest 1815 passed / 11 skipped）。**注意**：所有 ledger 路由的 `doc_id` 使用 query param（`?doc_id=`），因为 doc_id 可能是包含 `/` 的完整文件路径。`build_ledger` SSE 流在每个 promise 事件前先 yield anchor 事件，前端 `ledger.anchors` 才能正确填充。

论证地图 v2（见 docs/argument-map-v2-spec.md）：5 个 Phase 已全部完成，旧树实现已删除。当前 Toulmin 图 = v2 唯一版本，在论证陪练 v3 "审稿模式"中继续使用。

近期修复 (2026-05-15)：
- `llm_client.py` — reasoning 模型（deepseek-v4-pro）chain-of-thought 耗尽 token 后自动 2x 重试；Ollama fallback 修复 `result.translated` 属性
- `ai_ops.py` — 移除 `from __future__ import annotations` 避免 FastAPI 422；max_tokens 提升至 16384
- `ledger.py` — `_extract_promise_zone` 短文本截断修复（`//4` → `min(len, 3000)`）
- `useArgumentMap.ts` — SSE extractArgument 增加 `isDone` 回调避免流挂起
- `useArgumentLayout.ts` — 动态节点尺寸（150-320×56-140）+ 关系感知 edge minlen
- `ArgSourcePane.vue` — `spanSentenceMap` 处理无 block_id 的提取 span（paste/editor 模式回退到 `_virtual_` block）
- `ArgInspector.vue` — "采纳"新建节点定位到选中节点附近并自动创建 connecting edge
- `api_factory.py` — API key 持久化到 `default.local.yaml` 避免 reload 丢失
- `src-tauri/src/main.rs` — 启动前 `kill_port_owner()` 清理僵尸 Python 进程

安全 + 质量修复批次 (2026-05-15 Round 2，pytest 1624 passed / 11 skipped)：
- `tauri.dev.conf.json` — dev CSP 去掉 `unsafe-eval`
- `graph_store.py` / `companion_store.py` — 所有写方法加 `threading.RLock` 防并发丢数据
- `routers/translate.py` — SSE 任务槽位：`_run_pipeline` finally 块标记 error，过期任务清理顺序修正（先清 stale 再查 has_running），文件大小检查前置到 has_active 检查之前（保证 413 优先于 409）
- `api_factory.py` — `_TraceIdFilter` 覆盖 exc_info traceback 中的 Bearer token；`_validate_config` 补全 engine/timeout/model/max_tokens 四项校验；500 响应体携带 trace_id
- `cloud_client.py` — `_redact_key()` 屏蔽 api_key 出现在日志 warning 中
- `bash_session.py` — `_INJECTION_RE` 补全 `$((` / `$'...'` / `<<<` / `${}` / `>()` / `<()` / `eval` / newline 等注入模式
- `src-tauri/src/main.rs` — Python 路径 NUL 字节断言
- `useArgumentCompanion.ts` — 所有 catch 改 `pushError`/`pushWarning`，消除静默失败
- `sentenceAlign.ts` — `escapeHtml` 改为纯字符串 replace，去掉 DOM 依赖
- `routers/agent.py` — `ChatRequest.message` 加 `min_length=1`

可观测性增强 (2026-05-15)：
- `api_factory.py` — `RotatingFileHandler`：日志写入 `RUNTIME_DIR/logs/app.log`（10 MB × 5 备份），统一日志格式带 trace_id；`trace_id_middleware` 记录每个请求 method/path/status/耗时；新增 `GET /api/logs` 端点返回最近 N 行 + 文件路径
- `useToast.ts` — 新增 `errorLog` ring buffer（最多 50 条 warn/danger）、`unreadErrorCount`、`clearErrorLog()`、`markErrorsRead()`
- `DebugPanel.vue`（新文件）— 顶栏调试面板：前端错误历史（带时间戳/级别/消息）+ 后端日志查看（拉取 `/api/logs`）+ 打开日志目录按钮；有未读错误时显示红色数字徽标

agency-agents-zh SDLC 改造 (2026-05-18–19，分支 `feature/sdlc-borrow-agency-agents-zh`，4 Phase 全部完成)：
- **Phase A** — 翻译 prompt 5 规则外部模板化：`prompts/tasks_translate/academic_translate.md` + 7 个 section partials + `_prompt_loader.py`；`protect_citations` 扩展 author-year 引用保护；15 unit tests
- **Phase B** — 6 层 Prompt 骨架 + eval 框架：`src/prompts/schema.py` (PromptSpec)；6 个 tasks_*.md 加 YAML frontmatter；`tests/eval/runner.py` + YAML eval case；22 schema + 10 eval tests
- **Phase C** — Skill 三层文件分解：`_skill_model.py` 加 soul_path/agents_path/identity_path；`_skill_persistence.py` IDENTITY.md 检测；`_skill_migrate.py` 迁移脚本；`prompt_builder.py` active_skills/relevant_skill_names/skill_token_budget + SOUL 常驻/AGENTS 按需；12 unit tests
- **Phase D** — Reviewer 三角度并行：`_reviewer_perspectives.py` (method/experiment/writing + aggregate)；`run_review_parallel()` asyncio.gather + 去重；`ReviewPoint.perspective` 字段；4 个 prompt templates；路由接入 `POST /api/companion/review` mode=parallel + features.parallel_review 灰度开关；前端 CompanionPanel 下拉框切换；10 unit + 3 e2e tests
- **Bug fix pass** — 修 5 个 bug（_save_skill 写错文件 / _skill_migrate 空 name / _parse_llm_points 缺 category / 模板占位符未替换 / 串行路径缺 ollama_client）+ 40 adversarial tests
- 回归：1559 unit passed / 8 skipped + 326 vitest passed；计划详情见 `docs/sdlc-borrow-agency-agents-zh.md`

"Claude Code for Papers" 改造 (2026-05-22–23，5刀计划，main 分支)：
- **里程碑1** — workspace_root 接线：`AgentPanel.vue` 补传 `useFileTree.rootDir` → `useAgentChat.sendMessage` 第4参数 → `routers/agent.py._create_agent`；attachFile 改为只存路径（Agent 自己 read_file）；`refreshFileTree()` 在 sendMessage 后自动调用
- **里程碑2 (RAG 再平衡)** — 删除 `agent.py._build_messages` 中 RAG 自动注入块；`search_documents` 描述改为"跨文献长期回忆，当前项目用 read_file"；翻译自动入库保留（差异化护城河）
- **里程碑1.5 (越界审批)** — `security_gate.py`：`GateResult.force_approval` + `SecurityGate(workspace_root)` + `_check_workspace_escape()`；`workspace.py`：`workspace_escape_allowed: ContextVar[bool]`，resolve() 越界时查 ContextVar；`session.py`：SecurityGate 接收 workspace.root，`force_approval` 绕过 `auto_approve` 强制审批，审批通过后 ContextVar token 包裹工具执行；前端 `PendingApproval.reason` 字段补传，`AgentApprovalInline` 橙色显示原因
- **里程碑3 第4刀** — `useEditorTabs.reloadOpenTabs()`：Agent 每次 write_file/str_replace 完成立即刷新文件树 + Monaco（mid-stream watcher），有未保存修改的 tab 跳过；Tauri-only 动态 import 含 web 模式兜底
- **里程碑3 第5刀** — 删除 polish_text / summarize_text / expand_section / generate_outline（93行），同步清理 TOOL_DESCRIPTIONS + 集成测试 safe_args + mcp_server.py 注释；format_bibliography 保留
- **UI 适配** — "知识库" tab 改名"文献库"；workspace 状态栏（绿点 + 项目名 / "未打开项目"）；空状态 workspace 感知文案；TOOL_DESCRIPTIONS 覆盖所有19个工具
- 验证：1815 pytest passed / 11 skipped；347 vitest passed；E2E SSE 测试：越界路径 → await_approval → approve → ContextVar bypass → tool_result 全链路通过；计划详情见 `docs/claude-code-pivot-todo.md`

论证陪练 + Agent 修复 (2026-05-23)：
- `prompt_builder.py` — Agent 身份原则 #0：问候/闲聊直接回复，不调工具；DeepSeek/Qwen 模型指导同步补齐，修复"你好"触发无限工具调用循环
- `ledger.py` — `build_ledger` 在每个 promise 事件前 yield anchor SSE 事件；`rebuild_ledger` 同步透传 anchor 事件；修复前端 `ledger.anchors` 始终为空导致定位按钮失效
- `routers/argument.py` — 所有 ledger 路由的 `doc_id` 从 URL path param 改为 query param（`?doc_id=`），修复 doc_id 为完整文件路径（含 `/`）时路由 404
- `ReviewerThread.vue` — UI 重写为卡片式设计（展开折叠、状态下拉菜单、rebuttal 输入）；CSS 变量修正（`--c-error` → 硬编码 `#ef4444`，`--c-warning` → `--c-warn`，`--c-border` → `--c-surface-4`，`--c-text` → `--c-text-0`）
- `CompanionPanel.vue` — 评审进度条替代文字提示；blob 下载修复 Windows 兼容；移除多余 content prop
- `useArgumentCompanion.ts` — review 对象提前初始化，SSE 流式推入 points 实时显示
- `reviewer.py` — ledger_cross_check / coherence_check 标题和 prompt 中文化；discharge prompt 从严判断标准 + 首/中/尾采样替代截断
- `argument.py` — rebuttal 下载用 `tempfile.gettempdir()` 替代硬编码 `/tmp`
- 验证：1582 pytest passed / 8 skipped；326 vitest passed

死循环 + 论证账本可用性修复 (2026-05-23 Round 2)：
- `AiPanel.vue` — **润色/扩写/审阅/中英互译预设按钮改走 `/api/edit`**（一次性、无工具流式）而非 Agent ReAct 循环；根因：预设走 `/api/agent/v2/chat` 后 LLM 把"润色"当任务去 `write_file` 创建文档 → 卡死/循环。新增 `doEdit()` 消费 `delta` SSE 事件 + "未打开文本"守卫
- `session.py` — `_is_trivial_chat` 归一化加固：先用正则剥离尾部标点/语气词/emoji 再匹配预设词，"你好啊""你好~""hello!!" 等变体也命中短路；"你好，帮我润色"这类含指令的仍走完整流程（补 `import re`）
- `ledger.py` — **实际补上 anchor SSE 事件**（此前 CLAUDE.md 声称已做但代码并未实现）：`build_ledger` 在 src_anchor + 每个 discharge anchor 处 yield `anchor` 事件；`rebuild_ledger` 透传 `anchor`。修复前端 `ledger.anchors` 恒空导致"跳转原文/兑付处"按钮全失效
- `LedgerList.vue` / `CompanionPanel.vue` — 通篇未定义的旧 CSS 变量（`--border`/`--bg-2`/`--text-dim`/`--text`/`--accent`）全部映射到规范 `--c-*` token（修复浅色主题不可读）；账本列表加入场动效（`promise-in`）、hover 过渡、sticky 工具栏
- 验证：1582 pytest passed / 8 skipped；326 vitest passed

思维导图节点正文 + 编辑器双向同步 (2026-05-24)：
- `useMindMap.ts` — `MindMapNode` 新增可选 `body?: string` 字段；新增 `updateNodeBody(id, body)` 方法；`mindMapToMarkdown` 输出 heading + body 段落；`markdownToMindMapNodes` 解析 heading 间段落文本存入 body（返回 `MindMapTreeNode { text, body, children[] }`）；`cloneMap` 深拷贝 body；`toFlowNodes` 传递 body 到 flow node data；新增 `skipNextBackendLoad()` 防止 `loadFromBackend` 覆盖编辑器构建的数据
- `MindNodeCard.vue` — 节点右侧 `▸` 展开/收起按钮（有正文时高亮）；展开后显示可编辑 textarea（`nodrag nowheel`）；收起时显示首行预览（≤40 字）；`bodyPreview`/`draftBody` 直接从 store 读取，不依赖 Vue Flow data prop
- `MindMapCanvas.vue` — 改用 `watch(nodes) → setNodes` + `watch(edges) → setEdges` 强制同步 Vue Flow 节点数据
- `EditorLayout.vue` — `openMindMapFromEditor` 递归 `buildTreeNode` 构建带 body 节点树；`enterEditorFromMindMap` 恢复使用 outline（现在含完整正文）；调用 `skipNextBackendLoad()` 防覆盖；`handleExportPdf` 增加 tectonic 状态重检
- `pandoc_templates/__init__.py` — PDF 导出预处理：去掉 markdown 水平分隔线（`---` → 避免 `Misplaced \noalign`）；转义裸 `&`（论文引用 `Author & Coauthor, Year` → 避免 `Misplaced alignment tab`）
- 验证：1582 pytest passed / 8 skipped；345 vitest passed

翻译对齐 + Agent 死循环 + 发行版打包根治 (2026-05-24 Round 3，main 分支)：
- **文档问答一次性短路（Path A）** — `routers/agent.py` 新增 `_MUTATION_KEYWORDS` / `_has_mutation_intent()` / `_oneshot_doc_qa_stream()`：用户打开文档问"写得怎么样/总结/有什么问题"时，文档内容已在手，**不走 ReAct 工具循环**，直接单次 LLM 流式回答；仅当 `_has_mutation_intent`（明确要改文件/跑命令）时才进完整 Agent。根除文档问答触发的死循环。`session.py` 加 `[loop-guard v2]` 诊断日志
- **Agent read_file 增强** — PDF/Word/EPUB 走解析器提取纯文本，消除 Agent 读论文时的 ReAct 死胡同（`block_translator.py` 同源）
- **翻译 prompt 泄漏修复** — `block_translator.py` 章节感知指令（`[SECTION: ...]` / `[LOGIC: ...]`）改为透传 `section_prompt` 参数注入 **system prompt** 而非 prepend 到用户消息，避免 Qwen3:8b 把指令当正文翻译出来；`_sanitize_llm_output` 的 `_CTX_MARKER_RE` 补 `[SECTION:]`/`[LOGIC:]` 兜底清理
- **翻译对齐根治** — `_merge_excess_paras()`（LLM 多输出段落时合并最短/靠末尾相邻对，再 1:1 精确对齐）；`_distribute_by_char_ratio` 搜索窗口扩至 ±60 字符、优先 `\n\n` 段落边界；`_is_mostly_english` 阈值收紧为 `zh_chars==0 且英文>85%`（保留含术语的有效译文）；删段改替换空串保留位置；`block_translator.py` 严重对齐重试阈值 `ratio>0.5` → `>0.3`
- **QA 误报修复** — `post_qa.py` 句子长度阈值 `max_words` 30 → 45（学术英文复杂句普遍 35-45 词）
- **Agent 死循环根治** — `agent.py` `TASK_MAX_STEPS` 50→20、`GLOBAL_MAX_STEPS` 200→60；`session.py` 加 `_tool_call_counts`（单工具累计 >3 次强提示）+ `_loop_warnings`（第 2 次强制 `break` 走总结）+ `_force_stop` 复用步数耗尽总结路径；移除永不可达的 elif 死代码；任务分解连接词移除「再」
- **DeepSeek 400 熔断** — `_llm_helpers.py` assistant 工具调用消息 content 始终发字符串（DeepSeek 拒绝 null）+ `_sanitize_tool_pairs` 丢弃孤立 tool_call/tool_result；`session.py` 熔断器对 400/鉴权/欠费/模型不存在/超大请求体立即终止，其余累计 5 次终止；`agent.py` 每步重置重试预算防跨步泄漏
- **config max_tokens 修正** — `chunker.max_tokens` 2048 → 800（2048 约含 15+ 段落导致对齐回退）；`api.spec` 打包从**根目录** `config/default.yaml` 读取防漂移；`api_factory.py` 启动检测 `max_tokens==2048` 自动写 800 兼容老用户升级
- **发行版打包补齐** — `api.spec` 打包 Pandoc / Tectonic（预热 LaTeX 缓存）/ all-MiniLM-L6-v2 嵌入模型，首启播种到用户缓存，PDF 导出与文献库离线可用；`collect_submodules('src')` + `collect_all` 自动收隐藏依赖 + VC++ 运行库 + providers.yaml；`build-python.cjs` 加 `scripts/.tools-cache` 绕开 GitHub 超时；**翻译默认引擎改为 cloud**；`de6679b` 用 `python -m PyInstaller` 防 PATH 误选其他 Python 版本
- **导出模板文字清理** — `ieee.tex`/`ieee_conference.tex` 改用 IEEEtran 类（去掉 ieeeaccess 的 Logo/Received 行）；`neurips.tex` 从误用的 icml2026 包改为纯 article（去掉 "Under review at ICML 2026"）；`acm.tex`/`acm_sig.tex` 关闭 acmart 的版权/地址/Permission 模板文字
- **companion 可用性** — `ledger.py` discharge anchor 精确匹配失败时 fallback `relocate()` 模糊匹配（修复 LLM 意译引用导致兑付处恒 lost）；`reviewer.py` `continue_rebuttal` max_tokens 512 → 2048（修复中文长回复截断）；`useArgumentCompanion.ts` anchor lost 弹 toast；`CompanionPanel`/`LedgerList` "怎么补满"加 `suggestingId` 加载动画；`ReviewerThread.vue` 超 280 字回复默认折叠
- **argument 导出修复** — 导出草稿 SSE complete 事件携带 `task_id`，前端调 `/flatten_v2/{task_id}/download` + `saveBlob` 弹原生保存框（此前文件只写服务端从未下载）；导出 rebuttal 改 `saveBlob` 走 Tauri 原生另存为 + 错误 toast；`extractArgument` 完成后自动 dagre `autoLayout`
- **杂项** — `ccca9ce` 思维导图 AI 检查完成后自动打开右侧分析面板；`a0e6205` 合规检查在 Tauri 包内用 `API_BASE` 绝对路径（相对路径 `/api/compliance` 在 WebView 解析失败返回 HTML）；`0cf9674` 消除关闭时 taskkill 无窗口子进程的误导性错误日志
- 新增测试：`tests/unit/test_doc_qa_oneshot.py`（Path A 意图分类 + 事件序列）、`tests/unit/test_session.py` 跨工具空转强制停止
- 验证：1587 unit passed / 8 skipped（较上轮 1582 增 5）

Agent 工具指导全 provider 覆盖 (2026-05-30)：
- `prompt_builder.py` — `_get_model_guide` 对未匹配 `_MODEL_TOOL_GUIDES` 的模型不再返回空字符串，改为返回 `_DEFAULT_TOOL_GUIDE`（6 条通用指导：拒绝推脱、必须真调工具、不要编造路径、信息够就停）。此前仅 qwen/gpt/deepseek/gemini 四族模型有专属指导，其余 17 个 provider 的所有模型（moonshot、glm、llama、grok、mistral、sonar、doubao、ernie 等）拿到空指导，导致 Agent 拒绝执行工具调用
- 新增测试：`test_prompt_builder.py` 新增 17 个参数化测试覆盖全部未匹配模型 + 验证已知模型仍返回特定指导
- 验证：1815 pytest passed / 11 skipped；347 vitest passed
