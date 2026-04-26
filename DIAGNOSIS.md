# Project Diagnosis — Scholar Assistant

> 诊断日期: 2026-04-26  
> 覆盖范围: Python 后端 (`python/`)、Vue 3 前端 (`src/`)、配置与构建  
> 方法: 静态分析 + 代码审查，未运行程序，未修改任何文件

---

## 一、Bug 与潜在问题（按严重程度分级）

### 🔴 CRITICAL — 必须立即处理

---

#### C1. 明文 API Key 硬编码在仓库配置文件中
- **文件**: `python/config/default.yaml:39`
- **问题**: `api_key: sk-53790f5e78654ae695e2795ee2a78f02` 明文写入并随代码提交。`.gitignore` 未忽略该文件。
- **影响**: 任何有仓库访问权限的人可直接取用 DeepSeek API Key，产生未授权计费或数据泄露。
- **关联**: `python/config.json`（运行时生成）也可能落入 git 暂存区。

---

#### C2. `_busy_lock` 的 check-then-act 竞态条件
- **文件**: `python/api_factory.py:411-414, 451-454`
- **问题**: 
  ```python
  if not _busy_lock.locked():   # 检查
      await _busy_lock.acquire() # 加锁  ← 两步之间可被抢占
  else:
      raise HTTPException(409, ...)
  ```
  这不是原子操作。两个并发请求都能通过 `locked()` 检查并同时进入临界区，致使两个翻译管道同时运行。
- **影响**: GPU OOM 崩溃、任务状态覆盖、输出文件损坏。
- **正确做法**: 改用 `asyncio.Lock` 的 `try_acquire` 语义或 `async with lock` + 立即拒绝模式。

---

#### C3. SQLite 未启用 WAL 模式，缺少线程安全配置
- **文件**: `python/src/agent/memory.py:75,166,188,223,290,307,335`
- **问题**: 每次操作都用 `sqlite3.connect(self._db_path)` 创建新连接，无 WAL 模式、无 `check_same_thread=False`、无连接池。FastAPI 是异步框架，数据库写入发生在多个协程上下文中。
- **影响**: 并发对话时出现 `database is locked` 错误；Agent 记忆写入静默失败；极端情况下数据库文件损坏。

---

#### C4. 前端所有 SSE/Stream 读取器均无 `reader.cancel()` 清理
- **文件**: 
  - `src/composables/useTranslate.ts:168`
  - `src/composables/useAgentChat.ts:72`
  - `src/composables/useEditor.ts:401, 494`
  - `src/components/AiPanel.vue:367`
  - `src/components/EditorLayout.vue:441`
- **问题**: 全局 grep 确认 `reader.cancel` 在整个 `src/` 目录下**一处都不存在**。所有 `getReader()` 在 catch/finally 路径中均不调用 `cancel()`。当用户重置、切换标签页或连接中断触发重连时，旧 ReadableStreamDefaultReader 被孤立，持续占用网络连接和内存。
- **影响**: 内存持续增长；每次 SSE 重连都叠加一个泄漏的 reader；长时间运行后性能显著下降。

---

### 🟠 HIGH — 应在下个迭代中修复

---

#### H1. DOMPurify 显式白名单 `onclick`，等效于关闭 XSS 防护
- **文件**: `src/components/AiPanel.vue:282`
- **问题**: 
  ```typescript
  return DOMPurify.sanitize(h, { ADD_ATTR: ['onclick', 'data-id'] })
  ```
  `ADD_ATTR: ['onclick']` 使 DOMPurify **允许所有 onclick 属性通过**，包括来自后端 API 响应中的内容。`renderMd()` 的输出直接以 `v-html` 渲染（第 50、70 行）。
- **影响**: 若后端（或其调用的云 LLM）返回带 onclick 的内容，可直接执行任意 JavaScript。
- **根因**: 开发者为了让自己生成的 Copy/Insert 按钮（第 268-269 行）生效，错误地用 ADD_ATTR 全局放行了 onclick。应改为在 sanitize 后由 JS 动态绑定事件，而不是允许 onclick 属性。

---

#### H2. 拖拽调整宽度时组件卸载导致 `document` 事件监听器泄漏
- **文件**: `src/components/EditorLayout.vue:525-531, 565-568`
- **问题**: `startResize()` 向 `document` 注册 `mousemove` / `mouseup`，清理逻辑在 `onMouseUp` 回调内（拖拽结束时自清）。但 `onBeforeUnmount` 不清理这两个监听器。若用户在拖拽过程中组件被卸载（路由切换、HMR），两个监听器永久残留在 `document` 上。
- **影响**: 残留监听器持续响应鼠标事件，改变已销毁组件的响应式状态，引发内存泄漏和难以排查的 UI 异常。

---

#### H3. 翻译失败静默降级：用户无感知地得到未翻译内容
- **文件**: `python/api_factory.py` 内的 `_run_pipeline` 函数
- **问题**: 翻译重试两次失败后，代码 fallback 为 `translated = chunk.text`（原文），并继续向用户流式返回，整个任务状态标记为 `done`。
- **影响**: 用户下载的"翻译结果"中混有未翻译的英文段落，但界面显示"翻译完成"，无任何警告。

---

#### H4. 多个 `tasks` / `argument_tasks` / `_flatten_tasks` 字典无锁并发访问
- **文件**: `python/api_factory.py:310, 438, 474, 1579, 2252`
- **问题**: 三个独立的任务字典在并发路由处理器中无保护地读写。`_cleanup_tasks()` 在迭代 `tasks.items()` 的同时，另一个请求可能在插入/删除同一字典的 key。
- **影响**: `RuntimeError: dictionary changed size during iteration`；任务状态丢失；`task_id not found` 假阳性错误。

---

#### H5. `api_factory.py` 无任何输入长度限制
- **文件**: `python/api_factory.py` 的 `/api/chat` 端点
- **问题**: `ChatRequest` 的 `message`、`context_text`、`history` 字段无长度约束。`history` 可以包含数千条历史消息，全部加载进 Agent 上下文。
- **影响**: 单次请求即可耗尽服务器内存；无需认证的 DoS 攻击面。

---

#### H6. `asyncio.Lock` 在非 async 上下文创建时可能绑定错误事件循环
- **文件**: `python/src/translator/ollama_client.py`
- **问题**: `_ensure_lock()` 在首次调用时创建 `asyncio.Lock()`，若首次调用发生在非 async 上下文（如模块导入时），会绑定到错误的事件循环，在实际 async 路由中调用时抛出 `RuntimeError: This Lock is bound to a different event loop`。

---

### 🟡 MEDIUM — 计划处理

---

#### M1. Agent 上下文压缩失败时无 abort 保护
- **文件**: `python/src/agent/agent.py`（context compressor 调用处）
- **问题**: 压缩调用失败或未触发时（`was_compressed=False`），messages 原样传入，但没有检查是否超出 `num_predict` 上限。持续增长的上下文最终导致 Ollama 返回截断响应，而 Agent 仍继续循环。

---

#### M2. SQLite memories 表缺少约束
- **文件**: `python/src/agent/memory.py:76-102`（建表 DDL）
- **问题**: `importance` 列无 `CHECK(importance BETWEEN 0.0 AND 1.0)`；`content` 无唯一约束，同一内容可无限重复写入；无索引导致全表扫描。长期运行后内存表膨胀，查询变慢。

---

#### M3. `config/default.yaml` 加载无 Schema 校验
- **文件**: `python/api_factory.py`（`_load_config` 函数）
- **问题**: `yaml.safe_load()` 后直接使用，无结构校验。用户可将 `max_tokens` 设为 9999999、`temperature` 设为负值，在运行时才触发不可预测的错误。

---

#### M4. SSE 重连时旧 reader 未释放
- **文件**: `src/composables/useTranslate.ts:241-260`
- **问题**: 重连逻辑创建新的 `fetch` + `getReader()`，但不等待旧 reader 的 `read()` promise 解决。旧 reader 悬挂，占用底层 TCP 连接直到 GC 回收（不确定时间）。

---

#### M5. MarkdownPreview 中 KaTeX 输出在 DOMPurify 之后注入，绕过 XSS 防护
- **文件**: `src/components/MarkdownPreview.vue`
- **问题**: 渲染流程为：提取数学公式 → 渲染为 HTML placeholder → DOMPurify sanitize → **再替换回 KaTeX HTML**。最后一步在 sanitize 之后执行，KaTeX 渲染产生的 HTML 未经过滤直接插入 DOM。
- **影响**: 若后端返回精心构造的 LaTeX 表达式，可绕过 sanitizer 注入 HTML。

---

#### M6. `useAgentChat` 快速连续调用时旧 AbortController 被覆盖
- **文件**: `src/composables/useAgentChat.ts:46`
- **问题**: `abortController = new AbortController()` 直接覆盖旧值，未先调用 `abort()`。旧的 fetch 请求继续在后台运行，响应返回后会写入已被新请求覆盖的 `assistantMsg`，造成消息内容混乱。

---

#### M7. `useEditor.ts` ghost text 补全 timer 在组件卸载后可能触发
- **文件**: `src/composables/useEditor.ts`（completionTimer 相关）
- **问题**: `setTimeout` 回调在 Monaco 编辑器销毁后触发，尝试调用已销毁实例的方法，抛出 `Cannot read properties of null` 运行时错误。

---

### 🔵 LOW — 技术债，可排期处理

---

#### L1. `python/config/default.yaml` 未加入 `.gitignore`
- `.gitignore` 忽略 `.env`，但 `config/default.yaml` 明文暴露（同 C1 根因，需双管齐下）。

#### L2. `_cleanup_tasks` 在 finalizer 中调用，时机不稳定
- **文件**: `python/api_factory.py:688`
- `_cleanup_tasks()` 在翻译 pipeline 的 `finally` 块中调用，属于"写入时清理"策略，在高并发下可能永远不被触发（任务不完成就不清理）。

#### L3. `EditorLayout.vue` 中 `async function onKeyDown` 的错误未被捕获
- 若 `saveFile()` 抛出异常，toast 不会显示，错误被静默丢弃。

#### L4. `api.ts` 的 `API_BASE` 无格式校验
- **文件**: `src/utils/api.ts`
- 若 `VITE_API_URL` 环境变量缺少协议头，所有 fetch 调用以相对路径发出，难以定位。

#### L5. `MonacoEditor.vue` 中 `autoGhostTimer` 同名变量在模块级和 handler 内部双重声明
- **文件**: `src/components/MonacoEditor.vue`
- 内部声明遮蔽模块级变量，导致 `onBeforeUnmount` 清理的是未被使用的模块级变量，实际运行的 timer 不被清理。

#### L6. `argument/store.py` 中 `ArgumentStore` 无持久化
- 所有 Argument Map 数据仅存内存；服务重启后全部丢失，但前端无提示。

#### L7. 无全局速率限制
- `api_factory.py` 无任何 rate limiting 中间件。所有端点（`/api/translate`、`/api/chat`、`/api/rag/upload`）可被无限并发调用，易受 DoS 攻击。

---

## 二、代码质量问题

### Q1. `api_factory.py` 严重违反单一职责原则
**~2300 行**，包含翻译管道、Agent 聊天、RAG、Argument Mapping、Edit/Complete、Config、Plugin、Zotero、Paper Assets 共 9 个独立业务域。任何修改都需要在 2300 行中定位，测试困难，代码审查低效。建议按路由前缀拆分为独立 router 模块（`routers/translate.py`、`routers/agent.py` 等）。

### Q2. 重复的 SSE 流读取样板代码（6 处）
`useTranslate.ts`、`useAgentChat.ts`、`useEditor.ts`（×2）、`AiPanel.vue`、`EditorLayout.vue` 中均有相同的 `getReader → TextDecoder → buffer split → SSE parse` 逻辑，每处约 40-60 行，存在细微差异（错误处理路径不同、有无 AbortSignal 不同）。应抽象为 `src/utils/streamReader.ts` 统一实现。

### Q3. Agent 子系统过度设计与实际能力错配
`vram_manager.py`（KV cache 热切换）、`context_compressor.py`（比例阈值压缩）、`skill_system.py`（轨迹沉淀）、`trajectory.py`（JSONL 记录）、`hooks.py`（12 个生命周期点）、`review_agent.py`（后台审查）同时存在，相互依赖复杂。但从测试覆盖看（`tests/unit/` 中无专门测试 hooks、trajectory、review_agent 的用例），这些组件的集成路径未经充分验证。

### Q4. 前端 `useTranslate`、`useEditor`、`useFileTree` 是模块级单例，无法测试
模块级 `ref`/`reactive` 在 vitest 中跨测试共享状态，测试文件需手动重置。`src/__tests__/useEditor.test.ts` 实际能测试的范围因此受限。

### Q5. `default.yaml` 中 `system_prompt` 内嵌业务逻辑
翻译 system prompt 和 Agent system prompt 都硬编码在 YAML 配置中，包含大量业务规则。修改 prompt 需要重启服务，且 prompt 内容无版本管理。

### Q6. 错误处理模式不统一
后端存在三种并行的错误处理模式：`raise HTTPException`、`return {"error": ...}`、SSE `{"event": "error", "data": ...}`。前端对应地有三种解析路径，未收敛。

---

## 三、优先处理建议

以下按 **处理紧迫度** 而非严重程度排序，考虑了修复成本与收益比：

| 优先级 | 问题 | 原因 |
|--------|------|------|
| **P0 — 立即** | C1: 轮换 DeepSeek API Key，将 `config/default.yaml` 加入 `.gitignore` | Key 已暴露在 git history，必须轮换；防止重犯成本极低 |
| **P0 — 立即** | C2: 修复 `_busy_lock` 竞态 | 当前代码在并发请求下必然触发，生产环境崩溃概率高 |
| **P1 — 本周** | C4: 在所有 6 处 SSE reader 的 catch/finally 中加 `reader.cancel()` | 改动小（每处一行），收益大（内存泄漏、连接泄漏） |
| **P1 — 本周** | H1: 修复 DOMPurify `ADD_ATTR: ['onclick']` | 安全漏洞，改动小：去掉 onclick 白名单，改为 JS 动态绑定按钮事件 |
| **P1 — 本周** | C3: memory.py SQLite 加 WAL + `check_same_thread=False` | Agent 多用户场景必现崩溃，修复成本低 |
| **P2 — 本迭代** | H2: `EditorLayout.vue` onBeforeUnmount 补全 mousemove/mouseup 清理 | 一行修复，防止拖拽场景的内存泄漏 |
| **P2 — 本迭代** | H3: 翻译失败 fallback 时通过 SSE 发送 `warning` 事件 | 用户体验问题，前端已有事件处理框架，后端只需补一个 yield |
| **P2 — 本迭代** | M5: KaTeX 注入绕过 DOMPurify | 需重构渲染顺序，成本中等，安全影响有限（需恶意后端配合） |
| **P3 — 下迭代** | Q2: 抽象 SSE 读取工具函数 | 消除 6 处重复代码，同时统一 C4 修复 |
| **P3 — 下迭代** | Q1: 拆分 `api_factory.py` | 长期可维护性，建议先拆 agent / argument 两个 router |
| **P4 — 技术债** | M2, M3, L6 等 | 稳定性改善，可在常规迭代中逐步处理 |

---

### 关键说明

1. **C1 和 C2 是最高优先级**：C1 是安全事故，C2 是当前代码在高负载下必然触发的逻辑错误，两者修复成本都极低。
2. **C4 的影响被低估**：前端 SSE reader 泄漏在日常单用户使用中不明显，但用于演示或长时间会话时会导致浏览器卡顿，且 6 处同时存在说明这是系统性遗漏而非偶发。
3. **Q1（拆分 api_factory.py）不是紧急问题**，但它是所有其他问题（H4、H5、L2）难以修复的根因——大文件使得添加中间件、统一错误处理、编写测试都更困难，建议在 P0/P1 问题处理完后尽快启动。
