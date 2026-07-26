# 前端一致性收口 · 优化报告(待执行)

> 范围:Scholar Assistant(研墨)Vue 3 前端
> 目标:在不推倒现有设计系统的前提下,收口"手写 UI 与原语不一致、硬编码颜色绕过 token、全局焦点环缺失"三类问题,使全应用在暗/亮双主题下"像一个 App",并补齐键盘可达性。
> 状态:持续增量收口。2026-07-26 已完成一轮生产入口复核与高优先级交互修复；仍不代表全部页面完成桌面端视觉验收。

## 2026-07-26 当前代码复核

本轮只处理当前代码可以直接证明的问题，保留现有暖墨/纸张视觉方向、页面结构和常驻 AI 面板，不执行 `ui-redesign-proposal.md` 中的冷色 Atlas 换肤。

| 当前问题 | 用户影响 | 处理 |
|---|---|---|
| 首次从翻译页进入思维导图时，`shell-workspace-mode` 事件可能早于异步 `EditorLayout` 挂载 | 第一次点击可能落到写作页，需要再次点击 | 将目标工作区写入 `useAppMode` 的共享状态；`EditorLayout` 挂载后读取并执行目标模式，同时保留事件路径 |
| 当前文档关闭逻辑和确认弹窗存在，但页头入口缺失 | 用户无法从写作页触发安全关闭 | 恢复页头“关闭当前文档”按钮；未保存文档继续走确认弹窗 |
| “有未保存修改”使用 success 状态 | 状态颜色与含义相反，容易误判 | 未保存状态改用 warning，已保存状态保留 success |
| 面板调宽函数、状态和样式存在，但没有任何模板入口 | 形成不可达半成品并增加维护噪声 | 删除无入口的 resize 实现；保留当前响应式固定宽度策略 |
| `useAppWindow` 在普通浏览器中无条件调用 Tauri 窗口 API | `npm run dev` 页面启动期抛错，Vue 根节点无法挂载，只显示背景 | 仅在检测到 Tauri internals 时获取原生窗口；浏览器模式保留安全空操作，并增加双环境回归测试 |

验证边界：本轮补充了共享工作区目标、浏览器/Tauri 窗口边界的回归测试，并执行前端类型检查、Vitest、格式检查和生产构建；同时用 Edge 实际渲染普通浏览器入口。真实 Tauri 多尺寸视觉验收仍需单独进行，未据此把所有页面标记为完成。

---

## 1. 当前状态评估(已具备的资产)

设计系统底子扎实,打磨应做"收口"而非"重做":

- **令牌系统完整** `src/styles/tokens.css`:墨石双主题、spacing/radius/typography/motion 全量变量;动效曲线 `src/styles/transitions.css`(brush / ink-bleed / spring)且带 `prefers-reduced-motion` 降级。
- **UI 原语齐备** `src/components/ui/`:`UiButton`(7 种 variant)、`UiCard`(surface/glass/interactive)、`UiIconButton`、`UiSegmented`、`UiPopover`、`UiSelect` 等。
- **高感知界面已精致**:`InkBrushLoader`(研字红印 + 扫描进度)、`EditorWelcome`(水印 + hero 立柱生长 + 错峰入场)、`AppTopBar`(统一用原语)、`useAppTheme.ts`(View Transition 圆形 clip 主题切换)。
- **全局交互工具类**:`transitions.css` 已提供 `.u-interactive`(hover 抬升 + active 回弹)、`.anim-fade-in-up`、`.anim-stagger` 等。

**结论**:表层体验已达 premium,缺口集中在"一致性契约"——同一类交互在不同组件里样式/状态/可达性各写各的。

---

## 2. 关键发现(按杠杆排序)

### 发现 A — 全局焦点环(focus-visible)大面积缺失【最高优先级 · a11y + 一致性】

证据:
- 组件内 `:focus-visible` 仅出现 **37 次**,而手写 `<button>` 有 **253 个**(不含 `ui/` 定义)。
- 以下 **29 个含 `<button>` 的文件完全没有 `:focus-visible`**(键盘用户 Tab 时无可见焦点):
  - `AgentCheckpointCard.vue`、`AppTopBar.vue`
  - `argument/ArgEdge.vue`、`argument/ArgInspector.vue`、`argument/ArgSourcePane.vue`、`argument/ArgumentMapMini.vue`、`argument/ArgumentMapView.vue`、`argument/CompanionPanel.vue`、`argument/LedgerList.vue`、`argument/ReviewerWorkspace.vue`
  - `CommandPalette.vue`、`ComplianceModal.vue`、`DebugPanel.vue`、`DocumentOutline.vue`、`EditorLayout.vue`、`EditorWelcome.vue`、`FileTree.vue`
  - `mindmap/MindEdge.vue`、`mindmap/MindMapCanvas.vue`、`MindMapAiHints.vue`、`MindMapFloatingToolbar.vue`、`MindMapView.vue`、`MonacoEditor.vue`
  - `shell/AppShell.vue`、`shell/AppSidebar.vue`、`shell/RecentFiles.vue`、`shell/SegmentedControl.vue`
  - `TaskAgentPanel.vue`、`WorkflowList.vue`

**影响**:键盘可达性不符 WCAG 2.1 AA(2.4.7 Focus Visible);且焦点态缺失让"交互元素"在视觉上与原语割裂。
**高杠杆解法**:在 `main.ts` 引入一个全局 `base.css`(或补进 `tokens.css`),加一条基础规则一次性覆盖全部交互元素,无需逐文件改:

```css
/* 全局焦点环 —— 收口 29 个文件的 focus-visible 缺口 */
:where(button, [role="button"], a, input, select, textarea,
       .u-interactive, [tabindex]):focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);   /* = 0 0 0 3px var(--c-accent-ring) */
}
```

> 这一条规则即可把"发现 A"从 29 文件缺口降为 0,是本次性价比最高的单点修复。

---

### 发现 B — UI 原语采用率极低,手写按钮/卡片泛滥【一致性主因】

证据:
- 32 个顶层组件中仅 **8 个**引用 `UiButton`/`UiCard`;业务组件几乎全手写。
- `argument/` 下密集手写 `<button>`(节选,真实行号):
  - `argument/ArgInspector.vue`:44,49,54,105,106,121,123,128,133,151(`inspector-btn`、`span-action-btn`、`candidate-adopt-btn` 等自定类)
  - `argument/ArgSourcePane.vue`:7,12,17,23,29,51,52,96,103,111(`paste-btn`、`bind-btn`)
  - `argument/ArgumentMapView.vue`:22,23,29,39(`arg-toolbar-btn`、`arg-primary-btn`)
  - `argument/CompanionPanel.vue`:5,12,19,37,54,89,106,154(`reanalyze-btn`、`suggestion-close`)
  - `argument/ArgumentMapMini.vue`:11,26,36;`argument/LedgerList.vue`:4,59,69,76
- 主视图同样手写:`TranslateView.vue`、`EditorLayout.vue`、`MindMapView.vue`、`AiPanel.vue`、`CommandPalette.vue`、`AgentPanel.vue`(均 grep 命中 `<button`)。

**影响**:同一动作在不同组件里 hover/disabled/active 表现不一;亮色主题下部分手写按钮未接 token,观感割裂。
**解法**:采用"新代码强制用原语 + 存量靶向迁移"策略,避免一次性大改引发回归:
- 新增组件默认用 `UiButton`/`UiCard`/`UiIconButton`。
- 存量优先迁移 `argument/` 的**动作型按钮**(toolbar / 确认 / 取消 / 采纳 / 删除)到 `UiButton`(variant 映射见 §4),结构性/纯图标块保留但补 `.u-interactive` + 焦点环。

---

### 发现 C — 硬编码颜色绕过 token,亮/暗主题存在断裂风险【主题对等性】

证据(部分,真实行号):

| 文件:行 | 原值 | 风险 |
|---|---|---|
| `EditorLayout.vue:912` | `border: 1px solid rgba(255,255,255,0.05)` | **亮色主题下白边不可见 → 边框消失(真实 bug)** |
| `EditorLayout.vue:934-935` | `rgba(91,108,255,0.2)` / `rgba(91,108,255,0.15)` | accent 辉光绕过 `--c-accent-ring`/`--c-accent-soft` |
| `EditorLayout.vue:1115` | `box-shadow: 0 7px 22px rgba(50,43,31,.12)` | 仅适配亮色,暗色下投影异常 |
| `MindMapView.vue:1176` | `box-shadow: -18px 0 44px rgba(0,0,0,0.28)` | 暗色 OK,亮色偏重(可接受,建议 `--c-shadow`) |
| `MindMapView.vue:1234` | `radial-gradient(... rgba(91,108,255,.11) ...)` | accent 点阵绕过 token |
| `argument/ArgEdge.vue:61-66` | `#6f9276 / #7182a6 / #94a3a5 / #aa8757 / #a76f62 / #a77b5c` | 关系色**按暗色调校**,亮色下对比度崩 |
| `argument/ArgEdge.vue:115-120` | `#5f7f66 / #647595 / #758486 / #8d704a / #8d5d53 / #8d684f` | 标签色同上,亮色不可读 |
| `argument/ArgInspector.vue:380-383,457-462,502-505` | `#10b981 / #3b82f6 / #93c5fd / #f59e0b / #f97316` | 节点/关系类型色写死,无法主题化 |
| `argument/ArgNodeCard.vue:127-131` | `--arg-tone: #6f9276 …` | 与 ArgEdge 重复定义,两处易漂移 |
| `argument/ArgSourcePane.vue:612-614` | `#10b981 / #3b82f6 / #93c5fd` | 与 ArgInspector 同源色各写各的 |
| `argument/ArgSourcePane.vue:467` | `rgba(255,255,255,0.35)` | 亮色下白边不可见 |

**影响**:亮色主题切换后,多处边框/标签/关系线"看不见"或"脏";同一语义色(argument 关系类型)在 3 个文件各写一份,改一处不同步。
**解法**:
- 紧急:`EditorLayout.vue:912` 改 `var(--c-border)`(或 `--c-surface-3`);accent 辉光改 `--c-accent-soft`/`--c-accent-ring`。
- 关系/节点类型色抽成**单一来源**:在 `tokens.css` 增加"语义关系调色板" `--rel-supports / --rel-warrants / --rel-backs / --rel-qualifies / --rel-rebuts / --rel-counters`(暗/亮两套),`ArgEdge`/`ArgInspector`/`ArgNodeCard`/`ArgSourcePane` 统一引用,删除各文件散落的 hex。
- 纯 `rgba(255,255,255,x)` 边框 → 统一用 `--c-border` / `--c-glass-border`。

> 合理例外(报告中保留,不改):`#fff` 压在 accent 上的文字(`ArgInspector.vue:481` 等)、`color-mix(...)` 表达式、`--brand-red`(本就是 token)、keyframes 过渡色。

---

### 发现 D — 其他可打磨项(收口完成后锦上添花)

- **主题缺 system 选项**:`useAppTheme.ts` 仅 dark/light 切换,无跟随系统。可选补三态(light/dark/system)。
- **状态体验**:`TranslateView`/`EditorLayout` 缺少骨架屏与统一空状态组件(现有 `UiEmpty.vue` 未被广泛使用)。
- **微观交互**:原语仅 hover 抬升,缺磁吸、ripple、关键 CTA hover 辉光——属"高级感"层,建议放最后。

---

## 3. 分级执行计划

### P0 — 全局契约(一次性,低风险,高杠杆)
1. **全局焦点环**:新增 `src/styles/base.css`(或在 `tokens.css` 末尾追加),加入 §2·A 的 `:focus-visible` 基础规则;`main.ts` 引入。**影响:收口 29 文件缺口。**
2. **亮色不可见边框修复**:`EditorLayout.vue:912` → `var(--c-border)`;`ArgSourcePane.vue:467` 同理。
3. **accent 辉光 token 化**:`EditorLayout.vue:934-935`、`MindMapView.vue:1234` 改用 `--c-accent-soft`/`--c-accent-ring`。

### P1 — 语义关系调色板(一致性核心)
4. `tokens.css` 增加暗/亮两套 `--rel-*` 关系色 + 节点类型色,作为唯一来源。
5. 将 `ArgEdge.vue`、`ArgInspector.vue`、`ArgNodeCard.vue`、`ArgSourcePane.vue` 的硬编码 hex 改为引用新 token,删除重复定义。

### P2 — 原语迁移(argument/ 先行)
6. `argument/` 动作型按钮(`ArgInspector`、`ArgSourcePane`、`ArgumentMapView`、`CompanionPanel`、`LedgerList`)迁移到 `UiButton`,variant 映射:
   - 主操作(确认/采纳/新增节点)→ `variant="primary"`
   - 次操作(取消/关闭)→ `variant="ghost"` 或 `secondary`
   - 危险操作(删除/解绑)→ `variant="danger"`
   - 纯图标 → `UiIconButton`
7. 其余手写可交互块补 `.u-interactive` + 全局焦点环(已被 P0 覆盖)。
8. 主视图(`TranslateView`/`EditorLayout`/`MindMapView`/`AiPanel`)存量按钮按同一映射逐步迁移,新代码强制用原语。

### P3 — 体验与可达性收尾(可选)
9. 主题补 system 三态。
10. 引入统一 `UiSkeleton`/`UiEmpty` 到 TranslateView/EditorLayout 的等待与空状态。

---

## 4. 执行顺序与文件清单(建议提交节奏:每步一个干净 commit)

| 步骤 | 文件 | 动作 | 风险 |
|---|---|---|---|
| P0-1 | `src/styles/base.css`(新) + `main.ts` | 全局焦点环 | 低 |
| P0-2 | `EditorLayout.vue:912`、`ArgSourcePane.vue:467` | 白边→token | 低 |
| P0-3 | `EditorLayout.vue:934-935`、`MindMapView.vue:1234` | accent→token | 低 |
| P1-4 | `tokens.css` | 增加 `--rel-*` 调色板 | 低 |
| P1-5 | `ArgEdge/ArgInspector/ArgNodeCard/ArgSourcePane` | 引用 token | 中(需比对色值) |
| P2-6 | `argument/*` 5 个组件 | 按钮→`UiButton` | 中(布局回归风险) |
| P2-7 | 主视图存量 | 补 `.u-interactive` | 低 |
| P3-9/10 | `useAppTheme.ts`、`UiEmpty` 接入 | 增强 | 低 |

---

## 5. 验收标准

- `npm run typecheck` 与 `npm run build` 通过(无新增错误)。
- 暗/亮主题下逐屏目检:边框可见、关系线/标签可读、按钮 hover/disabled/active 一致。
- 键盘 Tab 走查:所有可交互元素有可见焦点环(P0-1 后应当全局生效)。
- `argument/` 关系色在 `tokens.css` 单源定义,4 个文件无重复 hex。
- 新组件评审:默认使用 `UiButton`/`UiCard`/`UiIconButton`。

---

## 6. 附:证据索引(已验证 grep)

- 手写 `<button>` 总数:**253**(`grep -rnE "<button" components/ | grep -v components/ui/`)。
- `:focus-visible` 出现:**37** 处;缺焦点环文件:**29** 个(见 §2·A 列表)。
- 硬编码 hex/rgba 在 `argument/` 与主视图均有分布(见 §2·C 表)。
- 顶层组件引用 `UiButton`/`UiCard`:**8 / 32**。

> 下一步:确认本报告方向后,按 P0→P1→P2→P3 顺序执行;P0 三步可先合并为一个 PR 快速收口可达性与亮色断裂。
