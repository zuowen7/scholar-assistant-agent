# REVIEW_CURRENT.md — 代码库现状评审

> 评审基准：当前 working tree（main 分支，最新 commit `1dcb684`）  
> 评审范围：完整源码（Python 后端 ~20.6k 行 + 前端 Vue/TS ~14.4k 行 + Tauri Rust ~385 行 + 测试 ~9.6k 行）  
> 方法：直接读取源代码，未参考任何历史评审/规划文档

---

## 0. 评分汇总

| 子系统 | 评分 | 一句话理由 |
|---|---|---|
| 翻译管道（parser/cleaner/chunker/translator/formatter） | **3 / 5** | 功能完整、链路清晰；但 `_helpers.py` 抽取**没有完成**，`ollama_client.py` 仍保留全部重复实现，并存在两个同名 `TranslationResult` 类。 |
| Agent / AWA 系统（python/src/agent/ ~25 个模块、~9.5k 行） | **2.5 / 5** | 架构层次野心很大（AgentLoop / AgentSession / SecurityGate / MemoryManager / SkillRegistry / ChangeJournal …）；`tools.py` 单文件 1957 行已成怪兽，路径解析/沙箱有两套并存（`_save_file` vs `_write_file_v2`），`AgentLoop.run()` 与 `AgentSession.drive()` 是两套并行实现，配套测试覆盖薄弱。 |
| 后端 API 层（api_factory + 5 个 routers） | **3.5 / 5** | `api_factory.create_app()` 重构干净（工厂模式 + 闭包注入 + 双入口 `api.py` / `api_cloud.py`），不过 `routers/translate.py` 单文件 804 行、`routers/editor.py` 721 行仍偏大，`/api/chat` 直接 forward 到 v2，留下 `/api/chat/v1` legacy。 |
| 前端状态管理与 SSE | **3.5 / 5** | 真单例 + 共享 `streamReader` 思路清晰；`EditorLayout.vue` 1319 行、`useEditor.ts` 802 行已偏厚；`API_BASE` 检测/重连/类型定义都到位。 |
| Tauri 进程管理 | **4 / 5** | 进程树终结、proxy env 清理、健康监控、单实例锁、热重启都做好了；权限文件膨胀但每条都有据可查。 |
| 配置与安全 | **2 / 5** | **真实 DeepSeek API Key 写入了仓库内的 `python/config/default.yaml` 与 `default.local.yaml` 两份**（被 `.gitignore` 救下未推到远端，但本地工作树仍长期存放明文密钥）；`python/data/agent/memory.db` 与 `python/data/argument_tree.json` 等运行时产物**已被 `git add` 入库**。 |
| 测试覆盖 | **3 / 5** | 单元 39 个、集成 6 个、~9.6k 行、~860 个 test 函数，规模可观；但翻译核心 `_helpers.py` 与 `ollama_client.py` 共存的两套实现没人验证一致性，`api_factory.py` 没有单元测试，`tools.py` 中 1957 行只对应少量集成测试。 |

> 加权综合（按对生产风险的影响）：约 **3.0 / 5**。距离 V1.0 还有明确阻塞项（重构未完成、密钥/二进制入库、Agent 层稳定度），但翻译流水线 + 桌面壳 + 前端骨架已经可用。

---

## 1. 当前工程健康度（详细）

### 1.1 翻译管道 — 3 / 5

**优点**

- `routers/translate.py:239-536` 的 `_run_pipeline` 把"解析→清洗→切块→翻译→格式化"5 步用 SSE 串得很清晰，事件名 `progress / parsed / cleaned / chunked / chunk_done / chunk_tm_hit / glossary_violation / complete / error` 一致。
- `parser/dispatcher.py` 用 `@_register` 装饰器维护了 16 种格式（`SUPPORTED_EXTENSIONS` at `parser/dispatcher.py:23-41`），扩展性好。
- `chunker/splitter.py` 分 sentence/paragraph/fixed 三策略，有 `syntax_splitter._split_long_sentence` 兜底。
- 云端客户端用了**模块级 rate limiter**（`cloud_client.py:46-64` 的 `_ProviderRateLimiter`），跨 `CloudClient` 实例稳定生效。
- TM (`memory_store.py` 301 行 / SQLite) + Glossary (`glossary_store.py` 410 行) 是真东西，前端 `/api/tm/*` `/api/glossary/*` 路由都接好了。

**问题**

- **`_helpers.py` 抽取没做完**（详见 §3 第 1 条）。
- `OllamaClient.translate_async` (`ollama_client.py:475-531`) 与同步 `translate` (`ollama_client.py:166-212`) 的 prompt 构建/post-processing 各写了一遍，`_call_api` (`ollama_client.py:239-350`) 与 `_call_api_async` (`ollama_client.py:374-461`) 也是两份高度雷同的代码。
- `cleaner/pipeline.py` 单文件 798 行，17 道清洗工序硬串在 `clean_text_full` 里，没有可独立测试的 stage 抽象。

### 1.2 Agent / AWA 系统 — 2.5 / 5

**架构清单（python/src/agent/）**

| 模块 | 行数 | 作用 |
|---|---|---|
| `agent.py` | 661 | `AgentLoop`：ReAct 主循环（`run()` + `step()` 两套入口） |
| `session.py` | 598 | `AgentSession`：状态机 + 任务队列 + 审批 + checkpoint，调用 `step()` 而非 `run()` |
| `tools.py` | **1957** | `ToolRegistry` + 全部工具实现（旧沙箱版 + AWA v2 工作区版混在一起） |
| `llm_client.py` | 849 | 三后端 LLM 抽象（Ollama / OpenAI 兼容 / Anthropic） |
| `skill_system.py` | 711 | SKILL.md 沉淀 + nudge |
| `mcp_server.py` | 664 | MCP 服务端 |
| `special_elements.py` | 661 | 特殊元素（公式/表格…）工具 |
| `context_compressor.py` | 404 | 上下文压缩 |
| `memory.py` | 365 | MEMORY.md + SQLite 记忆 |
| `trajectory.py` | 340 | 轨迹回放 |
| `error_classifier.py` | 316 | 错误分类 + 重试 |
| `auto_processor.py` | 305 | 自动处理 |
| `bash_session.py` | 279 | 持久 BashSession |
| `session_store.py` | 266 | SQLite 会话持久化 |
| `security_gate.py` | 263 | 工具审批门控 |
| `prompt_builder.py` | 261 | 系统提示词构建 |
| `review_agent.py` | 247 | 审计 Agent |
| `change_journal.py` | 197 | 文件变更日志 + undo |
| `models.py` | 192 | 数据模型 + Event 常量 |
| `hooks.py` | 180 | Hook 总线 |
| `workspace.py` | 122 | 工作区沙箱 |

**优点**

- `models.py` 把 `Message / ToolCall / AgentEvent / SessionState` 集中定义，事件常量 (`EVT_*`) 命名整齐。
- `AgentSession.drive()` (`session.py:112-225`) 与 `_drive_task()` (`session.py:226-430`) 把状态机/审批/串并行执行编排得相对清楚。
- `ChangeJournal` + `undo_last_change` (`tools.py:846-871`) + `WorkspaceEnv` 构成的 AWA v2 思路是真本事，已经能用。
- `SecurityGate.classify` 三档 + `auto_approve` 模式让 v2 可以零配置跑得起来。

**问题**

- **新旧两套 ReAct 循环并存**：`AgentLoop.run()` (`agent.py:316-486`) 是历史 v1 入口，被 `routers/agent.py:233 /api/chat/v1` 直连；`AgentLoop.step()` (`agent.py:204-314`) + `AgentSession.drive()` 才是 v2 主线。`/api/chat` 现已 forward 到 v2 (`routers/agent.py:227-230`)，但 v1 仍在运行、仍在测试 (`test_agent_v2_router.py`、`test_agent_dual_engine.py`)。两套都要维护。
- **`tools.py` 1957 行**单文件，含：
  - 沙箱版 `_save_file/_read_file` (`tools.py:523-558`)
  - AWA v2 版 `_read_file_v2/_write_file_v2/_str_replace/_undo_last_change` (`tools.py:568-871`)
  - LLM 包装工具 `polish/summarize/outline/expand/format_bibliography`
  - 占位实现 `_translate_text/_parse_document/_search_documents/_manage_knowledge`（被 `create_default_registry` 用闭包覆盖注入，`tools.py:400-432`、`tools.py:1415-1434`）
  - Phase 4 工具 `_shell_exec/_python_exec/_web_fetch/_web_search/_export_pdf`
  - 注册装配函数 `create_default_registry` 占了 ~500 行（`tools.py:1441-1957`）。
- `create_default_registry` 在 `workspace_root` 给定时**两次**注册同名工具（先注册沙箱版 `save_file/read_file`，然后被 v2 工具 `overwrite=True` 覆盖，`tools.py:1670-1685` vs `tools.py:1936-1951`）。
- `agent.py:194-202` 在 `AgentLoop` 中用 `@dataclass` 嵌套定义了 `StepResult`，但实例方法用 `self.StepResult(...)` 创建（line 227）— 可读性差，且把数据类塞进类里没明显收益。
- Agent 层缺一致性测试：`tests/unit/test_session.py` 14 个、`test_phase2.py` 31 个虽然名字到位，但 `_drive_task` 中的并行执行、审批超时、circuit breaker（连续 5 错）这些路径没有专门的端到端覆盖。

### 1.3 后端 API 层 — 3.5 / 5

**优点**

- `api_factory.create_app(cloud_only=)` (`api_factory.py:219-333`) 单一构造点，本地版 `api.py` 与纯云版 `api_cloud.py` 各自只剩 47 行 / 99 行 入口。
- 共享闭包注入：`load_config / save_config / build_cloud_client / mask_api_key / validate_file_path` 都从 `api_factory` 注入到各 router，不存在 router 之间相互 import 的耦合。
- `_validate_file_path` (`api_factory.py:198-213`) 简单但有效（黑名单系统目录 + 敏感扩展名 + 隐藏文件）。
- `_check_rate_limit` (`api_factory.py:74-85`) 按 IP 滑动窗口、30 RPM、in-process 实现，不引外部依赖；中间件 (`api_factory.py:245-255`) 仅对 `/api/translate /api/chat /api/rag/upload` 三条路径生效，符合设计。
- `_unhandled_exception_handler` (`api_factory.py:224-230`) 顶层兜底。

**问题**

- `routers/translate.py` 单文件 804 行：`_run_pipeline` (239-536) 把上传保存、TM 命中、并发翻译、Glossary 校验、RAG 自动入库、SSE 事件全混在一起，已经接近"上帝函数"的边界。
- `routers/editor.py` 721 行同病：编辑/补全/导出/视觉/引用/Zotero/scaffold 都塞在一起。
- `routers/translate.py:760-802` 的 `_build_block_translations` 用前缀匹配在原文-block 之间手工对位，注释也承认这是启发式（30 字符前缀），实际效果难保证；缺单测。
- `/api/chat` (`routers/agent.py:227-230`) 直接 forward 给 `v2_chat`，`/api/chat/v1` 仍在；前端如果还有调用 v1 的地方就会沉默地走旧路径。
- `routers/translate.py:75` 出现 `glossary_dir = Path(__file__).resolve().parent.parent / "data" / "translator" / "glossaries"` 这种 fallback — 跨 PyInstaller 打包/dev 模式不稳。
- `api_factory.py` 整文件**没有任何 pytest 文件**直接覆盖（只在集成测试里间接调用）。
- `_load_config` (`api_factory.py:131-147`) 缓存按 `mtime` 失效，但若用户调 `_save_config` (`api_factory.py:165-171`) 后立刻读取，写入与缓存设置都在同进程内成对，问题不大；多进程场景下 mtime 同分辨率可能出问题。

### 1.4 前端状态管理与 SSE — 3.5 / 5

**优点**

- `streamReader.ts` 47 行复用得很彻底（被 6 处 SSE 消费）。
- `useTranslate.ts` 470 行 / `useEditor.ts` 802 行 / `useFileTree.ts` 135 行都用模块级 `reactive`/`ref` 单例，符合 CLAUDE.md 描述。
- `useTranslate.ts:23-24` 给 SSE 加了 `MAX_ATTEMPTS=3 / DELAY=2000ms` 重连。
- `utils/api.ts` 仅 11 行，开发模式走 Vite 代理（避免 Tauri WebView2 的 HTTP_PROXY 坑），生产直连 18088，逻辑紧凑。
- 设计 token 系统 (`styles/tokens.css`) 与 `ui/` 原语已经成型，组件树已经从单体 App.vue 拆开。

**问题**

- `EditorLayout.vue` **1319 行**：包含 FileTree 调度、MindMap 切换、Welcome 屏、Tabs 容器、Resize handle、AI 面板、新工程向导等，已经逼近上一次拆 App.vue 之前的体量。
- `useEditor.ts` 802 行：Monaco 实例、tabs、AI 面板、ghost-text、Word/PDF 导出、Vision、Citation、Zotero、ImageUpload 都在一个 composable 里。注释列出了 7 个 response 接口（`useEditor.ts:55-105`），暗示职责膨胀。
- `App.vue` 仍有 682 行（CLAUDE.md 写的是 ~630 行）— 仍在长。
- `useAgentChat.ts` 是"普通 composable，每次 new state"（CLAUDE.md 注），但实际看 `useAgentChat.ts:10-18` 模块级 `messages / sending / ragDocuments / sessionId / pendingApproval` 都是模块级 `ref`，**也是单例**。文档与实现不一致。

### 1.5 Tauri 进程管理 — 4 / 5

- `main.rs:10-13` 用 `Mutex<Option<Child>>` 管理 python/ollama 子进程；
- `kill_tree`+`kill_child` (`main.rs:15-36`) 在 Windows 走 `taskkill /F /T /PID`，处理孤儿进程。
- `build_command` (`main.rs:53-66`) 主动 `env_remove` 6 个 proxy 变量，与 `main()` 里 (`main.rs:370-385`) 父进程清理双保险。
- 健康监控线程用 `HEALTH_MONITOR_RUNNING: AtomicBool` 防重复启动 (`main.rs:316`)，间隔从 30s 退避到 120s 也合理。
- `restart_backend` (`main.rs:163-181`) 等 `is_port_listening(18088)` 释放后再起新进程，最长 30 秒。
- 唯一小毛病：`save_file` (`main.rs:121-150`) 写文件白名单只放 `.md/.txt`，且要求 canonical parent 在 `$HOME` 内 — 但 capabilities 里 `fs:allow-write-file` 又开放到 `$HOME/**`，两层授权概念有点重叠。

### 1.6 配置与安全 — 2 / 5

- `python/config/default.yaml:3` 与 `python/config/default.local.yaml:3` 各保存了一份明文 DeepSeek API Key (`sk-cd83abedd26f4ab79899216bfe78ea70`)。两份文件都在 `.gitignore` 中（`/.gitignore:43-44` 排除 `python/config/default.yaml` 与 `python/config/*.local.yaml`），所以**未被推到 git**；但本地工作树长期保留生产密钥仍是泄露面。
- `python/data/agent/memory.db` 与 `python/data/argument_tree.json` **已被 git add**（`git ls-files` 确认），但 `.gitignore` 写了 `python/data/agent/`（line 36）和 `python/data/agent/`（line 35）— 文件在加 `.gitignore` 之前就入库了，没人 `git rm --cached`。SQLite 二进制随仓库分发是隐患（含历史对话内容、可能的私密查询）。
- `_validate_file_path` (`api_factory.py:198-213`) 黑名单仅覆盖 `/etc /proc /sys /dev /root C:\Windows C:\Program Files`，没覆盖 `~/.ssh ~/.aws ~/.config` 等用户敏感目录，也未做符号链接逃逸校验。
- CSP (`tauri.conf.json:25`) 允许 `'unsafe-inline'` + `'unsafe-eval'` — Monaco 自身需要 eval，没法立即收紧，但在 README/审查时应明确风险。
- API key 通过 `mask_api_key` (`api_factory.py:187-191`) 在 GET `/api/config` 时打码，`update_config` 又用 `is_masked` 判断保留旧值（`routers/translate.py:583-585`）— 这套逻辑正确，但前端如果 PUT 时没显式提交 key 会把空字符串覆盖（`update_glossary` 那种），需要再核 UI。

### 1.7 测试覆盖 — 3 / 5

- 单元测试 39 个文件、~6.4k 行，集成测试 6 个文件、~1.8k 行，前端测试 5 个文件、~1.2k 行。
- 翻译管道核心覆盖好：`test_translator.py` 352 行、`test_cleaner.py` 145、`test_chunker.py` 62、`test_glossary.py` 423、`test_translation_memory.py` 274、`test_parallel_runner.py` 187、`test_cloud_client.py` 296。
- Agent 层有名义覆盖但实际深度待定：`test_phase2.py` 333、`test_phase3.py` 296、`test_phase4_tools.py` 357、`test_session.py` 167、`test_session_store.py` 202、`test_security_gate.py` 253，但 1957 行的 `tools.py` + 661 行 `agent.py` 的真实覆盖率没量化。
- 缺口：
  - `api_factory.py` / `routers/translate.py` 没有 router 级单测（只有 `test_api_integration.py` 266 行的端到端）。
  - `_helpers.py` vs `ollama_client.py` 双份实现一致性没人验证。
  - `_build_block_translations` (`routers/translate.py:760-802`) 启发式没单测。
  - `tests/unit/test_translator.py:14-16` 直接 `from src.translator.ollama_client import _strip_think_tags`，测的是 `ollama_client.py` 内的 thin wrapper；如果有人改了 `_helpers.py` 真实实现而忘了改 wrapper，测试还是会过，**误导性强**。

---

## 2. 现存问题清单

> 严重度划分：🔴 P0 阻断/泄露 / 🟠 P1 严重 / 🟡 P2 中等 / 🔵 P3 整理

### 🔴 P0

1. **API key 明文落盘**  
   `python/config/default.yaml:3` 与 `python/config/default.local.yaml:3` 各存放一份真实 DeepSeek key。虽被 `.gitignore` 排除，但任何打包/快照/clone 错误都会泄露，应立即吊销该 key 并改环境变量 (`SCHOLAR_CLOUD_API_KEY` 在 `api_factory.py:160-162` 已有支持)。

2. **运行时 SQLite 入库**  
   `python/data/agent/memory.db` 与 `python/data/argument_tree.json` 被 `git ls-files` 列出，包含本地对话历史；`.gitignore` 已添加但旧文件未 `git rm --cached`。

3. **`TranslationResult` 同名两份**  
   - `python/src/translator/_helpers.py:30-34`：`@dataclass class TranslationResult: original: str = ""; translated: str = ""`
   - `python/src/translator/ollama_client.py:57-63`：`@dataclass class TranslationResult: original/translated/model/prompt_tokens/completion_tokens`  
   `python/src/formatter/renderer.py:14` 导入的是 `_helpers` 版（缺 `model/tokens` 字段），但实际传入的是 `ollama_client` 版 — 凭运行时鸭子类型才不爆。这是真的逻辑错误。

### 🟠 P1

4. **`_helpers.py` 重构不彻底**  
   `_helpers.py` 已实现 12 个共用函数，但 `ollama_client.py` 仍保留 6 个**完整重复实现**：
   - `_extract_term_pairs` (`ollama_client.py:621-644` vs `_helpers.py:41-63`)
   - `_validate_translation` (`ollama_client.py:667-756` vs `_helpers.py:170-240`)
   - `_repair_truncation` (`ollama_client.py:759-806` vs `_helpers.py:243-283`)
   - `_deduplicate_repetition` (`ollama_client.py:817-863` vs `_helpers.py:323-356`)
   - `_is_similar_sentences` 是 wrapper but `_restore_paragraphs` (`ollama_client.py:878-931` vs `_helpers.py:444-481`) 又是完整实现。  
   逻辑会逐渐发散；`cloud_client.py` 完全走 `_helpers.py`，但 `ollama_client.py` 自己用自己的版本，两条管道行为悄悄分叉。

5. **AgentLoop 的 `run()` 与 `step()/AgentSession.drive()` 双链路并存**  
   - `agent.py:316-486` 是 v1 主循环。
   - `agent.py:204-314` + `session.py:226-430` 是 v2。  
   `routers/agent.py:227-230` 已让 `/api/chat` 走 v2，但 `/api/chat/v1` (`routers/agent.py:232-273`) 仍直接调用 `agent.run()`。两条路径都要维护、都要 hook 上 SecurityGate/Memory/Skill — 边界有模糊。

6. **`tools.py` 1957 行单文件巨兽**  
   包含 5 类工具实现 + 注册工厂；`create_default_registry` (`tools.py:1441-1957`) 自身 ~500 行。改任何一个工具都要在这个文件里翻找，IDE 都开始卡。

7. **沙箱与 AWA v2 工作区双套文件 IO**  
   `_save_file/_read_file` (`tools.py:523-558`) 在 `~/scholar_agent_files`；`_read_file_v2/_write_file_v2/_str_replace/_undo_last_change` (`tools.py:568-871`) 在 `WorkspaceEnv.root`。注册时按 `workspace_root` 分支 + `overwrite=True` 覆盖（`tools.py:1670-1685`、`tools.py:1936-1951`），同名工具在不同模式下行为不同，文档没写清。

8. **根目录与 `python/` 各有一份 `main.py`，行为完全相同**  
   `D:/pycharm_study/translator/main.py` 与 `D:/pycharm_study/translator/python/main.py` 都是 166 行、`diff` 为空。其中一份是死的；`tauri.conf.json:9` 与 Rust 端 `resolve_python_dir` (`main.rs:354-368`) 都用 `python/` 下的；根 main.py 应删。

9. **根目录残留两份脚本式补丁**  
   - `_add_syntax_aware.py` (165 行)：脚本，用 `open('python/src/chunker/splitter.py').read()` 拼接字符串后 write 回去 — 一次性写 patch 用的工具，已无作用。
   - `_fix_ollama_helpers.py` (608 行)：同上，是用来生成 `_helpers.py` 的脚本（这正是上面问题 4 的来源）。  
   两份都被 `git ls-files` 列出，都不是 tests 也不是 src，是历史 patch 工具。

10. **`python/` 根有大量手动测试脚本被 git 跟踪**  
    `test_pipeline.py` (172 行) / `test_agent.py`（用户手动测试） / `_test_agent_live.py` / `manual_test_exception.py` — 不是 pytest 用例（都不在 `tests/`），但占据着 test_*.py 的命名。`server_test*.log`（4 份）在 `.gitignore` 内不会再 commit，但本地仍是工作树噪音。

11. **`/api/chat` 与 `/api/chat/v1`：v1 客户端兼容代码到底是给谁用？**  
    `useAgentChat.ts` 全部走 `/api/agent/v2/chat`，本地搜索没看到 v1 的调用方。建议直接删 `chat_v1` 函数（`routers/agent.py:232-273`）。

### 🟡 P2

12. **`OllamaClient.translate` 与 `translate_async`、`_call_api` 与 `_call_api_async` 各自一份重复 prompt 构造和 post-process**  
    `ollama_client.py:166-212` vs `:475-531`、`:239-350` vs `:374-461`，其中 prompt 构造完全相同但写两遍，post-process 列表也写两遍 (`:335-342` vs `:465-472`)。

13. **Sec：`_validate_file_path` 黑名单弱**（`api_factory.py:198-213`）  
    缺 `~/.ssh / ~/.aws / ~/.gitconfig / ~/.docker` 等用户敏感路径，未做 symlink resolve（用户传 `~/Public/link → /etc/passwd` 仍可读）。

14. **`api_factory.create_app` 未单测覆盖**  
    导致 rate limiter / config 缓存 / mask 逻辑只能在集成测试间接观察。

15. **`EditorLayout.vue` 1319 行 + `useEditor.ts` 802 行**  
    上一次 App.vue 拆分的红利正在被这两个文件吞回去。

16. **`useAgentChat.ts` 实际是单例，CLAUDE.md 说"new state per call"** — 文档与代码不符。

17. **`chunker/splitter.py:46-56` 的 `_estimate_chars_per_token` 与 `_estimate_tokens` 共存**，前者按比例返回每 token 多少字符，后者直接估 token 总数 — 两套估算函数都被引用，建议归并。

18. **`routers/translate.py:73-76`：glossary 目录有"开发期 fallback"**  
    PyInstaller 后 `Path(__file__).resolve().parent.parent` 的语义不确定，已知坑。

19. **`routers/translate.py:760-802` `_build_block_translations` 是启发式 + 没测试**  
    PDF 双语叠加导出的关键映射，靠 30 字符前缀匹配；遇到中英混排或被切两块的段落会错位。

20. **`agent.py:194-202` 把 `StepResult` 嵌套在 `AgentLoop` 内部** — 用 `self.StepResult(...)` 实例化，可读性低于普通 module-level dataclass。

21. **`tools.py:1602-1612` `summarize_text` 模板字符串错误**：  
    ```python
    prompt = (
        f"请用中文为以下文本生成摘要，不超过 {max_sentences} 个句子。"
        "提取核心论点和关键信息。\n\n{text}"   # ← 这一行非 f-string，{text} 不会被替换
    )
    ```
    实际输入 LLM 的 prompt 里 `{text}` 是字面量，文本内容根本没传进去。**真 bug**。

22. **`hooks.py` 中 `HookManager.trigger` 是异步的** (`agent.py:339, 357, 366` 直接 await)，但 `tools.py` 的 hook 触发只在 `_execute_single_tool` 进出（`agent.py:569-572, 583-586`）— `_execute_tools_parallel` (`agent.py:615-623`) 走 `_execute_single_tool` 间接触发，没问题，但若以后并行优化路径分叉得记住。

### 🔵 P3 整理

23. **`python/src/agent/skill_system_warnings.txt` 与 `python/src/constants_warnings.txt` 内容均只写 "OK"**，残留产物，但未入 git，可清理。
24. **`python/__pycache__` 被 `git ls-files` 跟踪过吗？** — 检查后未跟踪，但本地存在。
25. **`renderer.py` 注释 (`renderer.py:1-6`) 描述合并 chunk 时的优化，但 `_restore_paragraphs` 是从 `_helpers.py` 来的，并非 renderer 自己 — 注释稍有误导。**
26. **`_helpers.py:23` 仅在 `TYPE_CHECKING` 时 import `GlossaryStore`** — 但 `build_glossary_prompt` 实际 runtime 也要操作 `glossary_store.all_entries()`、`glossary_store.build_prompt_text()`；运行时全靠 duck typing，类型注解给的是字符串引用 — 现状能工作，但 mypy 会告警。
27. **CLAUDE.md 与代码已小漂移**：声明 App.vue ~630 行（实际 682）、`useAgentChat` 是非单例（实际单例）、router 列表少了 `mindmap.py`（已是 5 个 router）。

---

## 3. 重构质量评估

### 3.1 已完成的重构（亮点）

- **App.vue 拆分**：成功拆出 `AppTopBar / TranslateView / EditorLayout / AgentPanel / MindMapView` + `ui/` 原语，token 化 (`styles/tokens.css`) 也到位。
- **API 工厂模式**：`api_factory.create_app(cloud_only=)` + 5 个 router 注册，本地/云端/Docker 三模共用同一管线，骨架很清晰。
- **`streamReader.ts` 共用**：6 处 SSE 消费方都用同一个 reader，前端不重复造 SSE 解析。
- **AWA v2 工作区**：`WorkspaceEnv` + `ChangeJournal` + `BashSession` 是个完整的、可独立运转的子系统，与旧沙箱模式有明确边界（虽然边界有副作用，见下）。
- **AgentSession 状态机**：从 `AgentLoop.run()` 流式生成器进化到可暂停/可恢复的 `AgentSession.drive()`，是真重构。

### 3.2 遗留的"半完成"痕迹（疼点）

| 痕迹 | 位置 | 表现 |
|---|---|---|
| `_helpers.py` 抽离未完工 | `python/src/translator/{ollama_client.py, _helpers.py}` | `ollama_client.py:23-38` 用 `_impl` 别名导入 12 个 helper，又在 `:621-931` 重新本地实现其中 6 个；剩下 6 个改为 `_helpers.py:N(...)` 的 thin wrapper。**没有人在 PR 里把 `_call_api` 中的本地实现替换为 `_impl` 调用就合并了**。 |
| 两份 `TranslationResult` | `_helpers.py:30-34` vs `ollama_client.py:57-63` | 字段不同；`renderer.py` 的 import 与实参类型不匹配。 |
| 双 ReAct 循环 | `agent.py:run()` (v1) vs `step()` + `session.drive()` (v2) | 两套都跑得起来；`/api/chat/v1` 直连 v1。 |
| 双套文件 IO 工具 | `tools.py:523-558` 沙箱版 vs `:568-871` v2 版 | `register` 时 `overwrite=True` 覆盖同名工具。 |
| 根 `main.py` 与 `python/main.py` 内容相同 | 项目根 vs `python/` | 167 行 / 167 行，`diff` 空。 |
| 根目录补丁脚本 `_add_syntax_aware.py / _fix_ollama_helpers.py` | 项目根 | 历史一次性 patch 工具，仍 git tracked。 |
| `python/` 散落手动 test 脚本 `test_pipeline.py / test_agent.py / _test_agent_live.py / manual_test_exception.py` | python 根 | 不在 `tests/`，不被 pytest 收集，是手工跑的。 |
| `CLAUDE.md` 与代码小漂移 | `CLAUDE.md:74-79, 89-93, 88-92` | App.vue 行数、useAgentChat 单例标注、router 数量。 |
| 配置历史泄露 | `python/config/default.yaml`、`default.local.yaml` | 两份明文 API key（已 gitignore，但本地仍在）。 |
| 残留 `*_warnings.txt` 占位文件 | `python/src/constants_warnings.txt`、`python/src/agent/skill_system_warnings.txt` | 内容仅 "OK"，无被引用。 |
| `mindmap.json`、`tm.db*` | python 根 | 运行时产物 + 数据库缓存，散落工作树。 |
| 大量根 `.md` 历史文档 | `AGENT_REFACTOR_PLAN.md / DIAGNOSIS.md / ENGINEERING_REVIEW.md / PLAN_NEW_FEATURES.md / PROJECT_REPORT.md / DECISION_MATRIX.md / STRATEGY.md` | 7 份共 ~210KB 历史规划/评审；新规划/评审应放在 `docs/` 并 prune 老的（用户亦明确要求本次评审不参考）。 |

### 3.3 评估结论

**重构质量在 65/100 分**：方向对、骨架已经搭好；但**新旧实现并存**是反复出现的问题（翻译 helper、Agent 主循环、文件 IO 工具、main.py、TranslationResult），说明每次重构上线后没安排回头清扫。这种半完成态在跨人协作或自动重构 agent 接手时容易加深分裂。

---

## 4. 距离生产就绪还差什么

> 排序：紧急/影响大 → 不紧急/影响小。改动成本：S = 半小时～几小时；M = 一两天；L = 一周量级。

### 阻断 V1.0 的硬障碍

1. **吊销并清理仓库内的 DeepSeek API key【🔴 / S】**  
   `python/config/default.yaml:3`、`default.local.yaml:3`，立即换 key，改用 `SCHOLAR_CLOUD_API_KEY` env 注入；如果 key 曾经 commit 到任何远端，必须 `git filter-repo` 清史。

2. **`git rm --cached python/data/agent/memory.db` 与 `python/data/argument_tree.json`【🔴 / S】**  
   并补一行 `python/data/argument_tree.json` 到 `.gitignore`。

3. **统一 `TranslationResult`【🔴 / S】**  
   把 `_helpers.py:30-34` 删掉；`renderer.py:14` 改 `from src.translator.ollama_client import TranslationResult`，或者干脆把 `TranslationResult` 移到一个中立 `src/translator/types.py`。

4. **完成 `_helpers.py` 抽取，让 `ollama_client.py` 的 6 个函数全部 delegate【🟠 / S-M】**  
   或者**反过来**：删除 `_helpers.py`、`cloud_client.py`/`renderer.py`/`routers/translate.py` 直接 import `ollama_client.py`。两者择一，二选一即可。无论哪种都要在测试里加一个"单一来源"断言。

5. **决定 `/api/chat/v1` 与 `AgentLoop.run()` 是删还是留【🟠 / S】**  
   推荐删；前端无引用，留着只是负债。

6. **拆分 `tools.py` 1957 行【🟠 / M】**  
   建议拆成：`tools/registry.py`（`@tool`、`ToolRegistry`、`ToolDefinition`、`_extract_schema_from_function`），`tools/builtin_lite.py`（无 workspace 时的旧沙箱版），`tools/builtin_v2.py`（AWA v2 文件 IO + git_op），`tools/web.py`（arxiv/web_fetch/web_search/_export_pdf），`tools/llm_wrappers.py`（polish/summarize/outline/expand/format_bibliography），`tools/factory.py`（`create_default_registry`）。

7. **修 `summarize_text` 的 prompt bug【🟠 / S】**  
   `tools.py:1602-1612` 把第二行字符串字面量改成 f-string，否则文本根本没传进 LLM。

8. **拆 `routers/translate.py` 与 `routers/editor.py`【🟠 / M】**  
   `_run_pipeline` 至少抽 `_translate_chunks_with_tm`、`_finalize_with_rag` 两个子函数；editor.py 把 export/vision/citation/zotero 拆成各自的子文件或子函数。

### 体验/质量级阻碍

9. **删根目录死代码【🟡 / S】**  
   `main.py`（与 `python/main.py` 重复）、`_add_syntax_aware.py`、`_fix_ollama_helpers.py`、根 `*_warnings.txt`（如果有）。

10. **挪走/删除 `python/test_pipeline.py / test_agent.py / _test_agent_live.py / manual_test_exception.py`【🟡 / S】**  
    要么进 `tests/manual/` 并补 README，要么删；目前命名诱导新人以为是 pytest 用例。

11. **`EditorLayout.vue` 拆分【🟡 / M】**  
    把 Welcome、ProjectStart、Resize、TemplatePicker 触发按钮抽成独立子组件。`useEditor.ts` 拆出 `useEditorIO.ts`（导出）、`useEditorVision.ts`、`useEditorCitation.ts`。

12. **加 `api_factory` 的单测【🟡 / S-M】**  
    rate limiter、`_load_config` 缓存、`_validate_file_path`、`_mask_api_key/_is_masked`、`_apply_env_overrides` 都是纯函数，单测成本极低、收益高。

13. **统一前端 `useAgentChat` 的"单例 vs new"【🟡 / S】**  
    要么改回真 composable（每次 new state），要么修 CLAUDE.md。

14. **PDF 双语叠加 `_build_block_translations` 加用例【🟡 / S】**  
    至少给典型 IEEE 双栏论文 + 单栏论文各加一个固定 fixture 的回归测试。

15. **`_validate_file_path` 增强【🟡 / S】**  
    把 `~/.ssh ~/.aws ~/.config ~/.docker ~/.gitconfig` 加入黑名单；用 `Path.resolve(strict=True)` + `is_relative_to` 抵御 symlink。

16. **CSP 收紧（远期）【🔵 / L】**  
    Monaco 用 `unsafe-eval` 难以避开，但 `unsafe-inline` 可改 hash/nonce 模式。

17. **CLAUDE.md 校准【🔵 / S】**  
    更新 App.vue 行数、useAgentChat 状态描述、`routers/` 数量（含 `mindmap.py`）。

18. **大量历史 `.md` 归档【🔵 / S】**  
    `AGENT_REFACTOR_PLAN.md / DIAGNOSIS.md / ENGINEERING_REVIEW.md / PLAN_NEW_FEATURES.md / PROJECT_REPORT.md / DECISION_MATRIX.md / STRATEGY.md` 总计 ~210KB；建议挪到 `docs/archive/` 并加日期前缀，避免新人误把过期方案当真。

---

## 终评

代码确实经历过多轮重构，可见的进展是真：API 工厂、SSE 流水线、AWA v2 工作区、Tauri 进程管理、设计 token、单例 composable。但**每一次大重构都遗留了"旧实现没删干净"的尾巴**，最危险的两个是：
- 翻译核心 `_helpers.py` ↔ `ollama_client.py` 的双份实现 + 两个同名 `TranslationResult` 类；
- Agent 层 v1/v2 双链路 + `tools.py` 单文件 1957 行的双套文件 IO。

加上配置目录里仍有真实 API key、运行时 SQLite 入库这类历史遗留卫生问题，目前**还谈不上"生产就绪"**。但只要花上 1～2 周专门收尾（删冗余、合并实现、收紧密钥、补 router 单测），即可把质量推过 V1.0 的发布门槛。
