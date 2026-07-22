# 前端架构 Review 报告

> 评审人：Senior Developer　|　日期：2026-07-20　|　基于实际代码扫描

## 一、现状评估（8 维度，满分 10）

| 维度 | 分数 | 依据 |
|------|------|------|
| 设计系统 | 9 | `tokens.css` 双主题（墨色/素纸）+ glass + elevation + reduced-motion；`transitions.css` 8 种命名过渡 + 墨韵/笔触/宣纸主题动效 |
| UI kit | 8.5 | 16 个 `Ui*` 原子组件 + `shell/` 布局层；`UiButton` 7 variant + loading 呼吸动画 + focus-visible 无障碍 |
| 测试覆盖 | 8 | 52 个测试文件，覆盖 UI kit / composables / 业务组件 / voice 5 层 / 工具函数 + integration |
| composable 抽象 | 8 | useAgentChat/useEditor/useEditorTabs/useTranslate/useMindMap 职责清晰；WIP 在把副作用从组件下沉 |
| 架构分层 | 8 | `shell/`（布局）/ `ui/`（原子）/ `argument/` + `mindmap/`（业务域）边界清晰 |
| **文件健康度** | **4** | **6 个 1000+ 行巨型文件**（见下） |
| **性能可观测** | **5** | KeepAlive 内存、大列表虚拟化、bundle 分包均未验证 |
| 类型安全 | 7 | strict 开启；noUnusedLocals 等刚渐进收紧；测试代码已纳入 tsconfig.test.json |

## 二、当前优化阶段（WIP 揭示）

工作区未提交改动指向一个清晰方向：**Agent checkpoint → 编辑器联动加固**。

- `AiPanel.vue`：把原来内联的 `tab.content = cpContent` + `setContent()` 操作，下沉到 `useEditorTabs.applyExternalFileUpdate()`——一个 4 状态机（`not-open` / `conflict` / `unchanged` / `applied`），并加了 `content_truncated` 跳过 + 冲突 toast。
- `useAgentChat.test.ts`：新增多文件 checkpoint 流测试 + 开放式 SSE 测试工具。

**判断**：这是"Agent 写文件 → 编辑器正确刷新"链路的收尾。方向正确——副作用从组件挪到 composable，组件只管 UI 反馈。建议先把这条 WIP 收尾提交，再进入下面的重构。

## 三、核心问题清单

### 🔴 P0 — 6 个巨型文件

| 文件 | 行数 | 职责过载点 |
|------|------|-----------|
| `AgentPanel.vue` | 1584 | 窗口生命周期 + 拖拽浮动 + 语音 + 4 tab（chat/docs/templates/sessions）+ 聊天渲染 |
| `App.vue` | 1483 | 30+ import；背景层 + 拖拽 + recovery + 模式切换 + Settings 编排 + voice + agent + editor + project |
| `MindMapView.vue` | 1242 | 画布 + 节点 + 工具栏 + AI hints + 布局 |
| `EditorLayout.vue` | 1064 | 26 import；12+ 子组件总装 + 10+ composable 编排 |
| `AppTopBar.vue` | 907 | 顶栏聚合过多状态 |
| `AiPanel.vue` | 817 | AI edit + complete + citation + voice |

**影响**：维护成本高、热更新慢、新人上手难、测试难聚焦。

### 🟠 P1 — App.vue 上帝组件

`App.vue` 同时承担：背景视频/壁纸层、全局拖拽上传、翻译 recovery banner、模式切换（translate/editor/argument）、SettingsCenter 20+ props 编排、voice router、agent chat toggle、editor cleanup、project recent、UI zoom。这是典型的"方便起见先放这"累积出来的上帝组件。

### 🟡 P2 — legacy tokens 双命名并存

`tokens.css` 末尾有 "Legacy short aliases" 和 "Legacy shadow" 段：
- `--accent` / `--c-accent` 两套并存
- `--surface` / `--c-surface-*` 两套并存
- `--shadow-sm/md/lg` 与 `--elevation-1/2/3/4` 两套并存

**影响**：新代码不知道用哪套，风格不统一；删旧令牌时不敢动（不知道还有谁在用）。

### 🟡 P2 — 性能未验证

- `KeepAlive` 包裹 3 个模式视图，长时间使用是否内存累积未测
- `MindMapView` / `ArgumentMapCanvas` 节点多时是否虚拟化未知
- bundle 未做分包分析，Monaco/VueFlow/大依赖是否按需加载未知

## 四、4 阶段迭代计划（按投入产出比排序）

### Phase 1 · 拆 App.vue（目标 1483 → ~500 行）

把 App.vue 拆成"编排器 + 子模块"：

| 抽离项 | 去向 |
|--------|------|
| 背景视频/壁纸层 | `composables/useBackground.ts` + `<BackgroundLayer>` 子组件 |
| 全局拖拽上传 | `composables/useDragDrop.ts` |
| recovery banner | `<RecoveryBanner>` 子组件 |
| SettingsCenter 编排 | `composables/useSettings.ts`（收拢 20+ props 的获取/设置） |
| UI zoom | 已有逻辑收进 `useUiZoom` |
| App.vue 剩余 | 只保留模式路由 + AppShell 编排 + 顶层生命周期 |

**验收**：App.vue < 500 行；`npm run check` 通过；现有测试不回归。

### Phase 2 · 拆 AgentPanel.vue（目标 1584 → ~600 行）

| 抽离项 | 去向 |
|--------|------|
| 窗口/浮动/拖拽 | `composables/useAgentWindow.ts`（openAgentWindow/closeAgentWindow/toggleFloat/拖拽） |
| chat tab | `<AgentChatTab>` 子组件 |
| docs tab | `<AgentDocsTab>` 子组件 |
| templates tab | `<AgentTemplatesTab>` 子组件 |
| sessions tab | `<AgentSessionsTab>` 子组件（已有 AgentSessionList，进一步收口） |
| 语音逻辑 | 外移到 `useSpeechRecognition`（已有） |
| AgentPanel.vue 剩余 | 容器 + tab 切换 + 窗口状态 |

**验收**：AgentPanel.vue < 600 行；AgentApprovalInline/AgentSessionList 行为不变；voice 测试通过。

### Phase 3 · 清债审计

1. **legacy tokens 收敛**：全仓 grep `--accent[^-]` / `--surface[^-]` / `--shadow-`，逐个替换到 `--c-*` 命名，最后删除 tokens.css 的 Legacy 段。
2. **KeepAlive 内存审计**：在长会话下用 DevTools Memory 录制，确认 translate/editor/argument 切换不泄漏。
3. **大列表虚拟化排查**：MindMapView / ArgumentMapCanvas / FileTree 节点 > 200 时是否需要虚拟滚动。

**验收**：tokens.css 无 Legacy 段；长会话内存曲线平稳；大列表 60fps。

### Phase 4 · 性能收割

1. **bundle 分包**：`vite build --report`（或 rollup-plugin-visualizer），确认 Monaco / VueFlow / Tauri API 是否按需加载。
2. **路由级懒加载**：TranslateView / ReviewerWorkspace 用 `defineAsyncComponent`。
3. **Monaco worker**：确认 web worker 配置正确，不阻塞主线程。
4. **目标**：LCP < 1.5s，交互 60fps。

**验收**：bundle 主 chunk < 500KB（gzip）；LCP 达标；首屏可交互 < 1.5s。

## 五、迭代节奏建议

- 每阶段独立可交付，不阻塞功能开发
- 每拆一个文件：先补测试锁定行为 → 拆 → 跑 `npm run check` → 提交
- Phase 1、2 是"结构优化"，肉眼可见收益；Phase 3、4 是"体验优化"，需要量化指标
- 建议 Phase 1 优先——App.vue 是入口，拆完后面所有工作都受益
