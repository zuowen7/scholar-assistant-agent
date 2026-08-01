# Scholar Assistant 质量改进提示词手册

这份文档用于指导 AI/Codex/Claude 类 agent 系统化改进 Scholar Assistant 的可靠性、安全性和可用性。

核心原则：不要让 agent “优化项目”，而是让它在一个明确质量维度上，交付可验证改进。

## 使用方式

每次开新线程或派发任务时，按下面顺序选择提示词：

1. 不知道问题在哪里：用“总控审计提示词”。
2. 怀疑会丢文件、越权、泄漏密钥：用“P0 安全与数据保护审计”。
3. Agent 卡死、审批异常、写文件不同步：用“Agent V2 可靠性审计”。
4. 用户不知道怎么用、失败后不知道怎么办：用“可用性评审”。
5. 已经确认一个问题要修：用“修复执行提示词”。
6. 准备发布：用“发布前质量门禁提示词”。

所有提示词都要求当前代码和命令结果优先，文档只作为导航。

## 总控审计提示词

```text
你在 D:\pycharm_study\translator 工作。不要被文档描述误导，当前代码、测试、运行结果优先。

目标：审计 Scholar Assistant 的可靠性、安全性和可用性风险，不要直接改代码。

产品定位：
Scholar Assistant / 研墨 是隐私优先的学术写作工作台，可以把用户论文项目当 workspace，由 Agent 直接读取和修改草稿、PDF、BibTeX、笔记、导出文件和数据文件。

优先级定义：
- P0：可能丢用户文件、覆盖未保存内容、越权读写、泄漏 API key/论文内容、审批绕过、发布包夹带用户运行时数据。
- P1：核心链路卡死、SSE 状态错乱、Agent/翻译/导出/启动失败不可恢复、前后端协议不一致。
- P2：体验不清、提示差、性能慢、入口混乱、错误信息不可操作。

工作规则：
1. 先审计，不要直接改代码。
2. 每个问题必须给证据：文件路径、函数/组件、触发路径、可能后果。
3. 不确定就标记为“待验证”，不要脑补。
4. 只相信当前代码、测试和可复现命令；README/AGENTS/CLAUDE 只做线索。
5. Agent V2 是当前架构，不要复活旧 agent/ReAct 路径。
6. AI Panel 预设和 AgentPanel 职责分开评估，不要混成一个入口。
7. 配置、API key、provider、路径、导出相关改动必须考虑用户确认和敏感信息脱敏。

输出：
1. 缺陷登记表：ID | 等级 | 类别 | 现象/风险 | 证据 | 推荐测试 | 推荐修复顺序。
2. P0/P1 优先修复队列。
3. 需要手动验证的桌面场景。
4. 暂不建议修的事项和原因。
```

## P0 安全与数据保护审计

```text
审计 Scholar Assistant 的 P0 风险，范围只看可能造成数据损坏、越权、泄密或发布泄漏的问题。

重点资产：
- 用户论文项目文件：draft、PDF、BibTeX、notes、exports、data。
- API key/provider 配置。
- Agent session、RAG 数据、日志、导出文件。
- 本地 shell、文件系统权限、Tauri WebView 能力。

重点攻击面：
- python/api_factory.py
- python/routers/*.py
- python/src/agent_v2/runtime/*
- python/src/agent_v2/tools/*
- src/composables/useAgentChat.ts
- src/composables/useEditor*.ts
- src/components/AgentPanel.vue
- src-tauri/src/main.rs
- src-tauri/tauri.conf.json
- .github/workflows/release.yml
- .gitignore

必须检查：
1. 文件读写是否严格限制在选定 workspace。
2. 任何 Agent 写入是否可能覆盖未保存 Monaco tab。
3. approval 是否可能串 session、被绕过、超时后误执行。
4. run_command 是否可能绕过 workspace 和权限限制。
5. 日志、异常、SSE、配置接口是否可能输出 API key 或本地路径敏感信息。
6. release workflow 是否会把 runtime data、用户项目路径、session、db、logs 打进包。
7. Tauri CSP、assetProtocol、shell open、commands 是否过宽。

输出 STRIDE 风格表格：
威胁 | 入口 | 影响 | 现有防护 | 缺口 | 等级 | 推荐测试 | 推荐修复。

不要修改代码。只给证据和修复顺序。
```

## Agent V2 可靠性审计

```text
审计 Agent V2 文件读写、审批、SSE、session 可靠性。

默认路径：
- 前端：src/composables/useAgentChat.ts, src/components/AgentPanel.vue, src/components/AgentApprovalInline.vue, src/components/EditorLayout.vue, src/composables/useEditorTabs.ts
- 后端：python/src/agent_v2/router.py, python/src/agent_v2/runtime/conversation.py, python/src/agent_v2/runtime/session_control.py, python/src/agent_v2/runtime/permissions.py, python/src/agent_v2/tools/registry.py

重点检查：
1. await_approval、approval_received、tool_name、tool_result、checkpoint 的 payload 是否前后端一致。
2. ProviderResponse.blocks 里的 ToolUseBlock 是否稳定被提取和逐个执行。
3. write_file/str_replace 后 checkpoint 是否一定包含足够信息让前端刷新。
4. 当前打开且 dirty 的 Monaco tab 是否不会被 Agent 静默覆盖。
5. session 切换、abort、resume、fork 后 pendingApproval 是否不会串号。
6. approval 超时/拒绝/allow_once/allow_session 是否都能结束流并留下可解释状态。
7. run_command 输出截断、错误码、cwd、路径校验是否不会误导模型继续乱试。

输出：
- 问题清单，按 P0/P1/P2。
- 每个问题的证据路径和触发链路。
- 应新增的前端测试、后端测试、协议测试。
- 推荐第一批最小修复。

不要直接改代码，除非用户明确要求修复某个具体问题。
```

## 可用性评审

```text
从第一次使用者和高压写论文用户的角度评审 Scholar Assistant。

不要只评价界面好不好看，重点看用户能否顺利完成任务。

核心任务：
1. 创建或打开论文项目。
2. 写/改 draft/main.md。
3. 让 Agent 读取项目并修改文件。
4. 使用 Agent 面板做选中文本润色/扩写/翻译。
5. 建立论证账本并运行 Reviewer-2。
6. 翻译 PDF 并导出 Word/Markdown。
7. 配置云端 provider/API key 或本地 Ollama。
8. 后端离线、模型超时、导出工具缺失时恢复。

必须检查：
1. 用户是否知道第一步该做什么。
2. 单一 Agent 面板内的对话、预设编辑和文件操作职责是否清楚。
3. 失败提示是否告诉用户下一步怎么做。
4. 设置项是否可能让用户误操作，尤其 API key、provider、base_url、model、proxy、路径。
5. 操作成功/失败/进行中状态是否明确。
6. 是否存在“看起来成功，实际没有保存/刷新/导出”的假成功。

输出：
- 5 个最大 UX 阻塞。
- 每个阻塞的用户场景。
- 推荐文案或交互调整。
- 是否需要代码修改。
- 推荐手动验证步骤。
```

## 修复执行提示词

```text
从缺陷登记表里选择最高优先级的一个 P0/P1 问题修复。

任务：
[填入一个具体问题，不要一次修多个]

范围：
[填入允许修改的文件/模块]

禁止：
1. 不要做无关重构。
2. 不要复活旧 agent/ReAct 路径。
3. 不要重新引入第二套 AiPanel 或独立 Agent 状态。
4. 不要绕过既有 SSE/checkpoint/approval 协议。
5. 不要提交或打印 API key、用户本地隐私路径、运行时数据。

执行规则：
1. 先写或定位失败测试，证明问题存在。
2. 再做最小代码修改。
3. 如果涉及跨层协议，必须同时检查后端 emit 和前端 switch/handler。
4. 如果涉及文件写入，必须验证 workspace boundary 和 dirty tab 保护。
5. 如果涉及配置或 provider，必须验证脱敏、保存位置和用户确认。

验证要求：
- 运行最窄相关测试。
- 如果涉及共享协议/工具/session/route，再运行更宽测试。
- 给出桌面手动验证步骤：点哪里、应该看到什么、什么代表仍然坏。

最终输出：
1. 根因。
2. 修改了哪些文件。
3. 新增/修改了哪些测试。
4. 命令验证结果。
5. 手动验证步骤。
6. 剩余风险。
```

## 发布前质量门禁提示词

```text
做 Scholar Assistant 发布前质量门禁审计。不要发布，不要打 tag，除非用户明确要求。

检查范围：
1. git status 和未跟踪文件。
2. 版本号一致性：package.json, python/src/_version.py, src-tauri/tauri.conf.json。
3. release workflow：.github/workflows/release.yml。
4. runtime data 和 secret 泄漏：config、python/config、python/data、logs、sessions、tm.db、chromadb、src-tauri/python-dist、dist/build。
5. 本地验证命令和 CI 命令是否一致。
6. README/安装说明是否与当前代码版本一致。

建议命令：
- git status --short --branch
- npm run build
- npx vitest --run
- npx vue-tsc --noEmit
- cd python && pytest tests/ -q --tb=short
- cd python && python scripts/ci_test_quality.py

输出：
- 可发布 / 不可发布结论。
- 阻塞项和证据。
- 非阻塞风险。
- 需要清理的文件。
- 如果要发布，推荐的下一步命令。

不要自行推 tag、push、publish。
```

## 前端复杂度与性能提示词

```text
审计 Scholar Assistant 前端复杂度和构建体积。

重点：
1. 大组件：App.vue, TranslateView.vue, AgentPanel.vue, EditorLayout.vue, MindMapView.vue。
2. 大 composable：useTranslate.ts, useAgentChat.ts, useEditor*.ts, useArgumentCompanion.ts。
3. Vite build 警告：monaco、workers、动态 import 与静态 import 混用。
4. 状态是否集中在难以测试的组件里。
5. 拆分是否会破坏 SSE、Monaco、Tauri、i18n 或 Agent 协议。

输出：
- 最大 5 个复杂度热点。
- 每个热点的风险。
- 推荐拆分边界。
- 必须先补的测试。
- 不建议现在拆的部分和原因。

不要直接重构。先给可分批执行的计划。
```

## 缺陷登记模板

```markdown
| ID | 等级 | 类别 | 现象/风险 | 证据 | 推荐测试 | 推荐修复 | 状态 |
|----|------|------|-----------|------|----------|----------|------|
| Q-001 | P0 | 数据安全 | Agent 可能覆盖未保存 tab | 待验证：src/... | 前端 dirty tab 测试 + 手动验证 | 写入前检查 dirty tab 并提示 | 待验证 |
```

类别建议：

- `data-safety`：文件覆盖、路径越界、运行时数据。
- `secret-privacy`：API key、日志、配置、发布包泄漏。
- `agent-protocol`：SSE、approval、checkpoint、tool metadata。
- `runtime-stability`：后端启动、端口、模型超时、导出工具。
- `ux-recovery`：用户无法理解状态或恢复失败。
- `release-governance`：CI、打包、版本、仓库卫生。
- `performance`：冷启动、bundle、长任务、内存。

## 用户 bug 描述模板

给 AI 或自己登记 bug 时，不需要写得专业，按这个格式即可：

```text
场景：
我正在做什么？

现象：
屏幕上发生了什么？有没有卡住、没刷新、报错、结果不对？

期望：
我觉得它应该怎样？

危险：
它会不会丢文件、泄漏信息、误导用户、让用户无法继续？

复现：
能稳定复现吗？如果不能，大概发生在什么条件下？

证据：
截图、日志、文件路径、测试命令、报错文本。
```

## 手动验证格式

每个 P0/P1 修复最后都要给手动验证步骤：

```text
验证场景：
[一句话说明]

步骤：
1. 打开应用并进入 [模式/页面]。
2. 执行 [具体操作]。
3. 观察 [具体 UI/文件/日志]。

应该看到：
- [成功状态]
- [文件或界面变化]
- [错误被正确阻止/提示]

如果仍然坏：
- [坏的可见信号]
- [下一步要抓的日志或文件]
```

## 推荐改进节奏

第一轮只做审计，不改代码：

1. 总控审计提示词。
2. P0 安全与数据保护审计。
3. Agent V2 可靠性审计。
4. 可用性评审。

第二轮开始修复：

1. 先修 P0 数据安全和 secret/privacy。
2. 再修 P1 Agent/translation/export 核心链路。
3. 然后处理 UX recovery。
4. 最后处理性能和组件拆分。

每批修复都必须有：

- 一个明确问题。
- 一个失败测试或可复现证据。
- 一个最小修复。
- 一组命令验证。
- 一组桌面手动验证步骤。

## 交给 Agent 的一句话规则

```text
不要泛泛优化；按证据发现一个风险，按测试修掉一个风险，最后给我能在桌面上复验的步骤。
```
