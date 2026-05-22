# Claude Code for Papers — 改造 TODO

> 本文件防止上下文丢失。记录战略方向、已完成、待完成、关键决策。
> 最后更新：2026-05-22

## 战略定位

**"写论文版的 Claude Code"** — 把科研项目当 workspace，Agent 像 Claude Code 改代码一样
直接读/写文件，替你读文献、写论文、改稿。

- Agent = 脊椎（中枢），其它功能全是工具
- 翻译 → Agent 工具；论证陪练 → Agent 技能（"扮演 Reviewer-2 审我"）；导出 → Agent 工具
- RAG = 长期文献库（历史翻译积累），不再污染每轮 prompt
- 工作区文件（当前项目）→ 用 read_file/grep/str_replace 直接读改

## 已完成

### 里程碑 1 — 主干接线 ✅
- `src/components/AgentPanel.vue:571` — sendMessage 补传第 4 参数 `rootDir.value`，
  workspace_root 接到用户真实项目目录（来自 useFileTree 单例 rootDir）
- `src/components/AgentPanel.vue:577` — attachFile 不再读文件内容，只存路径；
  sendMessage 改为告诉 Agent 路径让它自己 read_file
- `src/components/AgentPanel.vue:421` — 引入 useFileTree，初始化 rootDir + refreshFileTree + workspaceName
- sendMessage 完成后自动调 refreshFileTree() 刷新文件树

### 里程碑 2 — RAG 退出热路径 ✅
- `python/src/agent/agent.py:398-414` — 删除 _build_messages 里 RAG 自动注入块
  （`if self.rag_store is not None: ... rag_auto_inject`）
- `python/src/agent/tools/registry.py:139,158` — search_documents 描述改为
  "检索个人文献库（历史翻译收录），仅跨文献回忆时调用；当前项目用 read_file/grep_files"
- `python/tests/integration/test_agent_integration.py` — 同步修改 RAG 注入测试断言

### UI 适配 ✅
- "知识库" tab 改名为 "文献库"
- docs tab 加副标题"历史翻译自动收录，供 Agent 跨文献检索"
- 空状态文案改为 workspace 感知（有无 rootDir 显示不同提示）
- 新增 workspace 状态栏（绿点 + 项目名 / "未打开项目"）
- TOOL_DESCRIPTIONS 补全 19 个工具描述（read_file/grep/str_replace/git_op 等）

### 验证 ✅
- Python 1752 passed / 11 skipped
- vitest 326 passed / 0 failed
- 手动集成测试：list_directory → read_file → str_replace → undo → grep 全链路通过

---

## 待完成

### 里程碑 1.5 — 越界审批（Claude Code 风格边界）
**决策**：默认严格锁在 rootDir 内；越界需用户审批才执行（和 Claude Code 一致）

需改：
- [ ] `python/routers/agent.py:399` — `SessionConfig(auto_approve=True)` 改为
  对文件操作非全自动（否则审批弹窗永远不触发）
- [ ] `python/src/agent/workspace.py` — `WorkspaceEnv.resolve()` 越界从
  硬抛 WorkspaceViolation 改为返回需审批信号，走 SecurityGate → await_approval
- [ ] 前端 `AgentApprovalInline`（已有）复用，展示越界原因 + 允许/拒绝

### 里程碑 3 — 打磨
- [ ] **第 4 刀**：确认文件树/编辑器在 Agent 写完后正确刷新
  （目前 refreshFileTree 在 sendMessage 完成后调用，但需验证 Monaco 编辑器
  是否需要额外的 reload 信号）
- [ ] **第 5 刀**：清理魔法按钮残留工具
  `python/src/agent/tools/registry.py` 里的 polish_text/summarize_text/
  expand_section/generate_outline — grep 确认无其他调用方后删除
  （format_bibliography 有实用价值，保留）

### 更长远
- [ ] 论证图（Toulmin 提取）→ Agent 的"符号表"：让 Agent 能通过论证图导航论文结构
- [ ] Citation 图 → Agent 的"import 图"：跨文献导航
- [ ] "帮你做实验" / 接入 VSCode：等核心 Agent 闭环稳定后再扩展

---

## 关键设计决策（已拍板，不要反悔）

| 决策 | 内容 |
|------|------|
| workspace 边界 | 严格锁在 rootDir 内，越界需用户审批 |
| RAG 职责 | 长期文献库（历史翻译），不自动注入，Agent 按需调 search_documents |
| 文件附件 | 只传路径，Agent 自己 read_file，不塞内容进 prompt |
| 魔法按钮 | 逐步降级为 Agent 技能，最终清理冗余工具函数 |
| 思维导图 | 与主线无关，降级到二级功能，暂不扩展 |

---

## 关键代码位置速查

| 位置 | 作用 |
|------|------|
| `src/components/AgentPanel.vue:571` | workspace_root 传入点 |
| `src/composables/useFileTree.ts:5` | rootDir 单例（项目根） |
| `src/composables/useAgentChat.ts:147` | sendMessage 函数签名（第 4 参数 workspaceRoot） |
| `python/routers/agent.py:262` | _create_agent：workspace_root 解析逻辑 |
| `python/src/agent/tools/registry.py:486` | workspace_root 回退到沙箱目录 |
| `python/src/agent/workspace.py` | WorkspaceEnv.resolve() 越界保护 |
| `python/src/agent/session.py:399` | SessionConfig(auto_approve=True) ← 1.5 刀改这里 |
| `python/src/agent/agent.py:398` | _build_messages（RAG 注入已删） |
