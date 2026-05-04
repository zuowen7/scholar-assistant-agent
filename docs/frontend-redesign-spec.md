# 研墨前端体验升级技术方案

> 适用范围：本仓库 `src/` 目录全部 Vue/CSS。本方案面向"另一个 AI 实施"，所有改动点都给到了文件路径、当前类名/行号锚、和期望产物。
> 评审基线：阅读 `src/styles/tokens.css`、`src/App.vue`、`src/components/AppTopBar.vue`、`src/components/TranslateView.vue`、`src/components/EditorLayout.vue`、`src/components/AgentPanel.vue`、`src/components/ui/UiButton.vue` 后撰写。
> **本方案目标**：把现有"功能堆砌型 SaaS UI"重塑为「**研墨**」自有的视觉语言——一种像翻一本装订考究的学术笔记一样、克制却有锋芒、能让用户截图发朋友圈的桌面应用。不是堆动画，不是抄 Linear/Notion，是建立**自己的品牌秩序**。

---

## 0. 设计愿景：「研墨」是什么样子

### 0.1 品牌叙事

**「研」**——研究、研磨、推敲。  
**「墨」**——东方书写的本源，专业、沉静、留白。

视觉语言关键词：**学院派 · 浓墨 · 工整 · 留白 · 一抹朱砂**。

参考坐标（精神而非抄袭）：

- *Things 3* 的呼吸感与排版克制
- *Arc Browser* 的彩色玻璃与圆角节奏
- *Linear* 的暗色层级与微反馈
- 中文古籍版芯（天头地脚、版心、鱼尾）的留白比例
- 雪峰 / 颜真卿《祭侄文稿》的浓淡转折

### 0.2 三条不可妥协的设计原则

1. **以版心为基准** — 内容居中收窄到 720–960px，两侧留白即"地"，禁止全屏铺满"全墨"。  
2. **一抹朱砂** — 全局只允许 1 处使用强调暖色（朱砂 `#C8503A`），用于"翻译完成"等签名瞬间。其余地方必须冷静。  
3. **动效服务于解释** — 任何动画必须能回答"它解释了什么状态变化"。装饰性动画一律砍掉。

### 0.3 签名调色板（取代当前通用 indigo）

```css
/* === 研墨色系 · Dark === */
--ink-0:  #0c0d10;    /* 砚池底色 */
--ink-1:  #14161b;    /* 主版面 */
--ink-2:  #1c1f26;    /* 卡片表面 */
--ink-3:  #262a33;    /* 浮起表面 */
--ink-4:  #353a45;    /* 描边 */
--ink-5:  #4a505c;    /* 高描边 */

/* 主墨色（替代 accent indigo）：靛青偏紫，更"东方" */
--accent-0: #5b6cff;   /* 主墨 */
--accent-1: #7a89ff;   /* 主墨高亮 */
--accent-2: #3b48d9;   /* 主墨深 */
--accent-glow: rgba(91, 108, 255, 0.35);

/* 朱砂（签名色，用得极省）*/
--vermilion-0: #C8503A;
--vermilion-1: #E0664E;

/* 宣纸色（用于 light 与中性强调）*/
--paper-0: #f5f1e8;    /* 仿古宣纸 */
--paper-1: #ede7d6;    /* 老宣纸 */

/* 文本：绝对的灰阶，避免泛蓝 */
--text-0: #ECEDEF;     /* H1 */
--text-1: #C9CBD1;     /* 正文 */
--text-2: #8C909B;     /* 次级 */
--text-3: #5C606C;     /* 弱化 */
```

把当前 `--c-accent: #6366f1` 全局替换为 `--accent-0: #5b6cff`（视觉差异肉眼可见但非常细微，更冷峻）。朱砂只允许出现在：翻译完成 done state、AI 编辑 accept 按钮、错误致命态。**不许**做成"双 accent"配色——朱砂是签名，多用即廉价。

### 0.4 字体策略（核心，决定第一眼气质）

| 用途 | 字体 |
|---|---|
| 显示性大标题（hero / done / 空状态） | **`Noto Serif SC` + `EB Garamond`**，serif 衬线，字重 600，`letter-spacing: -0.02em` |
| UI 正文 | `Inter Variable` + `Noto Sans SC` |
| 编辑器 / 代码 | `JetBrains Mono Variable`（已有 monaco 内置可用） |
| 论文阅读区 | 用户可选 `LXGW WenKai` / `Noto Serif SC` / 系统默认 |

> 关键洞察：当前所有标题都是 sans-serif，看起来跟随便哪个 SaaS 都一样。**hero / done / 空状态 / 段标题强制改 serif**，立刻拉开档次。

### 0.5 三个签名瞬间（详见 §11）

1. **启动**：水墨晕染 logo + serif "研墨" 由淡到深 → 1.4s 内完成。  
2. **翻译完成**：正文区"宣纸展开"动画（自上而下 unfurl 0.6s）+ 右上角朱砂印章一次性盖下（spring scale 0.6→1.05→1，120ms 钝角声）。  
3. **AI 思考**：Agent 调用工具时，思考链以"砚台滴墨"形式从上到下渗透显示（每条 60ms 错落淡入 + 左侧 1px 墨色竖线）。

这三个是**必须做的**，是用户截图发朋友圈的诱饵。

---

## 0.6 现状摘要

| 维度 | 现状 | 主要问题 |
|---|---|---|
| 设计令牌 | `tokens.css` 已分层（`--c-/-space-/-radius-/-text-/-shadow-/-ease-`），并保留 legacy 别名 | 新旧令牌共存，组件层混用；缺少状态色三件套（bg/border/fg）和层级令牌 |
| 主题 | dark / `.light` 双主题 | light 模式下 topbar 透明度、focus 可见性未系统化校验 |
| 组件 | `ui/` 已有 11 个原子（Button/Segmented/Popover/Dropdown/Card/Input/...) | 关键场景仍直接用原生 `<input>/<select>`（见 `AppTopBar.vue:78-124`），密度不一 |
| 动效 | 局部 `Transition` + 关键帧（drag-pulse、step-pulse），轨迹零散 | 缺统一过渡命名、缺 view 切换过渡、缺 reduced-motion、按钮无微反馈 |
| 信息架构 | 三模式（translate/editor/mindmap）+ 顶栏 + 浮动 Agent | 顶栏右半区控件过密；引擎/状态/设置/主题/Agent 全挤一行 |
| 状态恢复 | 仅主题、背景、阅读偏好、Agent 会话持久化 | 翻译结果、编辑器标签会话不持久；刷新即丢失 |
| 反馈 | 多处 `console.error` + `window.prompt` + `exportMessage` toast | 无统一 toast/通知系统 |

**升级目标**：见 §0。本节只列工程基线问题，避免与设计愿景重复。

---

## 1. 设计令牌（tokens.css）

文件：`src/styles/tokens.css`

### 1.1 颜色系统重整

- **状态色三件套**：`success / warn / danger / info` 各扩展 `-bg / -border / -fg / -strong` 四个变体，替换组件里散落的 `rgba(74,222,128,0.10)` 这类硬编码（`TranslateView.vue:716`、`:985-1001`、`:1031-1038` 等）。
- **层级令牌（重要）**：新增 `--layer-1/2/3/4`，分别对应 hairline / sunken / raised / overlay 四个深度。`elevation-1~4` 保留为阴影；`layer` 用于背景色。
- **accent 渐变令牌**：新增 `--c-accent-gradient: linear-gradient(135deg, var(--c-accent) 0%, #a78bfa 100%)`，将 `AppTopBar.logo` 与 `progress-fill` 等处的内联渐变收敛到令牌。
- **legacy 别名移除分两阶段**：第一阶段仅在 `tokens.css` 顶部加 `/* @deprecated */` 注释；第二阶段（P2）做全局替换并删除别名段（`tokens.css:117-153`）。

### 1.2 字体与排版

```css
/* 新增 */
--font-sans: 'Inter Variable', 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
--font-zh:   'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
--font-mono: ui-monospace, 'JetBrains Mono', SFMono-Regular, Menlo, monospace;
--font-serif-zh: 'LXGW WenKai', 'Noto Serif SC', serif;

/* Display 层级，给空状态 / Done / hero 用 */
--text-display: 32px;   /* hero-title 升级目标 */
--text-display-lg: 44px;
--leading-display: 1.15;
--tracking-tight: -0.02em;
--tracking-display: -0.025em;
```

`body` 字体栈改为 `var(--font-sans), var(--font-zh)`（`App.vue:610`）。

### 1.3 高度与圆角刻度

- 控件标准高度：`--control-sm: 24px / --control-md: 30px / --control-lg: 36px` → 全部加 2px → `28 / 32 / 38`，更接近 macOS Sonoma / Linear 节奏。
- 卡片圆角 `--radius-xl: 14px → 16px`；按钮 `--radius-sm: 6px → 8px`。
- 新增 `--radius-card: 16px`、`--radius-control: 8px` 语义令牌。

### 1.4 动效令牌补全

```css
--motion-fast: 120ms;      /* 保留 */
--motion-base: 180ms;      /* 保留 */
--motion-slow: 280ms;      /* 保留 */
--motion-page: 320ms;      /* 新增：视图切换 */
--motion-stagger: 40ms;    /* 新增：列表错落 */
--ease-out:   cubic-bezier(0.16, 1, 0.3, 1);
--ease-spring:cubic-bezier(0.34, 1.56, 0.64, 1);
--ease-smooth:cubic-bezier(0.4, 0, 0.2, 1);
--ease-emphasis: cubic-bezier(0.2, 0, 0, 1);   /* 新增：material 强调曲线 */
```

---

## 2. 全局动效系统

### 2.1 通用过渡类（新建 `src/styles/transitions.css`，由 `main.ts` 引入）

实现以下 Vue Transition 名：

| 名称 | 用途 | 进入 | 离开 |
|---|---|---|---|
| `v-fade` | 通用淡入淡出 | `opacity 0→1, var(--motion-base) ease-out` | `opacity 1→0, var(--motion-fast) ease-in` |
| `v-slide-up` | toast / hint | `translateY(8px)+opacity 0→1` | `translateY(4px)+opacity` |
| `v-scale-in` | popover / dropdown / modal | `scale(.97)+opacity 0→1, ease-spring` | `scale(.99)+opacity` |
| `v-page-cross` | 模式切换 / view 切换 | `opacity+translateX(8px)` | 反向 |
| `v-list-stagger` | 列表批量渲染（live-preview / 文件树） | `transform-group` + `transition-delay: calc(var(--i)*40ms)` | — |

`App.vue` 模式切换处（`:88-93`）目前是 `v-show`，改为 `<Transition name="v-page-cross" mode="out-in">` 包裹 `TranslateView/EditorLayout`。

### 2.2 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    transition-duration: 0.001ms !important;
  }
}
```

加在 `tokens.css` 末尾。所有 keyframes（`drag-pulse` `step-pulse` `btn-spin`）保留但被 a11y 媒体查询关闭。

### 2.3 主题切换：View Transitions API

`App.vue:355 toggleTheme()` 改为：

```ts
function toggleTheme(e?: MouseEvent) {
  const apply = () => { isDark.value = !isDark.value; persist() }
  if (!document.startViewTransition || !e) return apply()
  document.documentElement.style.setProperty('--vt-x', `${e.clientX}px`)
  document.documentElement.style.setProperty('--vt-y', `${e.clientY}px`)
  document.startViewTransition(apply)
}
```

CSS：

```css
::view-transition-old(root), ::view-transition-new(root) { mix-blend-mode: normal; }
::view-transition-new(root) {
  animation: vt-clip-in 320ms var(--ease-emphasis);
}
@keyframes vt-clip-in {
  from { clip-path: circle(0 at var(--vt-x) var(--vt-y)); }
  to   { clip-path: circle(150vmax at var(--vt-x) var(--vt-y)); }
}
```

Safari fallback：直接走原瞬时切换。

---

## 3. 通用组件（`src/components/ui/`）改造

### 3.1 UiButton（`UiButton.vue`）

- 新增 `bezel` 变体：`background: var(--c-surface-2); border-color: var(--c-surface-3); box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 0 rgba(0,0,0,0.2);`
- `:hover` 加 `transform: translateY(-1px)`，`:active` 改为 `transform: scale(.97)`（替换现有 `translateY(1px)`，`UiButton.vue:55`）。
- icon-left 入场加 0.3s 旋转：`<slot name="icon-left" />` 包一层 `<span class="btn-icon">`，加 `@keyframes btn-icon-in { from { transform: rotate(-30deg); opacity: 0; } }`。
- `loading` 状态：spinner 替换为三点呼吸（`btn-loader-dots`），减少视觉割裂。

### 3.2 UiSegmented

当前是文字切换无指示。升级要点：

- 加 sliding indicator：`<span class="seg-indicator" :style="{ left, width }" />`，绝对定位在选中项后方。
- 切换用 `transition: left/width var(--motion-base) var(--ease-emphasis)`。
- 选中项文字 `color: var(--c-text-0)`，未选中 `color: var(--c-text-3)`，hover 提升一档。
- 引用处需重测：`AppTopBar.topbar-center`、`AppTopBar settings-popover sp-tabs`、`AppTopBar engineOptions`、`TranslateView viewMode`。

### 3.3 UiPopover / UiDropdown

- 入场：`v-scale-in`（origin 取 `--popover-origin`，trigger 自动设为 `top right` / `bottom right`）。
- 背景：`backdrop-filter: blur(24px) saturate(1.5)`，`background: color-mix(in srgb, var(--c-surface-1) 88%, transparent)`。
- 阴影：`var(--elevation-3)` + `border: 1px solid var(--c-glass-border)`。
- `UiDropdown` 列表项 hover 加左 2px accent 装饰条：`box-shadow: inset 2px 0 0 var(--c-accent)`，过渡 `var(--motion-fast)`。

### 3.4 UiInput / UiTextarea

`AppTopBar.vue:88-104, 110-115, 173-179`、`TranslateView` 等多处仍直接 `<input>/<select>`。统一替换为 `UiInput`、`UiSelect`。

`UiInput` 升级：

- focus 用 `box-shadow: var(--ring-focus)` 替代 border 变色（更现代）。
- 错误态加 `aria-invalid` + 一次 0.4s 抖动 keyframe。
- 支持 `<template #prefix>` `<template #suffix>` 插槽（icon、单位）。

### 3.5 新增组件

| 组件 | 路径 | 责任 |
|---|---|---|
| `UiToast.vue` + `useToast.ts` | `src/components/ui/`、`src/composables/` | 4 等级 toast，全局唯一；接管 `EditorLayout.showExportToast()`（`EditorLayout.vue:429-433`）、各处 `console.error`。位置右下，最多 3 条堆叠，自动消失 3s |
| `UiSkeleton.vue` | `src/components/ui/` | 行/卡片/圆形三种形状；shimmer 过 1.6s linear。用于 FileTree 初始化、TranslateView 上传中、AgentPanel 等待响应 |
| `UiKbd.vue` | `src/components/ui/` | 抽 `EditorWelcome.vue:45` 的 `<kbd>`，统一字体、阴影 |
| `UiEmpty.vue` | `src/components/ui/` | 空状态：图示 + 标题 + 副标题 + 主操作。用于无文件夹的 FileTree、空对话的 Agent、无结果的 Zotero 搜索 |
| `UiCommandPalette.vue` | `src/components/ui/` | 升级现有 `CommandPalette.vue`：分组、模糊匹配、最近使用、显示快捷键 |

---

## 4. 关键场景重构

### 4.1 顶栏（`AppTopBar.vue`，高优）

**问题**：右侧从左到右堆了 9+ 个控件，密度过高，且和"研墨"的克制气质冲突。

**重构方向**：把顶栏改为**悬浮玻璃条（floating glass）**，不贴边、不撑满，给整体留白。

1. **高度** `44 → 52px`，更舒展；`padding: 0 24px`；外层 `padding-top: 8px`，使顶栏成为悬浮元素。
2. **背景**：`background: color-mix(in srgb, var(--ink-1) 72%, transparent); backdrop-filter: blur(20px) saturate(1.6); border: 1px solid var(--ink-4); border-radius: var(--radius-card); margin: 8px 12px 0;` —— **不再贴满整个窗口顶部**，而是一条 12px 内缩的玻璃条。
3. **brand 区**改为 serif "研墨" 字样 + 一个微型水墨晕染 SVG 圆形 logo。点击 brand 展开 about popover（版本、Changelog、Github）。
4. **中部 mode segmented**：
   - 应用 §3.2 sliding indicator。
   - **指示条用朱砂色**（`var(--vermilion-0)`），仅这一处主导航用朱砂，作为"你在哪一模式"的视觉锚点。
5. **StatusCluster 折叠为单点**：
   - 直径 8px 的圆 + 1px halo + 引擎名称 chip（`Ollama · qwen3:8b`）。
   - 点击展开 popover：明细表（后端 / Ollama / Cloud / Tectonic），每行一个状态条 + 操作按钮。
   - 颜色按"最低优先级"取：任一离线 → warn；后端离线 → danger。
6. **引擎切换前置**：把"本地/云端"作为状态 popover 内的第一个开关，并在 chip 上做镜像（点击 chip 直接切换），不再藏到设置里。
7. **设置 popover**：宽度 320 → 380，所有原生 input/select 替换为 `UiInput/UiSelect`，新建 `UiSlider`（带数值浮泡）。tab 切换用滑动指示器。
8. **窗口控件**：默认显示 6px 圆点（macOS 灯式）；hover 整组时显示 icon。Windows 习惯不强求，可加 `data-platform` 区分。
9. **声学层级**（CSS 不可见但要做）：顶栏与下方内容之间加一条 1px 渐隐渐变线 `linear-gradient(to right, transparent, var(--ink-4) 20%, var(--ink-4) 80%, transparent)`——这是"页眉"的骨架记忆点。

### 4.2 翻译模式 `TranslateView.vue`

#### 4.2.1 Idle 态（`TranslateView.vue:5-41`）—— 第一印象阵地

整体改为**对开版式**（asymmetric two-column）：

```
+------------------- 版心 720px ------------------+
|                                                  |
|  [左] hero 标题 + 副标题      [右] drop-zone 卡  |
|  serif 大字 "学术文献翻译"     dashed 玻璃        |
|  小字英文副标 "Scholar         + 拖拽提示        |
|  Translator"                                    |
|                                                  |
|  [底] 横排 chips + "最近翻译" 横向缩略列表        |
+--------------------------------------------------+
```

- **hero**：
  - 主标 `Noto Serif SC` + 字重 700 + `var(--text-display-lg)`（44px）+ `letter-spacing: -0.025em`。
  - 副标 EB Garamond italic + 28px + `color: var(--text-3)`，例：*"Scholar Translator · 落笔即读"*。
  - 主标左侧加 4px × 32px 朱砂色立柱（`background: var(--vermilion-0)`），仿古籍版心鱼尾。
- **drop-zone**：
  - 容器圆角 `var(--radius-card)`，dashed 描边改为 1.5px + `border-color: color-mix(in srgb, var(--accent-0) 40%, transparent)`。
  - 内置一个**水墨晕染 SVG 背景**（`<feTurbulence>` + `<feDisplacementMap>`，半透明，循环 18s 缓慢漂移）—— 这是"墨在纸上慢慢晕开"的隐喻，落地即停。文件已新建在 `src/assets/ink-bloom.svg`。
  - hover：`transform: translateY(-2px)` + `box-shadow: 0 24px 48px var(--accent-glow), 0 1px 0 var(--accent-1) inset`，墨晕动画提速 3 倍。
  - 鼠标点击：从光标位置发散一次 ripple（200ms），落地处 dz-icon 旋转 `15deg → 0deg` 弹回。
- **format chips**：横排 + 左右 mask 渐隐，底部 `font-feature-settings: "tnum"` 让数字单宽。
- **最近翻译**：横向缩略卡（最多 5 张），每张 80×100 缩略图（PDF 首页截图，后端已可生成，否则走通用图标），文件名在底部 1 行。点击 → 直接重译。
- **空闲微动**：drop-zone 边框存在一条 360° 缓慢游走的 1px 高亮点（CSS conic-gradient + `animation: orbit 12s linear infinite`），让 idle 不死寂。`prefers-reduced-motion` 下关闭。
- `error-banner`：增加"复制错误信息"按钮，`UiButton variant="ghost" size="sm"`。

#### 4.2.2 Working 态（`:44-107`）

- step dot 完成时加 spring 弹动：`@keyframes step-done-pop` + `transform: scale(.85→1.15→1)`。
- `progress-fill`：在现有渐变上叠加流光：`::after` 半透明白色斜条，`background-position` 1.6s linear 循环。
- `live-preview`（`:97-106`）改为 stack-card：
  - 新条目从底部滑入（保留），但先前条目向上挤压并轻微缩小（`scale(.98)` + `opacity: 0.85`）。
  - 滚动锚点固定在最新条目。
- **新增"取消翻译"按钮**：右上角，调用 `useTranslate.cleanup()`。当前架构没有取消能力——确认 `useTranslate.ts` 是否有 `AbortController`，没有则后端要加 `/api/translate/{id}/cancel` 接口（不在前端方案范围）。
- 块翻译失败实时提示：当 `state.misalignedChunks > 0` 时，working-card 顶部出现一条 inline 警告（折叠/展开）。

#### 4.2.3 Done 态（`:109-204`）—— **签名瞬间 #2**

这一帧是用户截图概率最高的页面，必须有戏剧性，但不能像营销页。

**入场编排**（按时序）：

1. 进度条满 100% → 停 240ms（让用户的眼睛追上）。
2. `v-page-cross` 切到 done 视图。
3. **宣纸展开动画**（核心）：result 容器从 `clip-path: inset(0 0 100% 0)` 0.6s `var(--ease-emphasis)` 展开到 `inset(0)`，配合 `transform-origin: top` 的 `scaleY(.98 → 1)`，营造"卷轴/宣纸自上而下铺开"的错觉。
4. **朱砂印章**（核心）：右上角一次性盖下一枚 56×56 SVG 印章（白底朱砂篆字"研墨"或对勾），动画为 `rotate(-12deg) scale(0.6) → rotate(0) scale(1.05) → rotate(0) scale(1)`，420ms `var(--ease-spring)`，落地后停留。印章位置 `top: 12px; right: 16px;`，绝对定位。**这是研墨最强的签名记号。**
5. confetti **不要**——太 SaaS 太廉价，与产品气质冲突。

**`result-bar` 重构**：

- 左侧：serif 大字"翻译完成"`var(--text-xl)`，下方一行小字 `Garamond italic` 元数据（"3,824 字 · 12 页 · 41 块 · 用时 18.3s"）。
- 右侧操作分级：
  - 主操作：`导出` `UiButton variant="primary"`，hover 时朱砂边框微闪（一次）。
  - 次操作：`复制全文` / `保存到工作台` / `发给 Agent`，`UiButton variant="bezel"`。
  - 危险操作：`新翻译`（清空当前结果），`UiButton variant="ghost"` 放最右、低调。
- 取消现"重启后端" `error-banner`（`:144-147`），改走 `UiToast`。

**句对齐 hover**（`:909-927`）：
- 背景色 `var(--accent-soft)` 保留。
- 加左侧 2px 朱砂细线（`box-shadow: inset 2px 0 0 var(--vermilion-0)`），暗示"批注"。
- 对应译文同步出现一条同色细线 → 视觉上"两栏被一根朱砂线穿起来"。

**视图切换** bilingual ↔ translation：`v-fade mode="out-in"`，外加 0.18s `transform: scale(.99 → 1)`，给操作一点重量感。

**失败块** `.dual-failed`：左 3px 朱砂条（**唯一允许使用第二处朱砂**——但仅在错误态）+ soft bg + `重试` 主操作 + `查看原文`折叠按钮。

### 4.3 编辑器 `EditorLayout.vue`

#### 4.3.1 三栏布局

- 三栏间分隔线改为 1px `linear-gradient(to bottom, transparent, var(--c-surface-3) 20%, var(--c-surface-3) 80%, transparent)`，两端淡出。
- `resize-handle`（`:609-617`）：默认 4px 透明，hover 时 4px accent + 鼠标 ::cursor 强化；激活时（拖拽中）8px。

#### 4.3.2 FileTree（`FileTree.vue`）

- `tree-search` 升级为 `UiInput` + 前缀图标 + 清除按钮。
- 文件项 hover 加 2px accent 左条（`box-shadow: inset 2px 0 0 var(--c-accent)`），过渡 `var(--motion-fast)`。
- 文件夹展开/折叠：`max-height: 0 → auto`（用 `:style="{ maxHeight: open ? '500px' : '0' }"`）+ `opacity`，`var(--motion-base)`。
- 搜索命中：将匹配子串 `<mark>` 包裹，加 `background: var(--c-accent-soft); color: var(--c-accent-hover);`。
- 空状态用 `UiEmpty`：图标（FolderOpen）+ "未打开文件夹" + 主按钮。

#### 4.3.3 EditorTabs / EditorWelcome / EditorToolbar

- `EditorTabs`：活动 tab 底部用 absolute 2px **朱砂**滑动条（仅一处，签名级标识——"你正在编辑这一篇"）；非活动 tab 关闭按钮 hover 显示。
- **`EditorWelcome.vue:13-42` 大改**——这是新用户进入编辑器看到的第一屏，不能再像 onboarding 模板：
  - 整页改为**全幅 hero**：
    - 顶部 `serif` 大字"开始一篇论文"（`var(--text-display-lg)` 44px，仿宋活字感）。
    - 下方一行 `Garamond italic` 副标，例：*"Where research takes form."*
    - **背景**：极淡的水墨"研墨"二字（PNG 或 SVG，`opacity: 0.04`，`scale(2)`，居中），透过文字若隐若现。
  - 4 张 `wc-card` 改为 **magazine 不对称栅格**：
    - 主卡（"新建工程"）跨 2 列高 1.5 行，包含一张抽象矢量插画（手绘风格的笔尖 + 节点图）。
    - 其余 3 张小卡同高，单列。
    - 每卡顶部一条 1px 渐变线，hover 时朱砂亮起（仅 1px、克制）。
  - 底部 `welcome-shortcuts` 改为**横排 chip 阵列**，每个 chip 内 `UiKbd` + 功能名，hover 反白（`var(--ink-3)`）。
- `EditorToolbar`：图标按钮加 tooltip（`UiTooltip`），所有 emit 操作反馈走 `useToast` 而非 `exportMessage`。

#### 4.3.4 右侧 Tab 面板

- `rp-tab` 切换加 sliding underline。
- `rp-content` 切换 `v-fade out-in`。
- AiPanel 输入框聚焦时容器加 0.5px accent ring（`box-shadow: 0 0 0 1px var(--c-accent-soft)`）。
- AiPanel 流式结果：新建 `useTypewriter` composable，按字符渲染（约 25-40 字/秒，可由用户关闭），增强"AI 正在写"的临场感。

### 4.4 Agent 面板 `AgentPanel.vue`—— **签名瞬间 #3**

把现有"事件流"升级为「**砚台滴墨**」的视觉隐喻——每条思考事件像一滴墨从砚台滴入水中，缓慢扩散。

- **入场**：从右侧滑入 + spring 110% → 100%（`var(--ease-spring)`，`var(--motion-page)` 320ms）。整体面板加一条 1px 朱砂边（仅左边缘 `box-shadow: inset 1px 0 0 var(--vermilion-0)`）作为"批注栏"暗示。
- **浮动模式**拖拽：`box-shadow: var(--elevation-4)`，释放 spring 回弹（半径 6px 内反弹一次）。
- **事件流（核心）**——给每个 event 类型一种"墨色 + 入场轨迹"：
  | event | 左竖线 1px 颜色 | 入场动效 |
  |---|---|---|
  | `thinking` / `thought` | `var(--accent-0)` 主墨 | `opacity: 0 → 1` + `mask-image` 由上至下渗透 360ms（CSS `mask-position` 过渡） |
  | `tool_call` | `#3b82f6` 钢蓝 | 左 16px 滑入 `translateX(-16px → 0)` 240ms |
  | `tool_result` (success) | `var(--c-success)` 墨绿 | `scale(.96 → 1)` 微弹 240ms |
  | `tool_result` (error) | `var(--vermilion-0)` 朱砂 | 左右轻抖 1 次 + 红条强调 |
  | `warning` | `var(--c-warn)` 土黄 | 仅淡入 |
  - 每个 event 项**整体**包成一个 12px 内边距的小卡，左侧 2px 竖线即类型色。
  - 思考链多条出现时按 `var(--motion-stagger)` 40ms 错落进入。
- **"墨色渗透"实现细节**（thinking）：
  ```css
  @keyframes ink-bleed {
    from { mask-image: linear-gradient(to bottom, #000 0%, transparent 0%); }
    to   { mask-image: linear-gradient(to bottom, #000 100%, transparent 100%); }
  }
  ```
- `dot-pulse`（思考中）改为单点呼吸 1.6s（不是 ping 圈），克制。
- `AgentApprovalInline` 整段高亮卡片化：`background: var(--ink-3)` + `border: 1px solid var(--accent-1)` + `border-left: 3px solid var(--accent-0)` + `border-radius: var(--radius-md)`，"等你拍板"的紧张感。
- 空状态：`UiEmpty` + 一句 italic Garamond 引语，如 *"Ask anything. The ink is ready."*

### 4.5 启动 Loader

- `InkBrushLoader` 退场加 `transform: scale(0.96)` 收缩 + opacity（同时 320ms）。
- 文案数组随机轮播：
  ```
  正在整理思路…
  调度模型，请稍候…
  研墨润笔中…
  ```

---

## 5. 操作逻辑优化

### 5.1 命令面板

升级 `src/components/CommandPalette.vue`：

- 全局 `Ctrl/Cmd+K` 触发（在 `App.vue` 注册键盘监听）。
- 命令分组：`文件 / 编辑 / 翻译 / Agent / 视图 / 设置`。
- 模糊匹配（fuzzy match，可借 `fzf-for-js` 或 50 行手写）。
- 最近 5 条命令置顶。
- 每条命令右侧显示快捷键（用 `UiKbd`）。
- 命令注册抽象成 `useCommandRegistry()`，各 composable 通过 `register({ id, group, label, run, shortcut, when })` 注册。

### 5.2 快捷键统一

| 快捷键 | 行为 | 注册位置 |
|---|---|---|
| `Ctrl+K` | 命令面板 | `App.vue` 全局 |
| `Ctrl+1` / `Ctrl+2` | 切换 translate / editor | `App.vue` |
| `Ctrl+B` | 切换文件树 | `EditorLayout.vue` |
| `Ctrl+J` | 切换右面板 | `EditorLayout.vue` |
| `Ctrl+S` | 保存（已有） | 保留 |
| `Tab` | 接受 ghost text（已有） | 保留 |
| `Esc` | 关闭最上层浮层（popover/dropdown/modal/agent panel） | 全局栈管理（新建 `useOverlayStack`） |

### 5.3 状态恢复

- 翻译结果持久化：`useTranslate` 增加 `persistDone()`，写 `IndexedDB`（结果可能 1-10MB，超出 localStorage）。下次启动若有未消费结果，顶部显示"上次未关闭的翻译" banner，可恢复或丢弃。
- 编辑器最近会话：`useEditorState` 持久化 tabs 列表（路径 + 是否 untitled + 草稿）。重启自动恢复。
- Agent 会话已存（`AgentSessionList`），加"继续上次会话"快捷入口（顶部条 24h 内最新一条）。

### 5.4 反馈统一

- 所有 `console.error` + `window.alert` + `window.prompt`（`EditorLayout.vue:349`、多处）走 `useToast()` / `useDialog()`。
- 后端离线：顶部一条 sticky 黄色 banner（`UiBanner` 新建），含"重启后端"按钮，替换 `App.vue` 当前的 `setError` 调用。

### 5.5 拖拽体验

- `App.vue` 的 `drag-overlay` 当前是固定文案。改为：
  - 检测拖拽内容（数量、扩展名），动态文案：`松开以翻译 N 个文件` / `不支持的格式：xxx`。
  - 不支持的格式：边框红色 + 禁用 cursor。

---

## 6. 实施优先级

### P0（1 周内，体感最强 → 必做）

1. `tokens.css` 重整（§1.1-1.4）；新建 `transitions.css` 全局过渡。
2. `UiButton` 微反馈（§3.1）+ `UiSegmented` sliding indicator（§3.2）。
3. `UiToast` + `useToast` + 替换 `EditorLayout.showExportToast`（§3.5、§5.4）。
4. `AppTopBar` StatusCluster 折叠 + 引擎切换前置（§4.1）。
5. `TranslateView` Idle 态升级（drop-zone 呼吸 + 最近翻译，§4.2.1）。
6. `Reduced Motion` 媒体查询（§2.2）。

### P1（2 周内）

1. `UiPopover/UiDropdown` 视觉升级（§3.3）。
2. `TranslateView` Working/Done 态（live stack、confetti、句对齐打磨，§4.2.2-4.2.3）。
3. 主题切换 View Transition（§2.3）。
4. 命令面板升级 + 快捷键统一（§5.1-5.2）。
5. `FileTree` 视觉（hover bar、搜索高亮、空状态，§4.3.2）。
6. AgentPanel 色条 + 入场动画（§4.4）。
7. 模式切换 `v-page-cross`（§2.1）。

### P2（后续）

1. `UiInput/UiSelect/UiSlider` 全面替换原生控件（§3.4）。
2. AiPanel typewriter（§4.3.4）。
3. 翻译结果 IndexedDB 持久化（§5.3）。
4. EditorWelcome magazine 布局 + 自绘 SVG 图示（§4.3.3）。
5. tokens legacy 别名移除（§1.1 第二阶段）。
6. light 模式所有组件回归测试。

---

## 7. 涉及文件一览

### 修改

```
src/styles/tokens.css                  (§1, §2.2)
src/main.ts                            (引入 transitions.css)
src/App.vue                            (§2.1 模式切换包 Transition、§2.3 主题切换、§5.5)
src/components/AppTopBar.vue           (§4.1 整体重构)
src/components/StatusCluster.vue       (§4.1 折叠为单点)
src/components/TranslateView.vue       (§4.2 全场景)
src/components/EditorLayout.vue        (§4.3.1, §5.4 toast 替换)
src/components/EditorWelcome.vue       (§4.3.3)
src/components/EditorToolbar.vue       (§4.3.3 tooltip)
src/components/EditorTabs.vue          (§4.3.3 sliding bar)
src/components/FileTree.vue            (§4.3.2)
src/components/FileTreeNode.vue        (§4.3.2 hover bar)
src/components/AgentPanel.vue          (§4.4)
src/components/AgentApprovalInline.vue (§4.4 高亮)
src/components/AiPanel.vue             (§4.3.4 ring + typewriter)
src/components/MarkdownPreview.vue     (字体令牌应用)
src/components/InkBrushLoader.vue      (§4.5 退场)
src/components/CommandPalette.vue      (§5.1 升级)
src/components/ui/UiButton.vue         (§3.1)
src/components/ui/UiSegmented.vue      (§3.2)
src/components/ui/UiPopover.vue        (§3.3)
src/components/ui/UiDropdown.vue       (§3.3)
src/components/ui/UiInput.vue          (§3.4)
src/components/ui/UiTextarea.vue       (§3.4)
src/components/ui/UiSelect.vue         (§3.4)
```

### 新增

```
src/styles/transitions.css             (§2.1 全局过渡类)
src/components/ui/UiToast.vue          (§3.5)
src/components/ui/UiSkeleton.vue       (§3.5)
src/components/ui/UiKbd.vue            (§3.5)
src/components/ui/UiEmpty.vue          (§3.5)
src/components/ui/UiSlider.vue         (§3.4 滑块抽象)
src/components/ui/UiBanner.vue         (§5.4 顶部横幅)
src/composables/useToast.ts            (§3.5)
src/composables/useOverlayStack.ts     (§5.2 Esc 栈)
src/composables/useCommandRegistry.ts  (§5.1)
src/composables/useTypewriter.ts       (§4.3.4)
src/utils/fuzzyMatch.ts                (§5.1)
```

---

## 8. 验收标准

- [ ] **可访问性**：所有交互元素 `:focus-visible` 都有可见焦点环；对比度 WCAG AA 通过（dark + light）。
- [ ] **动效**：开启 `prefers-reduced-motion: reduce` 后，无任何持续动画或位移。
- [ ] **响应式**：1920 / 1440 / 1180 / 980 四档宽度下，三栏与顶栏均不溢出、不撑破。
- [ ] **性能**：60fps（DevTools Performance 录制 5s 无帧丢失）；首屏交互可用 ≤ 600ms（含 InkBrushLoader 之后）。
- [ ] **状态恢复**：刷新后翻译完成结果可恢复，编辑器 tab 列表可恢复。
- [ ] **light 模式**：所有新增 / 修改组件在 light 主题下视觉一致、无未覆盖的 dark hex。
- [ ] **零控制台错误**：`npm run dev` 启动后浏览三个模式 + 设置弹层 + Agent 面板，控制台无 error/warning。
- [ ] **测试**：`src/__tests__/` 现有用例不破坏；为 `useToast`、`useCommandRegistry`、`fuzzyMatch` 新增单测。

---

## 9. 风险与回退

| 风险 | 缓解 |
|---|---|
| Tokens legacy 别名移除可能漏改组件 | P2 阶段执行；分两步：先标 `@deprecated` + 控制台警告 wrapper，再删 |
| View Transitions API 在 Safari/旧 WebView 不支持 | 自动 fallback 到瞬时切换；`if (!document.startViewTransition)` 已处理 |
| Confetti 引入 8KB | 设计为可关闭（默认开），通过 `useUserPreference('motion.confetti')` 控制 |
| StatusCluster 折叠后用户找不到细节 | 默认 hover 即展开 popover；首次点击有引导 tooltip（一次性） |
| IndexedDB 翻译结果持久化数据迁移 | 加版本号字段；schema 升级走 `onupgradeneeded` |
| 快捷键与 Monaco 冲突（Ctrl+K） | 仅在编辑器未聚焦时全局生效；Monaco 内 Ctrl+K 保持其原行为 |

---

## 10. 给实施 AI 的执行约束

1. **不要**重写 `useTranslate`、`useEditor`、`useAgentChat` 的核心业务逻辑——本方案只动 UI 层。如确需触动 composable，仅追加（不修改现有签名）。
2. **不要**升级或替换 Monaco / VueFlow / DOMPurify / marked 这类底层依赖。
3. **不要**引入 UI 框架（Element Plus / Naive UI 等），保持手工 ui/ 体系。
4. **可以**引入小型工具：`canvas-confetti`、`fzf-for-js`（或自写）、`@vueuse/core`（若尚未引入则评估必要性）。
5. **每个 PR 限定一个 P 项**（如 `P0-1: tokens 重整`、`P0-2: UiButton 微反馈`），便于回归。
6. **CSS 编写**：组件内 `<style scoped>`，全局只放 `tokens.css` 和 `transitions.css`；禁止用 `!important` 除非覆盖 Monaco 内置样式。
7. **类型**：所有新增 composable 全 TypeScript；`defineProps` 用类型字面量（参考现有 `UiButton.vue:19-26`）。
8. **测试**：每个新建 utility 至少一份 `*.test.ts`（参考 `src/__tests__/streamReader.test.ts`）。

---

---

## 11. 签名瞬间清单（Signature Moments）

下列 7 处是"研墨"在所有竞品里**最容易被一眼记住**的视觉/动效记忆点。它们是本方案的灵魂；如果实施 AI 出于工程便利只挑了"看起来像 Linear"的那部分而砍掉这些，那次升级就失败了。**全部必做**。

| # | 场景 | 文件 | 视觉/动效核心 | 不可替代性 |
|---|---|---|---|---|
| 1 | 启动 | `InkBrushLoader.vue` + `App.vue` | 水墨晕染 logo 由淡到浓，serif "研墨" 二字浮现，1.4s 完成；退场时 scale(.96) + clip-path 收缩 | 第一秒就告诉用户"这是一个有审美的应用" |
| 2 | 翻译完成 朱砂印章 | `TranslateView.vue` done state | 右上角 56×56 SVG 朱砂印章 spring 落下 + 卷轴自上而下展开 result 容器 | 截图传播力的核心，所有营销图都用这一帧 |
| 3 | Agent 思考 渗墨 | `AgentPanel.vue` event stream | 思考链以"墨色由上至下渗透"显示，每条左侧 1px 主墨竖线 | 解释 ReAct 流程 + 强化品牌 |
| 4 | 模式切换 朱砂指示条 | `AppTopBar.vue` segmented | 中部 mode 切换的 sliding indicator 是朱砂色（全局唯二朱砂之一） | 导航锚点，下意识看一眼就知道在哪 |
| 5 | drop-zone 墨晕呼吸 | `TranslateView.vue` idle | SVG `<feTurbulence>` + `<feDisplacementMap>` 的水墨晕染慢漂 18s，hover 提速 3 倍 | idle 不死寂，专业感 |
| 6 | 句对齐朱砂细线 | `TranslateView.vue` dual-view | hover 句子时，原文与译文同步出现一条朱砂左竖线"穿起两栏" | DeepL 也只做高亮，研墨做"批注线"——细节差异即专业感 |
| 7 | EditorTabs 朱砂活动条 | `EditorTabs.vue` | 活动 tab 底部 2px 朱砂滑动条 | 长时间凝视编辑器时持续提示当前焦点 |

### 11.1 朱砂的全局预算（约束）

整个应用允许出现朱砂色 `var(--vermilion-0)` 的位置**仅限**：
1. hero 主标左侧鱼尾立柱（idle）
2. mode segmented indicator
3. 翻译完成印章
4. 句对齐左竖线
5. EditorTabs 活动条
6. 错误致命态 `dual-failed` 左条
7. AI 编辑 accept 主按钮（可选）

**超过这个预算就是失控**。实施 AI 必须在 PR 描述里逐一标注本次引入了哪一个、并确认未超预算。

### 11.2 字体加载策略

- 在 `index.html` `<head>` 预加载 `Noto Serif SC` 和 `EB Garamond` 的 woff2（仅 200/700 两档），`<link rel="preload" as="font" crossorigin>`。
- `font-display: swap`，闪烁期 fallback 到 `Songti SC` / `Times New Roman`。
- Inter Variable 同样 preload。
- 不引入 `LXGW WenKai` 全量字体（10MB+）；仅作为"用户可选"的阅读区字体，按需 CDN 加载。

### 11.3 实施 AI 自检清单

实施完一个 P0 / P1 阶段后，对照下列问题自答：

1. 用户截图发到 Twitter/X，第一眼能否识别这是"研墨"而非任意通用 AI 产品？
2. 朱砂色出现的位置是否仍然只在 §11.1 列表中？
3. 字体栈是否真的加载了 serif，hero/done 是否真的是衬线大字？
4. 删除所有动画后产品是否仍然可用？（`prefers-reduced-motion` 检查）
5. 三个签名瞬间（启动 / 翻译完成 / Agent 思考）是否都做了？

任一答"否"——这一阶段就没完成。

---

> 方案完。本文档以"另一个 AI 实施"为前提书写：先读 §0 建立审美锚点，再按 §6 优先级逐步落地，每个 PR 自检 §11.3。
