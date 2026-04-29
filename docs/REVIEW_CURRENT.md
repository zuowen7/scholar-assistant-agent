# Scholar Assistant — 当前代码库评审

> 评审日期：2026-04-29  
> 评审范围：commit `f6b9fa8` 时点的全量代码（不参考历史评审文档）  
> 评审者：Claude (Opus 4.7)

代码规模：Python 后端 23,908 行（含测试）；前端 14,779 行（Vue + TS + Rust）。

---

## 1. 工程健康度评分

| 子系统 | 评分 | 关键依据 |
|---|---|---|
| 翻译管道（parser/cleaner/chunker/translator/formatter） | **4.5/5** | 17 阶段清洗 (`cleaner/pipeline.py:34-104`)、TM+术语+并行翻译 (`routers/translate.py:651-738`)、parallel_runner 严格按 index 顺序 yield (`parallel_runner.py:80-101`)、clear failure semantics + fallback。`pipeline.py` 仍 861 行单文件，可拆。 |
| Agent / AWA 系统（python/src/agent/） | **3.5/5** | 架构完整：AgentLoop + AgentSession + SecurityGate + HookManager + ErrorClassifier + Skill + Memory + Trajectory，phase 3 审批 + phase 4 持久化齐全 (`session.py:300-426`)。但存在 211 行的死类 `ToolGenerator`、659 行 `mcp_server.py` 与 `tools/registry.py` 严重重复。 |
| 后端 API 层（routers/） | **4/5** | `api_factory.py` factory 模式干净，五路由模块通过共享闭包注入；`features.py:32-35` 集中可选依赖检测；速率限制 + CORS + 全局异常处理已配置。但 `translate.py` 仍 1043 行（最大文件），`editor.py` 中 ocr/chart/table 直接调用同模块路由处理器（反模式）。 |
| 前端状态管理与 SSE（src/composables/） | **4/5** | useTranslate / useAgentChat / useEditor 均为模块级单例；`utils/streamReader.ts` 47 行复用于 6 个调用点；SSE 自动重连 (`useTranslate.ts:182-202`)；session 恢复 / 审批回流齐全 (`useAgentChat.ts:223-379`)。`App.vue:179` `showSettings` ref 是死代码。 |
| Tauri 进程管理（src-tauri/） | **4/5** | 进程树清理 (`main.rs:15-36`)、端口探活就绪检查 (`main.rs:340-347`)、健康监测线程去重 (`main.rs:316`)、proxy 变量清理 (`main.rs:59-65 + 374-383`)、`save_file` 限制写入 home (`main.rs:130-146`)。无 graceful shutdown 等待。 |
| 配置与安全 | **4/5** | 三层配置 (`api_factory.py:46-149`：default/local/env)、API key 掩码、文件路径黑名单 + 沙箱 (`api_factory.py:215-267`)、SecurityGate 黑/白名单 + 命令分级 (`security_gate.py:33-263`)、rate limiter 按 IP 限流。`AppData\Local\Temp` 例外是已知折衷 (`api_factory.py:259-263`)。 |
| 测试覆盖率 | **3/5** | 后端 38 个 unit + 6 个集成测试文件，**726 通过 / 5 跳过**；但 `tests/unit/test_word_exporter.py` 收集失败（导入已重命名的 `_apply_inline_format`），**会让 `pytest tests/unit/` 整体报错退出**。前端 5 个测试文件 / 98 通过；前端覆盖明显不及后端（25+ 组件 / 14 composable 仅 5 个测试文件）。 |

---

## 2. 现存问题清单

### P0 — 阻塞 / 必须立即修

1. **测试套件无法整体运行**  
   `python/tests/unit/test_word_exporter.py:10` 导入 `_apply_inline_format`，但该函数在 `python/src/formatter/word_exporter.py:67` 已重命名为 `_apply_inline`（`replace_all` 改名时漏改测试）。运行 `pytest tests/unit/` 会因 collection error 直接中断。  
   **影响**：CI/本地全量回归被堵；现有 726 个通过的 case 无法验证。

2. **Agent stats 端点报告错误的 max_steps**  
   `python/routers/agent.py:621` 返回 `"max_steps": agent_cfg.get("max_steps", 10)`；但实际 AgentLoop 在 `routers/agent.py:219` 用 `agent_cfg.get("max_steps", 6)`，常量 `agent.py:76 MAX_STEPS = 6`。前端展示的 max_steps 与运行时不符。

### P1 — 严重影响代码质量

3. **死代码：`ToolGenerator`**  
   `python/src/agent/tool_generator.py`（211 行）实现完整 LLM 动态工具生成器，但全仓搜索除自身外**无任何引用**（git log 显示 `9670f5b feat:` 提交后未接入路由/AgentLoop/registry）。该模块当前是"新功能孤儿"，建议接入或删除。

4. **大规模重复实现：MCP 工具与 Agent 工具**  
   `python/src/agent/mcp_server.py:86-306` 重复定义了 `_translate_text` / `_parse_document` / `_search_documents` / `_crawl_arxiv` / `_polish_text` / `_summarize_text` / `_generate_outline` / `_expand_section` / `_format_bibliography` / `_analyze_markdown_elements` / `_parse_table_structure` / `_generate_table_markdown_handler` / `_format_latex_formula_handler` / `_get_citation_context_handler` / `_analyze_image_with_vision_handler` / `_analyze_chart_image_handler` 共 16 个工具函数 —— 这些功能在 `python/src/agent/tools/registry.py:79-355` 和 `tools/builtin_tools.py` / `tools/atomic_tools.py` 已实现。  
   **影响**：bug 必须在两处修；提示词修改可能漂移；mcp_server 的实现没接入 SecurityGate / Hook / ErrorClassifier。

5. **路由处理器互相直接调用（FastAPI 反模式）**  
   `python/routers/editor.py:617,621,625` 中 `ocr_image` / `analyze_chart` / `extract_table` 直接调用同模块的路由函数 `analyze_image(file, analysis_type=...)`。虽因 Python 闭包能跑通，但绕过了 FastAPI DI；应抽出私有 `_analyze_image_helper`。

6. **`Any` 未导入但出现在签名（潜在 bug）**  
   `python/src/agent/tools/registry.py:36-37` 函数签名 `ollama_client: Any | None = None, cloud_client: Any | None = None`，但顶部仅有 `from __future__ import annotations`，**没有 `from typing import Any`**。当前因为注解是 lazy 字符串、无人对该函数调 `get_type_hints` 才不爆。一旦未来移除 `from __future__` 或别处对这函数做反射，立即 NameError。

### P2 — 一致性 / 可读性问题

7. **bilingual_pdf 输出目录与其他端点不一致**  
   `python/routers/translate.py:1017` 写入 `runtime_dir / "output"`；其他翻译产物写入 `data_root / "output"`（`data_root` 在 cloud-only 模式下是 `data_cloud`，见 `api_factory.py:321`）。云端独立模式的双语 docx 会落在错误目录。

8. **前端 → 后端的 `mode` / `format` 字段被忽略**  
   `src/composables/useTranslate.ts:381` 发送 `{ task_id, mode, format: 'docx' }`；后端 `routers/translate.py:1009-1038` 的 `BilingualPdfPayload` 仅声明 `task_id`，其余字段被 Pydantic 静默丢弃。前端注释还写着 `'below' | 'above' | 'replace'`，已与后端真实行为脱节（PDF 已废弃，固定输出 docx）。

9. **死代码：`App.vue:179` `showSettings`**  
   `const showSettings = ref(false)` 后从未读写。AppTopBar 抽取后遗留。

10. **`_run_pipeline` 错误重启路径**  
    `routers/translate.py:847-849` 允许从 `error` 状态重启 stream，但 `tasks[task_id]['error']` 字段未在重启前清空，前端可能拿到混合状态。

11. **bundled glossary 仅在打包模式拷贝**  
    `api_factory.py:48-57` 的 `bundled_glossary → runtime_glossary` 拷贝逻辑被 `if _is_frozen() and not DOCKER_MODE` 守卫；开发模式直接 `pip install` + `python api.py` 启动时，`runtime/data/translator/glossaries/` 不存在，`GlossaryStore.load_yaml_dir` 静默无果（`routers/translate.py:355`）。

12. **`_translate_one` 重试只重试一次且不带退避**  
    `parallel_runner.py:38-48` 对单 chunk 异常仅重试 1 次，固定 `retry_delay=2.0`，与 `cloud_client.py:32-43` 内部已有的指数退避（max 3 次）形成两套重试机制，行为难以预测。

13. **Agent v2 工具白名单与实际注册的工具集不对齐**  
    `routers/agent.py:35-39` 的 `_V2_TOOL_WHITELIST` 列出 8 个工具，但 `tools/registry.py` 默认注册 ≥ 25 个工具（含 polish/summarize/translate/parse/format_bibliography/special_elements 等）。直接调用端点 `/api/agent/v2/tool` 因此无法触达大多数工具，造成"测试调试受限"。

14. **`AgentLoop._build_messages` 中 RAG 注入 hardcoded `top_k=3`**  
    `python/src/agent/agent.py:378` 写死 `top_k=3`；agent 配置里没有暴露这个参数。

15. **`features.argument` 检测的是 `src.argument.models`，但 `register_argument` 总是被调用**  
    `routers/argument.py:96-359` 几乎所有端点都包在 `if _ARGUMENT_AVAILABLE:` 内；如果 argument 模块不可用（virtually 不会发生），整段路由空注册，但 `api_factory.py:373-379` 仍调用 `register_argument`。建议跟 plugin 子系统一样在 factory 层做条件 register。

### P3 — 小瑕疵

16. **Trajectory finalize 仅在 DONE 路径被调用**  
    `python/src/agent/session.py:200` 的 `_finalize_trajectory` 只在 `state == DONE` 时跑；abort/error 路径不记录最终轨迹（`session.py:171-181, 218-224`）。会导致失败案例不进入 memory/skills 的归因学习。

17. **mcp_server 出现 Windows Store Python 硬编码黑名单**  
    `mcp_server.py:33-38` 硬编码 `D:\\env\\anaconda` 作为 fallback Python 路径——只对原作者机器有效。

18. **`api_factory.py:336` 初始 `rag_store_getter=lambda: None`**  
    第 350-351 行通过 mutable dict 重写 `_state["rag_store_getter"]`，依赖路由注册顺序。如有人调换 `register_translate` / `register_agent` 顺序，自动 RAG 入库会静默失效。

19. **`_normalize_for_matching` / `_skeleton` / `_match_blocks` 等大量遗留启发式**  
    `routers/translate.py:145-235` 是 200+ 行专为"PDF 双语 overlay"做的 block 文本-翻译匹配启发式，但 PDF overlay 在 commit `4360197 fix: bilingual export → docx (废弃 PDF overlay)` 已被弃用，下游消费者只剩 docx。**这是历史遗留死代码，可直接删除**。

20. **测试目录对 routers/ 几乎没覆盖**  
    `tests/unit/` 只有 `test_api_factory.py` 和 `test_agent_v2_router.py`；translate/editor/argument/mindmap 路由层无单元测试，全靠少量集成测试 (`tests/integration/test_api_integration.py`)。

---

## 3. 重构质量评估

总体来看**重构是有方向、有节奏的**，最近 20 个 commit 中有大量 `refactor:` / `fix:` 提交：

✅ **干净的成果**：
- `skill_system.py` (711→112 行) 拆为 4 个 mixin (`_skill_model/_skill_persistence/_skill_matching/_skill_auto`)，主类用多继承组合。re-export 保持向后兼容。（commit `3fa4750`）
- `special_elements.py` (661→117 行) 同样拆为 4 个文件 (`_elements_types/_elements_parser/_elements_tools/_elements_vision`)。（commit `3fa4750`）
- `llm_client.py` (849→267 行) 拆为 3 个 backend mixin + helpers（commit `2549b45`）。
- `features.py` 集中可选依赖探测，替代散落的 `try/except ImportError`（commit `baf738b`）。
- 路由层从单体 `api.py` 拆出 5 个 `routers/*.py`，每个 register_* 函数收闭包。
- 前端 `App.vue` 提取 AppTopBar / TranslateView / AgentPanel / EditorLayout，主 shell 仅 686 行。

⚠️ **重构不彻底的痕迹**：

- **历史死代码堆积** — PDF 双语 overlay 的 200 行 block 匹配启发式 (`routers/translate.py:145-235`) 在功能弃用后未删除；`tool_generator.py` 实现完整但未接入；`App.vue:179` 残留 `showSettings`。
- **MCP 入口与 Agent 工具入口未统一** — `mcp_server.py` 仍在用一套裸函数定义工具，没切到 `ToolRegistry`；这是 v0.1 时期的实现，重构遗漏。
- **测试与代码漂移** — `_apply_inline_format` 改名后没改测试（commit `f8e6a38` 或 `7934700` 中遗漏的细节）。
- **配置一致性** — `routers/agent.py:621 max_steps=10` 与 `:219 max_steps=6` 默认值不一致；`AgentLoop.MAX_STEPS=6` (agent.py:76) 又是第三个值。重构 max_steps 时漏改其中一处。
- **导入完整性** — `tools/registry.py` 中 `Any` 未导入但出现在注解里，是 `from __future__ import annotations` 掩盖的"半完成"重构。
- **routers/translate 仍是巨型文件** — 1043 行，包含 block 重映射、TM、glossary、SSE pipeline、配置、TM/glossary CRUD、bilingual export，应再拆 2-3 个子模块。

---

## 4. 距离生产就绪还差什么（按优先级）

### 阻塞 V1.0 发布

| # | 障碍 | 改动成本 |
|---|---|---|
| 1 | 修 `tests/unit/test_word_exporter.py:10` 失效导入（改 `_apply_inline_format` → `_apply_inline`，验证测试逻辑仍对应 `_apply_inline` 行为） | **小**（5 分钟） |
| 2 | 删除或接入 `ToolGenerator`（211 行死代码影响信任度） | **小**（删 1 个文件 / 中等：接入并加测试） |
| 3 | 统一 `max_steps` 默认值（agent.py + routers/agent.py 三处对齐到同一常量） | **小** |
| 4 | 删除 `routers/translate.py:145-235` PDF overlay 死代码并清理相关 import | **小** |
| 5 | 修 `routers/translate.py:1017` `runtime_dir` → `data_root`，对齐 cloud-only 模式 | **小** |
| 6 | 前端 `useTranslate.ts:381` 移除已被忽略的 `mode/format` 字段，清理 jsdoc | **小** |
| 7 | 给 `routers/` 添加最低限度的单测（每个模块至少 1 个 happy path + 1 个错误路径） | **中** |

### 阻碍长期可维护性

| # | 障碍 | 改动成本 |
|---|---|---|
| 8 | `mcp_server.py` 重写为基于 `ToolRegistry` —— 把 16 个 `_xxx` 函数替换成对 `ToolRegistry.execute(name, args)` 的代理，省 ~400 行重复代码 | **中** |
| 9 | 拆分 `routers/translate.py` 1043 行（建议拆出 `_block_overlay_helpers.py`、`tm_glossary.py` 子路由） | **中** |
| 10 | 拆分 `cleaner/pipeline.py` 861 行（按"水印/连字符/段落/页码/引用区检测"分文件） | **中** |
| 11 | `routers/agent.py:35-39` `_V2_TOOL_WHITELIST` 与 `tool_registry.list_tools()` 自动同步，或改为黑名单 | **小** |
| 12 | `editor.py` 路由互调改为提取私有 helper（`_analyze_image_helper`） | **小** |
| 13 | 前端测试扩面 —— 至少给 `useAgentChat`、`useMindMap`、`useEditorIO` 加单测 | **中** |
| 14 | `mcp_server.py:33-38` 删除 `D:\env\anaconda` 硬编码 fallback | **小** |

### 安全 & 鲁棒性收尾

| # | 障碍 | 改动成本 |
|---|---|---|
| 15 | abort/error 路径补 `_finalize_trajectory`，让失败案例进入 memory 学习 | **小** |
| 16 | `parallel_runner.py:38-48` 与 `cloud_client.py` 重试机制合并（避免双层退避） | **中** |
| 17 | `api_factory.py:48-57` bundled glossary 拷贝逻辑去掉 `_is_frozen()` 守卫，开发模式同样初始化 | **小** |
| 18 | rate limiter 改为 Redis-backed（如未来横向扩展），或文档显式声明仅支持单进程 | **小（文档）/ 大（实现）** |
| 19 | session 持久化到 SQLite 已就绪，但 `AgentSession.resume` 测试覆盖应加强（当前主要靠 `tests/integration/test_session_resume.py`） | **中** |

### 已具备生产质量的子系统（可不动）

- 翻译管道核心算法（17 阶段清洗 + 3 种 chunk 策略 + TM + 术语表 + 并行）
- SecurityGate（命令黑/白名单分级）
- 错误分类 + 自动恢复策略（`error_classifier.py`，14 种错误类型）
- Hook 系统（16 个生命周期点，sync/async 兼容）
- LLM client 三后端抽象 + 流式标准化
- Tauri 进程管理 + 端口探活 + proxy 清理 + 健康监测
- 路由 factory 模式 + features.py 可选依赖检测

---

## 评分汇总表

| 子系统 | 分数 |
|---|---|
| 翻译管道 | 4.5/5 |
| Agent / AWA | 3.5/5 |
| 后端 API | 4/5 |
| 前端 SSE | 4/5 |
| Tauri | 4/5 |
| 配置 / 安全 | 4/5 |
| 测试覆盖 | 3/5 |
| **加权综合** | **3.9/5** |

## Top 5 待解决问题

1. **[P0] 测试套件无法运行** —— `tests/unit/test_word_exporter.py:10` 导入已删除符号，让 `pytest tests/unit/` 全量 collection 失败。
2. **[P1] 211 行死类 ToolGenerator** —— `python/src/agent/tool_generator.py` 实现完整但全仓零引用。
3. **[P1] mcp_server.py 与 tools/registry.py 严重重复** —— 16 个工具函数双写，安全/Hook/错误分类逻辑只在一边。
4. **[P1] max_steps 默认值三处不一致** —— `agent.py:76 = 6`、`routers/agent.py:219 = 6`、`routers/agent.py:621 = 10`；前端展示与运行时偏离。
5. **[P2] PDF 双语 overlay 死代码 200 行** —— `routers/translate.py:145-235` 在 commit `4360197` 弃用 PDF 后未清理。
