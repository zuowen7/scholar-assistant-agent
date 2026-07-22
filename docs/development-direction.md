# 研墨 / Scholar Assistant — 发展方向与优化路线图

> 配套文档：见 `docs/audit-report.md`（现状审计与风险清单）
> 定位：基于审计发现，给出"Agent 应用"端到端优化路线，并对齐既定的毕设方向
> 日期：2026-07-20

---

## 0. 战略定位（Strategic Position）

研墨的本质是**"以论文为中心的多智能体学术写作工作台"**。毕设/申报既定方向为：

> **基于小样本增强的学术写作多智能体调度策略研究与实现**

这一定位与产品架构天然契合：Agent V2 已经是"能读写工作区文件、可调工具、可派生子代理"的运行时，下一步不是重写，而是**把单 Agent 循环升级为"多角色调度"**，并把调度策略本身作为可比较、可评估的研究对象。

**安全表述原则**（来自 AGENTS.md 毕设上下文）：
- 把研墨定位为"学术写作助手的先验原型与实验平台"，而非成熟商业平台。
- 论文聚焦：多智能体角色建模、任务路由数据、调度策略对比、系统集成、评估。
- 轻量模型路由是**候选实验策略**，不是硬性成功条件。
- 正式文案避免承诺固定"混合架构"；应写"对比 规则路由 / 提示路由 / 轻量模型路由，再按准确率、成本、时延、稳定性择优"。
- 候选智能体角色：文献检索、写作/编辑、翻译精读、论证/审稿、结构规划、格式/导出、项目/文件、设置/配置。
- 设置/配置（provider、API Key、路径、导出、模型）变更需用户确认。

---

## 1. 优化原则（贯穿全程）

1. **先排雷、后加功能**：影子后端与日志泄漏是阻塞项，必须在任何新功能之前清除。
2. **契约先行**：SSE 事件名、`tool_name`、审批/checkpoint 负载、ledger `?doc_id=` 路由，前后端必须同步且文档化。
3. **小步原子提交**：当前 `refactor/reference-driven-ui` 分支 202 条脏变更，须按功能原子收口，避免集成覆盖滞后。
4. **测试跟着危险走**：provider 客户端、checkpoint 决策、resume 路径是高风险面，优先补测试。
5. **文档即契约**：删除/重写 `GAP_ANALYSIS.md`，让文档回到"代码事实的真相"。

---

## 2. 短期（1–2 个迭代 / 约 2–4 周）：排雷 + 补洞

> 目标：消除 P0/P1 风险，让"Agent 应用"端到端可用、可维护。

| 编号 | 任务 | 对应审计 | 验收标准 |
|------|------|----------|----------|
| S1 | **删除影子后端** `src-tauri/python/src/`（含 1762 行废弃 ReAct `agent/agent.py`），并在 `.gitignore` 加注释说明现行构建走 `scripts/build-python.cjs` | F1 | 工作区无旧后端树；现行 `python-dist` 构建不受影响 |
| S2 | **移除 `argument/ledger.py:151` 原始 LLM 打印**，改为默认关闭的 `logger.debug`；全局清理 `python/src` 其余 `print(` | F2 | `python/src` 无非必要 print；敏感内容不进日志 |
| S3 | **打通 checkpoint 决策**：新增后端 `POST /api/agent/v2/checkpoint/decide`，前端 `respondCheckpoint` 真实回传；或删除 `AgentCheckpointCard.vue` 死代码并改文档 | F3 | checkpoint 的 continue/pause/revise 真实生效（二选一，不可留假功能） |
| S4 | **修复 `useAgentChat.ts` 监听器泄漏**：用 `onScopeDispose` 或 `watch` 返回值在卸载时停止 `watch(sessionId)` | F4 | AgentPanel 反复挂载无 watcher 累积（可用 DevTools 内存快照验证） |
| S5 | **统一 resume 路径 SSE 参数**：`readSseStream` 两调用点签名一致，resume 可正确 `cancel` | F5 | resume 后流正常结束，无挂起 |
| S6 | **拆分 `agent_v2/router.py`**：把 265 行 `register_agent_v2_routes` 按端点组（chat/stream、session、approval、checkpoint、tools、skills/hooks）拆成子模块 | F6 | 单文件 < 400 行；行为不变（保留测试） |
| S7 | **收口当前 WIP**：把 `conversation.py`/`sse_adapter.py` 等 10 个脏文件按原子提交；把 180+ 未跟踪截图/中间文档移出仓库或归入 `artifacts/` + gitignore；提交 `pnpm-lock.yaml` | F8 | 工作树干净；仅有意的未跟踪项 |
| S8 | **修复 Docker 漂移**：统一入口为 `api.py`；`Dockerfile` 版本 LABEL 动态读取 | F9 | 容器可正常启动且版本正确 |

**短期限量指标**：P0 风险 = 0；`useAgentChat` 无监听器泄漏；checkpoint 决策可用或已诚实下线。

---

## 3. 中期（约 1–2 个月）：Agent V2  hardening + 多智能体调度

> 目标：把"单循环 Agent"升级为"可调度的多角色 Agent 系统"，并把调度策略做成可评估的研究对象。

### 3.1 Agent 运行时加固
- **Provider 客户端测试**（F10）：为 `openai_compat.py` / `anthropic.py` / `quirks.py` 补 mock-HTTP 回归测试，覆盖 21 家厂商的流式与 quirks 自动探测。
- **special_elements 测试**（F11）：补 parser/tools/types/vision 底层依赖的单元测试。
- **`AgentPanel.vue` 拆分**（F6）：拆出会话列表、审批卡片、工具调用渲染、流式消息等子组件，目标单文件 < 600 行。
- **SSE 契约文档化**（F7）：把 `tool_denied` / `usage` 补入事件清单；校准测试数量表述；删除/重写 `GAP_ANALYSIS.md`。

### 3.2 多智能体调度（毕设核心）
- **角色建模**：在 `agent_v2/` 内引入角色注册（literature / writing / translation / argument / structure / format / project / settings），复用现有 `ToolRegistry` 与 `run_sub_agent` 预设。
- **调度策略三选一对比**（研究主线）：
  1. **规则路由**：基于关键词/文件类型/意图分类器的硬规则分发。
  2. **提示路由**：用轻量模型做意图分类后派发（复用 `usage`/`ModelPricing` 做成本核算）。
  3. **轻量模型路由**：用本地 `qwen3:8b` 做路由决策，重活交给云端强模型。
- **可观测性**：复用 `UsageTracker` / `PromptCacheTracker` 产出"每策略 准确率 / 成本 / 时延 / 稳定性"四维指标，作为论文评估数据来源。
- **调度数据沉淀**：把真实路由决策写入 `data/*.jsonl`（仓库已有 40+ 条 jsonl），形成"小样本增强"的训练/评估语料。

### 3.3 RAG / 库升级（B- → B+）
- 当前 `rag_search` 为按需检索；建议补"项目级向量库自动构建 + 增量更新"，并把翻译 ingest 与 RAG 统一到同一 ChromaDB 集合，支撑多智能体共享记忆。

---

## 4. 长期（3–6 个月）：平台化与评估

- **调度策略评估框架**：建立离线评测集（任务→最优角色映射），对三种路由策略做对照实验，输出论文所需的图表与显著性。
- **配置单源化**（F12）：启动期校验 `config/default.yaml` ↔ `python/config/default.yaml` ↔ `default.local.yaml`，消除漂移。
- **跨平台与发布**：确认 Tauri 2 在 Windows/macOS/Linux 的一致性；把 Docker 部署纳入 CI；版本 LABEL 自动化。
- **毕设产出物对齐**：以"多智能体调度策略"为主线，将研墨作为实验平台，产出角色建模、路由数据集、策略对比、系统集成与评估五部分。

---

## 5. 优化建议清单（按优先级）

**P0（阻塞，立即）**
- [ ] S1 删除影子后端 `src-tauri/python/src/`
- [ ] S2 移除 `ledger.py` 原始 LLM 打印

**P1（本迭代）**
- [ ] S3 打通或下线 checkpoint 决策
- [ ] S4 修复 `useAgentChat` 监听器泄漏
- [ ] S5 统一 resume SSE 参数
- [ ] S6 拆分 `agent_v2/router.py`
- [ ] S7 收口 WIP + 仓库卫生
- [ ] S8 修复 Docker 入口/版本漂移

**P2（下阶段）**
- [ ] Provider 层测试（F10）
- [ ] special_elements 测试（F11）
- [ ] `AgentPanel.vue` 拆分
- [ ] SSE 契约与文档统一（F7）
- [ ] RAG 项目级向量库（B- → B+）
- [ ] 配置单源校验（F12）

**研究主线（贯穿）**
- [ ] 多智能体角色注册与 `run_sub_agent` 升级
- [ ] 规则/提示/轻量模型 三路由策略实现
- [ ] 四维指标采集（准确率/成本/时延/稳定性）
- [ ] 路由数据集沉淀到 `data/*.jsonl`

---

## 6. 度量指标（用于跟踪进展）

| 指标 | 当前 | 短期目标 | 中期目标 |
|------|------|----------|----------|
| P0 风险数 | 2 | 0 | 0 |
| 巨型文件（>1000 行）数 | 后端 1 / 前端 4 | 后端 1 | 前端 ≤ 2 |
| `python/src` 非必要 print | 2 | 0 | 0 |
| 工作树脏变更 | 202 | 0（原子提交） | 0 |
| Provider 层测试覆盖 | 0 | — | > 0（21 厂商冒烟） |
| checkpoint 决策可用 | stub | 可用/诚实下线 | 可用 |
| 路由策略对照实验 | 0 | — | 3 策略 + 评估集 |

---

## 7. 给毕设/申报文案的建议口径

- 平台定位：**"学术写作助手的先验原型与多智能体实验平台"**，不称成熟商业平台。
- 技术主线：**多智能体角色建模 + 调度策略对比（规则/提示/轻量模型路由）+ 四维评估**。
- 不承诺固定"混合架构"；写"对比后择优"。
- 平台选项建议 B01/B02/B03/B05；除非范围明确扩展到未来学习中心集成，否则不选 B08。
- 设置/配置变更（provider/API Key/路径/导出/模型）需用户确认——这点既是产品契约，也是论文中"可控可信 Agent"的卖点。

---

## 8. 一句话方向

**先把雷排干净、把洞补上，让 Agent 应用端到端可信；再用既有的 Agent V2 运行时把"单循环"升级为"多角色调度"，把调度策略本身做成可量化评估的毕设主线。**
