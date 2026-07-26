# 审计报告可靠性核查 + 逐项修复记录

> 核查对象：`docs/audit-report.md`、`docs/development-direction.md`
> 核查方式：对每条发现用 Read/grep/wc/实际运行测试进行独立复核（不轻信探索 agent 的结论）
> 日期：2026-07-20

---

## 1. 可靠性总评

**两份报告高度可靠：12 条发现全部在实质上成立**，没有伪造或方向性错误。核查中发现 **2 处实质不准确 + 几处轻微夸大**，均已在本次修复中更正。发展方向整体正确，仅需小幅修正。

| 类别 | 数量 |
|------|------|
| 完全属实（TRUE） | 9 |
| 属实但表述需修正（PARTIAL） | 3（F2、F5、F9） |
| 完全错误（FALSE） | 0 |

---

## 2. 逐项核查结果

| 编号 | 原结论 | 核查 | 证据 |
|------|--------|------|------|
| **F1** 影子后端 `src-tauri/python/src/` 孤立 | TRUE，且**范围比报告更大** | `git check-ignore` = YES；`scripts/api.spec` 从 `python/src` 打包；`resolve_python_dir()`（main.rs:634）dev→`repo/python/`、prod→`python-dist/`，**均不指向 `src-tauri/python/`**。整个 `src-tauri/python/`（含 api.py/api_factory.py，0 处 agent_v2 引用）都是 pre-agent_v2 陈旧拷贝 |
| **F2** `ledger.py:151` 打印原始 LLM 响应 | TRUE，但**第二处是误报** | `ledger.py:151` print 属实（已删）；`plugin/__init__.py:20` 的 `print(registry.get_stats())` 经查位于**模块 docstring 示例代码**中，非真实语句。原报告"2 处 print"更正为"1 处" |
| **F3** checkpoint 决策 stub + 未接入 UI | TRUE（"死 UI" 定性已修正） | `respondCheckpoint`（原 L597）仅清空状态、`_decision` 未用；`AgentCheckpointCard.vue`（50 行）当前全 `src` 零引用、router.py 无 checkpoint decide 端点。**但该组件是完整实现的 WIP（含 Continue/Pause/Revise 按钮与 `decide` emit），属"尚未接入"而非"死代码"**——经用户澄清后已撤回删除 |
| **F4** `watch(sessionId)` 监听器泄漏 | TRUE | L104 `watch(sessionId,…)` 无 `onScopeDispose`；`useAgentChat()` 被 6 处组件调用（App/AgentPanel×2/EditorLayout/MonacoEditor/TaskAgentPanel），每次调用注册一个 watcher |
| **F5** resume 路径漏传 `isDone` | TRUE，但**影响被轻微夸大** | L316 resume 确实缺 `isDone`（已补）。但缺它不会"挂起"——`readSseStream` 仍会在后端关闭流时正常退出；`isDone` 只是"done 后提前 cancel 读取器"的优化 |
| **F6** 巨型文件 | TRUE | 全部行数核实无误：pipeline 1200 / splitter 759 / router 721（注册函数 265）/ flatten 699 / reviewer 637；AgentPanel 1584 / App 1483 / MindMapView 1242 / EditorLayout 1064 |
| **F7** 文档领先于代码 | TRUE | `GAP_ANALYSIS.md` 列"无真流式/无 PermissionEnforcer/无自动保存/无系统提示词/路径穿越"——代码均已实现；AGENTS.md 事件清单缺 `tool_denied`(types.py:132)、`usage`(types.py:136)；`usage` 实际在 conversation.py:97/192/196 多处 emit |
| **F8** 脏工作树 | TRUE | `git status --short` = 202 条；10 个已修改 agent/voice 源+测试，180+ 未跟踪截图/文档 |
| **F9** Docker 漂移 | TRUE，且**比报告更严重** | `python/main.py` **实际不存在**（`find` 无结果），故 `Dockerfile` 的 `COPY python/main.py .` 会让镜像**构建直接失败**；compose `main.py` 入口也无法运行。原报告仅说"入口不一致"，低估了 |
| **F10** Provider 层无测试 | TRUE | `python/tests` 无 `openai_compat/anthropic/base/quirks` 的 `.py` 测试，仅 `test_mock_provider.py`。补充：曾有 `test_llm_client_anthropic`/`test_multi_provider_compat` 等，源码已删，仅留 **gitignored** 的 `.pyc`（非仓库问题） |
| **F11** special_elements 无测试 | TRUE | `test_special_elements.py` 源码已删，仅留 gitignored `.pyc`。当前无源测试 |
| **F12** 配置三副本 | TRUE | `config/default.yaml` + `python/config/default.yaml` + `default.local.yaml` 三份并存（AGENTS.md 已警示） |
| 附加 | TRUE | 后端无 `pdb`/`breakpoint()`/裸 `except:`；AGENTS.md 两项具名缺陷（sudo 标志、流式 tool-use）确已修复 |

---

## 3. 发现的不准确项（已更正）

1. **F2 误报**：`plugin/__init__.py` 的 print 是 docstring 示例，非真实代码 → 已在 audit-report.md 标注更正。
2. **F9 低估**：`python/main.py` 不存在，Docker 镜像根本 build 不过 → 已在 audit-report.md 补充，并实际修复。
3. **F5 轻微夸大**：缺 `isDone` 不会"挂起"，只是少一个提前 cancel 优化 → 仍修复，但定性更准确。
4. **F10/F11 框架偏差**：原报告把 `.pyc` 残留当仓库卫生问题；实测 `__pycache__` 被 gitignore、无 `.pyc` 被 git 跟踪 → 属本地构建产物，非仓库问题。当前"无源测试"的结论不变。
5. **F3 过度处置（已撤回）**：原报告把 `AgentCheckpointCard.vue` 当"死代码"删除。经用户澄清——前端正在活跃改进，该组件是**完整实现、尚未接入 `AgentPanel` 的 WIP**（含 Continue/Pause/Revise 与 `decide` emit，并 import 了 `PendingCheckpoint` 类型）。已恢复组件与 `respondCheckpoint` stub 并 amend 进 commit。真正待办是补后端 checkpoint decide 端点 + 在 AgentPanel 挂载该组件，而非删除。教训：对活跃开发中的项目，"当前未被 import" ≠ "死代码"。

> 注：核查中曾怀疑 `MindMapView.vue` 路径错误，复核后确认文件位于 `src/components/MindMapView.vue`、1242 行，**报告行数正确**——是我核查命令用了错路径，非报告错误。

---

## 4. 发展方向评估

**结论：方向正确、优先级合理，与毕设主线（多智能体调度策略）对齐。** 仅需以下小幅修正：

- **S1 范围扩大**：影子后端不止 `src-tauri/python/src/`，整个 `src-tauri/python/` 都应删除（已执行）。
- **S2 范围缩小**：真实 print 仅 `ledger.py` 一处（plugin 是 docstring 误报），无需"全局清理"。
- **S8 补充**：Docker 修复须含"移除 `COPY python/main.py .`"（main.py 不存在），原方向只提了入口与版本。
- **S6（router.py/AgentPanel.vue 拆分）建议独立迭代**：265 行注册函数与 1584 行组件的拆分属高风险重构，不宜在"排雷补洞"批次里仓促进行，应单列任务并配测试。

方向文档无需重写，上述修正已反映在修复记录中。

---

## 5. 逐项修复记录

### ✅ 已修复（本会话）

| 编号 | 修复内容 | 文件 | 验证 |
|------|----------|------|------|
| F1 | 删除孤立影子后端（整个 `src-tauri/python/`，含 1762 行废弃 ReAct `agent.py`）。先 tar 备份到 `/tmp/yanmo-backups/` 再删 | `src-tauri/python/`（已移除） | 真后端 `python/api.py`/`api_factory.py`/`agent_v2` 完好；`resolve_python_dir()` 不依赖该目录 |
| F2 | 移除 `ledger.py:151` 冗余 print（保留同行 `logger.warning`） | `python/src/argument/ledger.py` | `test_ledger.py` 24 passed；语法 OK |
| F3 | **撤回删除**（经用户澄清为 WIP）：恢复 `AgentCheckpointCard.vue`（50 行，完整实现）与 `respondCheckpoint` stub。原"死代码"判断错误——组件是尚未接入 `AgentPanel` 的在制品。真正缺口=后端 checkpoint decide 端点 + 前端挂载，留作 TODO | `src/components/AgentCheckpointCard.vue`（恢复）、`src/composables/useAgentChat.ts`（恢复 stub） | 组件恢复为干净 tracked 状态；`useAgentChat.test.ts` 20 passed |
| F4 | `watch(sessionId)` 加 `onScopeDispose` + `getCurrentScope` 守卫，作用域销毁时停止监听 | `src/composables/useAgentChat.ts` | 20 passed |
| F5 | resume 路径 `readSseStream` 补 `() => streamDone`（与初始路径一致） | `src/composables/useAgentChat.ts` | 20 passed；`streamReader.test.ts` 9 passed |
| F7a | AGENTS.md SSE 事件清单补入 `tool_denied`、`usage` | `AGENTS.md` | — |
| F7b | `GAP_ANALYSIS.md` 顶部加 ⚠️ STALE 通告，指向 AGENTS.md | `python/src/agent_v2/GAP_ANALYSIS.md` | — |
| F7c | audit-report.md 更正 F2（plugin 误报）、F9（main.py 缺失） | `docs/audit-report.md` | — |
| F9 | Dockerfile：移除 `COPY python/main.py .`、LABEL 版本 `0.3.6→0.5.0`；docker-compose：entrypoint `main.py→api.py` + `command: ["--port","18088"]`、更新用法注释 | `Dockerfile`、`docker-compose.yml` | main.py 不存在问题消除；入口与 Dockerfile/healthcheck 一致 |

### ✅ 已提交

- 审计修复已作为干净 commit 提交：`cebcd3a fix(audit): remove shadow backend, plug LLM log leak, wire agent cleanup`（7 文件）。
- **被 gitignore 排除、未进 commit**：`AGENTS.md`（.gitignore:127）、`docs/audit-report.md`（docs/*REPORT*.md）——磁盘修改保留，需用户决定是否 `git add -f` 或放宽 .gitignore。
- **F3 撤回**：初版 commit 曾删除 `AgentCheckpointCard.vue`，经用户澄清为 WIP 后已 amend 恢复（组件 + `respondCheckpoint` stub）。

### ⏸️ 仍未提交（F8 仓库卫生）

- 预存 WIP（`conversation.py`/`sse_adapter.py`/`AgentPanel.vue` 等 16 个 tracked-modified）+ 203 个 untracked（180+ 截图、质量基建、`pnpm-lock.yaml`）未动，待用户决策。
- **建议**：WIP 按原子提交收口；截图归入 `artifacts/` + gitignore；提交 `pnpm-lock.yaml`。

### 🔜 主动延后（需独立迭代，已给出理由）

| 编号 | 延后理由 |
|------|----------|
| F6（router.py 265 行注册函数 / AgentPanel.vue 1584 行拆分） | 高风险重构，触碰 Agent 端点注册与核心 UI；须单列任务、配回归测试，不宜在排雷批次仓促进行 |
| F10（provider 客户端测试） | 需为 21 家厂商写 mock-HTTP 回归，工作量较大，属新增测试而非"修复" |
| F11（special_elements 测试） | 同上，需新建测试套件 |
| F12（配置三副本校验） | 需设计启动期一致性校验，属功能增强 |

---

## 6. 测试结果汇总

| 测试 | 结果 |
|------|------|
| `src/__tests__/useAgentChat.test.ts` | **20 passed** |
| `src/__tests__/streamReader.test.ts` | **9 passed** |
| `python/tests/unit/test_ledger.py` | **24 passed** |
| `ledger.py` 语法检查 | OK |
| 后端无 pdb/裸 except | ✓ |
| 真后端完整性 | `python/api.py`、`api_factory.py`、`agent_v2/router.py` 均在 |

> 未运行完整后端套件（耗时且依赖 WIP 未提交改动）；本会话改动仅触及 `ledger.py` 与 `useAgentChat.ts`，均已通过对应单测。

---

## 7. 产物与备份

- 影子后端删除前已备份：`/tmp/yanmo-backups/src-tauri-python-src-removed-2026-07-20.tar.gz`（121KB）、`src-tauri-python-root-removed-2026-07-20.tar.gz`（25KB）。如需恢复可解压回 `src-tauri/python/`。
- 本核查记录：`docs/audit-verification.md`。
