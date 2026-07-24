# 研墨 UI / 动效 / 特效 · 目标体验蓝图(Target Experience Blueprint)

> 范围:Scholar Assistant(研墨)Vue 3 桌面前端的**目标态**——视觉语言、动效系统、特效与签名时刻、每屏终态。
> 定位:本文件回答"**到底应该是什么样子**";执行路线见 `frontend-consistency-audit.md`,第一步补丁见 `frontend-phase0-patch.md`。
> 铁律:**不换配色**(保留暖墨/纸 `#14130f`/`#FAF8F3` + 蓝紫强调 `#5b6cff` + 朱印 `#C8503A`),只换**工艺层**(材质、排版、动效、特效、微交互)。AI 是主角(右面板默认常驻)。
> 反 AI-slop 清单(明确禁止):青蓝渐变、霓虹辉光、默认深色发光、通用回弹缓动、Inter/Roboto 当唯一字体、生硬玻璃大面积、无意义装饰笔触。

---

## 0. 一句话目标

把研墨从"**能用的学术工具**"做成"**写出来有仪式感的墨工作间**":纸张有温度、墨迹有呼吸、AI 像一位坐在身侧的学者——安静,但随时在场。

质量标尺:Apple HIG 三支柱 **Clarity / Deference / Depth** + WCAG 2.1 AA;差异化靠"墨与纸"身份,不抄玻璃拟态。

---

## 1. 视觉语言(材质 + 排版 + 色彩纪律 + 深度)

### 1.1 纸张材质系统(替代"平涂 + 生硬边框")
| 场景 | 处理 |
|---|---|
| 暗色活动页面 | 一层**暖灯下稿纸光晕**:`radial-gradient(120% 80% at 50% 0%, rgba(255,240,210,0.05), transparent 70%)` 固定在 editor backdrop,模拟台灯稿纸 |
| 亮色活动页面 | 极淡纸纤维:`feTurbulence` SVG 噪点,`opacity ≈ 0.025`,或纯色 + 1px 毛边;**不**用大块投影 |
| 表面层级 | 4 层 `surface-0`(app bg)→`surface-1`(面板)→`surface-2`(卡片)→`surface-3`(输入/凸起),每层定义 bg + 1px 边框 + 柔阴影,形成"纸层叠"而非硬分隔 |
| 玻璃 | **仅浮层**(`UiCard glass` 克制用);禁止大面积 `backdrop-filter`(贵且伤可读性) |

### 1.2 排版工艺(CJK 优先,这是写作工具的核心体面)
- **字体**:标题/强调用衬线 `--font-serif`(Noto Serif SC / EB Garamond);正文用系统中文无衬线(可靠、不强行换 Inter)。混排即"学术感",不靠花字体。
- **字号阶梯(rem,基准 16px)**:

  | Token | 值 | 用途 |
  |---|---|---|
  | `--text-display` | 1.75rem / 28px | 欢迎页主标题 |
  | `--text-h1` | 1.5rem / 24px | 屏标题 |
  | `--text-h2` | 1.25rem / 20px | 区块标题 |
  | `--text-h3` | 1.125rem / 18px | 卡片标题 |
  | `--text-body` | 0.9375rem / 15px | 正文 |
  | `--text-sm` | 0.8125rem / 13px | 辅助 |
  | `--text-xs` | 0.75rem / 12px | 标签/元信息 |

- **行高**:正文 `--leading-normal: 1.6`;标题 `--leading-tight: 1.25`;列表 `1.5`。
- **CJK–Latin 间距**:`text-spacing-trim: space-first` + `text-autospace`(或手动 `word-break` 规则),消灭中英文"挤/太空"两极端。
- **数字对齐**:`font-variant-numeric: tabular-nums`(统计/页码/引用标号)。
- **悬挂标点**:引号/书名号 optical 处理,不顶格、不突出版心。
- **光学尺寸**:`font-optical-sizing: auto`。

### 1.3 色彩纪律(保留现有,收敛 sprinkling)
- `--c-accent #5b6cff` **只**用于主操作 + 激活态;次级动作走 `--c-surface-*` / `--c-text-*`。
- `--brand-red #C8503A` **只**用于朱印签名 + 极少数警示强调。
- 关系色抽 `--rel-*` 单源(论证/导图:绿/蓝/浅蓝/琥珀/橙 + 暗色调校),亮暗两套。
- 语义色:`--c-success` / `--c-warn` / `--c-danger` / `--c-info` 明确,不混用 accent。

### 1.4 深度与阴影(柔和长投影,暖调)
| 级 | box-shadow | 用途 |
|---|---|---|
| `--elevation-1` | `0 1px 2px rgba(20,19,15,0.06)` | 卡片静息 |
| `--elevation-2` | `0 4px 12px rgba(20,19,15,0.08)` | 卡片 hover / 浮起 |
| `--elevation-3` | `0 12px 28px rgba(20,19,15,0.12)` | 弹窗 / 命令面板 |
| `--elevation-4` | `0 24px 60px rgba(20,19,15,0.18)` | 模态 / Toast 栈顶 |

亮色投影更淡(同结构降 alpha),暗色投影用暖黑 `rgba(0,0,0,0.4)`。**禁止硬黑 + 霓虹辉光**。

---

## 2. 动效系统(用户重点 · 全局令牌)

### 2.1 缓动 / 时长令牌(写进 tokens.css)
```css
--ease-out:       cubic-bezier(0.22, 1, 0.36, 1);   /* expo-out,默认通用,无过冲 */
--ease-emphasized:cubic-bezier(0.20, 0, 0, 1);      /* 重要出现:起快落稳 */
--ease-spring:    cubic-bezier(0.34, 1.56, 0.64, 1);/* 仅限俏皮签名(朱印),带微过冲 */
--dur-micro:  120ms;
--dur-small:  160ms;
--dur-base:   220ms;
--dur-large:  320ms;
--dur-xl:     420ms;
```
**铁律**:布局/面板/视图转场**默认 `--ease-out`**,绝不用 `--ease-spring`(回弹只给朱印等 ≤2 处签名时刻)。

### 2.2 转场库(每组件条件渲染挂哪套,统一契约)
| 名称 | 形态 | 时长/缓动 | 用于 |
|---|---|---|---|
| `v-fade` | opacity 仅 | 160ms / out | 内容切换、tab 内容 |
| `v-scale-in` | scale .96→1 + opacity | 220ms / emphasized | 浮层、弹窗、下拉 |
| `v-slide-up` | translateY 8→0 + opacity | 220ms / out | Toast、hint、底部条 |
| `v-spring` | 压下 scale + 微旋 | spring | 朱印、徽章采纳 |
| `v-unfurl` | clip-path/max-h + opacity | 320ms / emphasized | 面板展开、宣纸展开 |
| `v-page-cross` | 共享元素 + cross-fade | 320ms / out | 视图切换(接回/删死代码) |
| `--anim-stagger` | 每项 +40ms delay | — | 列表/卡片错峰入场 |

### 2.3 微交互编排(高频组件的具体手感)
- **按钮**:hover 抬升 1px + 底色微变;active `scale(.97)`;loading 三点呼吸;focus 环 `--ring-focus`。主按钮用 accent 填充,次按钮用 surface 描边。
- **卡片**:hover 边框染 `--c-accent-soft` + 抬升 2px + 阴影升一级;可选极淡内光(`inset 0 1px 0 rgba(255,255,255,.04)` 暗色)。
- **输入**:focus 边框 accent + 环;错误态红边 + 下方红字(tabular 对齐);placeholder 用 `--c-text-3`。
- **开关/分段**:滑块 `--ease-spring` 短位移(≤120ms);选中态 accent 底。
- **标签栏**:激活指示条 `slide` 到目标 tab(`--ease-emphasized`),非瞬切。

---

## 3. 特效与签名时刻(让"一般"变"记得住")

### 3.1 墨滴 Bloom 启动(替代现有 InkBrushLoader)
- 一滴墨从中心 `scale(0)→1` + `blur(8px)→0` 晕开成 UI 入场;保留"研"字朱印 + 扫描进度条。**首屏即建立"墨工作间"基调**。

### 3.2 朱印 Seal(导出 / 保存完成)—— 最高级签名
- 朱红印章 `#C8503A` `v-spring` 压下 + 微旋(≤6°) + 落定回弹,伴极短 `anim-flash`(opacity 脉冲 120ms)。比笔触揭示更"贵气"且贴研墨。**全产品唯一允许回弹的动效**。

### 3.3 专注模式 Focus Mode(写作 App 的体面大头,当前缺失)
- 写作时顶栏/侧栏 `opacity + translateY` 缓退(`--dur-large` / out),正文独占;鼠标移动 / `Esc` 召回。
- **AI 面板不在此列**:专注模式只淡出 chrome,右 AI 面板保持常驻可召回(呼应 AI 主角)。

### 3.4 结构图 FLIP(论证图 / 思维导图)
- `autoLayout()` 与节点增删当前硬跳/重建 → 改 **FLIP**(First-Last-Invert-Play)平滑位移;节点入场 `v-spring` 错峰(≤2 处,允微弹)。

### 3.5 笔触降级为纹理
- `v-brush-stroke` 仅用于个别文本揭示(如 AI 总结首行);`v-ink-bleed` 作 hover 微纹理。**不作主语言**(用户评"一般")。

### 3.6 视图连续性(View Transitions API)
- 主题切换:圆形 clip 扩展(已有)→ 保持。
- 欢迎页项目卡 → 点击 **expand 成编辑器**(共享元素)。
- 命令面板结果 → **原地展开**为目标视图。
- 模式切换 → 共享元素 + `v-page-cross`。

---

## 4. 每屏目标态(具体"完成时长这样")

### 欢迎页
- 居中主标题(衬线,`--text-display`)+ 一句价值主张;**大号主 CTA"新建文档"**(accent 填充,hover 抬升);右侧/下方"最近项目"卡片行(错峰入场)。
- 空态:单色 ink 线稿插画 + "还没有文档,开始第一篇" + 主 CTA(教育性,非纯文字)。

### 写作视图(三区 IA,AI 常驻)
- **左**:文档大纲(可收起为 42px 轨,收起态显示章节点)。
- **中**:画布=主表面。衬线标题 + 无衬线正文,纸张材质(1.1 光晕/纤维),版心 `--page-width` 居中,行高 1.6。顶部一键"专注模式"。
- **右**:AI 面板**默认常驻、默认 AI 标签**。空态:`ac-empty` 线稿 + "问我任何问题,或 @ 引用选中文字"引导 + 预设 chips(polish/expand/review…)。消息气泡用纸卡,AI 头像用朱印小章。

### 翻译视图
- 双栏对照(原文 / 译文),当前翻译块**墨流高亮**(从左到右 `--c-accent-soft` 扫光,非闪烁);进度条用墨滴填充;逐句完成打朱点。

### LaTeX 视图
- 左源码(等宽,tabular)/ 右预览;`AiPanel workspace-variant` 常驻右侧,预设 polish/expand/rewrite/compliance。

### 思维导图
- canvas + 右侧 AI 提示(可收 42px 轨);节点卡片纸感,增删 FLIP;关系连线用 `--rel-*` 单源,hover 高亮当前分支。

### 论证 / 审稿
- 关系色 `--rel-*` 单源;节点卡片纸感;采纳某条建议 → 朱印"已采纳"动画(`v-spring`);反驳输入 focus 环。

### 设置中心
- 分组卡片(表面层级清晰);开关滑块 spring;主题切换即时无闪烁(shared transition);键盘全可达。

---

## 5. 空 / 加载 / 错误态(设计时刻,非占位)

- **骨架屏**:遵循纸张版心(非灰色块),列表 `--anim-stagger` 错峰。
- **空状态**:单色 ink 线稿插画 + 一句引导 + 主 CTA(`UiEmpty.vue` 接入 TranslateView / EditorLayout / 各空列表)。
- **错误**:非阻断 `Toast`(`v-slide-up`)+ 内联红字;危险操作走确认模态(`v-scale-in`,焦点陷阱 + Esc + 焦点归还)。
- **加载**:墨滴进度(翻译/导出),非转圈。

---

## 6. 可达性 & 性能(底线)

- WCAG 2.1 AA:全局焦点环(已存在,见审计 §5·A 收窄)、对比度达标、模态焦点陷阱 + 归还。
- `prefers-reduced-motion`:全局降级(已存在 tokens.css:345),保持。
- 60fps:动效只用 `transform` / `opacity`;`will-change` 按需;不与 monaco/图懒加载(D1/D3)抢主线程。

---

## 7. 与执行计划的关系

- **本蓝图 = "目标"**(what it should be)。
- `frontend-consistency-audit.md` = "路线"(Phase 0→3,WS1–WS4)。
- `frontend-phase0-patch.md` = "第一步"(边框修复 / 焦点环收窄 / 导航反馈)。
- **建议**:先做**写作视图 + 欢迎页**两个原型屏目检(材质 + 排版 + 朱印 + 专注模式),确认手感后再按 Phase 铺开其余屏与动效库。视觉/动效进阶不整包铺开,避免返工。
