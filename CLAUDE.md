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
- `routers/agent.py` — Agent chat, RAG document management
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
  - `useMindMap.ts` — singleton; mind map data (CRUD, undo/redo, flow adapters `toFlowNodes`/`toFlowEdges`)
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
  - `mindmap/` — MindMapCanvas (Vue Flow), MindNodeCard, MindEdge
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

Use this as the canonical "what works / what's polished / what's a stub" map. Updated 2026-05-23.

| # | Subsystem | Grade | Key evidence |
|---|-----------|-------|--------------|
| 1 | Translation pipeline (5-step SSE + multi-article split + citation placeholders + continuation rules + UTF-8 fix) | A | `routers/translate.py:295` multi-article via `parser/article_detector.extract_articles`; `block_translator.py:289,326` citation protect/restore; `cleaner/pipeline.py:258` pdfplumber encoding fix; `cleaner/pipeline.py:894-979` 6 continuation rules |
| 2 | 论证陪练 v3（账本 + Reviewer‑2 对抗 + 三角度并行评审 + Toulmin X 光 / 真实评审导入）| A | `argument/ledger.py` SSE 账本（anchor SSE 事件修复）; `argument/reviewer.py` run_review/run_review_parallel/continue_rebuttal/import_real_reviews; `argument/_reviewer_perspectives.py` method/experiment/writing 三角度 asyncio.gather; `argument/anchor.py` 三态锚定; `components/argument/CompanionPanel + LedgerList + ReviewerThread.vue` + 完整 rebuttal mini-chat; features.argument_companion=true; features.parallel_review 灰度开关; **ledger 路由全部用 `?doc_id=` query param** |
| 3 | Mind Map (Vue Flow + AI expand + dagre layout) | A- | LLM failure → hardcoded fallback nodes |
| 4 | LaTeX/Word export (IEEE Conf/Journal, ACM, NeurIPS, LNCS, Generic + Tectonic) | A | `word_exporter.py`, `pandoc_templates`, `pptx_exporter` |
| 5 | AI editor (Monaco + Ghost Text + AI Panel + mid-stream reload) | B+ | `useEditorTabs.reloadOpenTabs()` refreshes open tabs after each Agent write; completion quality average |
| 6 | Agent ReAct engine (ContextCompressor + SessionStore tool_calls + Skill 三层分解 + review + Memory dedup + greeting guard) | A- | `agent.py:149,176,214` ContextCompressor wired into `step()`; `session_store.py:199-225` tool_calls round-trip; `review_agent.py` skill quality gate; `agent/_skill_model.py` SOUL/AGENTS/IDENTITY 三层; `prompt_builder.py` skill injection + 原则 #0 问候不调工具 |
| 7 | 21 cloud LLM providers | B | Only OpenAI-compatible path tested end-to-end |
| 8 | RAG / 文献库 | B- | Demoted to on-demand `search_documents` tool (no longer auto-injected); translation auto-ingest intact; `tools/registry.py` full impl when `rag_store` injected |
| 9 | Zotero integration | C | Requires user API key |
| 10 | Vision / OCR | C | Depends on external MCP server |
| 11 | Agent workspace file tools (read/write/grep/str_replace/git_op + boundary approval) | B | E2E verified: workspace_root wired from `useFileTree.rootDir`; `SecurityGate.force_approval` + `WorkspaceEnv` ContextVar; `await_approval` SSE → frontend `AgentApprovalInline` → `POST /approve` → ContextVar bypass; 1752 pytest passed |

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

5 个 Phase（Phase 0–5）全部完成。功能包括：论证账本（承诺 ↔ 兑付，三态锚定）、Reviewer‑2 对抗（会议校准评审 + rebuttal mini-chat，reviewer 会被说服）、质疑这句/一致性/gap/RW 检查、真实评审导入（import_real_reviews）、实验缺口建议（suggest_experiment）、rebuttal 包导出（/download）。Toulmin v2 图（ArgGraph/Vue Flow）保留并复用为"审稿模式"可视化（ArgSourcePane 已有"从编辑器载入"入口）。features.argument_companion=true（已发布）。E2E 集成测试：`python/tests/integration/test_companion_e2e.py` 27 个测试覆盖全部 `/api/companion/*` 端点（pytest 1582 passed / 8 skipped）。**注意**：所有 ledger 路由的 `doc_id` 使用 query param（`?doc_id=`），因为 doc_id 可能是包含 `/` 的完整文件路径。`build_ledger` SSE 流在每个 promise 事件前先 yield anchor 事件，前端 `ledger.anchors` 才能正确填充。

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
- 验证：1752 pytest passed / 11 skipped；326 vitest passed；E2E SSE 测试：越界路径 → await_approval → approve → ContextVar bypass → tool_result 全链路通过；计划详情见 `docs/claude-code-pivot-todo.md`

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
