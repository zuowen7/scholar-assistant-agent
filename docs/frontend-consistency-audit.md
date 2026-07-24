# 前端打磨总纲 · 视觉 / 动效 / 操作逻辑 / 一致性(待执行)

> 范围:Scholar Assistant(研墨)Vue 3 桌面前端
> 目标:在不推倒设计系统的前提下,从**视觉、动效、操作逻辑、一致性**四个维度做一轮整体打磨,使产品达到"看起来高级、用起来顺、想得通"的状态。
> 状态:本报告现作为**审计 + 增量实施台账**使用。保持现有暖色墨/纸设计与 AI 常驻结构,按 Phase 0→3 小步修复,不从头设计。
> 质量标尺:对齐 Apple HIG 三支柱 **Clarity / Deference / Depth** + **WCAG 2.1 AA**;差异化靠研墨自身的"墨与纸"身份,而非抄玻璃拟态。
> **目标态蓝图**:完整视觉/动效/特效愿景见配套 `ui-target-blueprint.md`(本文件 = 路线与计划,蓝图 = "到底应该是什么样子")。
> **最近一次代码核查**:2026-07-22 已重新实读 `App.vue` / `EditorLayout.vue` / `EditorWelcome.vue` / `AgentPanel.vue` / `useProject.ts` / `useWakeWord.ts` / `useVoiceCommand.ts` 及相关测试。下方新增的“当前复核”优先于旧行号。

---

## 当前代码复核(2026-07-22,防止重复施工)

本轮先逐条对照当前代码,确认报告有一部分证据已经过期。后续只改仍可由当前代码证明的问题:

| 报告项 | 当前复核 | 处理 |
|---|---|---|
| 亮色下 `sidebar-rail-button` 边框近乎不可见 | 仍存在 | 已改为 `var(--border-color)` |
| 全局裸 `:focus-visible` 强制圆角 | 仍存在 | 已收窄到交互元素,并移除聚焦时强制圆角 |
| accent hover 使用固定 RGB | 仍存在 | 已改用 `--c-accent-rgb` |
| N1 多入口直接切 mode 导致导航状态易漂移 | 仍有分散入口 | 已收口到 `navigateTo(section)`；原 watch 保留为防线 |
| N2 PDF/LaTeX 未选模板时静默返回 | 当前代码已显示 `selectTemplate` 反馈 | 不重复修改 |
| N3 重复点击 Mind Map 会重建 | 当前已有 `workspaceMode === 'mindmap'` 守卫 | 不重复修改 |
| L1 Wake Word 监听器不清理 | 当前已有 `cleanup()`、移除监听器和 `onScopeDispose` | 不重复修改 |
| L2 Voice Command 定时器不清理 | App 卸载已调用 `voiceCmd.cleanup()` | 不重复修改 |
| L3 关闭项目残留 tabs | 当前 `closeProject()` 已清 `tabs/activeTabId` 且有测试 | 不重复修改 |
| N5 Agent 缺 tablist/焦点归还 | 当前已有 tablist/tab 键盘逻辑与焦点归还 | 不重复修改 |
| N6 写作页缺少返回欢迎路径 | 写作模式仍缺直接入口 | 已增加“关闭当前文档”；未保存时先确认,关闭最后一页后回到欢迎页 |

本轮还修复了欢迎页“删除最近项目”嵌套在“打开项目”按钮内的无效交互结构,但未改变欢迎页视觉方案。其余 Phase 1–3 项继续按本文件增量推进。

---

## 0. 设计哲学(据反馈收敛后的定稿)

用户对现有 `v-ink-bleed` / `v-brush-stroke` 评价"一般",并明确两件事:**(a) AI 才是主角,不要收起右面板;(b) 保留现有暖色"墨与纸"基调,不要整包换肤。** 据此定稿方向:


- ✅ 新主语言:**物理可信的过渡(非装饰笔触) + 视图连续性 + 专注模式(不藏 AI)+ 克制朱印签名 + 纸张材质**。笔触仅作 hover/纹理点缀。
- ✅ **AI 是主角**:右面板默认常驻且默认停在 AI 标签(代码已如此,见 §5·D),打磨只做"让它更像一等公民",绝不默认收起。
- ✅ **保留现有暖色基调**:`--c-accent:#5b6cff` + 品牌红 `#C8503A` + 纸色 `#FAF8F3/#14130f`。仅做纪律收敛与层级澄清,不换肤。

动效判准三条:**(1) 物理可信**(缓出/弹簧而非匀速,但布局/面板过渡**不用回弹 overshoot**)、(2) 空间连贯**(View Transitions 共享元素)、(3) 内容优先**(写作时 chrome 退场,但 AI 面板保持可召回)。

---

## 1. 四大工作流总览

| 工作流 | 目标 | 当前主要落差(代码核查后) | 优先级 |
|---|---|---|---|
| **WS1 视觉 Visual** | 纸张材质身份 + 排版工艺 + 强调色纪律 + 空/加载态 | 玻璃思维、CJK 排版未优化、关系色未单源 | 高 |
| **WS2 动效 Motion** | 缓出系统 + 视图连续性 + 专注模式(不藏 AI)+ 朱印签名 | 79 组件仅 13 有转场;签名动效 0 引用;`--ease-spring` 回弹误用风险 | 高 |
| **WS3 操作逻辑 Operation** | 统一导航模型 + 动作反馈 + 非破坏式导航 + 泄漏清理 | N1 高亮错位 / N2 静默导出 / L1-L3 泄漏 | 最高 |
| **WS4 一致性 Consistency** | 焦点环收口 + 原语 + 颜色 token 化 | 全局焦点环**已存在但过宽+冗余**;亮色边框真 bug;accent rgba 硬编码 | 地基 |

**执行顺序**:WS4(地基) → WS3(逻辑先稳) → WS1(视觉) → WS2(动效建于稳逻辑与一致令牌之上)。动效不能盖在破损逻辑或不一致令牌上。

---

## 2. WS1 视觉系统(Visual)· 进阶

### 2.1 纸张材质作为身份(替代玻璃拟态)
- 暗色下给"活动页面"加一层**暖色灯下光晕**(radial-gradient,极淡),模拟台灯下的稿纸;亮色下用极淡纸纤维纹理。
- 面板之间用**毛边/纸层叠**而非生硬边框:借 `--c-surface-*` 层级 + 1px `--c-border` + 极淡内阴影。
- 避免大面积 `backdrop-filter`(贵且伤可读性,且违研墨身份)。玻璃仅留给浮层(`UiCard glass` 已有,克制用)。

### 2.2 排版工艺(CJK + Latin 混排,写作工具的核心体面)
- **CJK–Latin 间距**:`text-spacing-trim` / `text-autospace`(或 `word-break` + 手动 ` ` 规则),消灭中英文"挤在一起/太空"两种极端。
- **悬挂标点**:标点不顶格、不突出版心;对引号/书名号做 optical 处理。
- **数字对齐**:`font-variant-numeric: tabular-nums`(表格/统计/页码);引用标号用 `tabular-nums`。
- **光学尺寸**:`font-optical-sizing: auto`;`--font-serif`(EB Garamond / Noto Serif SC)用于标题与正文强调。
- **垂直韵律**:以 `--leading-normal`(1.55)为基线,标题/列表用 `--leading-snug`,保证行距是 `--space-*` 的整数感。

### 2.3 强调色纪律(保留现有蓝 + 品牌红)
- `--c-accent`(#5b6cff)只用于**主操作 + 激活态**;次级动作走 `--c-surface-*` / `--c-text-*`。品牌红 `#C8503A` 仅用于朱印签名与极少数警示强调。
- 现有 hover 态存在 `rgba(91,108,255,0.2)` 之类硬编码(见 §5·C),应改用 `--c-accent-rgb` / `--accent-glow` token,避免日后换色时漏改。

### 2.4 空 / 加载态作为"设计时刻"
- 骨架屏遵循纸张版心(`--page-width`),非灰色块;列表用 `--anim-stagger` 错峰。
- 空状态配**小号 ink 插画**(单色线稿,沿用品牌红点缀),而非纯文字。现有 `UiEmpty.vue` 未被广泛使用 → 接入 `TranslateView` / `EditorLayout` / 各空列表。

### 2.5 关系色单源(承接 WS4·C)
- 论证/思维导图关系色(`#10b981/#3b82f6/#93c5fd/#f59e0b/#f97316` 及 ArgEdge 暗色调校色)抽到 `tokens.css` 的 `--rel-*` 单源,亮/暗两套,4 文件统一引用。

---

## 3. WS2 动效系统(Motion)· 进阶(用户重点)

### 3.1 缓出 / 弹簧系统(替代装饰笔触)
- 建立**统一缓动**:面板/弹窗/节点入场用 `cubic-bezier` 缓出(或 `linear()` 拟合的轻弹簧)。**关键约束:布局/面板类过渡默认不用回弹 overshoot**;现有 `--ease-spring: cubic-bezier(0.34,1.56,0.64,1)` 带过冲,仅限**极小且刻意的俏皮瞬间**(如侧栏收起按钮 EditorLayout:929),不得用于视图/面板主转场。
- 通用微交互走现有 `--ease-brush`(快起慢收,无过冲)与 `--ease-out`。

### 3.2 视图连续性(View Transitions API 复用)
- 主题切换已在用 View Transitions(圆形 clip)。**扩展到导航**:
  - 欢迎页项目卡 → 点击后 **expand 成编辑器**(共享元素转场)。
  - 命令面板结果 → **原地展开**为目标视图,而非闪切。
  - 模式切换 → 共享元素 + `v-page-cross` 语义统一(见 3.7)。

### 3.3 专注模式(Focus Mode)—— 写作 App 的"高级感"大头
- 写作时**chrome 渐隐**:顶栏/侧栏 `opacity + translateY` 缓退,正文独占;鼠标移动 / `Esc` 召回。
- **AI 面板不在此列**:专注模式只淡出顶栏/侧栏等 chrome,右 AI 面板保持常驻可召回(呼应 §0"AI 是主角")。当前**完全缺失**,与 WS3 导航态联动。

### 3.4 签名时刻:朱印(克制的高级感)
- 导出 / 保存完成 → 盖一枚**朱红印章**(`--brand-red` #C8503A):轻压下 + 微旋 + 落定回弹,伴随极短 `anim-flash`。比笔触揭示更"贵气"且贴合研墨。
- 首屏 `InkBrushLoader` 升级为**墨滴 bloom**(现有"研"字红印 + 扫描进度保留,加一滴墨晕开成 UI 的入场)。

### 3.5 结构图 FLIP(论证图 / 思维导图)
- `autoLayout()` 与节点增删当前是**硬跳/重建**(见 WS3·N3、性能 P1)。改用 **FLIP**(First-Last-Invert-Play)做平滑位移过渡;节点入场用错峰缓入。

### 3.6 笔触降级为纹理
- `v-brush-stroke` 仅用于个别文本揭示(如 AI 总结首行);`v-ink-bleed` 作 hover 微纹理。不作为主语言。

### 3.7 统一"应用级转场契约"
证据(grep 实测):
- **79 个 .vue 组件仅 13 个接 `<Transition>`**(约 16%)。
- **`v-ink-bleed` / `v-brush-stroke` 使用次数 = 0**(签名动效 dormant)。
- **`v-page-cross` 0 引用**(模式切换改走自定义 `mode-cross` @ `App.vue:1112`,实际有动画,非硬切)→ 死代码,统一或删。
动作:重定一套转场契约——`v-scale-in`(浮层)、`v-slide-up`(toast/hint)、`v-spring`(印章/徽章,**限定俏皮**)、`v-page-cross`(视图,接回或删)、`v-unfurl`(宣纸展开);明确每个组件在条件渲染时挂哪套。

### 3.8 60fps 纪律
- 动效只用 `transform` / `opacity`;`will-change` 按需;`prefers-reduced-motion` 已全局降级(tokens.css:345),保持。与性能 WS(D1–D3 懒加载、P1/P2 记忆化)协同,避免主线程长任务打断动画。

---

## 4. WS3 操作逻辑(Operation)· 进阶(用户重点)

> 证据来自 `frontend-audit-report.md` 导航/逻辑审计(N1–N8、L1–L8),此处升级为"打磨"视角。

### 4.1 统一导航模型(单一真相)
- `mode` + `shellSection` + 右面板态应同源。`useAppMode.ts:9` 的 `setMode` 多处直接调用不更新 `shellSection`(`App.vue:46,138,280,390`)→ **侧边栏高亮错位(N1)**,点高亮"像没反应"。
- 收敛为单个定向 helper(`navigateTo(module)`),所有入口走它。

### 4.2 动作必有反馈
- 导出 PDF/LaTeX 在 `!selectedTemplate` 时**静默 no-op**(`EditorLayout.vue:507,526`)→ 用户以为功能坏(**N2**)。
- 原则:**任何"有后果"的操作都给 toast / 状态回执**。导出前校验模板并 `showExportToast(t('editor.selectTemplate'))`。

### 4.3 非破坏式导航
- 每次点 mindmap 都 `resetMindMap + buildTreeNode` 重建(**N3**)→ 误操作丢失节点编辑。已 `workspaceMode==='mindmap'` 时不重建,仅保面板可见。
- **无返回欢迎页导航(N6)**:开 tab 后难回开始页/模板 → 补"返回欢迎"入口。

### 4.4 右面板态同步(N4)—— 当前实现已正确,保持
- 代码核查:`EditorLayout.vue:230` `rightPanelVisible = ref(true)`、`:255` `rightPanelTab = ref('ai')`、`:97` 写作模式渲染 `TaskAgentPanel`、`:96` LaTeX 模式渲染 `AiPanel(workspace-variant)`。**AI 默认常驻且为默认标签,已是"AI 主角"的正确实现,不要改为默认收起。**
- 仅补强:`toggleRightPanel(tab)` 已存在(`:257`);`rightPanelTab` 为 null 时默认 `'ai'`(`:274`)已正确,保持。

### 4.5 Agent 面板 a11y / 焦点(N5)
- `AgentPanel.vue:964,138` 浮层无 `role` / 焦点陷阱 / 焦点归还;tab 栏裸 `<button>` 无 `role="tablist"`。
- 补 `role="tablist"` + 焦点陷阱 + 关闭归还焦点(呼应一致性 WS4 焦点环)。

### 4.6 监听器 / 状态泄漏清理(长期健康)
- **L1** `useWakeWord.ts:212` 全局 `blur/focus/visibilitychange` + watcher 永不移除 → `stopWakeWord` 内 `removeEventListener` + `onScopeDispose`。
- **L2** `useVoiceCommand.ts:30` 模块级定时器无 `onScopeDispose` → 卸载清定时器。
- **L3** `useProject.ts:126` `closeProject` 不清 `tabs/activeTabId` → 残留幽灵标签;`closeProject` 中 `tabs.value=[]; activeTabId.value=null`。

### 4.7 命令面板作为万能入口
- `CommandPalette.vue` 已有 `@keydown.esc`(a11y 基础好)。将其定位为**全局统一 open 协议**:任意"打开 X"都经它,保证入口一致。

### 4.8 其余(低优先)
- **N7** write/mindmap 依赖脆弱 `window` 事件耦合(`App.vue:217-227` + `EditorLayout.vue:249-251`)→ 重构为显式 props/events。
- **N8 / L8** 死代码(`App.vue:164` 未用 `ArgumentMapView` 导入)、`_messagesByWorkflow` Map 无上界 → 清理。

---

## 5. WS4 一致性收口(Consistency)· 代码核查后修正

> ⚠️ 本报告**上一版**称"全局焦点环缺失"为 P0。经实读代码,该结论**不准确**,特此更正。

### 发现 A — 全局焦点环【已存在,收口而非新建】
- **更正**:`App.vue:815` 已有全局 `:focus-visible { outline:none; box-shadow: var(--ring-focus); border-radius: var(--radius-xs) }`,全站键盘焦点**已可见**。约 37 处组件又各自重复声明 `:focus-visible`(如 `AiPanel.vue:666/724/739/745/765`、`UiButton.vue:60`),属冗余但无害。
- **真问题(轻量)**:
  1. 全局规则是裸 `:focus-visible`(作用所有元素),会误伤非交互元素并强制 `border-radius: var(--radius-xs)`(聚焦瞬间改圆角,偶有跳变)。应收窄为交互目标:`button, [role=button], a, input, select, textarea, .u-interactive, [tabindex]:not([tabindex="-1"])`。
  2. 冗余本地副本可逐步删除,统一由全局收口,避免日后漂移。
- **结论**:降为 P1 维护性项,**不再是阻断性 P0**。a11y 底线已达标。

### 发现 B — UI 原语采用率
- 32 顶层组件约 8 用 `UiButton`/`UiCard`;`argument/*` 与主视图密集手写按钮。
- 解法:"新代码强制原语 + 存量靶向迁移";动作按钮→`UiButton`(primary/ghost/danger 映射),图标→`UiIconButton`(注意:UiIconButton 自身无 `:focus-visible`,依赖 §A 全局规则,保持即可)。
- 注意:原语迁移是**一致性/可维护性**收益,非 a11y 必需(焦点已由全局覆盖)。

### 发现 C — 硬编码颜色绕过 token,亮/暗断裂【含唯一真 P0 bug】
- **真 P0 bug**:`EditorLayout.vue:912` `border: 1px solid rgba(255, 255, 255, 0.05)` —— 亮色主题下近乎不可见(真实 bug)。**修复**:改为 `border: 1px solid var(--border-color)`(亮 `#E8E1D3` / 暗 `#232328`,tokens.css:323/201),两主题皆可见。
- **accent rgba 硬编码(轻量)**:`EditorLayout.vue:934-935` hover 用 `rgba(91, 108, 255, 0.2)` / `rgba(91,108,255,0.15)`。应改为 `rgba(var(--c-accent-rgb), 0.2)`(token 已存在,tokens.css:169)或 `--accent-glow`,避免换色漏改。
- **关系色四处各写**:`ArgEdge` / `ArgInspector` / `ArgNodeCard` / `ArgSourcePane` 各自定义关系色。抽 `--rel-*` 单源(见 WS1·2.5)。

### 发现 D — AI 面板作为主角(核查结论:现状正确)
- 见 §4.4:`rightPanelVisible=true`、默认 tab `'ai'`、`TaskAgentPanel`(写作)/`AiPanel`(LaTeX)默认渲染。**保持现状,打磨只增强其"一等公民"体感(如空态引导、焦点可见、与专注模式共存),绝不默认收起。**

---

## 6. 分级执行路线(合并,每 Phase 一个干净 commit)

### Phase 0 — 地基(WS4 + WS3 反馈/高亮)
1. **[真 P0]** 亮色不可见边框修复:`EditorLayout.vue:912` `rgba(255,255,255,0.05)` → `var(--border-color)`。
2. **[P1]** 收紧全局焦点环(`App.vue:815` 收窄选择器,去除冗余本地副本);accent rgba 改 token(`EditorLayout.vue:934-935`)。
3. `setMode` 同步 `shellSection`(N1);导出静默→toast(N2)。(右面板 N4 已正确,跳过。)

### Phase 1 — 逻辑稳(WS3 余下)
4. `closeProject` 清 tabs(L3);语音监听器/定时器 `onScopeDispose`(L1/L2)。
5. 非破坏式 mindmap 导航(N3);返回欢迎页入口(N6);Agent 面板 `tablist`+焦点陷阱(N5)。

### Phase 2 — 视觉(WS1)
6. 纸张材质(暖光晕 + 纸纤维 + 毛边层级);CJK 排版(`text-spacing-trim`/tabular-nums/悬挂标点)。
7. 关系色 `--rel-*` 单源(2.5);统一空/加载态接入 `UiEmpty`/骨架屏。

### Phase 3 — 动效(WS2,建于稳逻辑之上)
8. 统一缓动契约(默认无回弹;限定 `--ease-spring` 于俏皮点)+ 应用级转场契约(接回/删 `v-page-cross`,激活 `v-spring`/`v-unfurl`)。
9. 专注模式(3.3,**不藏 AI**);视图连续性(View Transitions 扩展,3.2)。
10. 朱印签名(3.4);结构图 FLIP(3.5)。

---

## 7. 验收标准

- `npm run typecheck` 与 `npm run build` 通过(无新增错误);`npx vitest run` 保持绿(批次 A 级改动)。
- **视觉**:暗/亮下边框可见(**Phase 0 即验证 EditorLayout:912**)、关系线可读、纸张材质与排版工艺目检达标;CJK–Latin 间距自然;强调色未 sprinkled。
- **动效**:所有条件渲染挂统一转场;缓动无不当回弹;专注模式可进出且 AI 面板常驻;朱印/视图连续性在关键路径可见;60fps(`transform`/`opacity` 为主)。
- **操作逻辑**:侧边栏高亮与视图一致;导出/危险操作均有反馈;导航非破坏(关项目/切模式不丢编辑);无监听器/标签泄漏(DevTools 验证 `onScopeDispose`)。
- **一致性**:交互元素焦点环由全局收口(无冗余漂移);`argument/` 关系色单源;新组件默认用原语;AI 面板默认常驻为 AI 标签。

---

## 8. 附:初始证据索引(部分已被“当前代码复核”覆盖)

> 本节保留最初审计的追溯线索,不再代表全部项目仍未修复。实施判断以文首 2026-07-22 当前代码复核和实际代码/测试为准。

- **焦点环**:全局规则 `@ App.vue:815`(`:focus-visible` 裸选择器);本地重复约 37 处(如 `AiPanel.vue:666/724/739/745/765`、`UiButton.vue:60`)。**结论:已存在,非 P0。**
- **AI 主角(已正确)**:`EditorLayout.vue:230`(`rightPanelVisible=true`)、`:255`(`rightPanelTab='ai'`)、`:97`(`TaskAgentPanel` 写作)、`:96`(`AiPanel` LaTeX)。
- **真 P0 bug**:`EditorLayout.vue:912` `border:1px solid rgba(255,255,255,0.05)`(亮色不可见)。
- **accent 硬编码**:`EditorLayout.vue:934-935` `rgba(91,108,255,0.2/0.15)`;`--c-accent-rgb` 已存在(tokens.css:169)。
- **原语**:`UiButton.vue`(7 变体 + focus-visible + loading)、`UiCard.vue`(flat/raised/sunken/glass)、`UiIconButton.vue`(无本地 focus-visible,依赖全局);开发约 250 处手写 `<button>`(焦点已被全局覆盖,迁移为一致性收益)。
- **转场**:79 组件仅 13 接 `<Transition>`;`v-ink-bleed`/`v-brush-stroke` 0 引用;`v-page-cross` 0 引用(WS2·3.7)。
- **reduced-motion**:全局 `@media (prefers-reduced-motion: reduce)` 已存在(tokens.css:345),`*` 级降级,保持。
- **缓动 token**:`--ease-spring: cubic-bezier(0.34,1.56,0.64,1)`(带过冲,tokens.css:69)、`--ease-brush: cubic-bezier(0.25,0.1,0.1,1)`(无过冲,72);通用过渡默认用 brush/out,spring 仅限俏皮点。
- **操作逻辑**:N1(`useAppMode.ts:9` + `App.vue` 多处)、N2(`EditorLayout.vue:507,526`)、N3(`App.vue:223`)、N4(`EditorLayout.vue:26,262`,已正确)、N5(`AgentPanel.vue:964,138`)、N6(`EditorLayout.vue:6`);L1(`useWakeWord.ts:212`)、L2(`useVoiceCommand.ts:30`)、L3(`useProject.ts:126`)。
- **性能(协同)**:monaco 首屏 1,094KB gz(D1)、hljs 全量(D2)、vue-flow 首屏(D3)、AgentPanel markdown 重解析(P2)、思维导图全量重建(P1)——详见 `frontend-audit-report.md` 构建实测。

---

## 9. 设计方向决策记录(防反复)

为免后续会话重复纠结"要不要换肤",在此固化决策:

| 候选方案 | 结论 | 原因 |
|---|---|---|
| Atlas(冷色 #0E1117 / 钴蓝 #2F6FED)整包换肤 | ❌ 否决 | 用户评"更不好看";钴蓝渐变+辉光+回弹 = AI-slop 感 |
| Quiet Canvas(暖陶土 + Plus Jakarta Sans) | ❌ 否决 | 用户评"跟之前配色一个样" |
| Quiet Teal(青绿 #0F766E 换肤) | ❌ 搁置 | 用户未确认方向;且违背"保留现有暖色"诉求 |
| **保留现有暖色墨/纸 + 增量打磨** | ✅ **采纳** | 用户明确"先保留现在的,一点点改";AI 主角已成立 |

**底线**:不整包换肤;动效默认无回弹;AI 面板永默认常驻且为默认标签;所有改动走 Phase 0→3 增量、每阶段干净 commit。视觉/动效进阶(Phase 2–3)先做 1–2 个原型页目检后再铺开。

> 下一步:确认方向后按 Phase 0→3 执行;Phase 0 三步(边框修复 + 焦点环收口 + 导航反馈)可先合并一个 PR 快速收口亮色断裂与导航反馈。视觉/动效进阶建议先出原型页目检。
