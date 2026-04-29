# Scholar Assistant 代码评审 — REVIEW_CURRENT.md

评审日期：2026-04-29  
评审分支：`fix/review-current-p0-p2-residual-issues`  
最近提交：`398d255 docs: update README and CLAUDE.md`

> 本报告完全基于当前工作树代码（**未参考任何历史评审文档**），所有结论锚定到具体文件 / 行号。

---

## 0. 全局画像

| 维度 | 数据 |
|------|------|
| Python 源码 | 84 模块 / 19,611 行（不含 tests） |
| Python 测试 | 40 单元 + 8 集成 = 48 文件 / 10,019 行 |
| 前端源码 (`src/`) | 38 ts/vue / 14,394 行 |
| Tauri Rust (`src-tauri/src/main.rs`) | 1 文件 / 385 行 |
| 三套配置文件 | `config/default.yaml`（仓库默认）/ `python/config/default.yaml`（运行时副本，gitignored）/ `python/config/default.local.yaml`（用户覆盖，gitignored） |
| 测试结果 | 前端：98/98 ✅；后端：727 通过、**11 失败**、5 跳过 |

---

## 1. 当前工程健康度

| 子系统 | 评分 | 关键依据 |
|--------|------|----------|
| 翻译管道 | **4 / 5** | 17 阶清洗、3 切块策略、TM+Glossary 联动、并行 runner、21 provider 预设；问题集中在重复 import 和退化路径 |
| Agent / AWA 系统 | **3 / 5** | 模块极其完整（37 个文件），但有大段已实现却未接入的死代码（ContextCompressor）、resume 反序列化丢失 `tool_calls`、SecurityGate 与 shell_exec 双层白名单 |
| 后端 API 层 | **3.5 / 5** | `api_factory.create_app()` + 5 routers 工厂模式干净；但版本字符串 4 处不一致、output reaper 定义后未启动、HTTP boilerplate 重复 4 处 |
| 前端状态 / SSE | **4 / 5** | 共享 `streamReader.ts`、所有大型 composable 都做成 module-level singleton，重连逻辑健壮；`useAgentChat` 中 `sendMessage`/`resumeSession` 事件分发逻辑高度重复 |
| Tauri 进程管理 | **4 / 5** | kill_tree、proxy 环境变量隔离、健康监控线程幂等；唯一注意点是 `restart_backend` 没有 emit「ready」事件，前端只能轮询 |
| 配置与安全 | **3 / 5** | 路径黑名单分层合理、CORS 白名单收敛、本机限制；但 `default.yaml` 实际持有真实 API Key（gitignore 保护，仍属潜在泄漏面）、v2 SSE chat 端点未做 localhost 收敛 |
| 测试覆盖率 | **3 / 5** | 测试文件齐备，覆盖面广；但 11 条用例与实际代码失同步，且 sentence-transformers 路径用 `assert` 而非 `pytest.skip` |

---

## 2. 现存问题清单

> 严重程度：🔴 阻塞 / 🟠 影响功能 / 🟡 可观察 / 🔵 清理项

### 🔴 阻塞类（必须修复）

1. **`/api/health` 与 `create_app(version=...)` 版本不一致**  
   `python/api_factory.py:281` 设为 `version="0.3.1"`，  
   `python/routers/translate.py:133` 返回 `{"version": "0.4.2"}`。  
   叠加 `package.json:3` 为 `0.2.0`、`src-tauri/Cargo.toml:3` 与 `tauri.conf.json:4` 均为 `0.3.1`，全仓共 4 个版本号、3 个不同值。客户端无法判断到底跑的是哪一版。

2. **`AgentSession` 持久化丢失 `tool_calls`，resume 后消息序列断裂**  
   `python/src/agent/session_store.py:217-224` 序列化时只写 `role / content / tool_call_id`，  
   `python/src/agent/session_store.py:240-249` 反序列化也只恢复这三字。  
   云端 Anthropic / OpenAI 的 `assistant→tool_call→tool_result` 三联约束被破坏，重启后 `resume` 走云端会复现历史上 `2486f0b` 修过的 400 错误。

3. **测试套件 11 条失败（与生产代码失同步）**  
   - `tests/unit/test_router_registration.py:55,101,126` 断言 `/api/translate/upload`、`/api/edit/ai`、`/api/mindmap/trees` 等路由——这些名字在当前路由层根本不存在；  
   - `tests/unit/test_agent_v2_router.py:85,90,96` 从 `routers.agent` import `_V2_TOOL_WHITELIST`——同样不存在；  
   - `tests/unit/test_word_exporter.py:115` 调用 `markdown_to_docx(..., page_width=6.0)`，但 `python/src/formatter/word_exporter.py:199` 签名根本没有这个 kwarg；  
   - `tests/unit/test_translation_memory.py:113` `assert hit.match_type == "fuzzy"`，但 sentence-transformers 缺失时本应跳过；  
   - `tests/unit/test_parallel_runner.py:138` `assert results[2].error is None`，但 `parallel_runner._translate_one` 不再做内部重试（注释见 `python/src/translator/parallel_runner.py:38-41`）。

### 🟠 影响功能

4. **`editor._start_output_reaper()` 永不启动 — DOCX 输出文件无限累积**  
   `python/routers/editor.py:107-111` 定义了清理任务，但全文件没有任何位置调用 `_start_output_reaper()`；只有 `_cancel_output_reaper`（`:113-117`）被注册到 shutdown。`python/data/output/` 中已经留有 10 个旧的 `*_bilingual.pdf/.docx`（评审时直接观察到）。

5. **`/api/agent/v2/chat` 未做 localhost 限制，但 abort/approve/sessions/resume/undo/tool 都做了**  
   一致性破坏发生在 `python/routers/agent.py:238-337` —— 同模块其余 6 个端点（`:340-365, :367, :416, :523, :628`）全部以 `if request.client.host not in ("127.0.0.1", "::1", "localhost"): raise 403` 起手；唯独 `v2_chat` 缺这层。任何能到 18088 端口的 IP 都能打开新 session。

6. **`python/config/default.yaml` 内嵌真实 DeepSeek API Key**  
   `python/config/default.yaml` 第 4 行包含 `api_key: sk-ea31fdfae3d64133bf1f7412d980d8c9`。该文件被 `.gitignore` 第 38 行覆盖（`python/config/default.yaml`），但：  
   ① `git add -f` 仍可上库；② 任何 PyInstaller 打包脚本若不区分 bundled 与 runtime config 都会把它带进发行包。建议改为强制从 `default.local.yaml` 注入，且在 `_save_config` 写入前强制检查 `cloud.api_key` 是否在白名单字段中。

7. **`AgentLoop` 接受 `context_compressor` 参数但永不使用 — `ContextCompressor` 是 404 行死代码**  
   `python/src/agent/agent.py:167` 形参 `context_compressor: Any | None = None`；  
   `python/src/agent/__init__.py:21,44` 重新导出；  
   `python/src/agent/context_compressor.py` 整 404 行 + 287 行测试 (`tests/unit/test_context_compressor.py`)；  
   但生产代码路径仍走 `agent.py:87 _trim_messages`（滑动窗口）。两套实现并存，文档（`__init__.py:5`）宣称已替换。

### 🟡 可观察问题（功能没坏，但容易踩坑）

8. **`/api/export/bilingual_pdf` 实际生成 docx**  
   `python/routers/translate.py:732-761` 路由名带 `pdf`，函数体调 `markdown_to_docx`，返回 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`；  
   `src/composables/useTranslate.ts:373-399` 函数命名 `exportBilingualPdf` 但保存为 `.docx`。命名与产物背离，`d7d3c7d` 与 `4360197` 提交说明确认 PDF overlay 已弃用，但端点未改名。

9. **mindmap LLM 调用通过临时改 `client.system_prompt` 复用 CloudClient.translate**  
   `python/routers/mindmap.py:47-62` 直接 `client.system_prompt = system_prompt; await asyncio.to_thread(client.translate, user_prompt)`。这是把翻译客户端当 chat 通道用，且依赖未文档化的内部字段（`_chunk_index`、`_prev_translation`）。如果未来 `CloudClient.translate` 重构掉这两个字段就会报错。

10. **`_validate_file_path` 与 `WorkspaceEnv.resolve` 与 `SecurityGate` 三套独立的"沙箱"**  
    - `python/api_factory.py:222-273`（`_validate_file_path`） — 用于 `/api/translate/path`、editor 文件读写  
    - `python/src/agent/workspace.py:57-75`（`WorkspaceEnv.resolve`） — 用于 AWA v2 工具  
    - `python/src/agent/security_gate.py:108-198`（`SecurityGate.classify`） — 用于命令/工具风险分级  
    它们互不知道对方的规则，同一个路径在三处可能给出不同判定。日后扩出"Roaming 但允许 X 子目录"之类例外时容易顾此失彼。

11. **`/api/edit`、`/api/complete`、`/api/compliance` 各自手写一份 httpx + httpx 流式分支**  
    `python/routers/editor.py:168-254` `_edit_stream_cloud/_edit_stream_ollama`，`:256-319` `complete_text`，`:468-514` `_call_cloud/_call_ollama`，逻辑高度重复且互不复用 `LLMClient`（已经在 `src/agent/llm_client.py:51` 实现了同源能力）。

12. **`useAgentChat.handleEvent` 在 `sendMessage` 与 `resumeSession` 中重复实现两份**  
    `src/composables/useAgentChat.ts:71-162` vs `:295-341`，处理同一组 SSE 事件，但 resume 路径没处理 `task_started/task_done/thought/tool_call/tool_result/token/warning`。任何加新事件都得改两处。

13. **`messages_to_anthropic` 与 `routers/agent.py` 的 reminder system_prompt 拼接重复 5 处**  
    `python/routers/editor.py:135-138` `prompts.loader.render_edit_*`、`python/routers/agent.py:198-207` `auto_processor.enrich_system_prompt`、`python/src/agent/agent.py:383-398` `_build_messages` 各自维护一套 system prompt 注入策略；增减 prompt 段时需要同步多处。

14. **`mindmap.json` 跟踪入库**  
    `git ls-files python/mindmap.json` 显示其在 git 中，且当前工作树修改未提交。它是用户运行时数据（`python/routers/mindmap.py:35` 的 persistence target），不应该跟踪——首次启动后 `git status` 永远 dirty。

15. **`python/output/`、`python/runtime/`、`python/tests/tm.db` 等运行时产物未 gitignore**  
    `python/output/` 含 10 个用户翻译产物 PDF/DOCX、`python/runtime/{agent,data}/` 含 SQLite DB 和 ChromaDB。当前 `.gitignore` 只覆盖 `python/data/agent/` 与 `python/tm.db*`，对 `python/output/`、`python/runtime/` 视而不见。

### 🔵 清理项

16. **`python/main.py` 已 gitignore（注释见 `.gitignore`），但仓内不存在该文件**  
    `.gitignore:67` 仍保留。

17. **Glossary 与 TM 对独立链路触发但 RAG ingest 异步 fire-and-forget**  
    `python/routers/translate.py:515-528` `asyncio.create_task(_bg_ingest())`，`asyncio.create_task` 的返回值被丢弃，pytest 与 mypy 都会报 unawaited task 警告（这个 lint 没启）。

18. **Agent 工具数量爆炸 — `create_default_registry` 逐个 `registry.register(...)` 21 次**  
    `python/src/agent/tools/registry.py:36-540`：500 行的工厂函数，工具与配置耦合；新增工具需直接编辑该函数。后续可考虑装饰器自动注册。

19. **死分支 / 注释过期**  
    - `python/src/agent/tools/atomic_tools.py:92` `sandbox_cmds = {"touch", "mkdir", "cp", "mv", "rm", "rmdir"}` 同时含 `rm/rmdir`，但 `:87-89` 的白名单检查会先把 `rm/rmdir` 拦下，永远走不到这个 `sandbox_cmds` 分支。  
    - `python/api_factory.py:67-68` `MAX_TASKS = 10`、`MAX_UPLOAD_SIZE = 200 * 1024 * 1024` 与 `python/routers/translate.py:36-37` 同名常量重复定义。translate 路由真正使用的是 `routers/translate.py` 副本，`api_factory.py` 的两个常量是死代码。

20. **`api_factory._unhandled_exception_handler` 直接把 `exc` 字符串塞进响应体**  
    `python/api_factory.py:283-289` `f"服务器内部错误: {exc}"`。生产环境会把内部 trace 文本（路径、主机名、键名）泄漏到客户端。仅记录日志、对外返回固定文案更安全。

---

## 3. 重构质量评估

> 项目存在多次大型重构（commit `3fa4750`、`baf738b`、`ad7c0e7`、`d0e76f9`），整体走在「split monolith → mixin / router / sub-package」的方向上。但留下了若干「半步」的痕迹：

| 现象 | 证据 |
|------|------|
| **新旧两套上下文管理并存** | `agent.py:87 _trim_messages`（旧滑动窗口，活跃）↔ `context_compressor.py:53 ContextCompressor`（新比例阈值，未接） |
| **路由命名与测试断言已脱钩** | `routers/translate.py:171` 用 `/api/translate`，`tests/unit/test_router_registration.py:55` 仍断言 `/api/translate/upload` |
| **同一动作三套实现** | LLM 文本流式：`editor._edit_stream_cloud` / `editor._call_cloud` / `agent/llm_client._stream_cloud` 互不复用 |
| **路由名遗留旧含义** | `/api/export/bilingual_pdf` 实际产出 docx；前端函数名也叫 `exportBilingualPdf` |
| **Phase 数字泄漏到注释** | `routers/agent.py:142,172` 注释含 "Phase 4 / AWA v2" 等开发期阶段字段——应是 PR 描述用语，不应在代码里固化 |
| **persistence layer 同名目录两份** | `python/data/agent/` 与 `python/runtime/agent/` 都有 `memory.db / sessions.db`，无明确文档说明哪个是"主"；从 `api_factory.py:327 data_root = RUNTIME_DIR / "data"` 看应是前者，后者是测试或旧版残留 |
| **`PluginRegistry` 与 `ToolRegistry` 双注册** | `routers/agent.py:319-322` 走 plugin，`agent/tools/registry.py:36` 走 ToolRegistry；当前两者覆盖范围不对称（plugin 没有 AWA v2 工具，ToolRegistry 没有 MCP 路由），且都自称"内置工具集" |
| **`_V2_TOOL_WHITELIST` 等被删但测试未跟随** | `tests/unit/test_agent_v2_router.py:85-98` 的 import 失败说明该常量在某次提交（看 `5f99851 step-limit summary` 之前）被移除，未补 test 删除/更新 |

整体感觉：**Agent 子系统是重构「最不彻底」的部分**——文档（`agent/__init__.py`）与代码现状有落差；翻译管道与 router 工厂模式则**已基本收敛**。

---

## 4. 距离生产就绪还差什么（V1.0 阻塞列表）

按优先级排列：

| # | 事项 | 成本 | 锚点 |
|---|------|------|------|
| **1** | 修复 11 条失败的单元测试，使测试套件回到 100% 绿 | **小** | 见 §2.3 |
| **2** | 统一全仓版本号；让 `/api/health` 从 `__version__` 单一来源读取 | **小** | `api_factory.py:281`、`routers/translate.py:133`、`package.json:3`、`Cargo.toml:3`、`tauri.conf.json:4` |
| **3** | 启动 `_start_output_reaper`（或直接删除该未使用的清理逻辑改用 `tempfile.TemporaryDirectory` 模式） | **小** | `routers/editor.py:107-117` |
| **4** | 给 `/api/agent/v2/chat` 加上与其他 v2 端点一致的 localhost 校验 | **小** | `routers/agent.py:238` |
| **5** | 把 `default.yaml` 中的 `api_key` 字段强制清空，让 key 只能从 `default.local.yaml` 或 `SCHOLAR_CLOUD_API_KEY` 注入；同时在 `_save_config` 拒绝写入非空 `api_key` | **中** | `api_factory.py:188-194`、`python/config/default.yaml` |
| **6** | 修复 SessionStore 序列化丢 `tool_calls` 问题，否则 cloud + Anthropic provider 的 resume 必坏 | **中** | `session_store.py:217-249` |
| **7** | 决策：删除 `ContextCompressor` 或把它接入 `AgentLoop.step` 替换 `_trim_messages` | **中** | `agent.py:87,167-260`、`context_compressor.py` |
| **8** | 重命名 `/api/export/bilingual_pdf` → `/api/export/bilingual_docx`，前端 `exportBilingualPdf` 同改 | **小** | `routers/translate.py:732`、`useTranslate.ts:373` |
| **9** | 抽出共享 `LLMTextClient` 接口替换 `editor.py` 4 处 httpx 重复 boilerplate | **中** | `routers/editor.py:168-514` |
| **10** | 合并 `useAgentChat.handleEvent` 两份事件分发 | **小** | `useAgentChat.ts:71-162, 295-341` |
| **11** | gitignore 收口：`python/output/`、`python/runtime/`、`python/tests/tm.db*`、`python/mindmap.json` | **小** | `.gitignore` |
| **12** | 路径校验三层（`_validate_file_path` / `WorkspaceEnv` / `SecurityGate`）合并到一个有清晰策略对象的模块；至少先写一份「这三个分别管什么」的内部文档 | **大** | §2.10 |
| **13** | 测试与代码同步策略：把 `tests/unit/test_*registration*.py` 的 hard-coded 路由列表改为从 `app.routes` 反向断言"必须包含的关键路径前缀"，避免重命名时大批失败 | **中** | `test_router_registration.py` |
| **14** | 全局异常处理器去除 `f"服务器内部错误: {exc}"`，避免泄漏 | **小** | `api_factory.py:283-289` |
| **15** | 文档：CLAUDE.md 已经是最新；但 `agent/__init__.py:5` 等仍宣称 "ContextCompressor 取代滑动窗口"——与现实不符，需修正 | **小** | `agent/__init__.py:1-50` |
| **16** | 更长期：`PluginRegistry` 与 `ToolRegistry` 二选一，避免功能漂移到不同的 registry 中 | **大** | `plugin/registry.py`、`agent/tools/registry.py` |

发布前**至少**要做完 1–8（多数是「小」成本）和 11、14。9、10、12、13、15 是质量改善项；16 是架构性投资，可以放到 V1.1。

---

## 附录：评分汇总（终端打印用）

```
+------------------+--------+
| 子系统           | 评分   |
+------------------+--------+
| 翻译管道         |  4 / 5 |
| Agent / AWA      |  3 / 5 |
| 后端 API 层      |  3.5/5 |
| 前端状态 / SSE   |  4 / 5 |
| Tauri 进程管理   |  4 / 5 |
| 配置与安全       |  3 / 5 |
| 测试覆盖率       |  3 / 5 |
+------------------+--------+
```

## 附录：Top 5 待解决问题

```
1. [🔴 阻塞] 全仓 4 处版本号不一致（api_factory.py:281 / translate.py:133 /
              package.json / Cargo.toml / tauri.conf.json）
2. [🔴 阻塞] SessionStore.serialize_session 丢失 tool_calls，
              session resume 在 cloud/Anthropic provider 上必坏
              (session_store.py:217-249)
3. [🔴 阻塞] 11 条单元测试与生产代码失同步（router 路径、_V2_TOOL_WHITELIST、
              page_width、TM fuzzy、parallel retry）
4. [🟠 功能] editor._start_output_reaper 永不启动，docx 文件无限累积
              (routers/editor.py:107)
5. [🟠 安全] /api/agent/v2/chat 未做 localhost 校验，与同模块其余
              v2 端点不一致 (routers/agent.py:238)
```
