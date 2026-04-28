# Scholar Assistant — 工程代码评审

**评审日期**：2026-04-28
**分支**：`refactor/editor-cleanup-and-review-fixes` (HEAD `073958e`)
**评审依据**：当前代码实际状态（不参考任何历史评审文档）
**代码体量**：Python ~23k 行（含 routers/src），前端 TS+Vue ~14k 行，Rust 385 行，测试 Python 10k + 前端 1.1k

---

## 1. 当前工程健康度评分

| 子系统 | 评分 | 主要观察 |
|---|---|---|
| 翻译管道 (parser/cleaner/chunker/translator/formatter) | **4.0 / 5** | 主流程稳定、有 OCR fallback、字符级空格修复、句法切分；多格式分发器优雅；Cleaner 17 阶段流水线复杂但有据可循。云端 + 本地双客户端共享 `_helpers.py` 已统一。 |
| Agent / AWA 子系统 (`src/agent/`) | **2.5 / 5** | 设计完整（ReAct + SecurityGate + ChangeJournal + Skill + Trajectory + Memory），但工程量超载（10k 行、26 个模块）。安全闸与原子工具白名单互相矛盾；`tool_generator.py` 是空 stub；`tools.py` 是 38 行兼容外壳。 |
| 后端 API 层 (`api_factory.py` + `routers/`) | **3.5 / 5** | 路由按子系统拆得很清晰，依赖注入模式干净。存在数处实际 Bug（双语 PDF 导出、Agent v2/tool 工具调用、paper-assets/ingest）和 `cloud_only` 路径错配。 |
| 前端状态管理 + SSE (`src/composables/`) | **4.0 / 5** | 14 个 composable 组织良好，singleton 模式一致；`useEditor.ts` 已拆为 5 个子模块；`streamReader` 共享。少量 `(editor as any)` 类型逃逸。 |
| Tauri 进程管理 (`src-tauri/`) | **4.0 / 5** | 单文件 385 行简洁有力，`taskkill /F /T` 清理进程树、proxy 环境变量清理、健康监控线程去重、文件保存路径校验都到位。`save_file` 限制 `.md/.txt` 且必须在用户家目录内。 |
| 配置与安全 | **3.0 / 5** | API Key 已从 git 移除（提交 `3614c96`）、`tm.db` 已 untrack；`_DENIED_PATH_PREFIXES` / `_DENIED_EXTENSIONS` 提供基本路径防护；CSP 已限制 connect-src/img-src。但 atomic_tools 沙箱白名单允许 `rm/rmdir/curl/wget`，与 SecurityGate 黑名单冲突。 |
| 测试覆盖率 | **3.0 / 5** | 45 个 Python 测试文件、10k 行；前端 5 个测试 1.1k 行。翻译管道、glossary、TM、cleaner、parser 覆盖良好；Agent 子系统虽有 8 个相关测试，但相对 26 个生产模块仍显薄弱；前端 composables 几乎只覆盖 `useEditor`。集成测试需运行实例（依赖外部服务）。 |
| **总评** | **3.4 / 5** | 翻译核心质量过硬可发布，Agent 子系统过度复杂、藏有真实 Bug、需要大幅瘦身或下沉到 V1.5 |

---

## 2. 现存问题清单（按严重程度）

### P0 — 阻断性 Bug（功能不可用 / 必须立即修）

1. **`routers/translate.py:794` — 双语 PDF 导出端点恒定失败**
   ```python
   results_by_block = _build_block_translations(t.get("chunks", []), blocks)
   ```
   `tasks[task_id]` 字典初始化时（第 250-259、287-295 行）从未写入 `"chunks"` key，pipeline 也只在 SSE `complete` 事件 payload 里 yield chunks，而非存到 task。所以 `t.get("chunks", [])` 永远是 `[]`，紧接着第 795-796 行 `if not results_by_block` 一定触发 400 "未找到有效的翻译结果"。

2. **`routers/agent.py:586-587` — V2 直接工具调用端点对协程函数处理反了**
   ```python
   if asyncio.iscoroutinefunction(tool_def.fn):
       result = await asyncio.to_thread(tool_def.fn, **req.args)   # ← 错
   else:
       result = tool_def.fn(**req.args)
   ```
   对协程函数应直接 `await tool_def.fn(...)`；`asyncio.to_thread` 在子线程同步调用，遇到协程函数只会得到一个 coroutine 对象，根本不会被 await。逻辑应该交换。

3. **`routers/editor.py:371` — `paper_assets_ingest` 调用 `await get_agent()` 但 `get_agent` 始终为 `None`**
   `api_factory.py:319` 注册时直接传 `get_agent=None`。命中此端点必然抛 `TypeError: 'NoneType' object is not callable`。要么把 `get_agent` 真接进来（agent state），要么去掉路由。

4. **`routers/editor.py:522` — Word 下载路径硬写死，`cloud_only` 模式下与上传不一致**
   写入用 `output_dir = data_root / "output"`（line 85），其中 `data_root` 在 cloud-only 时是 `data_cloud`；下载却用 `safe_dir = runtime_dir / "data" / "output"`。在 cloud-only 模式下，文件落在 `data_cloud/output` 但下载找 `data/output`，恒 404。

### P1 — 严重（影响安全/正确性/重构一致性）

5. **`agent/security_gate.py` 黑名单与 `agent/tools/atomic_tools.py:35-46` 白名单冲突**
   - SecurityGate `_CMD_BLACKLIST`：`rm/rmdir/sudo/dd/curl/wget/ssh/...`
   - atomic_tools `_SHELL_ALLOWED_COMMANDS`：包含 `rm/rmdir/curl/wget`
   `shell_exec` 的 SecurityGate 风险等级是 MODERATE，而 SessionConfig 默认 `auto_approve=True`（dev mode），意味着 LLM 可以在沙箱中执行 `rm/curl/wget`，在双闸门设计下属于"前后矛盾"。

6. **`routers/argument.py:97-349` — Fallback 路径已是死代码且 API 调用不匹配**
   `_ARGUMENT_AVAILABLE` 只有当 `src.argument.models` 不可导时才为 False，而后者是项目内模块、永远可导。所以"fallback"分支 173-349 行从不会执行。更糟的是它调用 `store.load()`、`store.upsert_node(tree, …)`、`store.delete_node(tree, …)` —— 这些 API 在 `src/argument/store.py:30-237` 根本不存在或签名不一致（实际方法是 `get_tree()` / `upsert_node(**kwargs)` / `delete_node(node_id, cascade)`）。一旦真的进入 fallback 路径就会 `AttributeError`。建议直接删除 fallback 段。

7. **`routers/translate.py:108-163` — busy lock 实现脆弱**
   - `_busy_lock` 是模块级单实例，整个进程只允许一个翻译任务（已在评论中承认），但前端可能同时打开多个任务上传；`_acquire_busy_lock` 用 `asyncio.wait_for(timeout=0)` 的非阻塞 `acquire`，正常情况这个写法是 anti-pattern（应直接 `lock.locked()` 检查）。
   - `_lock_reaper` 60 秒后强行释放：如果用户上传后立刻关闭页面，下一个任务会用脏 lock；orphan 检测 `_acquire_busy_lock` 替换 lock 也只是 best-effort，多用户/多任务场景会出现"任务已超时释放"误报。

8. **`api_factory.py:209-226` — `_validate_file_path` 防御不完整**
   - 没有解析符号链接：例如 `~/symlink_to_etc_passwd.txt`，`resolved.suffix` 不是敏感后缀也不在 DENIED 子目录里，直接放行。
   - DENIED list 写死 `C:\Windows`、`/etc`，未包含 `C:\\Users\\<user>\\AppData\\Roaming\\Microsoft` 等敏感目录；也未阻止 `..` 路径遍历后落到工作目录外（仅靠 resolve 不够，缺白名单）。

9. **`routers/editor.py:526-531` — Word 文件 30 分钟过期逻辑独立、可被绕过**
   `download_word` 给出 30 分钟过期；但 `data/output/` 下文件是写后即静态保留，不存在后台清理任务，磁盘会无限增长；`age_minutes > 30` 触发即时删除也会让正在下载的文件中断。

10. **`agent/auto_processor.py`、`bash_session.py`、`mcp_server.py` 等占用 ~1.5k 行但未在 V2 工具白名单**
    `routers/agent.py:36-40` `_V2_TOOL_WHITELIST` 只允许 8 个工具，bash_session/auto_processor/mcp_server 不在内，仅 AgentLoop 内部可能调用。功能尚未端到端打通，是"半成品"。

### P2 — 中等（代码质量 / 可维护性）

11. **`api_cloud.py` vs `api.py` 重复入口** — 两个文件功能重叠，`api.py` 用 `cloud_only=False`，`api_cloud.py` 用 `cloud_only=True`。可改为单一入口加 `--cloud-only` 旗标。`api_cloud.py:33` 在导入时立即创建 app，而 `--self-test` 模式根本不需要 app 实例，浪费启动时间。

12. **`python/main.py` 已 staged-deleted 但 `.gitignore:39` 也把它列入忽略** — 重复语义。`git status` 显示 `deleted: python/main.py` 已暂存但未提交，需要尽快清理这个不一致状态。

13. **`agent/tools.py` (38 行) 与 `agent/tools/__init__.py` (90 行) 都是 re-export 兼容层** — 注释说 "向后兼容（DEPRECATED）"，但项目内仍有代码直接 `from src.agent.tools import ...`。可以删旧文件或保留一个。

14. **`agent/tool_generator.py` (32 行) 是 stub** — 文件中所有方法都 `raise NotImplementedError`。要么实现，要么删。

15. **`routers/translate.py:125-142` `_restore_paragraphs_for_display` 与 `src/translator/_helpers.py` `_restore_paragraphs` 重复定义类似逻辑** — 前者只是后者的"先判断是否需要"再调用的薄包装，应该把启发式判断推到 helpers，避免路由层做业务判断。

16. **`routers/editor.py:103-114, 406-417` — System prompt 硬编码在路由代码里**
    几个 system prompt 直接写死在 router 函数中（中文+英文混合）；`prompts/` 目录已为此存在，应该迁移过去。

17. **`useEditor.ts:81, 114, 151, 231, 253` — Monaco Range 兜底类频繁出现**
    ```typescript
    const Range = (editor as any).monaco?.Range ?? class R {...}
    ```
    五处复制相同的"未挂 monaco 时回退"代码，应抽出顶层 helper。`as any` 也是类型逃逸。

18. **`agent/llm_client.py` 849 行单文件过厚** — 一个文件混合 Ollama / OpenAI / Anthropic 三家协议、流式/非流式两种模式、消息转换 helpers。建议按 provider 拆。

19. **`api_factory.py:46-49`、`routers/translate.py:116-119` — `BUNDLED_DIR / RUNTIME_DIR` 区分仅在 `api_factory.py` 实现，translate 路由 `glossary_dir` 第 116-118 行二次回退到 `Path(__file__).resolve().parent.parent`** —— 单冷启动时 `runtime_dir / "data"` 不存在则换路径，对 PyInstaller 包无意义。

20. **`agent/skill_system.py:711` 行、`agent/special_elements.py:661` 行** — 单文件超大，混合多个职责（Skill 数据/检索/衰减/纳吉、特殊元素的多种检测器）。

21. **频繁的 `try / except ImportError` 标记可选依赖**（agent.py:32-34, plugin 17 处, ocr fallback, agent register, 等）—— 是优雅降级模式，但累计后让"哪些功能在生产中可用"难以判断。建议把可选 backend 集中到一个 features module，运行时一次性检测。

### P3 — 轻微（清理 / 文档 / 风格）

22. **`api_factory.py:235` `app = FastAPI(version="0.4.2")` vs `package.json` 0.2.0 vs `tauri.conf.json` 0.3.1 vs CLAUDE.md "Tauri 0.3.1 / npm 0.2.0" — 多家版本号不同步**

23. **`MIGRATION_V2_COMPLETE.md` 与旧版 `REVIEW_CURRENT.md` 残留在仓库根目录** — 都是开发笔记，应该挪到 `docs/` 或在合并到 main 时删除。

24. **`routers/translate.py:31-32` 两行 `from src.translator._helpers import` 应合并**

25. **`config/default.yaml`（仓库根，48 行）vs `python/config/default.yaml`（gitignore） vs `python/config/default.local.yaml`（运行时）** — 三个 default 文件存在三种角色，新人不易理解；建议在 README 或 CLAUDE.md 单列章节说明。

26. **`api_factory.py:234` `parser = argparse.ArgumentParser(description=_app_title)` 创建后未使用** — 死变量。

27. **`routers/translate.py:43-86, 89-91` 顶层定义的 `ConfigUpdate` 与 `_build_block_translations` 在文件外不被复用** — 可降为 register 内部。

---

## 3. 重构质量评估

### 已经完成且干净的部分
- **API 路由按子系统拆分**：`api_factory.py` (345) → `routers/{translate,agent,editor,argument,mindmap}.py`，注入式架构清晰，依赖只往下传不上抓。
- **TranslationResult 统一**：`src/translator/_helpers.py` 提供单一 `TranslationResult`，`ollama_client.py:22-34` 和 `cloud_client.py:16-28` 都从 helpers 导入。
- **Editor composables 拆分**：`useEditor.ts` (284) 主入口 + `useEditorState/useEditorIO/useEditorTabs/useEditorVision/useEditorCitation` 五件套，单一真实源在 `useEditorState.ts`。
- **API Key 处理**：`_apply_env_overrides` (api_factory.py:159) 走 `SCHOLAR_CLOUD_API_KEY` 环境变量，`_mask_api_key` 在 GET /config 时遮盖；提交 `3614c96` 移除了 plaintext key。
- **Agent ReAct 主循环**：`agent.py:205-319` 的 `step()` 是无状态的、只追加 messages，`session.py:225-450` 的 `_drive_task` 才管控并行/审批/错误恢复，关注点分离。

### 重构未彻底的痕迹

- **死代码块**：
  - `routers/argument.py:97-349`（fallback 路径，永不命中且 API 不匹配）
  - `agent/tool_generator.py`（全 stub）
  - `agent/tools.py`（与 `agent/tools/__init__.py` 重复 re-export）
  - `python/main.py`（已暂存删除中）
  - `api_factory.py:234` 未使用的 `argparse.ArgumentParser`

- **新旧两套并存**：
  - 翻译管道有两条路径：`extract_document` 与 `extract_document_with_layout`（PDF 时走第二条），新路径只为双语 PDF 叠加导出存在；其他格式（含 PDF 不需要 overlay 时）依然走第一条。
  - `Glossary`（`ollama_client.py:61-91`，自动术语学习类）vs `GlossaryStore`（`glossary_store.py`，权威术语表 + YAML 加载）：两套术语机制并存，OllamaClient 的 `_glossary` 是私有兜底，路由层却又直接拼接 `glossary_store.build_prompt_text`（routers/translate.py:411-416），双重注入。

- **命名不一致**：
  - `auto_approve` vs `approved_categories` vs `pending_approvals` 三套审批状态混用 (session.py:102-103, 322)；
  - 路由 `/api/agent/v2/...` 但 frontend 文件名/composable 命名都不带 v2，而 `_V2_TOOL_WHITELIST` 只锁住 8 个工具 —— "v2" 是过渡命名而非正式产品概念，建议要么去掉，要么把 v1 的残影也清理。

- **导入双轨**：
  - `from src.agent.tools import ...` 与 `from src.agent.tools.core import ...` 都被使用；
  - `from src.translator.ollama_client import _strip_think_tags`（兼容 re-export）与 `from src.translator._helpers import _strip_think_tags`（直接源）并存。

- **注释掉的旧逻辑**：未发现明显残留（`grep TODO/FIXME/XXX/HACK` 在 `python/src+routers` 下命中数为 0），算是一个亮点。

- **复杂度积累**：
  - `python/src/agent/` 下 26 个模块、~10000 行，与 V1 实际可用的 8 个 agent 路由严重不对称；
  - `cleaner/pipeline.py` 861 行实现 17 个清洗阶段，单文件无内部分模块；
  - `llm_client.py` 849 行融合三家 API。

---

## 4. 距离生产就绪还差什么（V1.0 阻碍 + 改动成本）

按优先级排序：

| # | 阻碍 | 改动成本 |
|---|---|---|
| 1 | **修 P0 Bug：双语 PDF 导出（translate.py:794）、Agent v2 直接工具调用 async 反转（agent.py:586）、Word 下载路径不一致（editor.py:522）、paper_assets_ingest 注入缺失（editor.py:371）** | **小**（单文件 1-3 行修改 + 单元测试） |
| 2 | **统一 atomic_tools / SecurityGate 安全策略**：从 `_SHELL_ALLOWED_COMMANDS` 删除 `rm/rmdir/curl/wget`，或者让 SecurityGate 的黑名单成为唯一权威，atomic_tools 在执行前查询 SecurityGate.classify 决定是否放行 | **小**（一次性整理 + 加 1-2 个单元测试） |
| 3 | **删除死代码**：`routers/argument.py` fallback、`agent/tool_generator.py`、`agent/tools.py`、`api_factory.py:234`、`MIGRATION_V2_COMPLETE.md`/旧版 `REVIEW_CURRENT.md` 等 | **小**（机械操作） |
| 4 | **统一版本号**：`api_factory.py:235`、`package.json`、`src-tauri/tauri.conf.json`、`README.md`、CLAUDE.md 全部对齐到一个 V1.0 号 | **小** |
| 5 | **busy_lock + lock_reaper 改成 task_id 级锁**（translate.py:108-182），允许多任务排队/并行；orphan recovery 改为基于 task_status 而不是计时器 | **中**（影响并发模型，需测试） |
| 6 | **`_validate_file_path` 增强**：处理 symlink、补 Windows AppData/Roaming 敏感子目录、引入路径白名单（用户家目录或显式 work_dir）替代单纯黑名单 | **中** |
| 7 | **Agent 子系统瘦身决策**：要么把 V1 的 Agent 缩到 8 个路由白名单需要的 ~3-5 个模块（llm_client、agent、session、tools、security_gate、memory），把 `tool_generator/auto_processor/skill_system/special_elements/mcp_server/bash_session/review_agent/trajectory` 中没接通到端到端流程的部分挪到 `experimental/` 或 `next_v2/`；要么明确接通到 v2 路由白名单。当前状态对单元测试和文档都是负担。 | **大**（涉及 5k+ 行代码归类，测试需要重新对齐） |
| 8 | **集成测试矩阵补齐**：`tests/integration/` 6 个测试都依赖运行实例（`needs running API`，CLAUDE.md 已注明），缺 CI 中可运行的端到端 Mock；前端 vitest 只覆盖 5 个模块（`useEditor` 是唯一 composable 测试）。建议至少给 `useTranslate`、`useAgentChat`、`streamReader` SSE 错误路径补测。 | **中** |
| 9 | **配置文件三件套澄清** — 在 README 或 CLAUDE.md 加章节说明 `config/default.yaml`（仓库默认）、`python/config/default.yaml`（运行时拷贝）、`python/config/default.local.yaml`（用户私有覆盖）三者关系 | **小**（纯文档） |
| 10 | **API Key 安全升级**：当前 `_mask_api_key` 在 GET 时打码，PUT 时识别 `****` 不覆盖。但磁盘上 `default.local.yaml` 仍是明文。生产建议接系统 keychain 或 OS-level 加密存储 | **中** |
| 11 | **错误事件 SSE 标准化** — `routers/translate.py` 用 `chunk_error/error/glossary_violation` 等多种事件名，前端 `useTranslate.ts:241-260` 处理散落，建议引入 `ErrorEnvelope` 类型 + 前后端共享枚举 | **中** |
| 12 | **下载文件 GC 策略**：30-min 过期清理逻辑只在请求时触发，磁盘可能积压。引入后台 task / cron 或在 `_cleanup_tasks` 钩子里统一处理 | **小** |
| 13 | **CSP 收紧**：`unsafe-inline` 和 `unsafe-eval` 都在 script-src（`tauri.conf.json:23`），与"privacy-first"承诺有出入。Monaco 通常需要这两个，但可考虑 worker-src 单独白名单 | **大**（要确认 Monaco 行为） |
| 14 | **跨平台 sandbox 路径**：`atomic_tools.py:32` 写死 `~/scholar_agent_files`，Windows 下没问题但 Tauri 打包后没有对此目录的预创建/权限说明 | **小** |
| 15 | **观察性**：基本只用 `logging` 输出 stdout（被 Tauri pipe 到控制台），缺结构化日志、缺 trace id（每个翻译任务/会话都应带 task_id 链路日志） | **中** |

---

## 评分汇总（再次列出，便于扫读）

| 子系统 | 评分 |
|---|---:|
| 翻译管道 | 4.0 |
| Agent / AWA | 2.5 |
| API 路由层 | 3.5 |
| 前端 + SSE | 4.0 |
| Tauri 进程 | 4.0 |
| 配置 + 安全 | 3.0 |
| 测试覆盖 | 3.0 |
| **总评** | **3.4** |

## Top 5 待解决问题（按"投入产出比 × 阻断性"排序）

1. **`routers/translate.py:794` 双语 PDF 导出 — task["chunks"] 永远为空** （P0，10 分钟修）
2. **`routers/agent.py:586` async 函数误用 `to_thread` — V2 直接工具调用对协程工具无效** （P0，5 分钟修）
3. **`routers/editor.py:371, 522` paper_assets_ingest 与 Word 下载 — 路径/注入错误** （P0，30 分钟修）
4. **atomic_tools `_SHELL_ALLOWED_COMMANDS` 与 SecurityGate 黑名单冲突 — `rm/curl/wget` 被默认 auto_approve 后可执行** （P1，1 小时修+测）
5. **Agent 子系统总量决策（10k 行 vs 8 个生效路由）— 在发布 V1.0 前必须做"瘦身"还是"接通"的取舍** （P1，1-2 周）

---

*本评审基于当前代码静态阅读，未运行端到端验证。建议在落实任意修复前先补对应单元测试以锁定行为契约。*
