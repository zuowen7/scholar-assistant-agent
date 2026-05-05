# 研墨 · 前端美学优化执行报告

> 这份文档是给执行 AI 看的。请按顺序阅读，不要跳过"诊断"和"原则"直接动手。
> 所有文件路径相对于仓库根目录 `D:\pycharm_study\translator`。

---

## 0. 阅读须知（务必先读）

- **设计已有的资产**：项目已经有完整的 token 系统（`src/styles/tokens.css`）、墨韵主题（朱砂/靛青/砚石/宣纸）、大量动效（光晕、粒子、卷轴、笔触）。**不要推倒重做**——现有设计语言是合格的，问题是**节奏失衡 + 局部败笔**。
- **设计原则覆盖**：美学要服从下面"原则"，原则冲突时按本文档优先级裁决。
- **能不动就不动**：每改一处都要写明"为什么必须改"。已经合格的不要动。
- **每个任务写完都要在 dev 模式跑一次**：`npx tauri dev`（Windows 用 `start_dev.bat`），切到对应场景目视验收。**不要只跑类型检查就当完成**。
- **不要新增动画**：现有动效已经偏多，本次任务以"删减、统一节奏、提升排版"为主，新增动画须在报告中明确批准的项里。

---

## 1. 问题诊断

### 1.1 印章太突兀（用户首要痛点）

**位置**：`src/components/TranslateView.vue:189-207`（模板）+ `:1435-1482`（样式）

**当前实现**：
- 一个 56×56px 朱砂红方形 SVG 印章，里面竖排"研 / 墨"二字
- 落点在 `done-wrapper` 右上角 `top: 24px; right: 28px;`，绝对定位
- 入场动画：`stamp-down` 560ms（从上方旋转回弹落下）+ `seal-splash` 散墨环
- 朱砂阴影：`drop-shadow(0 3px 10px rgba(200,80,58,0.4))`

**为什么突兀**（按视觉权重排序）：
1. **饱和度过高**：纯朱砂 `#C8503A` 在暗色界面上是**最高对比度色块**，比正文还抢眼，注意力被一个 56px 的角落小方块拽走
2. **形态廉价**：方章 + Roughen 噪声滤镜在小尺寸下表现像"按图索骥的图标"，不像真正的篆刻——边缘锯齿、质感塑料感
3. **定位飘**：和右侧导出按钮 / 顶部卷轴轴在同一视觉热点区，形成"右上角扎堆"
4. **动画过激**：560ms 弹跳 + 散墨环 + 同时还有 ink-burst 粒子爆发——三组动效叠加，每次完成翻译都"过年"
5. **字号挤**：26px 内放两个汉字，笔画糊成一团（朱砂 + Roughen + 白字 0.95 不透明度），辨识度差

### 1.2 整体不够惊艳（用户次要痛点）

实际诊断（**不要被"动效已经很多"误导**——惊艳 ≠ 动效多）：

| 维度 | 现状 | 病灶 |
|---|---|---|
| **排版节奏** | h1 44px, h2 32px, body 14px | 标题与正文跨度小，**没有真正的"display moment"** |
| **留白** | 处处 `--space-4`/`--space-5` 平均分布 | **缺少呼吸点**，没有"大块沉默"衬托焦点 |
| **层次** | glass blur 24px 全场通用 | 玻璃面板都长一个样，**没有主从** |
| **焦点** | 上传页 hero 区被 brushstroke + fishtail + title + sub + 渐变 + 粒子 + 光晕同时拉扯 | **同一时间太多元素竞争注意力** |
| **色彩** | 朱砂只用在 logo / 印章 / 鱼尾 | **唯一的暖色被埋在装饰里**，形成"全屏冷调 + 三个红点"的廉价对比 |
| **字体细节** | 中英文都用 fallback 链 | **没有针对中文展示标题做精雕**（字距、字重、衬线选择） |
| **微观品质** | 边框 1px solid，阴影一档常用 `--elevation-2` | **缺少高级感来源：发丝边、双层阴影、内嵌高光** |

**关键洞察**：用户说"没有让人眼前一亮"——他要的不是"再加一个动画"，而是**一个能让人停下来截图发朋友圈的画面**。当前界面元素都"还行"，但没有任何一个"惊艳点"。

---

## 2. 设计原则（按优先级裁决冲突）

1. **克制 > 堆砌**：每删掉一个不必要的元素，剩下的元素就更值钱
2. **一处惊艳 > 处处花哨**：只允许 **1 个 hero moment**（建议是"翻译完成"），其它场景必须给它让路
3. **排版先于装饰**：先把字号、行距、字距、留白调对，再考虑加动效
4. **暗调底 + 一抹暖**：朱砂是限定品，**只在正面情绪时刻出现**（完成、成功、收藏），错误用 `--c-danger`，不要让朱砂背锅
5. **留白不可压缩**：版心 880px 宽 + 左右各 48px gutter——hero 区的 max-width 720px 太挤，必须放宽
6. **动效服从语义**：进入安静、悬停克制、完成激情。**不要在 idle 状态有任何 8s 以下循环的动画干扰阅读**
7. **不要 emoji，不要彩色 icon**：保持单色 stroke 图标系统（lucide）

---

## 3. 任务清单

> 标 **[P0]** 必做，**[P1]** 强烈建议，**[P2]** 锦上添花。
> 每个任务先读"目的"，再看"改动"，最后看"验收"。

---

### [P0-1] 重设印章 — 从"朱砂方章"改为"压角闲章"

**目的**：保留"翻译完成 = 落款盖印"的仪式感语义，去除当前廉价感。

**设计决策**：
- **形态改为竖椭圆 / 长方形 + 朱白文混合**——参考宋代藏书印 `清·乾隆御览之宝`、苏轼"东坡居士"印的比例（高:宽 ≈ 1.3:1）
- **改为单字 "研"** 一个字，不要两个挤一起。"研"字用 EB Garamond 配 Noto Serif SC 篆体感的字重 700
- **位置改为右下角**：`bottom: 32px; right: 40px;`——古人盖印就盖在画面右下款识旁，不在右上抢标题
- **尺寸调到 72×56**（比现在大但因位置下沉不抢戏）
- **替换 Roughen 滤镜**：用更细的 `feTurbulence baseFrequency="0.85" numOctaves="2"` + `feDisplacementMap scale="0.6"`——只保留极轻微的边缘飞白，**不要让噪声成为主视觉**
- **底色用 `--vermilion-0` + 0.92 不透明度** + 内层叠加一层暗朱砂 `#a3402c` 的 `mix-blend-mode: multiply` 营造"二次盖印"层次
- **去掉散墨环 `seal-splash`**——它把廉价感放大了。改为印章落下时**纸面下方出现一道极淡的朱砂晕染** 30% 不透明度，3s 内淡出
- **入场动画弱化**：`stamp-down` 改为 380ms，旋转幅度从 ±10deg 降到 ±3deg，不要弹跳过冲，落定后只有 1 次轻微回正
- **同时同步**：删除 `ink-burst` 那 20 颗粒子爆发——印章 + 卷轴展开 + 粒子三件套同时上是过载。**只保留卷轴展开 + 印章**，粒子爆发挪到 hover 印章时触发（彩蛋）

**改动文件**：
- `src/components/TranslateView.vue`：模板 189-207、脚本 358-378（清理 burstPhase）、样式 1360-1482、模板 184-187（删除 ink-burst 节点）
- 保留 `--vermilion-0`/`--vermilion-1` token 不变

**验收**：
1. 跑 `npx tauri dev`，进 translate 模式翻译一份 PDF
2. 完成时印章在右下角缓缓落定，**不带响**——感觉像艺术家盖章，不是游戏成就解锁
3. 截图问自己："这张能发小红书吗？"——能，过；不能，回去调
4. 朱砂晕染必须比印章本身**淡 3 倍以上**，不能抢戏

---

### [P0-2] Hero 区重构 — 上传页大字排版

**目的**：把"学术文献翻译 / Scholar Translator"做成第一眼焦点，让用户一开 app 就觉得"哇"。

**位置**：`src/components/TranslateView.vue:18-29`（hero-left）+ `:712-783`（样式）

**改动**：

1. **删除装饰元素**：
   - 删除 `hero-brushstroke` SVG 笔触（1.5s 划过的那条）——它在小字号下像装饰边角料
   - 删除 `hero-fishtail` 朱砂竖条——孤立的红色短条没有语义
   - 保留 hero-title 和 hero-sub

2. **放大主标题**：
   - "学术文献翻译" 字号从 `--text-display-lg` (44px) **提到 72px**（新增 token `--text-hero: 72px`）
   - `font-weight: 500`（不是 700——细一点更高级），`letter-spacing: -0.04em`，`line-height: 1.0`
   - 颜色用 `--c-text-0`，不要 text-shadow（现在那个紫色发光太"游戏 UI"）
   - **改用真正的衬线展示字体**：`font-family: 'Noto Serif SC', 'Source Han Serif CN', 'Songti SC', serif;`——确保 Noto Serif SC 已通过 fontsource 加载（如未加载，在 `package.json` 加 `@fontsource/noto-serif-sc` 并在 `main.ts` import 700/500/300 三个字重）

3. **重做副标题**：
   - "Scholar Translator" 改为 **小型大写体**：`font-size: 13px; letter-spacing: 0.18em; text-transform: uppercase; font-weight: 500;`
   - 颜色 `--c-text-3`
   - 在副标题前加一根 32px 长的细横线 `::before`，1px 厚 `--c-accent`——形成"标记 + 标签"的杂志感

4. **拓宽版心**：
   - `.upload-hero` 的 `max-width` 从 720px 改为 **920px**
   - `gap` 从 `--space-8` (64px) 加到 **96px**——左侧文字与右侧 drop zone 之间留更多呼吸

5. **drop-zone 简化**：
   - 删除 `dz-orbit`（绕圈高光）——孤悬的彩色圈在玻璃面板上廉价
   - 保留 `dz-bloom`，但 opacity 从 0.6 降到 **0.35**（hover 时恢复 0.85）
   - 保留 `dz-inkdrop` hover 触发的滴墨——这个有趣
   - 边框从 `1.5px dashed` 改为 **1px solid `color-mix(in srgb, var(--c-accent) 18%, transparent)`** + hover 时变 `--c-accent`——dashed 边在玻璃上看着像未完工

**验收**：
- 标题"学术文献翻译"必须是页面里**绝对最大的元素**，至少是次大元素的 3 倍字号
- 整个 hero 区只剩 4 个视觉元素：大标题 / 小副标题 / drop zone / 底部 format chips。**不允许有第 5 个**
- light 主题下也要漂亮——朱砂细线在宣纸色背景上对比度够（要测）

---

### [P0-3] 删减环境装饰 — 给视觉系统减负

**目的**：当前 idle 状态下同时有：宣纸纹理 + 自选背景 + 宣纸叠加 + 双光晕（靛青+朱砂） + 15 颗粒子 + scene-mesh 双色径向渐变 + drop-zone 内的 SVG bloom + orbit 高光 + dz-inkdrop ——**九层装饰同时跑**。

**改动**：
- `src/App.vue:31` — 墨粒子从 **15 颗减到 6 颗**，且 `opacity` 峰值从 0.85 降到 **0.45**（在 keyframes `particle-float` 里改）
- `src/App.vue:840-859`（`.ambient-orb::after` 朱砂第二光晕）— **删除**。只保留主光晕一个，让朱砂留给印章
- `src/components/TranslateView.vue:703-710`（`.scene-mesh`）— 删掉，让背景只由 App.vue 的全局光晕承担
- `src/components/TranslateView.vue` drop-zone 的 `.dz-orbit` — 已在 P0-2 删除，复核

**验收**：
- 打开 app idle 状态，**截一张静态图**，统计画面上能数出来的"动的东西"——必须 ≤ **3 项**（光晕 / 粒子 / drop-zone bloom）
- 闭眼 5 秒再睁眼，第一眼看见的应该是"学术文献翻译"那行字，不是飘动的紫色斑

---

### [P0-4] 顶栏品牌区精修

**位置**：`src/components/AppTopBar.vue:6-9`

**改动**：
- "研" logo 当前是个普通方块——改为 **24×24 圆角 6px 的微立体卡片**：
  - `background: linear-gradient(145deg, var(--vermilion-0), color-mix(in srgb, var(--vermilion-0) 75%, #000));`
  - `box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), 0 2px 6px rgba(200,80,58,0.30);`
  - 字色 `#fff`，字重 600，size 14px，font-family `--font-serif-zh`
- "研墨" 品牌名字距 `letter-spacing: 0.15em`，字号提到 15px，字重 500
- logo 与文字间距从默认改为 `gap: 10px`

**验收**：左上角"研 研墨"看起来像出版社 logo，不像 demo project。

---

### [P1-1] 翻译完成页排版精修

**位置**：`src/components/TranslateView.vue` `.result-bar`/`.dual-view`/`.reading-view`

**目的**：完成态是这个 app 的"产出物"——也是用户停留最久的页面。**这一页必须美**。

**改动**：

1. **完成提示从"标签"改为"署名"**：
   - 当前：`<span class="done-label">翻译完成</span>` + `<span class="done-meta">{{ blocks.length }} 块 · {{ paragraphCount }} 段</span>`
   - 改为：标题级排版 — `<h2>翻译完成</h2>`（28px serif）+ 下方一行小字 metadata（11px tracking 0.1em）
   - 视觉上让"翻译完成"和印章呼应（左上署名 + 右下印章 = 中国画落款格式）

2. **对照视图（bilingual）排版升级**：
   - 左右双栏间 gap 从默认放宽到 **80px**，模拟书籍跨页中缝
   - 译文衬线字体已设置，但需要确认 `--font-serif-zh` 链最前面是 `'Noto Serif SC'` 而不是 `'Songti SC'`（Mac/Win 渲染差异）
   - 段落间距 `margin-block: 1.2em`，行高 `1.85`
   - 原文（英文）改用 `font-family: 'EB Garamond', 'Crimson Pro', Georgia, serif;`——和译文中文宋体形成"双衬线对话"

3. **滚动条边缘扇贝渐隐**：
   - 在 `.dual-view` 顶部和底部加 `mask-image: linear-gradient(to bottom, transparent 0, black 24px, black calc(100% - 24px), transparent 100%);`
   - 让长文滚动时上下边缘是渐隐的，**这是一个免费的高级感细节**

**验收**：
- 完成页截图，左上"翻译完成"+ 右下印章，中间双栏排版——这一帧要能当封面图用
- 译文段落不会"撞到顶"或"撞到底"——有渐隐过渡

---

### [P1-2] 工作进行中（Working）页面调音

**位置**：`src/components/TranslateView.vue` `.work-scene` / `.work-card` / `.stepper` / `.progress-area`

**目的**：5 步进度条目前**视觉权重和上传页一样高**——但翻译过程是"过场"，不该抢戏。

**改动**：
- `.work-card` 加 **降级处理**：背景 `--c-glass` 透明度从 0.60 降到 **0.40**，blur 从 24px 降到 **40px**——更"虚"，让人感觉"内容在加载，主舞台还没开"
- `.stepper` 字号从 `--text-sm` 减到 **`--text-xs`**，灰度从 `--c-text-1` 降到 **`--c-text-2`**——不抢眼
- `.progress-fill` 当前是渐变色 + 流光——**保留**，但流光速度从默认 1.6s 慢到 **2.4s**（焦虑感降低）
- `.live-preview`（实时翻译预览）每条 item 的左侧加 **2px 朱砂细竖线**——告诉用户"这就是即将完工的内容"

**验收**：
- 翻译进行中时整体感觉"安静的等待"，不是"紧张的工厂"
- live-preview 出现的瞬间有一种"墨开始落到纸上"的渐入感

---

### [P1-3] 编辑器欢迎页（EditorWelcome）卡片优化

**位置**：`src/components/EditorWelcome.vue` 全文

**目的**：另一个 hero 时刻——用户切到编辑模式第一眼。

**改动**：
- "开始一篇论文" 字号现在是 28px 左右——**提到 56px**，改用 Noto Serif SC weight 500
- `.welcome-watermark` 那个 "研墨" 大水印——保留，但**字号翻倍**（200px → 400px），透明度从默认降到 **0.025**（极淡），位置移到右下角让其只能在屏幕角落看到
- magazine-grid 主卡（"新建工程"）：
  - 加 `border-image: linear-gradient(135deg, var(--c-accent), transparent) 1;` 或 hover 时左侧细线 `wc-card-line` 朱砂着色（不是 accent 蓝）——区分主次
  - hover 时 `transform: translateY(-3px)` + `box-shadow` 加重，**不要 scale**

**验收**：编辑模式入口要有"打开一本未写的书"的庄重感。

---

### [P2-1] 字体加载（如果项目还没用）

**目的**：Noto Serif SC 在系统没装时会 fallback 到 Songti——视觉差异巨大。

**改动**：
- `package.json` 加：`@fontsource/noto-serif-sc`、`@fontsource/eb-garamond`、`@fontsource-variable/inter`
- `main.ts` 加 `import` 语句加载 weight 400/500/700
- 在 `index.html` head 里加 `<link rel="preload" as="font" ...>` for 主标题字重

**验收**：开发者工具 Network 面板看到 woff2 加载，禁掉系统中文字体后界面仍然漂亮。

---

### [P2-2] focus ring 与按钮微调

**目的**：键盘 focus 时的环 (`--ring-focus`) 现在是 3px 粗，在小按钮上像创可贴。

**改动**：
- `--ring-focus` 改为 `0 0 0 2px var(--c-surface-0), 0 0 0 4px var(--c-accent-ring)` — 双层环（先用底色"挖"一圈再画 accent 环），这是 macOS 的标准做法
- `UiButton.vue` 的 hover transform 从 `translateY(-1px)` 取消，改用更细腻的 `box-shadow` 加深——按钮"原地变沉"，不是"跳起来"

**验收**：键盘 Tab 切换焦点，环线干净不糊。

---

### [P2-3] 滚动条统一

**目的**：默认滚动条在玻璃面板上很扎眼。

**改动**：
- 全局 `::-webkit-scrollbar` 宽度 6px，thumb 颜色 `color-mix(in srgb, var(--c-text-3) 40%, transparent)`，hover 时 `--c-text-2`
- 圆角 3px，no border, no track background
- Firefox `scrollbar-width: thin; scrollbar-color: ... transparent;`

**验收**：所有滚动场景滚动条都是低调一致的细灰条。

---

## 4. 不要做的事（防止跑偏）

- ❌ **不要**新增动画。报告里没写"加"的动效一律不加
- ❌ **不要**改 token 系统的颜色值（`--c-accent`、`--vermilion-0` 等）。本次任务**不动调色板**
- ❌ **不要**重构组件结构、不要拆 / 合 Vue 组件。**只动模板可见结构和样式**
- ❌ **不要**碰后端代码。这次纯前端
- ❌ **不要**改 light theme 的色值，但每个改动**必须在 light 模式下也验收一次**
- ❌ **不要**为了"惊艳"加 3D 变换、视差滚动、parallax background。这是阅读型 app，不是 portfolio
- ❌ **不要**给用户加新设置项。背景 / 字体 / 颜色这些设置已经够多了
- ❌ **不要**写 README 或文档说明做了什么——commit message 里写就够了

## 5. 提交规范

每个任务一个 commit：
- `style(seal): 重设朱砂闲章 - 单字研，移至右下角`
- `style(hero): 上传页大字排版重构`
- `style(ambient): 删减环境装饰层 - 减负 60%`
- ...

所有改动落到 `main` 分支前，**截图三张**贴在 PR 里：
1. 上传 idle 状态
2. 翻译进行中
3. 翻译完成（带印章）

dark + light 主题各一组 = 6 张图。

## 6. 完成定义（Definition of Done）

- [ ] P0 全部完成并截图
- [ ] P1 至少完成 2/3
- [ ] dark + light 主题都目视通过
- [ ] 无新增控制台报错 / 类型错误（`npx vue-tsc --noEmit` 通过）
- [ ] `npx vitest run` 全部通过
- [ ] 用户随机翻译一份 PDF，从打开 app 到看到印章落定，**全程不出戏**

## 7. 给执行 AI 的最后一句话

惊艳不来自"加多少东西"，而来自"减到刚好"。如果你做完一个任务还想再加点什么——**停手**，截图给用户看。
