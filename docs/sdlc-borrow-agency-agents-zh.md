# SDLC 借鉴落地：agency-agents-zh → Scholar Assistant

> **状态文档**。每个 Phase 完成时把对应 checkbox 从 `[ ]` 改成 `[x]`，并在末尾追一行变更日志。
> **来源**：`https://github.com/jnMetaCode/agency-agents-zh`
> **分支**：`feature/sdlc-borrow-agency-agents-zh`
> **计划 plan 文件副本**：`C:\Users\zuowen\.claude\plans\sdlc-async-hopcroft.md`

## 进度索引

| Phase | 主题 | 主要产出 | 测试增量 | 预估 | 状态 |
|---|---|---|---|---|---|
| 0 | 文档落仓 + 分支建立 | 本文件 + `feature/sdlc-borrow-agency-agents-zh` | 0 | 30 min | [x] |
| A | 翻译 prompt 5 规则 + 外部模板 | `prompts/tasks_translate/` + author-year 引用保护 | 15 unit | 1–2 天 | [x] |
| B | 6 层 Prompt 骨架 + eval 框架 | `prompts/schema.py` + `tests/eval/` | 18 unit | 2–3 天 | [x] |
| C | Agent Skill 三层文件分解 | `data/agent/skills/<name>/{SOUL,AGENTS,IDENTITY}.md` | 12 unit | 2–3 天 | [ ] |
| D | Reviewer-2 DAG 三角度并行 | `_reviewer_perspectives.py` + 3 个 `.md` | 13 unit + 3 e2e | 2–3 天 | [ ] |

**总测试增量**：58 unit + 3 integration（全 mock，不依赖真实 LLM）
**回归基线**：`pytest python/tests/unit/ -q` 现状 1624 passed / 11 skipped，每 Phase 不能下降

---

## 总体 SDLC 节奏（每个 Phase 严格遵守）

```
1. RED      写测试 → 跑 → 红
2. 用户确认  看测试用例，确认意图
3. GREEN    写最小实现 → 跑 → 绿
4. REFACTOR 整理
5. 用户验收  → 进下一 Phase
```

每个 Phase 都可独立合并并回滚，**不允许跨 Phase 提交**。

## Context

`jnMetaCode/agency-agents-zh` 这个仓库的 4 个设计模式对 Scholar Assistant 有直接收益：

1. **technical-translator-agent 的 5 条硬规则** — 当前翻译 prompt **硬编码在 `block_translator.py:255-289` / `ollama_client.py:204-243` / `cloud_client.py:245-272`**，规则散落、不可测；抽到外部模板后术语/格式稳定性会显著提升。
2. **prompt-engineer 的 6 层骨架（角色→任务→约束→格式→示例→兜底）** — 当前 `prompts/tasks_polish/` `tasks_expand/` `tasks_coherence/` `tasks_edit/` `tasks_compliance/` 5 个 prompt 文件结构不统一，没有评测集。
3. **OpenClaw 的三层文件分解（SOUL / AGENTS / IDENTITY）** — 当前 `agent/skill_system.py` 单文件 monolithic，会被全量塞进 context；按 SOUL（常驻）+ AGENTS（按需）+ IDENTITY（一行检索）切分可压 token。
4. **Orchestrator 的 DAG 并行** — 当前 `argument/reviewer.py` 单 Reviewer 串行，无法模拟真实会议评审的多角度并行。

**用户拍板**：4 项一次性做、外部 `prompts/tasks_translate/*.md` 模板、暂不引入 `style` 维度、unit 用 mock + 金标 fixture（不依赖真实 LLM）。

---

## Phase A — 翻译 Prompt 5 规则 + 外部模板

### 影响文件
- **新建** `python/prompts/tasks_translate/academic_translate.md` — 系统提示主模板（6 层骨架）
- **新建** `python/prompts/tasks_translate/_partials/section_{abstract,intro,methods,results,discussion,conclusion}.md`
- **新建** `python/prompts/tasks_translate/_partials/glossary_block.md`
- **修改** `python/src/translator/block_translator.py:255-340` — 改走 loader
- **修改** `python/src/translator/ollama_client.py:204-243` `_build_system_prompt()`
- **修改** `python/src/translator/cloud_client.py:245-272` `_build_system_prompt()`
- **修改** `python/src/translator/section_aware.py:72-141` — 字符串移到 .md
- **新增** `python/src/translator/_prompt_loader.py`
- **修改** `python/src/cleaner/pipeline.py:1169-1190` `protect_citations` — author-year regex

### RED — `python/tests/unit/test_translate_prompt_v2.py`（15 测试）

| ID | 用例 | 断言 |
|---|---|---|
| A1 | `test_prompt_loaded_from_template` | system prompt 含模板首行特征字符串 |
| A2 | `test_rule1_accuracy_first` | 含"准确性优先"指令 |
| A3 | `test_rule2_terminology_standardization` | glossary 注入到术语段 |
| A4 | `test_rule3_code_preserved` | ``` 代码块原样保留（金标） |
| A5 | `test_rule3_inline_code_preserved` | `` `func()` `` 不翻 |
| A6 | `test_rule3_inline_math_preserved` | `$x^2$` 不翻 |
| A7 | `test_rule3_display_math_preserved` | `$$...$$` 不翻 |
| A8 | `test_rule4_context_section_abstract` | abstract 子模板 |
| A9 | `test_rule4_context_section_methods` | methods 子模板 |
| A10 | `test_rule5_format_markdown_heading` | `#` `##` 保留 |
| A11 | `test_rule5_format_list` | `- ` `1. ` 保留 |
| A12 | `test_rule5_format_table` | `\|...\|` 结构保留 |
| A13 | `test_citation_protect_numeric` | `[1]` `(1,3)` `(1-5)` 回归 |
| A14 | `test_citation_protect_author_year` | `[Smith, 2020]` `(Smith et al., 2020a)` 新增 |
| A15 | `test_citation_restore_idempotent` | protect→restore 还原 100% |

**金标 fixture** — `python/tests/fixtures/translate_golden/`：
- `code_block.input.md` / `.expected_kept_lines`
- `inline_math.input.md` / `.expected_kept_tokens`
- `markdown_table.input.md` / `.expected_structure`
- `author_year_citations.input.md` / `.expected_placeholders`
- `nested_list.input.md` / `.expected_structure`

**Mock 策略**：`MagicMock` 包 `OllamaClient.chat` / `CloudClient.chat` → mock 返回输入原文 → 测 prompt 组装 + protect/restore，不验真实翻译质量。

### GREEN
1. 抽 `_build_system_prompt()` 字符串到 `academic_translate.md`
2. 实现 `_prompt_loader.py` (`load_translate_prompt(section, glossary_text) -> str`)
3. 替换 `block_translator.py:286` + 两个 client 硬编码
4. `protect_citations` regex 加 `\[[A-Z][a-z]+(?:\s+et\s+al\.?)?(?:\s+and\s+[A-Z][a-z]+)?,\s+\d{4}[a-z]?\]` 和小括号版本

### REFACTOR
- 删 `section_aware.py:72-141` 残余字符串
- 5 规则中文版写进 `academic_translate.md` 头部 docstring

### 验收
```bash
cd python
pytest tests/unit/test_translate_prompt_v2.py -v
pytest tests/unit/test_translator.py tests/unit/test_block_translator.py tests/unit/test_glossary.py tests/unit/test_special_elements.py -v  # 回归
```
现有翻译测试不挂；新 15 个全绿。

---

## Phase B — 6 层 Prompt 骨架 + 评测框架

### 影响文件
- **修改** `python/prompts/tasks_polish/academic_polish.md`（6 层重写）
- **修改** `python/prompts/tasks_expand/grounded_expand.md`
- **修改** `python/prompts/tasks_coherence/coherence_rewrite.md`
- **修改** `python/prompts/tasks_edit/edit_with_text.md` `edit_without_text.md`
- **修改** `python/prompts/tasks_compliance/compliance_check.md`
- **修改** `python/prompts/tasks_translate/academic_translate.md`（完善 6 层）
- **新建** `python/src/prompts/schema.py` — `PromptSpec` 强制 6 层
- **修改** `python/prompts/loader.py` — schema 校验
- **新建** `python/tests/eval/` 目录 + `runner.py`
- **新建** `python/tests/eval/cases/{translate,polish}/*.yaml`

### RED
**`python/tests/unit/test_prompt_schema.py`（10）**
- B1 `test_schema_six_layers_required`
- B2-B7 `test_<task>_passes_schema`
- B8 `test_role_layer_includes_persona`
- B9 `test_constraints_layer_quantified`
- B10 `test_fallback_layer_handles_empty_input`

**`python/tests/eval/test_eval_runner.py`（8）**
- E1 `test_eval_loads_cases`
- E2-E5 `test_eval_assertions_{contains,not_contains,regex_match,length_range}`
- E6 `test_eval_passrate_report`
- E7 `test_eval_failure_diagnostic`
- E8 `test_eval_mock_llm`

### GREEN
1. `PromptSpec` (Pydantic / dataclass)
2. `.md` 头部 YAML frontmatter
3. `loader.py` 加 schema 校验（先 `strict: false` 警告，下迭代 `strict: true`）
4. eval runner：yaml → render → mock LLM → 断言

### 验收
```bash
pytest tests/unit/test_prompt_schema.py tests/eval/ -v
python -m tests.eval.runner --suite translate  # passrate >= 90%
```

---

## Phase C — Agent Skill 三层文件分解

### 影响文件
- **修改** `python/src/agent/_skill_model.py` — Skill dataclass 加 `soul_path` `agents_path` `identity_path`
- **修改** `python/src/agent/_skill_persistence.py`
- **修改** `python/src/agent/_skill_matching.py` — 只读 IDENTITY
- **修改** `python/src/agent/prompt_builder.py` — SOUL 常驻、AGENTS 按相关性
- **修改** `python/src/agent/skill_system.py` — migration 兼容
- **新建** `python/src/agent/_skill_migrate.py`
- **新建** `python/data/agent/skills/<name>/{SOUL,AGENTS,IDENTITY}.md`

### RED — `python/tests/unit/test_skill_three_layer.py`（12）
- C1 `test_skill_loads_from_three_files`
- C2 `test_identity_under_200_chars`
- C3 `test_soul_always_in_context`
- C4 `test_agents_only_when_relevant`
- C5 `test_matching_reads_only_identity`（mock spy IO）
- C6 `test_token_budget_respected`
- C7 `test_migration_from_legacy_single_file`
- C8-C12 edge cases（缺文件 / 空目录 / 非法 YAML）

### GREEN
1. dataclass + 三文件 IO
2. matching 只读 IDENTITY
3. prompt_builder：SOUL 全注入，AGENTS 按 cosine similarity threshold（用现有 embed）
4. migration 脚本 + 自动备份 `python/data/agent/skills.backup-<timestamp>/`

### 验收
```bash
pytest tests/unit/test_skill_three_layer.py tests/unit/test_skill*.py -v
python -m python.src.agent._skill_migrate --dry-run
```

---

## Phase D — Reviewer-2 DAG 并行

### 影响文件
- **修改** `python/src/argument/reviewer.py` `run_review` — `asyncio.gather`
- **新建** `python/src/argument/_reviewer_perspectives.py`
- **新建** `python/prompts/tasks_review/perspective_{method,experiment,writing}.md` + `aggregator.md`
- **修改** `python/src/argument/companion_store.py` — Reviewer 加 `perspective` 字段
- **修改** `src/components/argument/ReviewerThread.vue` — UI 三栏

### RED
**`python/tests/unit/test_reviewer_parallel.py`（10）**
- D1 `test_three_perspectives_run_in_parallel`（timer+sleep mock 验证 gather）
- D2 `test_aggregator_merges_three`
- D3-D5 `test_perspective_<method,experiment,writing>_prompt_focused`
- D6 `test_aggregator_no_duplicate_points`
- D7 `test_failure_partial_tolerance`
- D8 `test_rebuttal_continues_on_aggregated`
- D9 `test_perspective_order_stable`
- D10 `test_token_cost_logged`

**`python/tests/integration/test_reviewer_parallel_e2e.py`（3）**

### GREEN
1. 抽 3 个 reviewer prompt 到 .md
2. `run_review` 改 `gather(method, experiment, writing) → aggregator(results)`
3. companion_store schema migration（向前兼容旧单 reviewer）

### 验收
```bash
pytest tests/unit/test_reviewer_parallel.py tests/integration/test_reviewer_parallel_e2e.py -v
pytest tests/integration/test_companion_e2e.py -v  # 现有 27 个 e2e 不挂
```

---

## 全局验证

每个 Phase 结束都跑：

```bash
cd python
pytest tests/unit/ -q
pytest tests/integration/ -q
npx vitest run
```

UI 改动（仅 Phase D 末尾涉及 ReviewerThread.vue）：
```bash
npx tauri dev
# 手工验证：上传论文 → 论证陪练 → run reviewer → 看到 method/experiment/writing 三角度
```

---

## 关键已有可复用资产

- `python/src/cleaner/pipeline.py:1169` `protect_citations` / `:1186` `restore_citations`
- `python/src/translator/glossary_store.py` `Glossary.build_prompt_text()`
- `python/prompts/loader.py`
- `python/src/agent/_skill_matching.py`
- `python/tests/integration/test_companion_e2e.py` 27 e2e

## 已知风险与回滚开关

1. **Phase A `protect_citations` regex 误伤** — A14/A15 金标兜住；必要时加 feature flag `translator.use_author_year_protection: false` 默认关
2. **Phase B schema 强制 6 层破坏现有 prompt** — 先 `strict: false` 警告，下迭代 `strict: true`
3. **Phase C skill 迁移丢数据** — `--dry-run` + 自动备份
4. **Phase D 三倍 token 成本** — config 加 `argument.reviewer.parallel: true`（默认 false），灰度开

## 不做的事

- 不引入 `style: paper|api|blog`
- 不动 21 个 cloud provider 适配层
- 不动 Tauri / Rust 侧
- 不重写 Vue 组件结构（仅 ReviewerThread.vue 视觉小改）

---

## 变更日志

- **2026-05-18 Phase 0**：建分支 `feature/sdlc-borrow-agency-agents-zh`；落地本文档
- **2026-05-18 Phase A**：29 tests green (A1-A15)；新增 `_prompt_loader.py` + `academic_translate.md` + 7 section partials；扩展 `protect_citations` author-year regex；回归 133 passed
- **2026-05-18 Phase B**：32 tests green (B1-B10 × 22 + E1-E8 × 10)；新增 `src/prompts/schema.py` (PromptSpec + PromptSchemaError)；6 个 tasks_*.md 加 YAML frontmatter；新增 `tests/eval/runner.py` + 5 个 YAML case 文件；eval runner 验证 translate/polish 套件 5/5 pass；回归 1514 passed / 8 skipped
