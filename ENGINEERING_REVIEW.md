# Scholar Assistant 工程评审

> 评审日期: 2026-04-26
> 评审者视角: 即将接手项目的资深工程师
> 评审范围: Python 后端 + Vue 前端 + Tauri 层 + 测试 + AWA 重构方案
> 方法: 静态代码审查 + DIAGNOSIS.md / AGENT_REFACTOR_PLAN.md 对照阅读

---

## 0. 评分汇总（看一眼就知道烂在哪）

| 子系统 | 评分 | 一句话判断 |
|--------|------|-----------|
| 翻译管道 | **3.5 / 5** | 业务逻辑成熟，但锁/降级/资源管理三处脆弱，离生产差临门一脚 |
| Agent 系统 | **2.0 / 5** | 模块齐全到过剩，状态污染 + 单例 + workspace 死代码，是整个工程最大的技术债 |
| 前端状态管理 | **2.5 / 5** | 单例 + 模块级 abortController 在并发/卸载场景必崩；SSE reader 取消问题已部分修，但仍有断流 |
| Tauri 进程管理 | **2.5 / 5** | 健康检查仅触发一次、Ollama 关窗不杀、调试与发布路径分叉，分发链路缺失 |
| 配置与安全 | **3.0 / 5** | C1（key 硬编码）已修；但 `/api/agent/v2/tool` 暴露任意工具调用、无鉴权、无速率限制 |
| 测试覆盖 | **2.0 / 5** | 23 个单元测试热闹但盲区致命：并发锁、SSE 重连、chat 端点、cloud_client 全部 0 覆盖 |
| **整体（加权平均）** | **2.5 / 5** | **工程化早期向中期过渡，离 V1.0 至少 6-8 周的纯整改时间** |

---

## 1. 整体工程健康度

### 项目所处阶段：**工程化早期，远非生产就绪**

判断依据（不是凭感觉，是看代码出来的）：

1. **核心模块体量与组织失衡**：`python/src/agent/agent.py` 单文件 1961 行，`tools.py` 1865 行，`vram_manager.py` 715 行——而真正的状态机/会话管理仍混在一个 `for step in range(MAX_STEPS):` 主循环里（`agent.py:365`）。这是典型的"功能堆叠优于结构演进"的早期工程产物。
2. **路由拆分做了一半**：`api_factory.py` 已拆出 `routers/translate.py / agent.py / editor.py / argument.py`（DIAGNOSIS Q1 已动），但 `_busy_lock` 竞态（DIAGNOSIS C2）**没修**——`routers/translate.py:124-126` 的 `if not _busy_lock.locked(): await _busy_lock.acquire()` 仍然是 check-then-act 非原子。
3. **测试形式化**：23 个 unit + 3 个 integration 看似热闹，但**核心并发路径、SSE 路径、Cloud Client 全部 0 覆盖**——`test_translator.py` 只有 23 行，`test_api_integration.py` 不测 chat 端点。
4. **AWA 重构方案与现状割裂**：方案声称"Phase 1 不能开工"等待前置，但实际已经偷跑了——`workspace.py / change_journal.py / tools._str_replace / _write_file_v2 / _undo_last_change` 都已经存在并有测试（`test_workspace.py / test_str_replace.py`），只是没接进 chat 主路径。这是典型的"PR 切碎了塞进去但没整体收尾"。

### 最突出的 3 个系统性问题（跨子系统）

#### 问题 1：单例模式被滥用，并发场景必出污染

| 位置 | 问题 |
|------|------|
| `routers/agent.py:68` | `_agent_instance: AgentLoop \| None = None`，全局单例，工作区从首次 config 捕获后再不刷新（line 88: `workspace_root = agent_cfg.get("workspace_root", "")`）|
| `routers/agent.py:75-180` | `_get_agent()` 双检锁建实例后，所有用户共用同一个 `AgentLoop`，包括其内部的 `_format_error_retry`、`_token_usage`、`_http_client`、`scheduler` |
| `agent.py:312, 314-320` | `self._format_error_retry`、`self._token_usage` 在 `run()` 入口重置——两个并发 chat 请求会互相覆盖标志位和用量统计 |
| 前端 `useTranslate.ts:45`、`useEditor.ts:11-20`、`useFileTree.ts` | 三个真单例（模块级 `reactive/ref`），多 tab/HMR 场景下状态不可隔离 |
| 前端 `useEditor.ts:371` | `let abortController: AbortController \| null` 是 module 级，`aiEdit / inlineEdit / requestCompletion` 共享同一个，最后一个调用赢 |

DIAGNOSIS L3 只点了 `_format_error_retry`，这只是冰山一角。**整个 Agent 的并发模型是错的**——它假设单用户单会话，但部署时根本无法保证。

#### 问题 2：SSE 流和 abort/cancel 路径的资源回收破败

- `useTranslate.ts:174` 用 `readSseStream(reader, ...)`——好，DIAGNOSIS Q2 已抽出。但失败重试路径（`startStream(taskId, attempt + 1)`）**新建 reader 不取消旧的**，DIAGNOSIS C4 只修了一半。
- `useTranslate.ts:160`：`startStream` 递归重试时直接 `abortController = new AbortController()` **覆盖旧值**，旧 fetch 永远不会被 abort（DIAGNOSIS M6 同模式）。
- `useEditor.ts:371-422` 同样问题，`aiEdit` 和 `inlineEdit` 与 `requestCompletion` 共享 `abortController`，三者并发时旧请求的响应会污染新请求的 state（`aiResult.value`）。
- `routers/translate.py:124-126,168-170,400-413`：`_busy_lock` 的释放路径依赖前端按顺序调用 POST→GET stream。若用户上传后**不连接 SSE**（断网、关页面），锁永远不释放，整个翻译服务僵死。`/api/translate` 路径里有 `try: ... except: _busy_lock.release()`，正常路径靠 stream `_wrapped()` 的 finally——但中间这段**用户主动 abort 的窗口锁会被泄漏**。

#### 问题 3：Agent 子系统过度工程化，价值与代码量倒挂

`python/src/agent/` 共 17 个文件、~10000 行：
- **复用率低**：`vram_manager.py`（KV cache 切换）、`context_compressor.py`、`memory.py`、`skill_system.py`、`trajectory.py`、`review_agent.py`、`hooks.py`（12 个 HookPoint）、`auto_processor.py`、`special_elements.py` 同时存在，相互依赖
- **接入面窄**：实际只有 `routers/agent.py:182 /api/chat` 这一个端点在用
- **测试缺位**：`tests/unit/` 中没有专门的 hooks / trajectory / review_agent / special_elements 集成测试。`test_phase2/3/4.py` 是历史里程碑式而非回归式
- **新增的 AWA 框架（workspace + change_journal）不在主路径**：`routers/agent.py /api/chat` 完全没用 `WorkspaceEnv`，只在 `/api/agent/v2/tool` 直接暴露调用——主聊天流仍是旧 `~/scholar_agent_files` 沙箱

**新人安全修改核心逻辑需要的时间估算**：3-5 个工作日（光读 agent.py 1961 行 + tools.py 1865 行 + vram_manager.py 715 行就需要 1-2 天，再加上理解 hooks / scheduler / compressor 三方耦合）。这个数字对于一个 0.4.x 的项目来说**偏高了**。

---

## 2. 各子系统逐一评审

### 2.1 翻译管道 — **3.5 / 5**

**现状**（`routers/translate.py:192-392 _run_pipeline`）：5 步 SSE 管道（parse→clean→chunk→translate→format），每步用 `asyncio.to_thread` 包同步代码，正确避免阻塞 event loop。CloudClient (`cloud_client.py`) 支持 18 个云提供商，`PROVIDER_PRESETS` 设计干净。Glossary 提取 + 跨 chunk 注入（`cloud_client.py:267`）这种细节做得不错。

**主要问题**：

1. **`_busy_lock` 竞态未修**（`routers/translate.py:124-126`、`168-170`）
   ```python
   if _busy_lock.locked():
       raise HTTPException(409, ...)
   await _busy_lock.acquire()  # ← 与上面的 locked() 检查之间可被抢占
   ```
   DIAGNOSIS C2 早就指出，2 个月过去仍未修。**正确写法是 `if not _busy_lock.locked() and await asyncio.wait_for(_busy_lock.acquire(), 0)`**，或干脆用 `try: await asyncio.wait_for(lock.acquire(), timeout=0)` 的 try/except TimeoutError 模式。

2. **锁泄漏路径**：`/api/translate` POST 成功后立即 `await _busy_lock.acquire()`（line 126），但锁的释放 **只在** `/api/translate/{task_id}/stream` GET 的 `_wrapped()` finally（line 412）。**用户上传后不连流就锁死整个翻译服务**。需要加 task 创建时间戳 + 后台 reaper（如果 task 创建后 60s 内没被 stream，自动释放）。

3. **静默降级**（DIAGNOSIS H3，`routers/translate.py:296-311`）：翻译失败 → `result = TranslationResult(original=text, translated=text, model="")` → 继续 yield `chunk_done` 含 `fallback: true`。**前端 `useTranslate.ts:230-235` 收到了 fallback 标志并累计 `fallbackChunks`，最后 `complete` 事件下展示警告（line 245）**——所以这个问题前端已部分处理。**但后端 `task["status"] = "done"` 还是写 done，下载接口不知道翻译质量降级**。前端友好，后端契约骗人。

4. **`CloudClient` 并发隔离问题**（`cloud_client.py:222`）：`_last_request_time` 是实例字段，每次 pipeline 都 new 一个 client（`routers/translate.py:267`），所以**速率限制在新建 client 后立即失效**。多任务串行时第二个任务初始 `_last_request_time = 0.0`，立即发请求，可能触发云端 429。

**改进建议**：
- 立即修 `_busy_lock`：用 `try: await asyncio.wait_for(_busy_lock.acquire(), timeout=0); except asyncio.TimeoutError: raise HTTPException(409)`。
- 给 task 加创建时间戳，加个后台 task 做 60s 超时 reaper。
- `H3 静默降级`：`task["status"]` 改为 `"done_with_warnings"`，下载接口 response header 加 `X-Translation-Warnings: 3`。
- `CloudClient` 的 rate limiter 提到模块级（per provider+api_key 单例），用 `asyncio.Lock` + 时间戳。

---

### 2.2 Agent 系统 — **2.0 / 5**

**现状**：`AgentLoop` 实现了双策略 ReAct（Ollama native tool calling + 文本降级，`agent.py:493-616`），加上 Phase 1-4 的 `context_compressor / memory / skill_system / hooks / trajectory / review_agent` 全套配置。云端 + 本地 Ollama 的 OpenAI/Anthropic 三套接口在 `_call_llm_*` 已对齐到统一 Ollama 字典格式。

**主要问题**：

1. **状态污染（确认 DIAGNOSIS L3 仍存在）**（`agent.py:312, 314-320`）：
   - `self._format_error_retry`、`self._token_usage` 在 `run()` 入口重置
   - `routers/agent.py:68-80` 的 `_get_agent()` 是全局单例
   - **结论：两个用户同时发 `/api/chat` 必然互相污染重试标志、token 用量，并共享同一个 `_http_client`**

2. **`workspace_root` 配置错位**（`routers/agent.py:88, 114`）：
   - `workspace_root` 从 `agent_cfg.get("workspace_root", "")` 读，**只在创建 agent 单例那一次取值**
   - `ChatRequest` 已加了 `workspace_root: str | None = None`（`routers/agent.py:40`），**但 `chat()` handler 从未消费它**
   - **新增的 `WorkspaceEnv` + `ChangeJournal` + `_str_replace/_write_file_v2/_undo_last_change` 在主聊天流根本没接入**——只有 `/api/agent/v2/tool` 这个调试端点能用上

3. **`/api/agent/v2/tool` 是开放的命令注入面**（`routers/agent.py:275-299`）：
   ```python
   @app.post("/api/agent/v2/tool")
   async def v2_tool_invoke(req: V2ToolRequest):
       ...
       result = tool_def.fn(**req.args)  # 任意工具，任意参数
   ```
   - 无鉴权、无 SecurityGate、无速率限制
   - 任何能 reach 18088 端口的人可以直接触发 `_str_replace`、`_write_file_v2`，写入服务器配置文件里的 `workspace_root`（默认空 = 服务器进程 cwd）
   - 注释写"开发调试用"，但端点已注册到生产 app

4. **Plan-and-Execute 名实不符**（DIAGNOSIS 与 AWA 方案均提及，`agent.py:340-351, 824-872`）：plan 只是塞进 system message 文本，没有"当前在第几步"的状态，`MAX_STEPS = 10` (line 77) 配合 config "max_steps: 20" (`default.yaml:2`)，实际取 `agent_cfg.get("max_steps", 10)`（routers/agent.py:160）= 20。**AWA 方案 L1 说"MAX_STEPS = 10 写死"是错的**，已经被 config 覆盖。

5. **重 IO 工具上下文隔离的代码污染主循环**（`agent.py:528-591`）：63 行的 `if has_heavy: ... else: ...` 分支让主循环肿胀，`vram_manager.MultiplexingScheduler` 的 KV cache flush 跟 ReAct 步进搅在一起。AWA 方案打算把这块拆出去是对的。

6. **`AgentMemory`（`memory.py:356`）和 `MemoryManager`（`memory.py:50`）双驱动重叠**：前者写 JSONL，后者写 SQLite，**同一份对话同时存两份**（`agent.py:501-510` + `agent.py:632`）。功能重复 + 未来同步成本 = 隐患。

**改进建议**：
- 拆 `AgentLoop` 为 `LLMClient`（无状态）+ `AgentSession`（per-request 状态），删除 `_format_error_retry / _token_usage` 实例字段
- `_get_agent()` 改成 `_create_agent_per_request()` 或至少按 `workspace_root` cache
- 立即给 `/api/agent/v2/tool` 加：(a) 仅 `127.0.0.1` 白名单，(b) `workspace_root` 必填且校验存在，(c) 调用次数限制
- 删除 `AgentMemory` 类（JSONL 写入），保留 `MemoryManager` 一份
- 砍掉 `vram_manager` 的 KV cache 切换（云端模式根本用不到，本地 Ollama 也只有 8B 模型，切换收益小）

---

### 2.3 前端状态管理 — **2.5 / 5**

**现状**：3 个真单例 (`useTranslate.ts:44`、`useEditor.ts:9-20`、`useFileTree.ts`) + `useAgentChat.ts` 普通 composable。共享 `streamReader.ts` 处理 SSE（DIAGNOSIS Q2 已完成）。`useEditor.ts` 集成 Monaco + ghost text + AI inline edit + Zotero + 视觉分析等大量功能。

**主要问题**：

1. **DIAGNOSIS C4 只修了一半**：`useTranslate.ts:174` 用 `readSseStream(reader, handler)`，但**重试路径 (line 187 `await startStream(taskId, attempt+1)`) 不取消旧 reader**——`reader` 是局部变量，被新调用屏蔽，旧 reader 直到 GC 才被回收。
2. **`abortController` 模块级共享**（`useEditor.ts:371`）：`aiEdit / inlineEdit / cancelAiEdit` 都用同一个，**任何一个新调用直接覆盖旧引用**（line 459 `if (abortController) abortController.abort()` 只在 inlineEdit 里），DIAGNOSIS M6 在 useAgentChat 里识别了，但**useEditor 的同款问题没在 DIAGNOSIS 中**。
3. **`useTranslate.ts:160` 重连递归**：每次重试 `abortController = new AbortController()` 重置，旧 fetch 永远不能被外部 `reset()` 取消（line 49 `abortController.abort()` 只能取消最新一次）。
4. **`useEditor.ts:568-647` ghost text timer 与 Monaco 生命周期解耦**：DIAGNOSIS M7 已识别。`completionTimer` 是 closure 变量但 `requestCompletion()` 内部用的是 `monacoEditor.value`，编辑器销毁后 `setValue is undefined`。
5. **状态泄漏**：`crashListener` (`useTranslate.ts:46`)、`inlineDecoration` (`useEditor.ts:426`)、`ghostDecoration` (`useEditor.ts:567`) 都是闭包内的可变数组，没有任何卸载清理钩子。Vue HMR 时残留。
6. **`api.ts:7` API_BASE 容错弱**（DIAGNOSIS L4）：缺协议头只 `console.warn`，所有 fetch 仍以相对路径打出去——开发环境不会暴露，部署到子路径反向代理时会静默失败。

**改进建议**：
- 把 module 级 abortController 改成 Map：`const abortControllers = new Map<string, AbortController>()`，按 `'aiEdit' / 'inlineEdit' / 'completion'` 分桶
- 在 `streamReader.readSseStream` 内部包一层 `try/finally { reader.cancel().catch(() => {}) }`，所有调用方一次性受益
- `useTranslate.startStream` 重试前显式 `await abortController?.abort()` + `abortController = null`
- 给 ghost text/decorations 加 `onBeforeUnmount` 卸载（即便组件级，单例 composable 也应该被显式 reset）

---

### 2.4 Tauri 进程管理 — **2.5 / 5**

**现状**（`src-tauri/src/main.rs`，337 行）：用 `Mutex<Option<Child>>` 管理 Python + Ollama 子进程，启动时 spawn，窗口关闭时 kill。Windows 用 `taskkill /T` 杀进程树。`build_command()` 主动清掉 4 个 proxy 环境变量（解决 httpx 在 Windows 代理环境下卡死，CLAUDE.md 提到）。健康检查通过 TCP 端口探测。

**主要问题**：

1. **关窗只杀 Python，不杀 Ollama**（`main.rs:188-196`）：
   ```rust
   .on_window_event(|window, event| {
       if let CloseRequested = event {
           if let Some(mut child) = lock_state!(state.python).take() { kill_child(&mut child); }
           lock_state!(state.ollama).take();  // ← 只 take()，不 kill_child()
       }
   })
   ```
   Ollama 进程**永远不会被这段代码杀掉**——`take()` 把 Option 里的 Child 取出来扔了，但 Drop trait 不会自动 kill child（Rust 标准库的 `Child::drop` 是 no-op）。如果 Ollama 是被这个 app spawn 的，关闭后变成孤儿进程，下次启动时端口冲突。

2. **健康检查只触发一次**（`main.rs:285-302`）：监听线程 `if !is_port_listening { emit("backend-crashed"); break; }`。**break 后线程结束**，再次崩溃无监测。而且每次 `restart_backend` 又起新线程，多次重启后多个线程在循环（虽然每个都会 break，但若长期运行会出现意外路径）。

3. **`spawn_python_inner(app, None)` 初始化无健康检查**（`main.rs:179`）：因为 `app_handle` 传 None，`if let Some(h) = app_handle.cloned()` 分支跳过——首次启动后**没有任何崩溃监测**。只有 `restart_backend` 路径才有。

4. **dev/release 路径分叉**（`main.rs:319-331`）：dev 模式找 `python_dir/api.py` 调 `python` 解释器；release 找 `exe_dir/python-dist/api/api.exe`。**这个 `python-dist` 目录从哪来？没有 npm script、没有 tauri build hook、没有 CI 配置**。换句话说 `npx tauri build` 直接打包**会失败**，因为找不到 `api.exe`。

5. **`save_file` 写盘无锁、无校验目录权限**（`main.rs:118-130`）：只校验后缀 .md/.txt，但路径任意。在用户机器上能写到任何用户能写的地方，包括 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\` —— **如果 webview 出现 XSS（DIAGNOSIS H1 已识别），就能调 `invoke('save_file', ...)` 写自启动**。

**改进建议**：
- 关窗时也调 `kill_child(&mut child)` for Ollama
- 健康监测改为持续循环 + 指数退避，加 atomic flag 防止多线程
- 初始化路径也传 `app_handle` 进去
- 在 `save_file` 加白名单：仅允许写到用户 Documents 或 app data 目录
- 加 `npm run pack:python` script 调 PyInstaller 产出 `python-dist/`，并在 tauri.conf.json 的 `beforeBuildCommand` 里串起来

---

### 2.5 配置与安全 — **3.0 / 5**

**现状**：`api_factory._load_config()` 支持 `default.yaml + default.local.yaml + 环境变量` 三层覆盖，敏感字段通过 `_mask_api_key` 在 GET 时打码（`api_factory.py:137`）。`_validate_file_path` 拦截系统目录和 `.env/.key/.pem` 等敏感后缀（`api_factory.py:148-163`）。CORS 白名单明确（`api_factory.py:182-187`）。

**正面进展**（DIAGNOSIS C1/L1）：
- `default.yaml:49` 现在 `api_key: ''`（已清空）
- `.gitignore` 已加 `python/config/default.yaml` 和 `python/config/*.local.yaml`
- `default.local.yaml` 中是新 key（必须确认旧 key `sk-****` (已轮换) 已在 DeepSeek 控制台撤销！git history 中仍可查到）

**主要问题**：

1. **`/api/agent/v2/tool` 完全无防护**（`routers/agent.py:275`）— **这是当前最严重的安全口**。详见 2.2。
2. **`config/default.local.yaml` 仍含明文 key**：`sk-cd83abedd26f4ab79899216bfe78ea70`（DeepSeek）。git ignored 但**对所有有访问开发机的人可见**。生产部署时若误打包到 PyInstaller bundle 就泄漏。建议改用 OS keychain（`keyring` 包）或环境变量。
3. **DIAGNOSIS H1 未修**：DOMPurify `ADD_ATTR: ['onclick']` 在 `AiPanel.vue:282` 等效关闭 XSS 防护
4. **DIAGNOSIS H5 未修**：`/api/chat` ChatRequest 无字段长度限制，`history` 可塞数千条
5. **DIAGNOSIS L7**：完全没有 rate limiting，`/api/translate /api/chat /api/rag/upload` 全暴露
6. **配置 schema 缺校验**（DIAGNOSIS M3）：`yaml.safe_load` 后直接用，不规范的 `temperature: -1` 不会立即报错，运行时才崩

**改进建议**：
- **本周**：`/api/agent/v2/tool` 加 `@app.post(..., dependencies=[Depends(_local_only)])`，校验 `request.client.host == '127.0.0.1'`
- 用 Pydantic 给 ChatRequest / V2ToolRequest 字段加 `max_length` 和 `Field(..., max_items=N)`
- 加 `slowapi` 中间件做粗粒度速率限制
- 把 `system_prompt` 从 yaml 移到 `python/prompts/*.md`（DIAGNOSIS Q5）

---

### 2.6 测试覆盖 — **2.0 / 5**

**现状**：23 个 unit + 3 个 integration 测试文件，~5500 LOC 测试代码（看 `wc -l` 输出）。

**已覆盖路径**：
- 单模块基础逻辑：parser、cleaner、chunker、formatter、word_exporter
- Agent 子模块：context_compressor、prompt_builder、auto_processor、special_elements、change_journal、workspace、str_replace、phase2/3/4 各阶段产物
- Edge cases：`test_edge_cases.py`、`test_exception_handler.py`
- Vision：`test_mcp_vision.py`
- 集成：`test_agent_integration.py`（601 行，最大）—— 但用 mock LLM，不真跑

**致命盲区**：

| 缺失测试 | 影响 | 风险等级 |
|---------|------|---------|
| `_busy_lock` 并发竞态 | DIAGNOSIS C2 修不修都不知道是否修对 | 🔴 |
| `_run_pipeline` 端到端 SSE | 翻译路径无回归保障 | 🔴 |
| `routers/agent.py /api/chat` SSE | Agent 主路径无回归 | 🔴 |
| `cloud_client.py` 18 个 provider | `test_translator.py` 仅 23 行 | 🔴 |
| `useTranslate` SSE 重连/abort | 用户体验关键路径 | 🟠 |
| `useEditor` AbortController 共享场景 | 见 2.3 问题 2 | 🟠 |
| Tauri `restart_backend` 端口竞态 | `main.rs:149-157` 30s 轮询的极端边界 | 🟠 |
| `MemoryManager` 并发写 SQLite | DIAGNOSIS C3 仍存在 | 🟠 |
| `WorkspaceEnv` + 主聊天流的端到端 | AWA Phase 1 名义已就绪，但未接入 | 🟡 |

**改进建议**：
- 增加 `tests/integration/test_concurrency.py`：`asyncio.gather(translate(), translate())` 验证 409
- 增加 `tests/unit/test_cloud_client.py`：mock httpx，跑通 OpenAI/Anthropic/DeepSeek 三种格式 + 错误路径
- 前端 `__tests__/streamReader.test.ts` 现在是空白，给个最小 mock + abort 用例
- 后端测试加 `pytest --cov=src --cov=routers --cov-report=term-missing`，目标 >70%

---

## 3. AWA 重构方案评审

### 3.1 与现有代码现实脱节的部分

| 方案声明 | 现实 | 影响 |
|---------|------|------|
| "Phase 1 阻塞于 C1/L1，建议同期推进 C3" | C1/L1 **已完成**（default.yaml 清空 + gitignore），C3 **仍未做**（`memory.py:75` 单连接无连接池） | 重构 Phase 1 实际可立刻启动，但 C3 未做的话 Phase 1 引入的 ChangeJournal 写入可能加剧 SQLite 锁问题 |
| "L1 — MAX_STEPS = 10 写死" | `agent.py:77 MAX_STEPS = 10` 但 `routers/agent.py:160 max_steps=agent_cfg.get("max_steps", 10)` 实际从配置读取，default.yaml 是 20 | 方案的 L1 描述不准；但仍存在"超出即 abort 不可恢复"的核心问题 |
| "Phase 1 改造现有 `_read_file / _save_file`" | `tools.py` 中 `_read_file_v2 / _list_directory / _str_replace / _write_file_v2 / _undo_last_change` **已经存在**，且有完整测试（`test_str_replace.py` 215 行） | Phase 1 实际**已完成 80%**，剩下的只是"接入主聊天流" |
| "Phase 2 必须等 C4 + Q2" | Q2（streamReader 抽象）**已完成**（`utils/streamReader.ts` 6 处复用），C4（reader.cancel 清理）**仍未完成** | Phase 2 阻塞被高估了 |
| "新增 4 个 HookPoint" | `hooks.py` 共 176 行，已有 12 个 HookPoint，但**主聊天路径中真正会触发的 hooks 集成测试为 0** | 加 4 个新 HookPoint 等于把不可观测的接口面再扩 33% |
| "AgentSession + TaskQueue + EventBus + ApprovalChannel" | 当前 `AgentLoop` 1961 行已经很难维护，**方案在不删旧代码的前提下加 +800/+1500 净增量**——4 个 Phase 后 agent/ 目录预计冲到 13000+ 行 | 重构本身在加剧 DIAGNOSIS Q3 已识别的"过度设计与实际能力错配" |

### 3.2 当前工程基础是否支撑得起这个重构？

**短答：不支撑，缺 4 个前置**。

1. **`MemoryManager` SQLite 并发写**（DIAGNOSIS C3）：方案 Phase 1 引入 ChangeJournal（jsonl 但有大量串写），Phase 4 引入 SessionStore（SQLite）。**没有连接池 + WAL fast-checkpoint 配置，并发场景下 `database is locked` 必现**。
2. **测试基础设施**：方案验收标准包含"5 并发 v2 SSE 不串污染"——当前没有任何并发测试模板，不可能在 Phase 2 临时凑出来。需要先建 `tests/integration/test_concurrency.py` 框架。
3. **路由单例隔离**：方案的"按 workspace_root 维度的多实例缓存"在当前 `_get_agent` 单例模式下是大改造。先把 singleton 拆掉，再谈 session pool。
4. **打包/分发链路**：`pywinpty / pexpect`（Phase 3）在 PyInstaller 下都有已知问题，**且 Tauri 当前没有打包 Python 的脚本**（main.rs 找 `python-dist/api/api.exe` 但仓库里没有产出它的工具）。Phase 3 的 BashSession 在 release 模式下大概率打不出来。

### 3.3 方案的设计盲点

1. **不删旧代码**：方案"完全向后兼容、保留 v1"——意味着 `agent.py` 永远精简不下来。8 周后要维护两份 ReAct 实现。**应该在 Phase 4 强制砍掉 v1**，至少把 `agent.py:528-591` 的 has_heavy 分支和 `vram_manager.MultiplexingScheduler` 删掉。
2. **审批超时 = deny 的 UX 灾难**：方案规定"600s 无响应即 deny"。用户离开电脑 10 分钟、回来发现 Agent 把"回退所有改动"当作 deny 拒绝了，整个会话报废。**应该是"挂起 session"而不是"deny"**，恢复时弹原审批。
3. **审批回流端点没考虑认证**：`POST /api/agent/approve/{session_id}/{event_id}` 谁都能 POST。如果服务监听 0.0.0.0，任何同网段的人能替用户决策"allow_session"。
4. **无 Skill 衰减机制**：方案在 Phase 4 提"故意构造任务连跑 3 次自动产生 skill"，但**没说 skill 何时被淘汰**。半年后 `data/agent/skills/` 里 200 个过期 skill 都注入到 system prompt，是 token 浪费 + 信号干扰。
5. **方案声明的"可观测性"只增加了 trajectory.jsonl**：但 trajectory 已经存在了（`trajectory.py` 233 行）。真正缺的是**操作日志** + **审计 trail**——审批决策、撤销操作都没明确说要怎么持久化、给谁看、保留多久。
6. **MAX_STEPS 全局 200 软上限的成本未真测**：每步压缩调用一次（`agent.py:375` `compressor.compress(ollama_dicts)`）= 200 次额外 LLM 调用。Qwen3:8B 单次摘要 5-10s = **额外 1000-2000s 的纯压缩开销**。方案 §7 A2 用"流式而非常驻"轻描淡写带过——但实测过吗？
7. **Phase 2-4 的串行依赖断点不清**：方案最后给的"如人力允许 Phase 3+4 并行" 假设两人同时改 BashSession 和 SessionStore——但两者都要触碰 `routers/agent.py`，并发改动必撞。

### 3.4 如果我来主导这个重构

**优先做的 5 件事（顺序非常重要）**：

1. **第 1 周：把 Agent 单例先打散**——把 `_get_agent()` 改成 per-request agent，`AgentLoop.__init__` 拆分出无状态的 `LLMClient`，把 `_format_error_retry / _token_usage / _http_client` 等所有 instance state 全干掉。这一步是后续所有重构的基础。
2. **第 2 周：把 `WorkspaceEnv` 接入 `/api/chat`**——`ChatRequest.workspace_root` 已有字段但没消费，把 `_str_replace / _write_file_v2 / _undo_last_change` 真正暴露给 Agent，删掉 `~/scholar_agent_files` 旧沙箱。这一步收益最大、改动最小。
3. **第 3-4 周：精简过度设计**——砍掉 `vram_manager.MultiplexingScheduler` 的 KV cache 切换逻辑（云端模式根本用不到，本地 8B 切换收益小）；删除 `AgentMemory` JSONL 双写；把 `auto_processor.py` 和 `special_elements.py` 合并到 prompt_builder。`agent/` 目录从 ~10000 行 → ~5000 行。
4. **第 5-6 周：再做 SecurityGate + Approval**——但**仅对 `_str_replace / _write_file_v2 / shell_exec` 做**，不要试图做 ToolRiskLevel.MODERATE 的"启发式升级"和"会话级 allow_session"，那是后期优化。
5. **第 7-8 周：测试 + 打包闭环**——所有上面的成果接入 e2e 测试，PyInstaller 打包真跑通，写 `npm run pack:python` 串到 `tauri build`。

**砍掉的部分**：
- 整个 Phase 4 的 SessionStore + Resume——**还没人确认用户真的需要这个功能**，先 ship Phase 1-3 看反馈
- TaskPlanner 的"结构化 JSON 计划"——LLM 自己规划即可，不要再搞调度器
- `pywinpty / pexpect` 持久 BashSession——一次性 subprocess.run 已经够 90% 场景，加持久 shell 是 over-engineering（这几乎是 Claude Code 的护城河，本地 Qwen3:8B 的"工作流 Agent"目标用户根本碰不到这个 ceiling）
- `vram_manager` 全部——KV cache 热切换的 ROI 在云端模式下为 0，在本地单 8B 模型下也不显著

---

## 4. 跨平台分发可行性

### 4.1 当前架构的最大工程障碍

**Tauri + PyInstaller + Ollama 三方分别独立的依赖链**，且**没有任何一处把它们粘起来**：

1. **PyInstaller 部分**：`main.rs:330` 期望 `exe_dir/python-dist/api/api.exe`——但仓库里没有 `python-dist/`、没有 `.spec` 文件、没有 `npm run pack:python` 脚本、没有 CI workflow。**`npx tauri build` 现在直接 100% 失败**。
2. **Ollama 部分**：完全独立的 ~600MB 本地服务 + ~5GB 模型权重（qwen3:8b）。当前流程要求用户预装 Ollama 并 `ollama pull qwen3:8b`，**对非技术用户完全不友好**。可选方案：(a) 不打包 Ollama，首次启动引导用户去官网下，(b) 把 GGUF 模型作为 ChromaDB 风格的 lazy download。
3. **Pandoc 部分**：`formatter/renderer.py` 用 `subprocess.run('pandoc', ...)` 调外部二进制，**完全没考虑 Pandoc 不存在的情况**。Pandoc 需要单独安装，Mac 上 brew，Windows 要下 msi。导出 LaTeX/Word 在普通用户那里直接报错。
4. **LaTeX 部分**：`renderer.py` 用的 LaTeX 模板需要 MikTeX/MacTeX——**5GB+ 的依赖，没有任何 desktop app 会捆绑这个**。建议改用 Typst 或者 ReportLab 做 PDF 渲染。

### 4.2 Python 依赖的 PyInstaller 已知问题

| 依赖 | 问题 |
|------|------|
| `chromadb` | 拉 `onnxruntime`、`sqlite-vec`、`hnswlib`，~500MB 总打包大小；hidden imports 经常漏，需手动 `--hidden-import=chromadb.utils.embedding_functions` |
| `sentence-transformers` (`all-MiniLM-L6-v2`) | 模型权重 ~100MB，PyInstaller 不会自动包含，需 `--add-data="venv/Lib/site-packages/sentence_transformers/...":"sentence_transformers"` |
| `PyMuPDF` (fitz) | C 扩展，PyInstaller 5.x 之前需 `--collect-all=fitz`；macOS arm64 需要 universal2 wheel |
| `pdfplumber` | 拉 `pdfminer.six`，依赖 `pycryptodome`，正常但增大体积 |
| `httpx` | 在 Windows 系统代理下卡死（CLAUDE.md 已记录解决方案，但 release 包里仍要清 env 变量） |
| `unstructured` / `pypandoc` | 拉外部二进制，PyInstaller 不会管，必须 sidecar 解决 |

**典型成品体积估算：未压缩 ~1.5GB（Python 运行时 200MB + chromadb 500MB + torch 700MB 是 sentence-transformers 拉的 + 模板/资源 100MB）+ Tauri 部分 ~10MB + Ollama 模型 ~5GB**。

### 4.3 Windows 风险点

1. `start_dev.bat` 是 dev 模式 workaround，release 走的是 `main.rs:build_command()` 清环境变量——如果 release 模式下用户用其他启动器（如 Steam-style 启动器）注入 `HTTP_PROXY`，仍会卡死
2. PyInstaller 在 Win 11 上打包后 Windows Defender 经常误报为恶意软件，需要做 EV 代码签名（$300/年）
3. `taskkill /T /F` 在某些权限场景下会失败，遗留孤儿进程
4. `sqlite3` 模块的 WAL 模式在 OneDrive 同步目录下表现异常（Agent 数据落在用户 home 时可能踩到）

### 4.4 macOS 风险点

1. **代码签名 + 公证**强制：未签名的 .app 用户右键→打开都很麻烦，签名要 Apple Developer Program ($99/年) + notarize
2. **arm64 vs x86_64**：M 系列 Mac 需 universal2 binary，PyInstaller 打两份再 lipo 合并
3. **Gatekeeper 会扫描所有捆绑的 .so/.dylib**，扫描时间与体积成正比，1.5GB 的 .app 第一次启动可能要 30s+
4. macOS 沙箱：Tauri app 默认是非沙箱，但 App Store 分发要求沙箱——届时 `subprocess.run` 调 ollama/pandoc 都会被禁
5. 没有 `start_dev.bat` 的 macOS 等价物——dev 体验差

---

## 5. 面向 V1.0 的行动建议

### 🔴 立即要做（不做就别谈 V1.0）

| # | 行动 | 影响范围 | 改动成本 | 不做的风险 |
|---|------|---------|---------|-----------|
| A1 | 修 `_busy_lock` 竞态：`routers/translate.py:124-126,168-170` 改为 `try: await asyncio.wait_for(_busy_lock.acquire(), 0); except asyncio.TimeoutError: raise HTTPException(409)` | 后端翻译路由 | **小**（< 20 行） | 高负载下并发请求都进入临界区，GPU OOM / 输出文件互相覆盖 |
| A2 | 关闭 `/api/agent/v2/tool` 任意工具调用面：限制 `127.0.0.1` only + 加白名单工具集 | 后端 Agent 路由 | **小**（< 30 行） | 任何能 reach 18088 端口的人能写文件、跑 Shell |
| A3 | 锁泄漏 reaper：上传后 60s 无 stream 连接自动释放 `_busy_lock` | 后端翻译路由 | **小**（< 50 行） | 用户上传后断网，整个翻译服务僵死直到重启 |
| A4 | 撤销旧 DeepSeek key `sk-****`（已在 git history 中），轮换 `default.local.yaml` 中的新 key 至环境变量或 OS keychain | 配置层 | **小**（5 分钟操作 + 文档更新） | 旧 key 仍在 git history，任何 git clone 用户可拿到 |
| A5 | 修 DIAGNOSIS H1：`AiPanel.vue:282` 删除 `ADD_ATTR: ['onclick']`，改为 sanitize 后用 JS 动态绑定按钮 | 前端 | **中**（重写复制/插入按钮交互） | 后端/云 LLM 返回带 onclick 的 HTML 直接 RCE |

### 🟠 重构前要做（AWA 方案的真正前置）

| # | 行动 | 影响范围 | 改动成本 | 不做的风险 |
|---|------|---------|---------|-----------|
| B1 | 拆 `AgentLoop` 单例：`routers/agent.py:_get_agent` 改为 per-request；`agent.py` 删除所有 instance state | Agent 全栈 | **大**（~500 行重构 + 测试） | AWA Phase 2 所谓"5 并发不污染"的验收无法通过 |
| B2 | `MemoryManager` 加连接池 + WAL fast checkpoint（DIAGNOSIS C3） | Agent 持久化 | **小**（< 50 行） | AWA Phase 1 的 ChangeJournal 写入加剧锁竞争 |
| B3 | 给所有 ChatRequest / V2ToolRequest 字段加 Pydantic Field 长度上限（DIAGNOSIS H5） | 后端路由 | **小**（< 30 行） | DoS 攻击面，且 LLM context 被超长 history 撑爆 |
| B4 | 加 `tests/integration/test_concurrency.py` 模板，跑 `asyncio.gather` 多请求 | 测试基础设施 | **中**（~150 行） | AWA 验收"5 并发"无法自动化 |
| B5 | 修前端 SSE reader 取消 + abortController 共享：在 `streamReader.readSseStream` 内 `try/finally { reader.cancel() }`；`useEditor` 用按场景分桶的 Map 替换 module 级变量 | 前端 | **中**（~150 行） | 长会话内存泄漏 + 并发 AI 编辑结果错乱 |
| B6 | 写 `npm run pack:python` 脚本 + PyInstaller `.spec`，跑通至少 Windows release 打包 | 分发链路 | **中**（首次需 1-2 天调 hidden imports） | `npx tauri build` 当前 100% 失败，AWA 的 BashSession 在 release 下不可能打通 |

### 🟡 与重构并行（同步推进）

| # | 行动 | 影响范围 | 改动成本 |
|---|------|---------|---------|
| C1 | 把 `WorkspaceEnv` 接入 `/api/chat` 主聊天流，删除 `~/scholar_agent_files` 旧沙箱 | Agent 工具层 | 中 |
| C2 | 砍掉 `vram_manager.MultiplexingScheduler` KV cache 切换 + agent.py 主循环里的 has_heavy 分支 | Agent 主循环 | 中 |
| C3 | `cloud_client.py` 的 `_rate_limit_wait` 改成模块级（per provider+key 单例） | 翻译层 | 小 |
| C4 | 给 `AgentSkillRegistry` 加 30 天衰减：未被使用的 skill 标记 deprecated 不再注入 prompt | Agent 技能层 | 中 |
| C5 | `routers/translate.py` H3 fallback 加 `task["status"] = "done_with_warnings"`，下载接口 header 标注 | 翻译路由 | 小 |
| C6 | 加 `slowapi` 速率限制中间件（DIAGNOSIS L7） | 后端 | 小 |

### ⚪ 推迟到 V1.0 之后

| # | 推迟项 | 原因 |
|---|-------|------|
| D1 | AWA Phase 4 的 SessionStore + Resume | 当前没有用户痛点说"刷新页面任务丢了"——先做 Phase 1-3 看反馈 |
| D2 | `pywinpty / pexpect` 持久 BashSession | over-engineering；一次性 subprocess.run 已覆盖 90% 场景 |
| D3 | "allow_session" 审批粒度 + 风险升级启发式 | 第一版做"每次审批"已经够用；UX 复杂度先压住 |
| D4 | TaskPlanner 结构化 JSON 计划 | 当前 plan-as-text 已经在工作；LLM 不会因为有 JSON 就规划得更好 |
| D5 | 多 workspace session pool | 接入 `WorkspaceEnv` per-request 后已经 80% 解决；单实例共享池属于"高并发用户"才需要的优化 |
| D6 | macOS App Store 分发 | 沙箱限制下 subprocess 无法调 ollama/pandoc，工程改造成本远超回报 |
| D7 | 自定义 PDF 渲染替代 LaTeX | Pandoc + LaTeX 用户群里"接受装 MikTeX"的还有；先支持下载 .docx 即可，PDF 先标 "experimental" |

---

## 附录：核心文件源码引用速查

| 议题 | 文件 / 行 |
|------|----------|
| `_busy_lock` 竞态 | `python/routers/translate.py:124-126, 168-170, 400-413` |
| Agent 单例污染 | `python/routers/agent.py:68-180`；`python/src/agent/agent.py:312, 314-320` |
| `/api/agent/v2/tool` 安全口 | `python/routers/agent.py:275-299` |
| WorkspaceEnv 死代码 | `python/src/agent/workspace.py:1-122`（已建未接入主链路） |
| ReAct 主循环过肿 | `python/src/agent/agent.py:277-616`（470+ 行） |
| Plan 名实不符 | `python/src/agent/agent.py:340-351, 824-872` |
| has_heavy 分支污染主循环 | `python/src/agent/agent.py:528-591` |
| 静默降级（H3） | `python/routers/translate.py:296-311`；前端 `src/composables/useTranslate.ts:230-235, 245` |
| 前端 abortController 共享 | `src/composables/useEditor.ts:371, 459`；`src/composables/useTranslate.ts:160` |
| Tauri Ollama 不杀 | `src-tauri/src/main.rs:188-196` |
| Tauri 健康检查只触发一次 | `src-tauri/src/main.rs:285-302` |
| Tauri release 模式无打包链路 | `src-tauri/src/main.rs:319-331` + 仓库根目录无 `python-dist/` |
| 前端 API_BASE 容错弱 | `src/utils/api.ts:1-7` |
| 测试覆盖盲区 | `python/tests/unit/test_translator.py` 仅 23 行；并发 / SSE / chat / cloud 0 测试 |
