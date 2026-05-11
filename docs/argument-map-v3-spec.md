# 论证陪练 v3 实施规范（Argument Companion：论证账本 + Reviewer‑2 对抗）

> 本文件是**可逐条执行的实施规范**。任何 AI/开发者实施时必须严格按本文件执行，不得自行扩大范围、跳过测试、或一次性大改。
> 实施第一步就是把本文件落盘进仓库（`docs/argument-map-v3-spec.md`）并把"约束条款"写进 `CLAUDE.md`（见 §0），防止后续会话上下文丢失导致偏离。

---

## Context（为什么做这件事）

v2 已经把"论证地图"重写成了 Toulmin 图（`python/src/argument/models_v2.py` + `src/components/argument/*` + Vue Flow 画布 + AI extract/critique/suggest + 图→草稿 flatten）。技术上是对的，但**用户实际用下来的反馈**：

- 它是一个"用户要自己往上摆节点、连边"的**自由画布** —— 交互动作（摆节点、拖线、双击改字）跟思维导图**完全一样**。Toulmin 的六种类型只是给节点染了不同颜色，在用户手上感觉不到区别。
- AI 功能（extract/critique/suggest）是"贴在画布上的几个按钮"，是配菜不是主菜；而那个主菜（你来建图）恰恰是没人想做的劳动。
- 对**真正写论文的人**没有不可替代性 —— 语法、扩写、"帮我润色一下"、画张图，粘贴到 ChatGPT 里都能做。

### v3 的判断（用户已确认，不可再改）

| 决策点 | 结论 |
|---|---|
| 核心定位 | **它不是"帮你写论文",是"在 Reviewer 2 之前先当你的 Reviewer 2 —— 而且它从不睡觉、记得你改了什么、并且会被你说服"。** 不可替代性来自一个 ChatGPT 对话框天生持有不了的东西：**一个常驻的、锚定在正文上、随改稿而存活的"全篇论证模型"** |
| 主界面形态 | **写作时 = 编辑器（Monaco）里的一层 overlay/侧栏**，不是独立画布；论证结构活在 prose 里、活在用户真正写字的地方，永不脱节 |
| 第一优先功能 | **「锚定到段落/句子的对抗式对话」（能回嘴的 Reviewer‑2 / 魔鬼辩护人）** —— 用户能逐条反驳，reviewer 据此推回或被说服。这是把"静态思维导图克隆"变成"活的东西"的那一下 |
| 老画布的命运 | **不删、不丢**。现有 ArgGraph + Vue Flow + `ArgumentMapView` 在 Phase 5 归并为**"审稿模式"的可视化**（"承重路径 X 光"），由 AI extract 出来给用户检视，而不是用户来建。后端 extract/critique/span 那套全部复用 |
| 思维导图的关系 | **不直接连**。导图（发散草稿）→ 一键扁平成提纲塞进编辑器 → 在编辑器里写 → （想审视整体结构时）对**当前草稿**跑 extract 得到 X 光图。中间永远隔着"编辑器里的实际文本"。**不做**"导图→Toulmin 图智能移植"、**不做**双向溯源 |

### v3 的三件核心产出（用户视角的"应该的样子"）

1. **论证账本（Claim Ledger）—— 不可替代的日用品。** 学术论文本质是一串承诺（abstract/intro：「我们证明了 X、Y、Z」），正文必须逐条兑付。账本把你立的每条承诺列出来，链到正文里兑现它的位置，标上状态：
   - "Abstract 第 1 段承诺了 3 个 contribution。Contribution 2（'我们的方法能 scale 到 N=1e6'）—— 全文找不到在哪儿演示了。"
   - "Contribution 3 在 §5 演示了，但实验用的是 N=1e5，不是 1e6 —— 对不上（mismatch）。"
   - 没有人给你做这件事；你导师在 deadline 前夜做（如果运气好）。这个工具持续地做。
2. **Reviewer‑2 兵棋推演 + 对抗对话 —— 惊艳那一下。** 按目标会议的评审习惯校准的、狠的、每一条都钉在具体句子上的模拟评审（"你的 baseline 弱，因为没跟 [那个明显该比的] 比"），并且**你能在它旁边当场起草 rebuttal，它继续怼你 / 被你说服**。等真投稿时这场仗已经打过三轮了。这一家族（同一种 `ReviewPoint`，都能逐条 rebuttal）还包括：**「质疑这句」**（选中任意句子 → 针对那句的裁判级批评）、**首尾一致性 + gap 匹配检查**（abstract/intro 立的 thesis 和 conclusion 说的是不是一回事；intro 声称的 gap 你真的填了吗）、**related work 定位检查**（你在"摆位置"还是只在"罗列"，画的对比是否属实）、**（Phase 5）真实评审导入**（粘贴真实审稿意见 → 同样的对抗/导出流程）。
3. **承重路径 X 光（Phase 5 / 后续，复用老画布）。** 在真实草稿上画出来：哪几句话在扛主 claim、链条哪一截是细的、结构上缺了哪块没人写（最常见的洞不是"某 claim 没证据"，而是"没有 Warrant —— 你展示了 A 和 B 相关，却从没论证为什么这意味着你的方法导致了提升"）。

### 不可替代的 MVP（不用先做漂亮的图）

**「论证账本 + 锚定的 Reviewer‑2 对抗」，挂在 Monaco 编辑器里。** 流程：
1. 用户在编辑器里写论文草稿。
2. 点「分析论证账本」→ 侧栏维护账本（每条承诺 / 兑付状态 / 链到正文）+ 行号槽徽标（"⚠ 这条 contribution 在全文没有兑付"）。
3. 点「红队这篇」→ 出一份会议校准的模拟评审，每条锚到句子（含账本来的 claim_overreach、首尾不一致、related work 问题）；选中任意句 →「质疑这句」→ 针对那句的裁判级批评也进列表。
4. 逐条点开 review point 起草 rebuttal，reviewer 继续推回或让步。
5. 改完草稿 → 账本/评审标记"可能过期"，一键重新分析；锚点用模糊重定位（像 `git blame` 之于论证）扛住编辑。

承重路径 X 光（Phase 5）作为"审稿模式"的可视化后补 —— 复用现有 `ArgumentMapView` + Vue Flow。

### 反过来设计（什么会让它不惊艳，必须避免）

- **泛泛 = 死。** "考虑增加更多证据"——立刻关掉。对抗必须**具体 + 懂这个会议 + 引精确句子**（reviewer 输出必须带 `verbatim_quote`，锚到正文）。
- **要手动建图/建账本 = 死。** 账本和评审是 AI 跑出来的，人只反应（编辑/采纳/忽略/反驳）。
- **改一句话锚点就崩 = 死。** 持久模型必须扛住编辑 —— 模糊重锚是工程核心难点（`anchor.py`），做不好整个东西就是玩具，必须有 exact/drifted/lost 三态的单测。
- **是个要你记得去打开的独立 app = 弱。** 它活在编辑器里，主动在侧栏冒出来（不弹窗 —— 是侧栏的状态在变 + gutter 徽标）。

---

## §0 实施前必做（Phase 0，纳入第一个 PR）

> 这一步是为了**防止后续 AI 会话丢失上下文而偏离计划**。

1. 把本规范文件落盘进仓库：`docs/argument-map-v3-spec.md`（内容即本文件）。
2. 在 `CLAUDE.md` 中新增一节"### 论证陪练 v3（进行中）"，内容包含以下**硬性条款**：

```markdown
### 论证陪练 v3（进行中 — 见 docs/argument-map-v3-spec.md）

正在把"论证地图"的重心从"画布编辑器"转向"编辑器里的论证陪练"：①论证账本（abstract/intro 的承诺 ↔ 正文的兑付，带状态、锚定到句子）；②Reviewer‑2 对抗（会议校准的模拟评审，每条锚到句子，可逐条 rebuttal，reviewer 会被说服）；③现有 Toulmin 图/Vue Flow 在最后归并为"审稿模式"的可视化（承重路径 X 光），不删。实施约束：
1. 不可大改一把梭。严格按 docs/argument-map-v3-spec.md 的 Phase 1→5 顺序，一个 Phase 一个 PR。
2. 测试先行（TDD）。每个 Phase 先写失败的测试，再写实现让测试通过。锚定（anchor.py）是工程核心，必须有 exact/drifted/lost 三态的单测，不允许"写完再补测试"。
3. 新代码暗发布。新功能全程挂在 config flag `features.argument_companion` 后（默认 false，Phase 4 完成才翻 true）。
4. 旧代码不提前删。现有 ArgGraph / graph_store.py / ai_ops.py / critique.py / ArgumentMapView.vue / Vue Flow 画布在 Phase 5"审稿模式归并"前不动。
5. 每个 PR 合并前门禁：`cd python && pytest tests/ -v` 全绿 + `npm run build` 成功 + `npx vitest` 全绿。任一失败不许合。
6. 范围冻结。仅：anchoring、论证账本、Reviewer‑2 + rebuttal 循环、审稿模式归并 —— 不附带无关重构/清理。
7. 每个 Phase 完成后跑 /review 或 /security-review。
```

3. 用 `TaskCreate` 建立 5 个 Phase 任务并设置 `blockedBy` 依赖（Phase N+1 依赖 Phase N）。
4. 在 `config/default.yaml`（仓库根）和 `python/config/default.yaml` 模板的 `features:` 下加 `argument_companion: false`。
5. 建分支 `feat/argument-companion-phase1`。后续每个 Phase 一条新分支。

---

## §1 总体架构

### 新增的是什么（与现有 ArgGraph 并存，不替换）

| 概念 | 一句话 | 落在哪 |
|---|---|---|
| `Anchor` | 一个"尽力而为"的指向正文的弱锚点（quote + 上下文窗口），改稿后用模糊重定位扛住 | `argument/anchor.py` + `companion_models.py` |
| `Ledger` / `Promise` | 论证账本：abstract/intro 里立的每条承诺 + 它在正文哪儿兑付 + 状态 | `argument/ledger.py` + `companion_models.py` |
| `ReviewSession` / `ReviewPoint` / `RebuttalTurn` | Reviewer‑2 一次评审会话 + 每条带锚的批评点 + 每条点下的 rebuttal 对话线程 | `argument/reviewer.py` + `companion_models.py` |
| `CompanionStore` | 上述对象的 JSON 持久化（沿用 `ArgGraphStore` 的"内存 + 每对象一个 JSON"风格） | `argument/companion_store.py` |
| 编辑器 overlay | 行号槽徽标（未兑付承诺/评审点）+ jump-to-anchor + "质疑这句"动作（选区→scoped review） | `MonacoEditor.vue` 改动 + `useArgumentCompanion.ts` |
| 论证陪练侧栏 | 右侧 Tab：「论证账本」子页 + 「Reviewer 2」子页（含逐点 rebuttal mini-chat） | `components/argument/CompanionPanel.vue` 等 |
| 审稿模式（Phase 5） | 现有 `ArgumentMapView` + Vue Flow 改造成"对当前草稿 extract 出 Toulmin 图 + 承重路径"的只读可视化 | 改造现有 `src/components/argument/*` |

> 现有 `python/src/argument/` 的 `models_v2.py` / `graph_store.py` / `ai_ops.py` / `critique.py` / `flatten_graph.py` 和 `src/components/argument/Arg*.vue` **不动**，Phase 5 才归并。新代码全部是**新增文件**。

### 后端模块（`python/src/argument/` 新增）

| 文件 | 内容 |
|---|---|
| 新增 `anchor.py` | `make_anchor()` / `make_anchor_from_quote()` / `relocate()` / `relocate_all()` / `section_path_at()` —— 锚定与模糊重定位（工程核心） |
| 新增 `section_utils.py` | `find_section(text, names)`（按标题名抽 abstract/intro/conclusion/related-work 段）/ `split_paragraphs(text)` / `has_contrast_marker(para)` —— ledger 与 reviewer 共用的"找段落"工具 |
| 新增 `companion_models.py` | `Anchor` / `Promise` / `Ledger` / `ReviewPoint` / `RebuttalTurn` / `ReviewSession` Pydantic 模型 |
| 新增 `companion_store.py` | `CompanionStore`：`{runtime_dir}/companion/ledgers/{doc_id}.json` + `{runtime_dir}/companion/reviews/{session_id}.json`，内存 dict + JSON flush |
| 新增 `ledger.py` | `build_ledger()`（SSE：提取承诺 → 逐条找兑付/判状态 → 锚定 → 流式产出）/ `rebuild_ledger()`（与现有账本合并，保留 user_overridden） |
| 新增 `reviewer.py` | `run_review()`（SSE：会议画像 + 多路并行 → 批评点 → 锚定 → 流式；含确定性"账本交叉检查" + `coherence_check`（首尾一致 / gap 匹配）+ `related_work_check`（定位检查）；支持 `focus`「质疑这句」、`checks` 选路、`session_id` 追加）/ `continue_rebuttal()`（reviewer 推回/让步 + 状态迁移）/ `import_real_reviews()`（Phase 5：粘贴真实审稿 → 点列表）/ `ledger_cross_check` `_load_venue_profile` 等 |
| 新增 `venue_profiles.yaml` | 会议名 → "该会议 reviewer 在意什么" 要点列表（NeurIPS/ICML/ICLR、CHI/CSCW、ACL/EMNLP、CVPR/ICCV、KDD/WWW、Generic…）；自由文本会议名 → Generic + 把名字塞进 prompt |
| 改动 `routers/argument.py` | 新增 `register_companion(app, *, store, load_config, build_cloud_client)`（独立于 `register_argument_v2`） |
| 改动 `api_factory.py` | 实例化 `CompanionStore` 并调 `register_companion`（同 `ArgGraphStore` 的注入位置旁边） |

复用：`python/src/argument/llm_client.py` 的 `call_llm_chat(prompt, cloud_client, ollama_client, max_tokens, temperature)`；`critique.py` 里"结构性确定性检查"的写法（`structural_critique` 是 `ledger_cross_check` 的范本）；`sse-starlette` 的 `EventSourceResponse`；`api_factory.py` 里 `_build_cloud_client` / `_load_config` 的注入模式。

### 前端模块（`src/` 新增/改动）

| 文件 | 内容 |
|---|---|
| 新增 `composables/useArgumentCompanion.ts` | **singleton**（module-level reactive state）：账本/评审 state + 所有 API 调用 + SSE 消费（build/review/rebut）+ 编辑器桥（`focusAnchor` / `onEditorEdit` debounced relocate） |
| 新增 `components/argument/CompanionPanel.vue` | 右侧 Tab 容器：两个子页「论证账本」「Reviewer 2」+ 顶部 doc 状态/staleness 提示 |
| 新增 `components/argument/LedgerList.vue` | 承诺列表：按状态分组，每行 = 状态徽标 + 承诺文本 + 「跳到承诺处」+（若已兑付）「跳到兑付处」+ AI 备注 + 「这条不对」可编辑 |
| 新增 `components/argument/ReviewerThread.vue` | 一个 review point：severity 徽标 + category + title + detail（markdown）+「跳到被攻击的句子」+「起草 rebuttal」（展开内嵌 mini-chat：author 输入 → SSE reviewer 回复）+「采纳 / 忽略」 |
| 新增 `components/argument/companionGutter.ts` | 纯函数：给定 `Ledger` + `ReviewSession` + 当前 doc 文本 → 算出 Monaco `IModelDeltaDecoration[]`（行号槽 glyph + hover message + 关联的 promise_id/point_id），供 `MonacoEditor.vue` 用 |
| 改动 `components/MonacoEditor.vue` | (a) 监听 `useArgumentCompanion` 的 ledger/review，用 `companionGutter` 算 decorations 并 `deltaDecorations`；(b) 暴露 `revealAnchor(charStart, charEnd)` 方法（`model.getPositionAt` → `revealRangeInCenter` + 临时高亮 decoration）；(c) glyph 点击 → 通知 `useArgumentCompanion.focusFromGutter(promiseId|pointId)` |
| 改动 `components/EditorLayout.vue:77-114` | 右侧面板把现在的「论证」Tab（`<ArgumentMapMini>`）内容改为 `<CompanionPanel>`（Tab 文案改"论证陪练"）；`ArgumentMapMini` 暂时保留组件文件但从这里摘掉，Phase 5 进"审稿模式" |
| 改动 `composables/useEditorState.ts` + tab 模型 | 给每个 tab 加一个**稳定的 `doc_id`**（已保存文件用 `path`；未命名用持久的 `untitled-{uuid}`），`useArgumentCompanion` 据此 key 账本/评审 |
| 改动 `types/index.ts` | 加 `Anchor` / `Promise` / `Ledger` / `ReviewPoint` / `RebuttalTurn` / `ReviewSession` 的 TS 类型（镜像后端） |

复用：`utils/streamReader.ts` 的 `readSseStream(reader, (eventType, data) => {})`；`utils/api.ts` 的 `API_BASE`；`composables/useAgentChat.ts` 的 SSE-chat 范式（rebuttal mini-chat 照搬它的 `sendMessage` + `readSseStream` 结构）；`components/MarkdownPreview.vue`（渲染 review detail）；现有 `MonacoEditor.vue` 里 ghost-text 的 `deltaDecorations` 用法（decoration 范本）；`useEditor()` / `useEditorState()` 取当前 doc 文本。

### 复用清单（不要重新造轮子）

- SSE 后端：`sse-starlette` 的 `EventSourceResponse`（项目已用，见 `routers/argument.py:174`）
- SSE 前端：`src/utils/streamReader.ts` 的 `readSseStream`
- LLM 调用：`python/src/argument/llm_client.py` 的 `call_llm_chat`（三层降级 Cloud→Ollama→空串，已经在 ai_ops.py/critique.py 里用）
- 确定性检查范本：`python/src/argument/critique.py` 的 `structural_critique`（`ledger_cross_check` 照它写）
- 注入模式：`python/api_factory.py` 的 `_build_cloud_client` / `_load_config` / `RUNTIME_DIR`，以及 `register_argument_v2(...)` 紧挨着的位置加 `register_companion(...)`
- 存储范本：`python/src/argument/graph_store.py`（`ArgGraphStore` 的"内存 dict + 每对象 JSON、tmp+os.replace flush、glob 加载"风格，`CompanionStore` 照搬）
- 聊天 mini-chat：`src/composables/useAgentChat.ts` 的 `sendMessage` + `readSseStream(reader, handleEvent)` 流程，以及 `AgentPanel.vue` 的消息列表渲染
- Monaco decoration：`src/components/MonacoEditor.vue` 现有 ghost-text 的 `editor.deltaDecorations([], [{ range, options: { ... } }])` 用法
- Markdown 渲染：`src/components/MarkdownPreview.vue`
- 句子边界（如需把锚点对齐到整句）：`src/utils/sentenceAlign.ts` 的 `splitSentences()`

---

## §2 后端详细设计

### 2.1 `argument/anchor.py`（工程核心 —— 优先把这个做扎实）

```python
from __future__ import annotations
import difflib, re
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid

CONTEXT_CHARS = 48          # 上下文窗口字符数（每侧）
FUZZY_THRESHOLD = 0.62      # difflib 相似度阈值

class Anchor(BaseModel):
    id: str = Field(default_factory=lambda: f"a_{uuid.uuid4().hex[:10]}")
    doc_id: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    quote: str                       # 创建时的精确切片（弱锚点，必填）
    context_before: str = ""         # quote 前 ~CONTEXT_CHARS 字符
    context_after: str = ""          # quote 后 ~CONTEXT_CHARS 字符
    section_path: Optional[str] = None   # best-effort 标题链，如 "3.2 Method"
    status: Literal["anchored", "drifted", "lost"] = "anchored"

def make_anchor(doc_id: str, text: str, char_start: int, char_end: int) -> Anchor:
    """从已知偏移建锚点：截 quote + 上下文 + 推断 section_path。"""
    ...

def make_anchor_from_quote(doc_id: str, text: str, quote: str) -> Anchor:
    """从一段 verbatim quote 建锚点：先 _locate(quote, text) 拿偏移再 make_anchor；
    定位不到则 status='lost'、偏移 None、仍保留 quote（前端标"未锚定，请手动框选"）。"""
    ...

def relocate(anchor: Anchor, new_text: str) -> Anchor:
    """改稿后重定位。返回更新后的 anchor（不原地改）。流程：
    1. new_text.find(anchor.quote) 唯一命中 → status='anchored'，更新偏移与上下文。
    2. 否则用 (context_before[-K:] + quote + context_after[:K]) 作组合 needle 再 find；唯一命中 → 'anchored'。
    3. 否则 difflib 滑窗模糊匹配（窗口长度≈len(quote)，步长 max(1,len//3)），最佳 ratio≥FUZZY_THRESHOLD → status='drifted'、更新偏移。
    4. 都不行 → status='lost'、偏移置 None、保留 quote/context（让用户手动重绑）。"""
    ...

def relocate_all(anchors: list[Anchor], new_text: str) -> list[Anchor]:
    ...

def section_path_at(text: str, char_offset: int) -> Optional[str]:
    """从 char_offset 往上扫 markdown 标题（^#{1,6}\s+），拼成最近的标题链。"""
    ...
```

要点：
- `relocate` 必须是**纯函数**（输入旧 anchor + 新文本，输出新 anchor），方便单测覆盖三态。
- 不引入新依赖；`difflib` 是标准库（`ai_ops.py:_locate_quote` 已经在用同样套路，可抽公共逻辑但**不强制重构 ai_ops.py**）。
- 性能：超长文本（>50k 字符）的 difflib 滑窗可能慢 → 先用 `quote[:24]` 做一次粗 `find` 缩小搜索区间，再在 ±2k 窗口内做精细模糊匹配。

### 2.2 `argument/companion_models.py`

```python
NodeKind = Literal["contribution", "claim", "hypothesis", "gap_statement", "scope"]
PromiseStatus = Literal["paid", "partial", "unpaid", "mismatch", "unknown"]

class Promise(BaseModel):
    id: str = Field(default_factory=lambda: f"p_{uuid.uuid4().hex[:10]}")
    text: str                            # 承诺原话（"we show our method scales to N=1e6"）
    kind: NodeKind
    source_anchor_id: str                # 承诺出现处（abstract/intro）
    discharge_anchor_ids: list[str] = Field(default_factory=list)  # 正文兑付处
    status: PromiseStatus = "unknown"
    severity: Literal["info", "warning", "error"] = "info"
    note: Optional[str] = None           # AI 备注："§5 用 N=1e5,不是 1e6 —— 不一致"
    created_by: Literal["user", "ai"] = "ai"
    user_overridden: bool = False        # 用户手改过 → rebuild 时不覆盖

class Ledger(BaseModel):
    id: str = Field(default_factory=lambda: f"L_{uuid.uuid4().hex[:10]}")
    doc_id: str
    doc_title: str = ""
    promises: list[Promise] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    doc_hash: Optional[str] = None       # 上次分析时 doc 文本的 hash → 前端判"过期"
    last_built_at: float = Field(default_factory=time.time)

# ── Reviewer‑2 ──
PointSeverity = Literal["minor", "major", "fatal"]
PointCategory = Literal[
    "motivation", "novelty", "baseline", "ablation", "soundness",
    "claim_overreach", "missing_related_work", "reproducibility",
    "experiment_design", "writing_clarity",
    "inconsistency",      # 首尾 thesis 不一致（coherence_check）
    "gap_mismatch",       # intro 声称的 gap 与实际交付对不上（coherence_check）
    "weak_positioning",   # related work 只罗列没定位 / 画的对比不属实（rw_check）
    "term_drift",         # 术语在不同处定义/用法漂移（ledger mismatch 的泛化）
    "other",
]
PointStatus = Literal["open", "rebutted", "accepted", "dismissed"]
PointSource = Literal[
    "llm",            # run_review 的 LLM 整体评审
    "ledger_check",   # ledger_cross_check（未兑付/不一致承诺）
    "coherence_check",# 首尾一致 + gap 匹配
    "rw_check",       # related work 定位检查
    "scoped",         # 「质疑这句」对选中片段的针对性批评
    "imported",       # 从用户粘贴的真实审稿意见解析而来（Phase 5）
]

class RebuttalTurn(BaseModel):
    id: str = Field(default_factory=lambda: f"rt_{uuid.uuid4().hex[:10]}")
    role: Literal["author", "reviewer"]
    text: str
    created_at: float = Field(default_factory=time.time)

class ReviewPoint(BaseModel):
    id: str = Field(default_factory=lambda: f"rp_{uuid.uuid4().hex[:10]}")
    severity: PointSeverity
    category: PointCategory
    title: str                           # 一行（"Baseline comparison is incomplete"）
    detail: str                          # 完整批评，reviewer 口吻
    anchor_id: Optional[str] = None       # 被攻击的句子/小节
    status: PointStatus = "open"
    source: PointSource = "llm"          # 这条点从哪条路来的（决定 UI 角标）
    reviewer_label: Optional[str] = None # imported 时区分 "Reviewer 1/2/3"
    thread: list[RebuttalTurn] = Field(default_factory=list)

class ReviewSession(BaseModel):
    id: str = Field(default_factory=lambda: f"R_{uuid.uuid4().hex[:10]}")
    doc_id: str
    doc_title: str = ""
    venue: Optional[str] = None          # "NeurIPS" / "CHI" / 自由文本
    # persona="real"（Phase 5）：points 由用户粘贴的真实审稿意见解析而来；rebuttal 循环与导出照常用
    persona: Literal["reviewer2", "ac", "domain_expert", "friendly", "real"] = "reviewer2"
    checks: list[str] = Field(default_factory=lambda: ["llm"])  # 这轮跑了哪些检查
    points: list[ReviewPoint] = Field(default_factory=list)
    anchors: list[Anchor] = Field(default_factory=list)
    doc_hash: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
```

约定：`doc_hash` 用 `hashlib.sha1(text.encode()).hexdigest()[:16]`（仅用于"过期"提示，不参与逻辑）。`anchors` 放在 `Ledger` / `ReviewSession` 各自身上（轻度重复，但简单，且与 `ArgGraph.spans` 的设计一致）。一个 `ReviewSession` 可以被多次 `run_review`/`scopedReview`/`import` 追加点（前端选"追加进当前会话"还是"开新一轮"）。

### 2.3 `argument/companion_store.py`

`CompanionStore`（照搬 `ArgGraphStore` 风格）：
- 构造接 `runtime_dir`；`{runtime_dir}/companion/ledgers/` 和 `{runtime_dir}/companion/reviews/` 两个目录；启动时 glob 加载到内存 dict。
- 账本按 `doc_id` 唯一（一个 doc 当前一本账本）→ 文件名用 `doc_id` 的安全化（`re.sub(r'[^\w.-]', '_', doc_id)`）；评审按 `session.id` → 文件名 `{session_id}.json`（一个 doc 可有多轮评审，保留为历史）。
- 方法：
  - `get_ledger(doc_id) -> Ledger | None` / `save_ledger(ledger)` / `list_ledgers() -> list[dict]`（doc_id/doc_title/promise 计数/last_built_at）/ `delete_ledger(doc_id)`
  - `upsert_promise(doc_id, promise)`（设 `user_overridden=True` 由路由层在"用户编辑"时传入）/ `delete_promise(doc_id, pid)`（级联删该 promise 独占的 anchor）
  - `get_review(session_id) -> ReviewSession | None` / `save_review(session)` / `list_reviews(doc_id) -> list[dict]`（session_id/venue/persona/点数/状态汇总/created_at）/ `delete_review(session_id)`
  - `update_point(session_id, pid, status)` / `append_turns(session_id, pid, turns: list[RebuttalTurn])`
  - flush：`tmp.write_text(json.dumps(model_dump(), ensure_ascii=False, indent=2)); os.replace(...)`，每次写操作后立即 flush 对应文件。

### 2.4 `argument/ledger.py`

```python
async def build_ledger(
    doc_id: str, doc_title: str, text: str, store: CompanionStore,
    cloud_client=None, ollama_client=None,
) -> AsyncIterator[dict]:
    """SSE 事件：promise*（逐条）→ progress(可选)→ complete（带计数 + warnings）。失败 → error，不写脏数据。"""
```

流程：
1. **划"承诺区"**：启发式找 abstract + introduction —— `re.search(r'^#{1,3}\s*abstract', ...)` / `'introduction'`（中英）取到下一个同级标题为止；都找不到则取**前 ~25% 或前 N 段**。其余为"正文区"。
2. **LLM #1（提取承诺）**：prompt：「你是学术论证分析专家。从这篇论文的 abstract/intro 提取作者立下的"承诺"（contribution / 核心 claim / 假设 / gap 陈述 / 适用范围）。输出严格 JSON：`{"promises":[{"local_id":"p1","kind":"contribution|claim|hypothesis|gap_statement|scope","text":"承诺原话(可适度归一)","verbatim_quote":"abstract/intro 里的精确子串"}]}`。」用 `text` 的承诺区（截断到 ~3000 字符）。
3. **LLM #2（逐条找兑付/判状态）**：对每条 promise（可批量：一次喂全部 promise + 正文区，截断到模型上限），prompt：「对每条承诺，在正文里找它在哪儿被兑现：给出 1-N 个 `verbatim_quote`（正文里的精确句子）；判 `status`：`paid`(充分兑现) / `partial`(部分) / `unpaid`(全文找不到) / `mismatch`(兑现了但数字/条件/范围对不上)；给一行 `note` 说明（mismatch 时必须点明差在哪）。输出严格 JSON 数组，每项 `{"promise_local_id":"p1","status":"...","discharge_quotes":["..."],"note":"..."}`。」
4. **锚定 + 组装**：
   - 每条 promise 的 `verbatim_quote`（来源）→ `make_anchor_from_quote(doc_id, text, quote)` → `source_anchor_id`；
   - 每个 `discharge_quote` → `make_anchor_from_quote(...)` → 进 `discharge_anchor_ids`；
   - `severity`：`unpaid` → `error`，`mismatch` → `error`，`partial` → `warning`，`paid` → `info`，`unknown` → `info`；
   - `local_id → 真实 id` 映射；建 `Promise(created_by="ai")`。
   - 每组装好一条就 `yield {"event":"promise","data": promise.model_dump_json()}`。
5. **写库**：组装 `Ledger(doc_id, doc_title, promises, anchors, doc_hash)`，`store.save_ledger(...)`，`yield {"event":"complete","data": json.dumps({"promise_count":..., "by_status":{...}, "warnings":[...]})}`。
6. **失败兜底**：任一 LLM 调用空串/非法 JSON → 该步重试一次（更严格 prompt）→ 再失败 → `yield {"event":"error", ...}`，**不调 `save_ledger`**。

```python
async def rebuild_ledger(doc_id, doc_title, text, store, cloud_client=None, ollama_client=None) -> AsyncIterator[dict]:
    """同 build，但与现有账本合并：
    - 现有 promise 中 user_overridden=True 的：保留 text/kind/status/note 不变，仅对其 anchor 跑 relocate。
    - 其余：用 quote 相似度（difflib ratio≥0.7）尽量匹配旧 promise 复用 id，否则新建；旧的没匹配上的丢弃。
    - 所有 anchor（含 source/discharge）跑 relocate_all，更新 status。
    流式产出同 build。"""
```

### 2.5 `argument/reviewer.py`

```python
def ledger_cross_check(ledger: Ledger | None) -> list[ReviewPoint]:
    """确定性半路（不调 LLM）：把账本里 status in {unpaid, mismatch} 的 promise
    转成 ReviewPoint(category='claim_overreach', source='ledger_check', anchor=该 promise 的 source_anchor)：
      unpaid  → severity='major'，title="Claimed contribution not demonstrated"，detail 引用 promise.text + "全文未找到对应的实验/论证"
      mismatch→ severity='major'，title="Claim does not match the evidence"，detail 引用 promise.text + promise.note
    无账本 → []。"""

async def coherence_check(
    ledger: Ledger | None, full_text: str, cloud_client=None, ollama_client=None,
) -> list[ReviewPoint]:
    """首尾一致性 + gap 匹配（混合：少量确定性 + 一遍 LLM），失败静默返回 []。
    1. section_utils.find_section 抽 conclusion/discussion（找不到 → 取最后一节）。
    2. 确定性：abstract 是否提到了 intro 里找到的所有 contribution（账本的 promises）；无 conclusion 段 → 一条 info 点。
    3. LLM #1（一致性）：「abstract/intro 立的 thesis/contributions：[ledger.promises]。conclusion：[...]。conclusion 的重点/thesis 和当初承诺的是不是一回事？列出不一致处。」→ ReviewPoint(category='inconsistency', source='coherence_check', anchor=conclusion 或 abstract 对应句)。
    4. LLM #2（gap 匹配）：抽 intro 里"gap 陈述"（账本里 kind='gap_statement' 的 promise，或现抽）+ 论文实际交付（账本 contributions）→「实际交付的是否真填了所声称的 gap？」→ ReviewPoint(category='gap_mismatch', source='coherence_check')。
    LLM 不可用 → 只返回第 2 步的确定性点。"""

async def related_work_check(
    full_text: str, paper_summary: str | None = None, cloud_client=None, ollama_client=None,
) -> list[ReviewPoint]:
    """related work 定位检查（混合），失败静默返回 []。
    1. section_utils.find_section 抽 related work / background 段；找不到 → 一条 info 点"未找到独立的 related work 节"。
    2. 确定性：section_utils.split_paragraphs 切段，每段 has_contrast_marker(however|but|in contrast|unlike|whereas|与此不同|然而|相比之下|前人工作…)；某段一个都没有 → ReviewPoint(category='weak_positioning', severity='info', detail="这段只在 summarize 前人工作，没有把本文摆进去")。
    3. LLM：「related work 节：[...]。本文做什么：[paper_summary 或现抽]。作者画的每一条与前人的对比——给定本文实际做的，是否属实？列出虚假或无支撑的对比。」→ ReviewPoint(category='weak_positioning' 或 'missing_related_work', source='rw_check', anchor=对应句)。
    LLM 不可用 → 只返回第 2 步的确定性点。"""

def _load_venue_profile(venue: str | None) -> str:
    """从 venue_profiles.yaml 取该会议的"reviewer 关注点"要点串；未知会议名 → Generic 要点 + 把名字塞进返回串。"""

async def run_review(
    doc_id: str, doc_title: str, text: str, venue: str | None, persona: str,
    ledger: Ledger | None, store: CompanionStore,
    *, focus: dict | None = None,           # {"quote","char_start","char_end"}：「质疑这句」时只针对这段
    checks: list[str] | None = None,        # 选跑哪些路；None=["llm"]；可选 "llm","ledger","coherence","rw"
    session_id: str | None = None,          # 给定则把新点追加进已有 session（"质疑这句"常用），否则新建
    cloud_client=None, ollama_client=None,
) -> AsyncIterator[dict]:
    """SSE：review_point*（确定性点先吐；各路 LLM 并行跑、完成一路就把该路的点逐个 yield）→ complete（带 session_id + by_category 计数）。
    流程：
      1. 确定性点：若 "ledger" 在 checks（或 checks=None）→ ledger_cross_check(ledger)；逐条 yield。
      2. focus 给定 → 只跑 "scoped" 一路：LLM「针对论文里这段：«focus.quote»（上下文：前后各 ~400 字符）给 1-3 条裁判级批评，每条 severity/category/title/detail/verbatim_quote」→ ReviewPoint(source='scoped', anchor=focus 位置)。跳过下面 3。
      3. 否则按 checks（缺省 ["llm"]）并行（asyncio.gather + asyncio.Queue 边产边发）：
         - "llm"：「你是 {venue} 的 {persona}。这是论文全文（截断到模型上限）。{_load_venue_profile(venue)}。产出 5-9 条批评点（severity/category/一行 title/完整 detail/verbatim_quote）。」→ source='llm'
         - "coherence"：coherence_check(ledger, text, …) → 已是 ReviewPoint，源 'coherence_check'
         - "rw"：related_work_check(text, …) → ReviewPoint，源 'rw_check'
         persona 决定 LLM 口吻：reviewer2=苛刻挑刺；ac=权衡 trade-off 给倾向；domain_expert=技术深挖；friendly=建设性。
      4. 每条 LLM/scoped 点：verbatim_quote → make_anchor_from_quote(doc_id, text, quote) → anchor；建 ReviewPoint；yield review_point。
      5. session：session_id 给定 → store.get_review 取出、append points + 新 anchors + 把这次的 check 名并进 session.checks；否则新建 ReviewSession(venue, persona, checks)。store.save_review。yield complete（含 session_id、by_category、各路是否降级的 warnings）。
      失败：某路 LLM 不可用 → 那一路返回该路的确定性子集（coherence/rw 都有确定性兜底；纯 "llm" 路返回空），整体不报 error；全部 LLM 不可用且无 ledger 检查 → complete 带一条 info 'LLM 不可用'。**任何情况下不写脏点**（解析失败的 LLM 输出整条丢弃 + warning）。"""

async def import_real_reviews(
    doc_id: str, doc_title: str, text: str, reviews_raw: str, store: CompanionStore,
    cloud_client=None, ollama_client=None,
) -> AsyncIterator[dict]:
    """（Phase 5）把用户粘贴的真实审稿意见解析成一个 persona='real' 的 ReviewSession。
    1. LLM：「下面是这篇论文收到的真实审稿意见（可能多位 reviewer）。拆成结构化 concern：每条 {reviewer_label, severity, category(见枚举), title, detail(原意可精简), quote_from_paper(这条 concern 攻击/对应论文里的哪句话,尽量找;找不到留空)}。输出严格 JSON 数组。」
    2. quote_from_paper → make_anchor_from_quote(doc_id, text, quote)（找不到 → anchor=None）；建 ReviewPoint(source='imported', reviewer_label=…, status='open')。逐条 yield review_point。
    3. 组装 ReviewSession(persona='real', venue=None, checks=['imported'])；store.save_review；yield complete with session_id。
    之后这些点照常走 continue_rebuttal（"我对这条 reviewer concern 的回应是…" → 它当 reviewer 推回/认可）和 /download（导出 rebuttal 包）。LLM 不可用/解析失败 → error，不写脏数据。"""

async def continue_rebuttal(
    session_id: str, point_id: str, author_message: str, doc_text: str,
    store: CompanionStore, cloud_client=None, ollama_client=None,
) -> AsyncIterator[dict]:
    """SSE：reviewer_reply（一次性整段；MVP 不做 token 流，够用）→ status（point 是否迁移到 rebutted / 仍 open）→ complete。
    流程：
      1. 取 session、point；append RebuttalTurn(role='author', text=author_message)。
      2. 上下文 = point.title+detail + （anchor 附近的 doc 摘录 ±400 字符）+ point.thread 全部 turns + author 这条新消息。
      3. LLM：「你是该 reviewer。作者回复如上。若回复站不住——具体指出哪里还是不够（保持苛刻但讲理）；若被说服——明确说'这点可以认为已 rebutted'并简述为何。只输出你的回复文本。」
      4. 解析回复里是否包含让步信号（出现"已 rebutted"/"撤回这条"/明确认可等 → status='rebutted'；否则保持 open）。append RebuttalTurn(role='reviewer', text=reply)。
      5. store.append_turns + （若状态变了）store.update_point；yield reviewer_reply → status → complete。"""
```

`venue_profiles.yaml` 示例结构（每会议 3-6 条要点，写人话）：

```yaml
NeurIPS: |
  - baselines 是否完整、是否漏了明显该比的方法
  - ablation 是否真的 isolate 了所声称的机制
  - 理论假设与实验设定是否一致（theorem 的前提在实验里成不成立）
  - claim 是否过度（"SOTA"/"first" 是否站得住）
  - 复现性：超参、随机种子、统计显著性
CHI: |
  - 研究效度：被试数、任务生态效度、混淆变量
  - related work 是否覆盖到位、contribution 框定是否准确
  - 定性/定量分析方法是否恰当
  - 对 HCI 社区的实际意义
Generic: |
  - 动机是否清楚、问题是否重要
  - 方法是否新颖、与现有工作的区分是否说清
  - 实验/证据是否支撑结论、是否有过度声称
  - 写作清晰度、结构完整性
# … ICML/ICLR/ACL/EMNLP/CVPR/ICCV/KDD/WWW 等
```

### 2.6 路由 `python/routers/argument.py` —— 新增 `register_companion`

> 全部端点在 `features.argument_companion=True` 时注册（沿用 `register_argument_v2` 的 `flag_enabled` 套路）；为 false 时这些路径返回 404，旧端点不受影响。`register_companion` 从 `api_factory.py` 接收 `store: CompanionStore`、`load_config`、`build_cloud_client`（用现成的 `_get_cloud_client` 闭包构造方式）。

| Method | Path | Body / 说明 |
|---|---|---|
| POST | `/api/companion/ledger/build` | `{doc_id, doc_title?, text}` → **SSE**：`promise`* → `complete`。若已有账本则走 `rebuild_ledger`，否则 `build_ledger` |
| GET | `/api/companion/ledger/{doc_id}` | 当前账本，无则 404 |
| PUT | `/api/companion/ledger/{doc_id}/promise` | upsert 一条 promise（无 id 新建）；标记 `user_overridden=True`；返回 promise |
| DELETE | `/api/companion/ledger/{doc_id}/promise/{pid}` | 删 promise（级联其独占 anchor） |
| POST | `/api/companion/ledger/{doc_id}/relocate` | `{text}` → 对账本所有 anchor 跑 `relocate_all`，更新 `doc_hash`，返回更新后的账本 |
| DELETE | `/api/companion/ledger/{doc_id}` | 删账本 |
| POST | `/api/companion/review` | `{doc_id, doc_title?, text, venue?, persona?, focus?, checks?, session_id?}` → **SSE**：`review_point`* → `complete`（`data` 含 `session_id` + `by_category`）。会先拉该 doc 的当前账本喂给 `ledger_cross_check` / `coherence_check`。`focus={quote,char_start,char_end}` = 「质疑这句」（只针对那段，结果追加进 `session_id` 指定的会话或新建）；`checks` 省略 = `["llm"]`，可加 `"ledger"/"coherence"/"rw"` |
| POST | `/api/companion/review/import` | **（Phase 5）** `{doc_id, doc_title?, text, reviews_raw}` → **SSE**：`review_point`* → `complete`。把粘贴的真实审稿意见解析成 `persona='real'` 的 session |
| GET | `/api/companion/review/{session_id}` | 整个 session |
| GET | `/api/companion/reviews?doc_id=...` | 该 doc 的所有 session 摘要 |
| POST | `/api/companion/ledger/{doc_id}/promise/{pid}/suggest-experiment` | **（Phase 5）** 无 body → `{suggestion}`：对 `partial`/`unpaid` 承诺给"当前覆盖到的条件 → 还需要的条件 → 建议的实验设计" |
| PUT | `/api/companion/review/{session_id}/point/{pid}` | `{status: "accepted"\|"dismissed"\|"open"}` → 更新点状态 |
| POST | `/api/companion/review/{session_id}/point/{pid}/rebut` | `{message}` → **SSE**：`reviewer_reply` → `status` → `complete`。需要 doc 文本：从 session 存的 anchor 附近摘录拿不到完整 doc → **body 里也带 `text`**（前端传当前编辑器内容） |
| DELETE | `/api/companion/review/{session_id}` | 删 session |
| GET | `/api/companion/download/review/{session_id}` | **（Phase 5）** 把 session 的所有点 + thread 导出为 markdown 文件（"rebuttal 草稿"），`FileResponse` |

实现注意：所有 SSE 端点用 `EventSourceResponse(_gen())`，`_gen` 里 `yield {"event": ev["event"], "data": ev["data"]}`（照 `routers/argument.py:163-174` 的 `v2_extract`）。AI 模块用**延迟 import**（`from src.argument.ledger import build_ledger` 写在 handler 内），与现有 `v2_extract` 一致。

### 2.7 `api_factory.py` 接线

在现有 `register_argument_v2(...)` 那段（约 `python/api_factory.py:381-397`）旁边追加：

```python
try:
    from src.argument.companion_store import CompanionStore
    from routers.argument import register_companion
    _companion_flag = bool(_load_config().get("features", {}).get("argument_companion", False))
    _companion_store = CompanionStore(runtime_dir=RUNTIME_DIR)
    register_companion(
        app,
        store=_companion_store,
        flag_enabled=_companion_flag,
        load_config=_load_config,
        build_cloud_client=_build_cloud_client,
    )
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning("argument_companion setup skipped: %s", _e)
```

---

## §3 前端详细设计

### 3.1 `composables/useArgumentCompanion.ts`（singleton）

```ts
// module-level reactive state（singleton，照搬 useMindMap/useAgentChat 模式）
const state = reactive({
  docId: '' as string,
  ledger: null as Ledger | null,
  building: false,
  ledgerStale: false,                 // doc 改了 且 hash 不匹配
  review: null as ReviewSession | null,   // 当前打开的评审 session
  reviewList: [] as ReviewSummary[],
  reviewing: false,
  rebuttalSending: '' as string,      // 正在发 rebuttal 的 point_id（''=无）
  // 编辑器桥：
  flashAnchor: null as { start: number; end: number } | null,  // 让 MonacoEditor reveal+flash
})

// 设当前 doc（EditorLayout 切 tab 时调）：setDoc(docId, docTitle) → 拉 getLedger + listReviews
// 账本 API：buildOrRebuildLedger(text)（SSE 消费，逐条 push promise 进 state.ledger）
//          getLedger() / upsertPromise(p) / deletePromise(pid) / relocate(text)（debounced，由 onEditorEdit 触发）
// 评审 API：runReview(text, venue, persona)（SSE，逐条 push review_point；complete 时 setReview + 刷新 reviewList）
//          getReview(sid) / listReviews() / updatePointStatus(pid, status) / deleteReview(sid)
//          rebut(pointId, message, text)（SSE：收 reviewer_reply → push 两条 turn 进 point.thread；收 status → 改 point.status）
// 编辑器桥：focusAnchor(anchorId)（查 anchor → 设 flashAnchor，MonacoEditor watch 之）
//          focusFromGutter(kind, id)（gutter glyph 点击 → 切到对应子页 + 滚到该 promise/point）
//          onEditorEdit(text)（编辑器内容变 → debounce 1.5s → 若有 ledger/review 则 relocate(text) + 设 ledgerStale=true）
```

约定：`Ledger`/`ReviewSession` 等 TS 类型加在 `src/types/index.ts`。SSE 消费照 `useAgentChat.ts`：`fetch(POST) → res.body.getReader() → readSseStream(reader, (event, data) => switch(event){...})`。

### 3.2 `components/argument/CompanionPanel.vue`（右侧 Tab 容器）

- 顶部：当前 doc 标题 + 子页切换 `[论证账本] [Reviewer 2]` + 一个状态条：账本"上次分析 hh:mm·N 条承诺（K 未兑付 / J 不一致）"；`ledgerStale` 时变黄并显示"草稿已改 → 可能过期，[重新分析]"。
- 「论证账本」子页 → `<LedgerList>` + 顶部「分析论证账本 / 重新分析」按钮（`building` 时禁用 + 进度）。
- 「Reviewer 2」子页：
  - venue 选择：preset chips（NeurIPS / ICML / ICLR / CHI / ACL / CVPR / KDD / Generic）+ 一个自由文本输入（"或输入会议名/期刊名"）。
  - persona 选择：`Reviewer 2（苛刻）` / `AC（权衡）` / `领域专家（技术深挖）` / `合作者（建设性）`。
  - 「红队这篇」按钮 → `runReview(content, venue, persona)`（`reviewing` 时禁用 + 流式长出点）。
  - 当前 session 的点列表（按 severity 排序，`fatal` 在上）：每条 `<ReviewerThread>`。
  - 下方"历史评审"折叠区：`reviewList` 每项"第 N 轮·venue·M 处问题（X rebutted / Y open）·hh:mm"，点开切换 `state.review`。

### 3.3 `components/argument/LedgerList.vue`

- 按 `status` 分组渲染（顺序：`unpaid` → `mismatch` → `partial` → `paid` → `unknown`），分组标题带计数。
- 每行 promise：
  - 左：状态徽标（`unpaid`/`mismatch` 红、`partial` 黄、`paid` 绿、`unknown` 灰）+ `kind` 小 chip（contribution / claim / …）。
  - 中：`text`（可点 → `focusAnchor(source_anchor_id)`，编辑器滚到承诺处并闪一下）；下方灰字 `note`（AI 备注）。
  - 右：若 `discharge_anchor_ids` 非空 → 「→ 兑付处 (n)」按钮（点 → 依次 `focusAnchor` 各 discharge anchor；多个则下拉）；若该 anchor `status==='lost'` → ⚠"未在正文中定位"。
  - 「这条不对」→ 内联编辑 `text` / `status` / 删除（`upsertPromise` 时后端置 `user_overridden=true`；删除走 `deletePromise`）。
- 空态："还没分析。点上方「分析论证账本」让 AI 把你 abstract/intro 里立的承诺逐条对到正文。"

### 3.4 `components/argument/ReviewerThread.vue`（一个 review point + rebuttal mini-chat）

- 头：severity 徽标（`fatal` 红 / `major` 橙 / `minor` 灰）+ category chip + `title`；右上按 `source` 出小角标（账本 / 一致性 / RW / 质疑这句 / 真实评审 + `reviewer_label`）。
- 体：`detail`（用 `MarkdownPreview` 渲染）；若有 `anchor_id` → 「→ 被攻击的句子」按钮（`focusAnchor`）。
- 操作行：「起草 rebuttal」（展开下方 mini-chat）/「采纳」(`updatePointStatus(pid,'accepted')`，行变灰)/「忽略」(`'dismissed'`)。点状态为 `rebutted` 时头部加绿色"已 rebutted"标。
- mini-chat（展开后）：渲染 `point.thread`（author 右对齐 / reviewer 左对齐，照 `AgentPanel.vue` 消息样式）；底部输入框 + 发送（`rebut(pid, message, content)`；`rebuttalSending===pid` 时禁用 + "reviewer 思考中…"）；reviewer 回复流式追加；收到 `status` 事件后若 `rebutted` 则在 chat 顶部出一条系统提示"reviewer 认为这点已 rebutted"。

### 3.5 编辑器 overlay（`MonacoEditor.vue` 改动 + `companionGutter.ts`）

`companionGutter.ts`（纯函数，便于单测）：
```ts
export function computeCompanionDecorations(
  ledger: Ledger | null, review: ReviewSession | null, monaco: typeof import('monaco-editor'),
  model: import('monaco-editor').editor.ITextModel,
): import('monaco-editor').editor.IModelDeltaDecoration[] {
  // 对每条 status in {unpaid,mismatch,partial} 的 promise：取其 source_anchor（status!=='lost' 且有偏移）→
  //   model.getPositionAt(charStart) → 该行 → glyphMarginClassName: 'arg-gutter-promise-<status>'，
  //   hoverMessage: `⚠ ${promise.text} —— ${note}`
  // 对每条 status==='open' 的 review point：取其 anchor → 同样在所在行加 glyph 'arg-gutter-review-<severity>'，hover = title
  // 同一行多个 → 合并成一个 glyph，hover 列全部
}
```
`MonacoEditor.vue`：
- `watch([() => companion.state.ledger, () => companion.state.review, contentVersion], ...)` → 算 decorations → `decorationsCollection = editor.createDecorationsCollection(decos)`（或 `deltaDecorations`，与现有 ghost-text 一致）。glyph 的 CSS 类在组件 `<style>` 里定义（小圆点/三角，颜色按 status/severity）。
- glyph 点击：Monaco 的 `editor.onMouseDown` 判 `target.type === GUTTER_GLYPH_MARGIN` → 从该行找回 promise_id / point_id → `companion.focusFromGutter(...)`（切右面板到论证陪练 tab + 对应子页 + 滚到该项）。
- 暴露方法 `revealAnchor(start: number, end: number)`：`const p1 = model.getPositionAt(start); const p2 = model.getPositionAt(end); editor.revealRangeInCenter(new Range(...)); ` + 加一个 ~1.2s 后自动移除的高亮 decoration（`className: 'arg-flash'`）。`watch(() => companion.state.flashAnchor, v => v && revealAnchor(v.start, v.end))`。
- "质疑这句"动作：编辑器有选区时，在选区上方浮一个小按钮"质疑这句" → 调 `companion.scopedReview({quote, char_start, char_end})`（= `runReview` 带 `focus`、`session_id`=当前 doc 最近 session，无则新建）→ 后端返回 1-3 条 `source='scoped'` 的 ReviewPoint，前端切到 Reviewer 2 子页并滚到这些新点。Phase 3 落地（与 `run_review` 的 `focus` 参数同期）。

### 3.6 `EditorLayout.vue` 接入

- `RightTab` 类型仍是 `'preview' | 'ai' | 'argument'`；把 `argument` Tab 的渲染从 `<ArgumentMapMini>` 换成 `<CompanionPanel>`，Tab 文案"论证" → "论证陪练"（图标可保留 `GitBranch`）。
- 切 tab / 打开 doc 时调 `companion.setDoc(activeTab.docId, activeTab.name)`（需要 tab 上有稳定 `docId` —— 见 §3.7）。
- 编辑器内容变（`onDidChangeContent` 或 `contentVersion` watch）→ `companion.onEditorEdit(content.value)`（内部 debounce）。
- `ArgumentMapMini.vue` 文件**不删**，只是从 `EditorLayout` 里摘掉引用（Phase 5 进"审稿模式"）。

### 3.7 tab 的稳定 `doc_id`

- 在 `useEditorState.ts` 的 tab 数据结构里加 `docId: string`：新建未命名 tab 时 `docId = 'untitled-' + crypto.randomUUID()`；打开/保存文件后 `docId = path`（保存导致 untitled → 有 path 时，把旧 untitled 的账本/评审**留在原 doc_id 下**即可，前端 `setDoc(newPath)` 会拉到空账本 —— 这是已知取舍，见 §6）。
- `useArgumentCompanion` 一切以 `state.docId` 为 key。

---

## §4 分阶段实施（5 个 PR，每个独立可工作）

> **每个 Phase 必须：先写测试（TDD）→ 跑测试看它失败 → 写实现 → 测试通过 → `cd python && pytest tests/ -v` 全绿 + `npm run build` 成功 + `npx vitest` 全绿 → 跑 /review → 合并。** 详见 §0 条款。

### Phase 0 — 落盘 + 约束（并入 Phase 1 的 PR）
- 落盘 `docs/argument-map-v3-spec.md`；`CLAUDE.md` 加约束节（§0 第 2 条原文）；`config/default.yaml` + `python/config/default.yaml` 的 `features:` 下加 `argument_companion: false`。
- `TaskCreate` 建 5 个 Phase 任务 + 依赖链。

### Phase 1 — 后端：锚定 + companion 模型 + 存储 + 账本（**不含 reviewer**）
**先写测试**：
- `python/tests/unit/test_anchor.py`：`make_anchor` 截 quote/上下文/`section_path`；`make_anchor_from_quote` 命中/不命中（→ `status='lost'`）；`relocate` 三态 —— 文本未变→`anchored`、改了 quote 周边的字但 quote 在→`anchored`、quote 被改写但模糊匹配过阈值→`drifted`、整段删了→`lost`；`relocate_all` 批量；长文本（>50k）性能不超时（粗定位缩窗）。
- `test_companion_models.py`：枚举/默认值；`Promise.user_overridden` 默认 false；`Ledger.doc_hash` 可空。
- `test_companion_store.py`：ledger create/get/list/delete；`upsert_promise` 新建 vs 更新 + 级联删独占 anchor；JSON 落盘后 reload 一致；review session save/get/list/delete；`update_point` / `append_turns`；doc_id 安全化文件名。
- `test_ledger.py`（LLM 用 fake/mock）：mock LLM #1 返合法 JSON + #2 返合法 JSON → 产出 promises，状态/severity 正确，anchor 偏移算对；`mismatch` 的 `note` 非空；某 quote 不是精确子串 → 该 anchor `status='lost'` 但 promise 仍在；LLM 返非法 JSON → 重试一次→仍失败→`error` 事件且 `save_ledger` 未被调；`rebuild_ledger`：`user_overridden=True` 的 promise 不被覆盖、其 anchor 仍 relocate；旧 promise 按 quote 相似度复用 id。
- `test_companion_router.py`（账本部分）：`/ledger/build` SSE 事件序列；`/ledger/{doc_id}` 200/404；`/promise` PUT 设 `user_overridden`；`/relocate` 返回更新后 anchor 状态；`flag_enabled=False` 时全 404。

**再写实现**：`anchor.py`、`companion_models.py`、`companion_store.py`、`ledger.py`、`routers/argument.py` 加 `register_companion`（只含 `/ledger/*` 端点）、`api_factory.py` 注入 `CompanionStore`、两个 config 加 flag。

**用户可见变化**：无（前端还没接）。
门禁：上述测试 + 全量 pytest 绿。

### Phase 2 — 前端：论证账本面板 + 编辑器 gutter 标记 + jump-to-anchor
**先写测试**（vitest）：
- `src/__tests__/useArgumentCompanion.test.ts`：`buildOrRebuildLedger` 消费 mock SSE → `state.ledger.promises` 逐条填充；`relocate` 调用后 anchor 状态更新；`focusAnchor` 设 `flashAnchor`；`onEditorEdit` debounce 后置 `ledgerStale=true`。
- `src/__tests__/companionGutter.test.ts`：给定 ledger（含 unpaid/mismatch/paid promise）+ mock monaco model → 只对 unpaid/mismatch/partial 出 glyph，行号对、hover 文案含 note；`status==='lost'` 的 anchor 不出 glyph。
- `src/__tests__/CompanionPanel.test.ts`（或 `LedgerList.test.ts`）：mount → 按状态分组渲染；点 promise 文本触发 `focusAnchor`；点"分析"触发 `buildOrRebuildLedger`。

**再写实现**：`useArgumentCompanion.ts`、`CompanionPanel.vue`（先只「论证账本」子页 + 状态条 + 「分析/重新分析」）、`LedgerList.vue`、`companionGutter.ts`、`MonacoEditor.vue` 改动（decorations + `revealAnchor` + glyph 点击）、`useEditorState.ts` 加 `docId`、`EditorLayout.vue` 右面板 `argument` Tab 换 `CompanionPanel` 并摘掉 `ArgumentMapMini` 引用、`types/index.ts` 加 TS 类型。

**用户可见变化**：写论文 → 「分析论证账本」→ 侧栏列出承诺 + 状态；未兑付/不一致的承诺在 abstract/intro 对应行出 ⚠ gutter；点徽标/点承诺 → 编辑器滚过去并闪一下；改稿后状态条变黄提示"可能过期"。
门禁：vitest 绿 + `npm run build` 成功 + 手工点一遍。

### Phase 3 — Reviewer‑2 评审：红队 + 质疑这句 + 一致性/gap/RW 检查（带锚的批评点，**不含 rebuttal 循环**）
**先写测试**：
- `python/tests/unit/test_section_utils.py`：`find_section` 抽 abstract/intro/conclusion/related-work（中英标题、无标题兜底）；`split_paragraphs`；`has_contrast_marker` 命中/不命中。
- `python/tests/unit/test_reviewer.py`：
  - `ledger_cross_check`：`unpaid` → `claim_overreach` major、anchor=promise.source_anchor、`source='ledger_check'`；`mismatch` 同理 detail 含 note；无账本 → []。
  - `coherence_check`（mock LLM）：abstract 漏掉某 contribution → 确定性 info 点；mock 一致性 LLM 返一条不一致 → `inconsistency` 点；mock gap LLM → `gap_mismatch` 点；LLM 不可用 → 只剩确定性点。
  - `related_work_check`（mock LLM）：无对比标记的 RW 段 → `weak_positioning` info 点；mock LLM 返"虚假对比" → 对应点；无 RW 节 → 一条 info；LLM 不可用 → 只剩确定性点。
  - `_load_venue_profile`：已知会议返回该 profile、未知 → Generic + 名字。
  - `run_review`（mock LLM）：先吐确定性点、再并行各路点；`focus` 给定 → 只吐 1-3 条 `source='scoped'` 点、跳过整篇 LLM/coherence/rw；`checks=["ledger"]` → 只跑那一路；`session_id` 给定 → 点追加进该 session；某路 LLM 不可用 → 该路降级到确定性子集、整体不报 error；session 写库；`by_category` 计数对；解析失败的 LLM 条目被丢弃 + warning。
- `test_companion_router.py` 扩展：`/review` SSE 序列 + `complete` 带 `session_id`+`by_category`；带 `focus` 的 scoped 调用；`/review/{sid}` 200/404；`/reviews?doc_id=` 列表；`/point/{pid}` PUT 改状态。
- vitest：`useArgumentCompanion`：`runReview`/`scopedReview` 消费 SSE → `state.review.points` 填充、`reviewList` 刷新；`updatePointStatus`。`ReviewerThread.test.ts`：render severity/category/detail/`source` 角标、点"被攻击的句子"触发 `focusAnchor`、"采纳/忽略"触发 `updatePointStatus`。

**再写实现**：
- 后端：`section_utils.py`；`reviewer.py`（`ledger_cross_check` + `coherence_check` + `related_work_check` + `_load_venue_profile` + `run_review` 带 `focus`/`checks`/`session_id`，各路 `asyncio.gather` 并行 + 边产边发）；`venue_profiles.yaml`；`routers/argument.py` 加 `/review`（含 `focus`/`checks`/`session_id` body）`/review/{sid}` `/reviews` `/point/{pid}`。
- 前端：`CompanionPanel.vue` 加「Reviewer 2」子页（venue/persona 选择 + 「红队这篇」+ 一组"附加检查"复选（一致性 / related work）+ 点列表）；`ReviewerThread.vue`（不含 mini-chat，"起草 rebuttal" 按钮先 disabled 占位；`source` 角标）；`MonacoEditor.vue` 选区浮按钮"质疑这句" → `companion.scopedReview(...)`；`companionGutter.ts` 把 `open` 的 review point 也算进 glyph；`useArgumentCompanion` 加 `runReview`/`scopedReview`/review CRUD。

**用户可见变化**：「红队这篇」→ 流式长出会议校准的批评点（含账本来的 claim_overreach、首尾不一致、related work 问题），每条能跳到被攻击的句子；选中任意句 →「质疑这句」→ 针对那句的批评进列表；可"采纳/忽略"；gutter 也标 review point。
门禁：pytest + vitest + build + 手工 e2e（写一篇 → 分析账本 → 红队 → 看各类点 → 选句质疑 → 跳句子）。

### Phase 4 — Reviewer‑2 对抗对话（rebuttal 循环 —— **第一优先功能**）
**先写测试**：
- `python/tests/unit/test_reviewer.py::continue_rebuttal`（mock LLM）：append author turn → LLM 回复 → append reviewer turn；回复含让步信号（"已 rebutted"等）→ `point.status` 迁移 `rebutted` 并 `update_point` 被调；回复无让步 → 保持 `open`；session 落盘含 thread。
- `test_companion_router.py` 扩展：`/point/{pid}/rebut` SSE 序列 `reviewer_reply → status → complete`；body 缺 `message` → 422。
- vitest：`useArgumentCompanion.rebut` 消费 SSE → `point.thread` 追加两条 turn、收 `status` 改 `point.status`；`rebuttalSending` 锁。`ReviewerThread.test.ts` 扩展：展开 mini-chat、发送、流式追加 reviewer 回复、`rebutted` 标出现。

**再写实现**：`reviewer.py` 的 `continue_rebuttal`、`routers/argument.py` 加 `/point/{pid}/rebut`、`ReviewerThread.vue` 的内嵌 mini-chat（复用 `streamReader` + `AgentPanel` 消息样式）、`useArgumentCompanion` 的 `rebut`、点状态迁移 UI。
**收尾**：`config/default.yaml` 的 `features.argument_companion` 翻 `true`（暗发布转正式）。

**用户可见变化**：点开任一批评点 → 「起草 rebuttal」→ 内嵌对话：你回一句 → reviewer 推回或让步 → 反复几轮 → 它认可时标"已 rebutted"。投稿前这场仗已经打过。
门禁：pytest（含新 rebuttal 测试）+ vitest + build + 手工 e2e（完整兵棋推演：写 → 账本 → 红队 → 逐条 rebuttal → 部分 rebutted/部分采纳）。

### Phase 5 — 审稿模式归并（承重路径 X 光）+ 真实评审导入 + 实验缺口建议 + 导出 + 清理
**先写测试**：
- 后端：`test_companion_router.py` 加 `/download/review/{sid}` —— 把 session + thread 导出为 markdown（按 reviewer point / `reviewer_label` 分组，每点 + 其 rebuttal 往来），`FileResponse`。
- `test_reviewer.py` 加 `import_real_reviews`（mock LLM）：粘贴一段多 reviewer 意见 → 解析成多条 `source='imported'`、`reviewer_label` 区分、能锚的锚上、`persona='real'` session 写库；LLM 不可用/解析失败 → error，不写脏数据。`test_companion_router.py` 加 `/review/import` SSE 序列。
- `test_ledger.py`（或 `test_companion_router.py`）加 `suggest_experiment_for_promise`（mock LLM）：`partial` 承诺 → 返回含"当前覆盖条件 / 还需条件 / 建议设计"三段的 suggestion 文本；`/promise/{pid}/suggest-experiment` 端点返回 `{suggestion}`。
- 若给 ArgGraph 喂账本的 mismatch promise 作 `claim_overreach` issue（让两个视图一致）：`test_argument_critique.py` 加一条 —— 传入含"已知 unpaid 承诺"的上下文 → `critique_graph` 结果含对应 issue。（**仅当确实做这个打通时才加；否则跳过。**）
- vitest：`ArgumentMapView` 新增"从当前编辑器草稿载入 → extract"的入口（按钮存在、点击触发 extract）；`CompanionPanel` 的"导入真实审稿意见"入口（粘贴框 → 触发 `importReviews`）；`LedgerList` 的「怎么补满」按钮（`partial`/`unpaid` 承诺旁，点击触发 `suggestExperiment`）。

**再写实现**：
- 把现有 `src/components/argument/ArgumentMapView.vue`（+ `ArgSourcePane`/`ArgumentMapCanvas`/`ArgInspector`）**重新框定为"审稿模式"**：原文来源新增"从当前编辑器文件载入"（已部分存在）；强调"点提取论证 → AI 抽出 Toulmin 图供检视"，弱化"手动建节点"（保留但不是主入口）；`ArgInspector` 没选中时的统计面板里加一段"承重路径"视图占位（哪几个 claim 是终点、各经哪些 grounds/warrant；MVP 用文字列表，真正的图布局见 §7）。
- `ArgumentMapMini.vue`：作为编辑器右面板"论证陪练"里的一个可选小折叠区"📊 当前草稿的论证图缩略"（按需渲染，节点 >30 时退化为静态摘要），点"在审稿模式中打开"跳到全屏 `ArgumentMapView`。
- 后端：`reviewer.py` 的 `import_real_reviews`；`ledger.py`（或 `ai_ops` 风格的小函数）`suggest_experiment_for_promise`；`flatten`/markdown 导出复用 `_format_markdown` 的轮子做 rebuttal 包；`routers/argument.py` 加 `/review/import`、`/promise/{pid}/suggest-experiment`、`/download/review/{sid}`。
- 前端：`CompanionPanel.vue` 加"导入真实审稿意见"入口（粘贴框 → 流式长出 `imported` 点 → 之后照常 rebuttal/导出）+「导出评审+rebuttal」按钮；`LedgerList.vue` 在 `partial`/`unpaid` 承诺旁加「怎么补满」按钮（→ `suggestExperiment` → 弹出建议文本，可一键插入编辑器作 TODO）；`ReviewerThread`/`CompanionPanel` 的导出入口。
- （可选打通）账本 mismatch/unpaid → 在用户对当前草稿 extract 出图后，把这些作为 `claim_overreach` issue 注入图（让 X 光图和账本一致）。

**清理**：更新 `CLAUDE.md` 的子系统成熟度矩阵 —— "论证地图（Toulmin v2…）"那行改写为"论证陪练 v3（账本 + Reviewer‑2 对抗 + Toulmin X 光）"，并把"### 论证地图 v2 重写约束"和"### 论证陪练 v3（进行中）"两节合并为一节"已完成"说明；`config` 里 `features.argument_companion` 保留为 true（v3 成为正式形态）或删 flag；更新 `docs/argument-map-v3-spec.md` 标注"已完成"；`docs/argument-map-v2-spec.md` 顶部加一行指针指向 v3。**注意：不删任何 v2 代码** —— ArgGraph / Vue Flow / extract / critique / flatten 全部在"审稿模式"里继续用。

门禁：全量 pytest + vitest + build + 手工 e2e（含 rebuttal 导出 + 审稿模式 extract）+ /review。

---

## §5 端到端验证清单

- 后端单测：`cd python && pytest tests/unit/test_anchor.py tests/unit/test_section_utils.py tests/unit/test_companion_models.py tests/unit/test_companion_store.py tests/unit/test_ledger.py tests/unit/test_reviewer.py tests/unit/test_companion_router.py -v`
- 后端全量回归：`cd python && pytest tests/ -v`
- 前端单测：`npx vitest`
- 前端构建：`npm run build`
- 手工 e2e（`npx tauri dev`，Windows 用 `start_dev.bat` 清代理变量）：
  1. 编辑器里粘一篇论文草稿（abstract + intro + method + experiment + conclusion）。
  2. 右面板「论证陪练」→「分析论证账本」→ 侧栏列出承诺，几条标 `unpaid`/`mismatch`；abstract/intro 对应行出 ⚠ gutter。
  3. 点一条 `mismatch` 承诺 → 编辑器滚到承诺处闪一下；点「→ 兑付处」→ 跳到正文那句（或提示"未在正文中定位"）。
  4. 把某条 unpaid 承诺在正文里真的写一段证据 → 状态条变黄"可能过期" → 「重新分析」→ 那条变 `paid`，gutter ⚠ 消失。
  5. 改一句被锚定的话的措辞（不删）→「重新分析」→ 锚点仍命中（`anchored` 或 `drifted`），没崩。
  6. 「Reviewer 2」子页 → 选 venue=NeurIPS、persona=Reviewer 2、勾上"一致性 / related work"附加检查 →「红队这篇」→ 流式长出 5-9 条批评点，含 LLM 整篇评审 + 账本来的 claim_overreach + 首尾不一致 / gap_mismatch + related work 的 weak_positioning；每条能跳到句子，`source` 角标对得上。
  7.（Phase 3）选中一句很猛的话 →「质疑这句」→ 列表里多 1-3 条针对那句的 `scoped` 批评、能跳回那句。
  8. 点一条 major 点 →「起草 rebuttal」→ 内嵌对话：回一句站不住的 → reviewer 推回；再回一句到位的 → reviewer 认可 → 点标"已 rebutted"。另一条点「采纳」→ 行变灰、gutter 标消失。
  9.（Phase 5）「导入真实审稿意见」→ 粘一段（哪怕是编的）多 reviewer 意见 → 解析成点列表（带 `reviewer_label`）→ 对其中一条点「起草 rebuttal」走对抗 →「导出评审+rebuttal」拿到按 reviewer 分组的 rebuttal 草稿。
  10.（Phase 5）账本里一条 `partial` 承诺旁点「怎么补满」→ 得到"当前覆盖条件 / 还需条件 / 建议设计"；`ArgumentMapView`/审稿模式 →「从当前编辑器文件载入」→「提取论证」→ Toulmin 图长出来；没选中时 Inspector 的"承重路径"列出哪些 claim 是终点。

---

## §6 风险与待定项（实施中如需用户拍板，在对应 Phase 提出）

1. **锚定鲁棒性是成败关键。** 改稿是高频操作，模糊重锚做不好整个东西就是玩具。Phase 1 的 `test_anchor.py` 必须把三态 + 长文本性能覆盖死；上线后若 `drifted`/`lost` 比例高，Phase 范围内迭代（加"句子边界对齐"`splitSentences` 兜底、加"段落指纹"二级锚），不扩到本规范之外。
2. **账本提取质量。** LLM 判 `paid` vs `partial` vs `mismatch` 很主观，可能误报。对策：`note` 必须给理由让用户自己判；`user_overridden` 让用户一键纠正且 rebuild 不覆盖；误报多 → Phase 内迭代 prompt（先要 LLM 给"兑付证据 quote"再判状态，证据为空才允许 `unpaid`），不扩范围。
3. **Reviewer‑2 不能泛泛。** 一旦输出"考虑增加更多证据"这种话，比没有还糟。硬约束：每条点必须带 `verbatim_quote`（锚到正文或小节标题）；prompt 强制"具体到为什么、引用论文里的话"；`venue_profiles.yaml` 提供关注点。质量不达标 → Phase 内迭代 prompt + 给 few-shot 范例，不扩范围。
4. **doc_id 与"未命名保存后改名"。** 未命名 tab 保存成文件后 doc_id 从 `untitled-xxx` 变 `path`，旧账本/评审会留在旧 doc_id 下（前端拉新 path 时是空账本）。MVP 接受这个取舍（重新分析一次即可）；若用户抱怨，后续加"保存时把 untitled 账本迁移到新 path"。
5. **长论文上下文上限。** `build_ledger` 的 LLM #2 和 `run_review` 要喂"正文 / 全文"，长论文会超上限。MVP 先截断（承诺区 ~3000 字符、正文/全文截到模型上限）；分块处理（先骨架后填充）作为 Phase 4 内的优化项，不阻塞。
6. **rebuttal 让步信号识别。** 靠在 reviewer 回复里找关键短语判 `rebutted` 不够鲁棒。MVP 够用（也允许用户手动「标记已 rebutted」）；后续可让 LLM 在回复里额外输出一个结构化 `{"conceded": true/false}` 字段。
7. **gutter glyph 密度。** 大文档很多未兑付承诺 + 很多 open 点 → gutter 一堆图标。同一行合并成一个、hover 列全部；若仍嫌吵，加一个"只显示 error 级"开关。
8. **Mini 缩略图（Phase 5）性能。** 大图在窄面板里渲染 Vue Flow 卡 → 节点 >30 退化为静态 SVG 摘要（沿用 v2-spec §6.6 的结论）。
9. **"红队这篇"的 LLM 调用数量。** 整篇 LLM 评审 + coherence（2 次）+ rw（1 次）= 一次"红队"可能 4-5 次 LLM 调用，慢且费 token。对策：各路 `asyncio.gather` 并行 + 边完成边流式吐点（先到的先看到）；前端"附加检查"复选默认只勾"整篇评审"，一致性/RW 让用户按需勾；"质疑这句"只 1 次调用，轻。Ollama 本地模型多路并行可能拖垮显存 → 检测到本地后端时改串行 + 提示。

---

## §7 之后的发展方向（5 个 Phase 之后，按价值排序）

> 注：「质疑这句」「首尾一致 / gap 匹配」「related work 定位检查」已并入 Phase 3；「真实评审导入」「rebuttal 包导出（按 reviewer 分组的 markdown）」「partial 承诺的『怎么补满』」已并入 Phase 5。下面是这些之后的。

1. **投稿前论证分诊（"从结果到论文"向导）。** 不同的入口：你还没草稿，只有一堆"我发现了什么"。把结果列表 + 你想立的 thesis 喂进去 → "你的证据只撑得起一个更弱的 claim，最强能立的是 X""你这是两篇论文，不是一篇""要立你想立的 claim，还差证据 Y"。产出一份*论证提纲*（thesis → 2-3 个组成 claim → 各自的证据 → 连接的 warrant），可一键塞进编辑器当骨架。把"论证地图"用在写第一个字之前；接 `EditorNewProject` / 新建论文流程。
2. **实验计划面板（experiment-gap planner 完整版）。** Phase 5 的「怎么补满」是单条按钮；完整版把账本里所有 `partial`/`unpaid` 承诺汇成一个"要让论文站住，还需做的实验"清单，每条给"当前覆盖到的条件 → 还需要的条件 → 建议的实验设计"。让*研究者*（不只是写作者）会回来。
3. **论证 diff（改版前后）。** v1 vs v2：抽取两版的论证结构对比 —— "你给 §4 加了两段，但它撑的那条 claim 还是 `partial` —— 你回应到 Reviewer 2 的真实关切了吗""新版把 contribution 3 删了，但 abstract 还在承诺它"。重投 / 大改时用。
4. **「rebuttal 包」深化。** Phase 5 的 `/download` 是 markdown 汇总；深化版：限字数、引用行号、对每条 reviewer concern 给"我们的回应 + 我们做的修改 + 涉及的章节"，直接可投的格式（含 LaTeX 模板）。
5. **「会议画像」深化。** 从 `venue_profiles.yaml` 的手写要点 → 让用户粘 1-2 篇该会议的真实 review（脱敏）few-shot 校准；再进一步内置 OpenReview 公开 review 语料做检索增强（"这个会议历史上最常 reject 的理由是…"）。
6. **「承重路径」真可视化。** Phase 5 先用文字列表占位；完整版在草稿上画"哪几句扛主 claim"——主 claim → 经哪些段落 → 落到哪些证据，链上薄弱处加粗预警。`ArgGraph` 的一个新布局/视图，挂审稿模式里。
7. **「跨文献反证」接入（用起 `observer.py` 的 RAG）。** reviewer 指出 novelty / missing_related_work 时，自动从用户 Zotero/arXiv 库检索"可能撞车"的文献附在 review point 上（"[Smith 2023] 看起来也做了 X"）。把现有 RAG 真正用起来。
8. **「导图 → 草稿提纲」单向桥。** 思维导图里选节点 →「发到编辑器当大纲」一键扁平成提纲塞进 Monaco（**不做**"智能移植成 Toulmin 图"、**不做**双向溯源）。低成本补全创作链条：导图发散 → 提纲 → 编辑器里写（陪练守着）→ 想看整体结构时对草稿 extract 出 X 光图。
9. **「持续守护」（后台哨兵，不打断）。** 编辑器停顿 N 秒后，对**改动过的段落**做极轻量增量 re-check（只问"这次改动有没有破坏某条已兑付的承诺 / 引入新的未兑付承诺 / 让某个被 rebutted 的点重新成立"），结果只更新 gutter 和状态条，**绝不弹窗**。把 reviewer 从"一次性按钮"变成"后台哨兵"。
10. **persona 扩展为"合作者/导师"。** 不是找茬，而是"如果我是你导师，我会建议把 contribution 2 和 3 合并，因为…"。同一套基础设施换 prompt。
11. **「投稿就绪度」仪表盘。** 现有 `/api/compliance` 的 required-sections 检查 + 账本的承诺兑付率 + reviewer 的 fatal/major 计数，三者合并成一个"距离可投还差什么"的单页视图。

---

## 关键文件索引（实施时定位用）

**后端**：
- 新建：`python/src/argument/anchor.py`、`section_utils.py`、`companion_models.py`、`companion_store.py`、`ledger.py`、`reviewer.py`、`venue_profiles.yaml`
- 改动：`python/routers/argument.py`（加 `register_companion` —— ledger CRUD/build/relocate + review/import/point/rebut + suggest-experiment + download）、`python/api_factory.py`（注入 `CompanionStore`）、`config/default.yaml` + `python/config/default.yaml`（加 `features.argument_companion`）
- 复用不动：`python/src/argument/llm_client.py`（`call_llm_chat`）、`critique.py`（`structural_critique` 范本）、`graph_store.py`（存储风格范本）、`flatten`/`flatten_graph` 的 `_format_markdown`（rebuttal 包导出复用）
- 不删（Phase 5 才归并为审稿模式）：`python/src/argument/models_v2.py`、`graph_store.py`、`ai_ops.py`、`critique.py`、`flatten_graph.py`
- 测试新建：`python/tests/unit/test_{anchor,section_utils,companion_models,companion_store,ledger,reviewer,companion_router}.py`

**前端**：
- 新建：`src/composables/useArgumentCompanion.ts`、`src/components/argument/{CompanionPanel,LedgerList,ReviewerThread}.vue`、`src/components/argument/companionGutter.ts`
- 改动：`src/components/MonacoEditor.vue`（gutter decorations + `revealAnchor` + glyph 点击）、`src/components/EditorLayout.vue`（右面板 `argument` Tab 换 `CompanionPanel`、摘掉 `ArgumentMapMini` 引用）、`src/composables/useEditorState.ts`（tab 加 `docId`）、`src/types/index.ts`（加 companion TS 类型）
- 复用：`src/utils/streamReader.ts`、`src/utils/api.ts`、`src/composables/useAgentChat.ts`（SSE-chat 范式）、`src/components/AgentPanel.vue`（消息样式）、`src/components/MarkdownPreview.vue`、`src/utils/sentenceAlign.ts`（`splitSentences`）
- 不删（Phase 5 归并）：`src/components/argument/{ArgumentMapView,ArgumentMapCanvas,ArgNodeCard,ArgEdge,ArgInspector,ArgSourcePane,ArgumentMapMini}.vue`、`src/composables/{useArgumentMap,useArgumentLayout}.ts`
- 测试新建：`src/__tests__/{useArgumentCompanion,companionGutter,CompanionPanel,ReviewerThread}.test.ts`

**文档/约束**：
- 新建：`docs/argument-map-v3-spec.md`（= 本文件）
- 改动：`CLAUDE.md`（加 §0 约束节；Phase 5 尾更新成熟度矩阵 + 合并约束节）；`docs/argument-map-v2-spec.md`（顶部加指针指向 v3）
