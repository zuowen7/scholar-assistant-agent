# 论证地图 v2 重写实施规范（Toulmin Argument Map）

> 本文件是**可逐条执行的实施规范**。任何 AI/开发者在实施时必须严格按本文件执行，不得自行扩大范围、跳过测试、或一次性大改。
> 实施第一步就是把本文件落盘进仓库（`docs/argument-map-v2-spec.md`）并把"约束条款"写进 `CLAUDE.md`（见 §0），防止后续会话上下文丢失导致偏离。

---

## Context（为什么做这件事）

当前 `python/src/argument/` + `src/components/ArgumentMap.vue` 实现的"论证地图"本质是**一个加了 RAG 引用绑定和"逻辑审查"按钮的缩进大纲树**，外加一个把树 flatten 成论文初稿的 4 阶段管道。它的问题：

- **没有论证语义**：`ArgumentNode`（`python/src/argument/models.py:55-71`）字段只有 topic/content/depth/position/domain_tags/references/logic_status/rule_issues/agent_feedback/status/children——**没有 `node_type`，没有带类型的关系边**。Claim / Evidence / Warrant / Backing / Qualifier / Rebuttal 这些核心论证角色在数据模型里完全不存在。
- **节点间只有 parent-child 一种关系**，没有"支持 / 反驳 / 前提→结论 / 为论证保证提供支撑"这类论证特有的有向关系。它是一棵树，不是论证图（DAG）。
- **没有视觉区分**：`ArgumentMap.vue` 只是按 `depth` 缩进的 `<button>` 列表，节点靠左边框颜色显示 `logic_status`，看不出谁是论点、谁是证据。它在用户眼里"就是另一个思维导图"。
- **没有"映射"**：论证树和翻译/原文之间**没有任何关联**——没法在读译文时高亮某句话→对应到论证节点，也没法从节点回跳原文。
- **逻辑校验是大纲完整性检查**（`logic_checker.py` 的 5 条规则查"是否覆盖问题→建模→分析→验证→结论五段式关键词"），不会判断"这个 claim 有没有 evidence 支撑""warrant 有没有 backing""rebuttal 有没有被回应"。
- **flatten 是大纲→论文段落生成**，不是论证结构化。

### 用户已确认的方向（不可再改）

| 决策点 | 结论 |
|---|---|
| 核心用途 | **构建论证（写论文用）+ 评审找漏洞（审稿/批判性阅读用）** 两者都要 |
| 映射形态 | **原文 span ↔ 论证节点** 双向映射（选一段文字绑到节点，点节点高亮文字，点文字高亮节点） |
| 论证本体 | **Toulmin 六元**：Claim / Grounds(Data/Evidence) / Warrant / Backing / Qualifier / Rebuttal，节点带类型，前端按类型区分颜色/形状 |
| 兼容策略 | **彻底重写**：旧的缩进列表 UI 和旧节点模型作废替换 |
| 宿主位置 | **两者都要**：①提升为顶级全屏模式（translate/editor/mindmap/**argument** 并列）作主工作区；②编辑器右侧 tab 保留一个**只读缩略图**供"瞄一眼当前论证结构" |
| flatten | **重写成「图 → 草稿」**（保留 pandoc 模板 + md/tex/docx 输出轮子，重写遍历逻辑走 Toulmin 图），但**放最后一个 Phase**，前面 4 个 Phase 不依赖它 |

### 预期成果（用户视角的"应该的样子"）

1. 翻译完一篇论文 → 打开"论证地图"模式 → "从上次翻译结果载入原文" → 点"提取论证" → AI 抽出这篇论文的 Toulmin 论证图（带类型的节点 + 带类型的有向边 + 每个节点回链到原文 span）。
2. 点图里某个节点 → 左侧原文面板滚动并高亮对应句子；点原文里某句 → 图里对应节点高亮。
3. 点"批判审查" → 节点上出现问题徽标（"这个 claim 没有 grounds 支撑""这个 warrant 没有 backing""这个 rebuttal 没被回应""这里疑似 fallacy"），Inspector 列出问题清单。
4. 写论文时：手动建 Claim 节点 → 点"建议依据" → AI 给候选 grounds/warrant → 用户接受 → 拖一条 `supports` 边 → 重新审查 → 问题消除。
5.（Phase 5）点"导出草稿" → 按论证图生成 md/docx/tex 初稿。

---

## §0 实施前必做（Phase 0，纳入第一个 PR）

> 这一步是为了**防止后续 AI 会话丢失上下文而偏离计划**。

1. 把本规范文件落盘进仓库：`docs/argument-map-v2-spec.md`（内容即本文件）。
2. 在 `CLAUDE.md` 中新增一节"### 论证地图 v2 重写约束（进行中）"，内容包含以下**硬性条款**（每个实施者都必须遵守）：

```markdown
### 论证地图 v2 重写约束（进行中 — 见 docs/argument-map-v2-spec.md）

正在用 5 个独立 PR 把"论证地图"从缩进大纲树重写为 Toulmin 论证图。实施时必须遵守：
1. **不可大改一把梭**。严格按 docs/argument-map-v2-spec.md 的 Phase 1→5 顺序，一个 Phase 一个 PR。
2. **测试先行（TDD）**。每个 Phase 必须先写失败的测试，再写实现让测试通过。不允许"写完主程序再补测试"。
3. **新代码暗发布**。新论证图功能全程挂在 config flag `features.argument_map_v2` 后面（默认 false，直到 Phase 4 完成才在 default.yaml 翻 true）。
4. **旧代码不提前删**。旧的 /api/argument/* 树端点、ArgumentMap.vue、expander.py / logic_checker.py / feedback_generator.py / flatten.py(树版) 只在最后的 cleanup Phase（Phase 5 尾）删除，且必须在新路径经手工 e2e 验证可用之后。
5. **每个 PR 合并前的门禁**：`cd python && pytest tests/ -v` 全绿 + `npm run build` 成功 + `npx vitest` 全绿。任一失败不许合。
6. **范围冻结**。不在本次重写里附带无关重构/清理。Toulmin 六元、原文 span↔节点映射、Vue Flow 图视图、AI 提取/批判/建议、图→草稿 flatten —— 仅此而已。
7. 每个 Phase 完成后跑 /review 或 /security-review。
```

3. 用 `TaskCreate` 建立 5 个 Phase 任务并设置 `blockedBy` 依赖（Phase N+1 依赖 Phase N）。
4. 建分支 `feat/argument-map-v2-phase1`。后续每个 Phase 一条新分支。

---

## §1 总体架构

### 数据模型从"树"变"图（DAG）"

旧：单棵树，节点只有 parent_id/children。新：**多张论证图（一张图 = 对一篇论文/草稿的论证分析）**，每张图包含「带类型的节点」+「带类型的有向边」+「节点↔原文 span 的映射」+「批判审查产出的问题」。

### 后端模块重组（`python/src/argument/`）

| 文件 | 处理方式 |
|---|---|
| `models.py` | **重写**：新增 `ArgNode` / `ArgEdge` / `SpanMapping` / `ArgIssue` / `ArgGraph` Pydantic 模型 |
| `store.py` → `graph_store.py` | **重写**：`ArgGraphStore`，多图，内存 dict + JSON 落盘到 `RUNTIME_DIR/argument_graphs/{gid}.json` |
| `logic_checker.py` → `critique.py` | **重写**：`Critic`——结构性规则（确定性）+ LLM 一遍（fallacy/弱链）。产出 `ArgIssue[]` |
| `expander.py` / `feedback_generator.py` | **删除（Phase 5 尾）**，能力合并进新 `ai_ops.py` |
| 新增 `ai_ops.py` | `extract_argument()`（文本→Toulmin 图，SSE 流式）/ `suggest_element()`（给某节点建议下一个元素）/ `critique_graph()`（调 `critique.py` + LLM） |
| `observer.py` | **保留**（ChromaDB RAG 检索"在我的文献库里找支持证据"，Phase 4 可选接入；Phase 1-3 不动它） |
| `llm_client.py` | **保留**（论证模块的统一 LLM 接口） |
| `flatten.py` → `flatten_graph.py` | **Phase 5 重写**：保留 `_format_markdown/_format_latex/_format_docx` 和 `pandoc_templates` 调用，重写遍历逻辑走 Toulmin 图 |

### 前端模块重组（`src/`）

| 文件 | 处理方式 |
|---|---|
| `components/ArgumentMap.vue` | **删除（Phase 2 替换时）** |
| 新增 `components/argument/ArgumentMapView.vue` | 顶级全屏模式：三栏 [原文面板 \| Vue Flow 图 \| Inspector] |
| 新增 `components/argument/ArgumentMapMini.vue` | 编辑器右侧 tab 的只读缩略图（复用 ArgumentMapCanvas，禁用编辑交互） |
| 新增 `components/argument/ArgumentMapCanvas.vue` | Vue Flow 画布，照搬 `mindmap/MindMapCanvas.vue` 结构 |
| 新增 `components/argument/ArgNodeCard.vue` | 自定义节点，按 `node_type` 区分颜色/形状/图标 |
| 新增 `components/argument/ArgEdge.vue` | 自定义边，bezier + 关系类型小标签 chip |
| 新增 `components/argument/ArgInspector.vue` | 选中节点详情：文本编辑、所属 span（带"跳到原文"）、问题清单、"建议依据"按钮 |
| 新增 `components/argument/ArgSourcePane.vue` | 原文面板：载入原文（上次翻译结果/当前编辑器文件/粘贴）、按句渲染、选中→绑定到节点、双向高亮 |
| 新增 `composables/useArgumentMap.ts` | **singleton**，照搬 `useMindMap.ts` 模式：state + `toFlowNodes/toFlowEdges` 适配器 + undo/redo + 所有 API 调用 + extract/critique 的 SSE 消费 |
| 新增 `composables/useArgumentLayout.ts` | dagre 布局（照搬 `useMindMapLayout.ts`，但 Toulmin 图用 `rankdir:'TB'` + rank 提示：claim 在底、grounds/warrant 在上、backing 在 warrant 之上、rebuttal 在侧） |
| `utils/sentenceAlign.ts` | **复用现有** `renderSentenceMarkedHtml()`（已存在但未使用，包 `<span data-sent-idx data-block-id data-side class="sent">`），ArgSourcePane 直接用它 |
| `components/TranslateView.vue` | **可选**（Phase 3 收尾，非必须）：也改用 `renderSentenceMarkedHtml()` 渲染，使翻译视图本身也支持选句 |
| `App.vue` / 顶级 mode 切换 | 新增 `argument` 模式入口（参考现有 `mindmap` 模式怎么挂的） |
| `components/EditorLayout.vue:88-112` | 把 `<ArgumentMap>` 换成 `<ArgumentMapMini>`（只读缩略图） |

### 复用清单（不要重新造轮子）

- Vue Flow 套路：`src/components/mindmap/MindMapCanvas.vue` / `MindNodeCard.vue`（Handle 用法、双击编辑）/ `MindEdge.vue`（`BaseEdge` + `getBezierPath()`、hover/selected 样式、右键删除）
- 数据→Flow 适配器套路：`src/composables/useMindMap.ts` 的 `toFlowNodes()/toFlowEdges()`、undo/redo
- 布局：`src/composables/useMindMapLayout.ts`（dagre，`@vue-flow/core` 和 `dagre` 已在 `package.json`）
- 键盘：`src/composables/useMindMapKeyboard.ts`（Tab/Enter/F2/方向键/Ctrl+Z）
- SSE：`src/utils/streamReader.ts` 的 `readSseStream(reader, (eventType, data) => {})`；`src/utils/api.ts` 的 `API_BASE`
- 选择→fetch→SSE→更新 的交互范式：`src/components/MonacoEditor.vue:132-181` 的 AI-edit 流程
- 句子拆分/对齐：`src/utils/sentenceAlign.ts` 的 `splitSentences()` / `findCorrespondingSentenceIdx()` / `renderSentenceMarkedHtml()`
- 翻译块：`src/composables/useTranslate.ts`（singleton）的 `state.blocks: BlockData[]`；`BlockData` = `{ id, type, level?, translatable, original, translated, status? }`（`src/types/index.ts:18-26`）
- 后端：`api_factory.py` 的 `register_argument(app, ...)` 注入模式（config getters / runtime dirs / rag_store）；`python/src/argument/llm_client.py`；`pandoc_templates`
- SSE 后端：`sse-starlette`（项目已用）

---

## §2 后端详细设计

### 2.1 数据模型 `python/src/argument/models.py`（重写）

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid, time

NodeType = Literal["claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"]

# 关系类型与"允许的(source_type -> target_type)"约束（见 2.3 校验）
RelationType = Literal[
    "supports",   # grounds  -> claim   （论据支持论点）
    "warrants",   # warrant  -> claim   （论证保证：解释 grounds 为何支持 claim；MVP 简化为指向 claim）
    "backs",      # backing  -> warrant （为论证保证提供支撑）
    "qualifies",  # qualifier-> claim   （限定 claim 的确定程度）
    "rebuts",     # rebuttal -> claim   （反驳/例外，攻击 claim）
    "counters",   # claim/grounds -> rebuttal （对反驳的回应）
]

class SpanMapping(BaseModel):
    id: str = Field(default_factory=lambda: f"sp_{uuid.uuid4().hex[:10]}")
    node_id: str
    source_type: Literal["block", "selection", "editor", "extracted"]  # 来源
    block_id: Optional[str] = None        # 若来自翻译块
    side: Literal["orig", "trans"] = "trans"
    char_start: Optional[int] = None       # 在该块/该文本里的字符偏移（best-effort）
    char_end: Optional[int] = None
    quote: str                             # 实际引用的原文片段（弱锚点，必填，用于模糊重定位）
    source_label: Optional[str] = None     # 文档标题/文件名

class ArgIssue(BaseModel):
    id: str = Field(default_factory=lambda: f"is_{uuid.uuid4().hex[:10]}")
    node_id: Optional[str] = None          # 问题挂在节点上
    edge_id: Optional[str] = None          # 或挂在边上
    severity: Literal["info", "warning", "error"]
    category: Literal[
        "missing_grounds", "missing_warrant", "missing_backing",
        "unaddressed_rebuttal", "fallacy", "weak_link", "orphan",
        "unsupported_qualifier", "other",
    ]
    message: str
    suggestion: Optional[str] = None

class ArgNode(BaseModel):
    id: str = Field(default_factory=lambda: f"n_{uuid.uuid4().hex[:10]}")
    node_type: NodeType
    text: str                              # 节点内容（一句话/一条主张）
    label: Optional[str] = None            # 卡片上的短标签（None 则截断 text）
    confidence: Optional[float] = None     # qualifier 语义可用；0-1
    position: Optional[dict] = None        # {"x": float, "y": float} for Vue Flow
    span_ids: list[str] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)
    created_by: Literal["user", "ai"] = "user"

class ArgEdge(BaseModel):
    id: str = Field(default_factory=lambda: f"e_{uuid.uuid4().hex[:10]}")
    source_id: str
    target_id: str
    relation_type: RelationType
    label: Optional[str] = None
    created_by: Literal["user", "ai"] = "user"

class ArgGraph(BaseModel):
    id: str = Field(default_factory=lambda: f"g_{uuid.uuid4().hex[:10]}")
    title: str = "未命名论证图"
    nodes: list[ArgNode] = Field(default_factory=list)
    edges: list[ArgEdge] = Field(default_factory=list)
    spans: list[SpanMapping] = Field(default_factory=list)
    issues: list[ArgIssue] = Field(default_factory=list)
    source_doc: Optional[str] = None       # 来源论文/文件标识
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
```

### 2.2 持久化 `python/src/argument/graph_store.py`（重写）

`ArgGraphStore`：
- 构造接收 `runtime_dir`；图存到 `runtime_dir / "argument_graphs" / f"{gid}.json"`。
- 内存缓存 `dict[str, ArgGraph]`；首次访问某图时按需从磁盘 lazy load；写操作后立即 flush 该图 JSON（保持和旧 store 一样的"内存+JSON"风格）。
- 方法：`list_graphs() -> list[dict]`（id/title/node_count/updated_at）、`get(gid)`、`create(title, source_doc=None)`、`delete(gid)`、`upsert_node(gid, node)`、`delete_node(gid, nid)`（级联删 incident edges、删该节点 span/issue）、`upsert_edge(gid, edge)`（先校验，见 2.3）、`delete_edge(gid, eid)`、`add_span(gid, span)`、`delete_span(gid, sid)`、`set_issues(gid, issues)`（critique 用，整体替换）、`replace_graph(gid, partial)`（extract 完成后批量写入 nodes/edges/spans）。
- 旧的 `argument_tree.json` **不迁移**——形态不同、价值低，直接忽略。

### 2.3 边的合法性校验（在 `upsert_edge` 里）

```
ALLOWED = {
  "supports":  {("grounds", "claim")},
  "warrants":  {("warrant", "claim")},
  "backs":     {("backing", "warrant")},
  "qualifies": {("qualifier", "claim")},
  "rebuts":    {("rebuttal", "claim")},
  "counters":  {("claim", "rebuttal"), ("grounds", "rebuttal")},
}
```

非法组合返回 400，错误体 `{"error": "invalid_edge", "detail": "..."}`。也要拒绝自环、重复边（同 source/target/type）。

### 2.4 路由 `python/routers/argument.py`（重写）

> 全部新端点**在 `features.argument_map_v2` 为 true 时才注册**；为 false 时仍注册旧端点（Phase 1-3 期间二者并存）。`register_argument` 依旧从 `api_factory.py` 接收 config getters / runtime dirs / rag_store；新增持有一个 `ArgGraphStore` 实例。

| Method | Path | Body / 说明 |
|---|---|---|
| GET | `/api/argument/graphs` | 列表 |
| POST | `/api/argument/graph` | `{title?, source_doc?}` → 新建空图，返回 graph |
| GET | `/api/argument/graph/{gid}` | 全图 |
| DELETE | `/api/argument/graph/{gid}` | 删图 |
| PUT | `/api/argument/graph/{gid}/node` | upsert 节点（无 id 则新建），返回节点 |
| DELETE | `/api/argument/graph/{gid}/node/{nid}` | 删节点（级联） |
| PUT | `/api/argument/graph/{gid}/edge` | upsert 边（经 2.3 校验），返回边或 400 |
| DELETE | `/api/argument/graph/{gid}/edge/{eid}` | 删边 |
| PUT | `/api/argument/graph/{gid}/span` | `{node_id, source_type, block_id?, side?, char_start?, char_end?, quote, source_label?}` → 新建 span，返回 span |
| DELETE | `/api/argument/graph/{gid}/span/{sid}` | 删 span |
| POST | `/api/argument/graph/{gid}/extract` | `{text, source_label?, side?}` → **SSE**：`event: node`（逐个）→ `event: edge` → `event: span` → `event: progress`（可选）→ `event: complete`（带最终 graph 摘要）。详见 2.5 |
| POST | `/api/argument/graph/{gid}/critique` | 无 body 或 `{node_id?}`（限定范围）→ 返回 `{issues: ArgIssue[]}` 并写入图。详见 2.6 |
| POST | `/api/argument/graph/{gid}/suggest` | `{node_id}` → 返回 `{candidates: ArgNode[], suggested_edges: ArgEdge[]}`（**不自动落库**，前端让用户接受）。详见 2.7 |
| POST | `/api/argument/graph/{gid}/flatten` | **Phase 5**：`{template, latex_template, ...}` → 启动异步任务，返回 `{task_id}` |
| GET | `/api/argument/graph/{gid}/flatten/{task_id}` | **Phase 5**：SSE 进度流 |
| GET | `/api/argument/download/{task_id}` | **Phase 5**：下载产物（沿用旧逻辑） |

旧端点（`/api/argument/tree` 等）在 Phase 5 尾的 cleanup 里删除。

### 2.5 `extract_argument()`（killer feature，`ai_ops.py`）

输入：源文本（一篇论文译文或选中片段）、`side`、`source_label`。
策略：
1. 文本过长则按段/按句切块，分批喂；或先让 LLM 出"全局论证骨架"，再逐块补 span。MVP 先做"单批，截断到模型上下文上限"，能跑通再优化。
2. Prompt 要点（用 `argument/llm_client.py`）：
   - 角色：学术论证分析专家。
   - 任务：把给定学术文本的论证结构抽成 Toulmin 图。
   - 输出**严格 JSON**：`{"nodes":[{"local_id":"c1","type":"claim|grounds|warrant|backing|qualifier|rebuttal","text":"...","verbatim_quote":"<原文里的精确子串，用于定位>"}], "edges":[{"source":"<local_id>","target":"<local_id>","relation":"supports|warrants|backs|qualifies|rebuts|counters"}]}`。
   - 约束：`verbatim_quote` 必须是输入文本的精确子串（若做不到则给最接近的片段）；每个 claim 至少尝试找 grounds；识别文中的让步/例外作 rebuttal。
3. 后端拿到 JSON 后：
   - 用 `str.find` 定位 `verbatim_quote` → 算 `char_start/char_end`；找不到则用 `difflib.SequenceMatcher` 模糊匹配取最相似窗口（阈值 0.6），仍不行就 `char_start=char_end=None`、span 仍保留 `quote`（前端可标"未锚定，请手动重绑"）。
   - `local_id` → 真实 `node.id` 映射；建 `ArgNode`（`created_by="ai"`），建 `ArgEdge`（经 2.3 校验，非法的丢弃并在 `progress` 事件里报 warning），建 `SpanMapping`（`source_type="extracted"`，带 `block_id` 若能对上翻译块）。
   - 边产边 SSE 推（`event: node` / `event: edge` / `event: span`），最后 `event: complete`。
   - 全部写进 `graph_store.replace_graph`。
4. 失败兜底：LLM 不返合法 JSON → 重试一次（更严格的 prompt）→ 再失败则 `event: error`，**不写脏数据**。

### 2.6 `critique_graph()`（评审找漏洞，`critique.py` + `ai_ops.py`）

混合两路：
- **结构性确定性检查**（不调 LLM，纯遍历图）：
  - claim 没有任何入边 `supports` → `missing_grounds`(warning)
  - claim 有 `supports` 入边但没有 `warrants` 入边 → `missing_warrant`(info)
  - warrant 没有 `backs` 入边 → `missing_backing`(info，弱)
  - rebuttal 没有 `counters` 入边 → `unaddressed_rebuttal`(warning)
  - qualifier 没连到任何 claim → `unsupported_qualifier`(info)
  - 任意节点完全孤立（无任何边） → `orphan`(warning)
- **LLM 一遍**：把图序列化成可读文本（节点列表 + 边列表）喂给 LLM，问"找逻辑谬误（以偏概全、循环论证、稻草人、诉诸权威等）、薄弱的支持链、未定义术语"，输出 `[{node_local_id?, edge_local_id?, severity, category:"fallacy|weak_link|other", message, suggestion}]`。映射回真实 id。
- 合并两路 → `set_issues` 写入图，同时把 `issue_id` 挂到对应 `node.issue_ids` / `edge`。返回 `{issues}`。

### 2.7 `suggest_element()`（构建模式辅助，`ai_ops.py`）

输入 `node_id`。若是 claim：让 LLM 给 2-3 个候选 `grounds`（每个带 text）+ 1 个候选 `warrant`，并给出建议的边。返回 `{candidates: ArgNode[](created_by="ai", 但还没 id 落库——给临时 local_id), suggested_edges}`。前端在 Inspector 里展示，用户点"采纳"才真正 PUT 落库。

### 2.8 `flatten_graph()`（Phase 5，`flatten_graph.py`）

- 拓扑：找所有 claim（按某种顺序：有 `counters`→`rebuts` 链的放后面；或简单按创建顺序）。
- 每个 claim 生成一段：主题句=claim.text；接其 grounds（"依据：..."），接 warrant（"之所以...是因为..."），接 backing；若有 qualifier 调整语气（"在...条件下""很可能"）。
- 所有 rebuttal 汇成"局限性/反对意见"段，每个 rebuttal 后接其 `counters`（回应）。
- 复用旧 `flatten.py` 的 `_format_markdown` / `_format_latex` / `_format_docx` + `pandoc_templates`（6 个 LaTeX 模板：IEEE Conf/Journal、ACM、NeurIPS、LNCS、Generic）。异步任务 + SSE 进度沿用旧机制。

---

## §3 前端详细设计

### 3.1 `useArgumentMap.ts`（singleton，照搬 `useMindMap.ts`）

```ts
// 模块级 state（singleton）
state = reactive({
  graph: null as ArgGraph | null,
  graphList: [] as GraphSummary[],
  selectedNodeId: '' as string,
  selectedEdgeId: '' as string,
  hoveredSpanId: '' as string,     // 从原文面板 hover 过来
  highlightNodeIds: [] as string[], // 点原文 span 时要高亮的节点
  extracting: false, critiquing: false,
  source: { mode: 'paste'|'translation'|'editor', text: '', label: '', side: 'trans', blocks: [] as BlockData[] },
})
// 历史栈（undo/redo），照搬 useMindMap
// API：loadGraphList / createGraph / openGraph / deleteGraph / upsertNode / deleteNode / upsertEdge / deleteEdge / addSpan / deleteSpan
// AI：extractArgument(text)（消费 SSE，逐个 push node/edge/span 到 state.graph）/ critiqueGraph() / suggestElement(nodeId)
// Flow 适配器：toFlowNodes() -> [{id, type:'argNode', position, data:{node_type, text, label, issueCount, selected}}]
//             toFlowEdges() -> [{id, source, target, type:'argEdge', label:relation_type, data:{relation_type, selected}}]
// 来源载入：loadSourceFromTranslation()（import useTranslate(); 取 state.blocks 拼 text）/ loadSourceFromEditor()（import useEditor()）/ setPastedSource(text)
// 映射高亮：focusNode(nodeId)（→ 让 ArgSourcePane 滚到其 span）/ focusSpan(spanId)（→ 高亮对应 node）
```

### 3.2 节点视觉规范（`ArgNodeCard.vue`）

| node_type | 颜色（用 `styles/tokens.css` 的 `--c-*`） | 形状/边框 | 图标提示 |
|---|---|---|---|
| claim | `--c-accent`（强调色），实心填充 | 圆角矩形，**粗边框** | ◆ / "主张" |
| grounds | 绿色系 | 圆角矩形 | ▣ / "依据" |
| warrant | 蓝色系 | 圆角矩形，**虚线边框**（表示"逻辑桥") | ∴ / "论证保证" |
| backing | 蓝色浅色调 | 圆角矩形，较小 | ⌐ / "支撑" |
| qualifier | 琥珀/橙色 | **小药丸 pill** | ~ / "限定" |
| rebuttal | 红/橙色 | 圆角矩形，**虚线 + 警示色** | ✕ / "反驳" |

- 卡片显示 `label`（无则截断 `text` 到 ~40 字），hover 显示完整 `text`。
- 右上角问题徽标：`issue_ids.length` 个，颜色按最高 severity（error 红 / warning 黄 / info 灰）。点徽标→Inspector 跳到该节点的问题。
- 双击进入编辑（改 `text`），blur/Enter 提交（PUT）。
- Vue Flow `Handle`：四边各放 target+source（照搬 `MindNodeCard.vue`）。
- `created_by === 'ai'` 的节点加一个小 AI 角标，且加"未确认"态（细微样式差异），用户编辑过即转为已确认。

### 3.3 边视觉规范（`ArgEdge.vue`）

- `BaseEdge` + `getBezierPath()`（照搬 `MindEdge.vue`）。
- 颜色：`supports` 绿、`rebuts` 红、`counters` 橙、`warrants`/`backs` 蓝、`qualifies` 琥珀。
- 中点放一个小 chip 标关系名（"支持"/"反驳"/"保证"/"支撑"/"限定"/"回应"）。
- hover/selected 加粗 + 变色（照搬 `MindEdge`）。
- 右键菜单：删除、改关系类型（弹一个小 select，改完 PUT，若新组合非法则后端 400→前端 toast 回滚）。
- `@connect`（用户从一个 Handle 拖到另一个）：默认按 source/target 的 node_type 自动推断 relation_type（查 2.3 的 ALLOWED 反查唯一解；多解则弹选择）；推断不出（非法组合）→ 拒绝并 toast。

### 3.4 布局 `useArgumentLayout.ts`

- 用 dagre（照搬 `useMindMapLayout.ts`），`rankdir: 'TB'`。
- rank 提示：给每个节点设 rank/层级 —— claim 在最下层；指向它的 grounds、warrant、qualifier 在上一层；backing 在 warrant 之上；rebuttal 放在 claim 同层但靠右（或单独一侧），其 counters 在其上。
- 提供"自动布局"按钮（手动触发，不每次都自动跑，避免用户拖完又被打乱——和 MindMap 行为一致）。
- 节点有 `position` 就用 `position`，没有才布局。

### 3.5 原文映射 UX（`ArgSourcePane.vue`）—— 这是"映射"的核心

1. **载入原文**：面板顶部三个来源按钮：
   - 「从上次翻译结果载入」→ `useArgumentMap` 调 `useTranslate()` 取 `state.blocks`，按块渲染，每块用 `renderSentenceMarkedHtml(block.translated, block.id, 'trans')`（已有工具，包 `<span data-sent-idx data-block-id data-side class="sent">`）。可切 orig/trans。
   - 「从当前编辑器文件载入」→ 取 `useEditor()` 当前 tab 内容，按句渲染（一个虚拟 block）。
   - 「粘贴文本」→ textarea 输入，按句渲染。
2. **选中→绑定**：用户在面板里点选一句（或框选跨句）→ 该 span 上浮一个小工具条「绑定到节点 ▾」：
   - 选项：绑定到当前选中的图节点；或「新建并绑定 → Claim / Grounds / Warrant / Backing / Qualifier / Rebuttal」（用选中文字作新节点的 text）。
   - 确认后 → `addSpan`（POST `/api/argument/graph/{gid}/span`，带 `block_id`/`char_start`/`char_end`/`quote`/`side`）；若是"新建并绑定"再先 `upsertNode`。
3. **双向高亮**：
   - 点图里的节点 → `focusNode(nodeId)` → ArgSourcePane 给该节点所有 span 对应的 `.sent` 元素加 `.arg-mapped-active` 类并 `scrollIntoView({block:'center'})`。
   - hover/点原文里某 `.sent` → 读它的 `data-block-id`+`data-sent-idx` → 找到 `quote` 落在这个 span 里的 SpanMapping → 对应节点加高亮（`state.highlightNodeIds`），Vue Flow 里那些节点描边变亮。
   - 配色：mapped（有绑定但非当前）淡色下划线；active（当前聚焦）实色高亮。
4. **「提取论证」按钮**：在 ArgSourcePane 顶部 → 用当前载入的原文调 `extractArgument(text)` → SSE 逐个把 node/edge/span 灌进图，画布实时长出来。
5. **未锚定 span**：`char_start === null` 的 span 在原文里找不到精确位置 → 在节点 Inspector 里标"⚠ 此引用未在原文中定位，点击重新框选绑定"。

### 3.6 Inspector（`ArgInspector.vue`）

选中节点时显示：
- 节点类型（带颜色徽标）+ 可编辑 `text` / `label` / （qualifier 时）`confidence`。
- 该节点的 span 列表：每条显示 `quote` 摘要 + 来源标签 + 「跳到原文」（→ `focusSpan`）+ 「解绑」。
- 该节点的 issue 列表：severity 徽标 + message + suggestion + （若 suggestion 可执行，如"补一个 grounds"）一个快捷按钮。
- 「建议下一个元素」按钮（claim 时高亮）→ `suggestElement` → 列出候选 grounds/warrant + 「采纳」按钮。
- 入边/出边列表（可点跳到对应节点/边）。
选中边时显示：关系类型（可改）、source/target 节点摘要、删除。
没选中时：显示全图统计（各类型节点数、问题数）+「批判审查」按钮 +「自动布局」+「导出草稿」(Phase 5)。

### 3.7 顶级模式接入

- 参考现有 `mindmap` 模式怎么在 `App.vue` / 顶部 mode 切换里挂的，新增 `argument` 模式 → 渲染 `ArgumentMapView.vue`（三栏：左 `ArgSourcePane` | 中 `ArgumentMapCanvas` | 右 `ArgInspector`；列宽可拖）。
- 模式切换处加图标按钮（在 `features.argument_map_v2` 为 true 时才显示）。
- `EditorLayout.vue:88-112` 的右侧 'argument' tab：把 `<ArgumentMap>` 换成 `<ArgumentMapMini>`（复用 `ArgumentMapCanvas` 但 props `readonly=true`：禁用拖拽/连线/编辑/右键菜单，只能看 + 点节点跳到原文 + 一个「在论证模式中打开」按钮跳到全屏模式）。Mini 显示的是"当前打开的那张图"（`useArgumentMap` 的 `state.graph`）。

---

## §4 分阶段实施（5 个 PR，每个独立可工作）

> **每个 Phase 必须：先写测试（TDD）→ 跑测试看它失败 → 写实现 → 测试通过 → `pytest tests/ -v` 全绿 + `npm run build` + `npx vitest` 全绿 → 跑 /review → 合并。** 详见 §0 条款。

### Phase 0 — 落盘 + 约束（并入 Phase 1 的 PR）
- 落盘 `docs/argument-map-v2-spec.md`；`CLAUDE.md` 加约束节（§0 第 2 条原文）；`config/default.yaml`（仓库根）和 `python/config/default.yaml` 模板里加 `features.argument_map_v2: false`。
- `TaskCreate` 建 5 个 Phase 任务 + 依赖链。

### Phase 1 — 后端：模型 + 图存储 + CRUD + span 端点（**不含 AI**）
**先写测试**（`python/tests/unit/test_argument_models.py`、`test_argument_graph_store.py`、`test_argument_router.py`）：
- 模型字段/默认值/枚举校验；非法 node_type、非法 relation_type 被拒。
- `ArgGraphStore`：create/get/list/delete；upsert_node 新建 vs 更新；delete_node 级联删 incident edges + span/issue；upsert_edge 经 2.3 校验（合法过、非法 400、自环拒、重复边拒）；add_span/delete_span；JSON 落盘后能 reload。
- 路由：所有 CRUD + span 端点的状态码和返回体；`features.argument_map_v2=false` 时新端点 404、旧端点仍在；`=true` 时新端点可用。
**再写实现**：`models.py` 重写、`graph_store.py` 新建、`routers/argument.py` 加新端点（旧的不动）、`api_factory.py` 注入 `ArgGraphStore`。
**用户可见变化**：无（前端还在用旧 ArgumentMap.vue）。
门禁：上述测试 + 全量 pytest 绿。

### Phase 2 — 前端：Vue Flow 图视图替换缩进列表
**先写测试**（`src/__tests__/useArgumentMap.test.ts`、`useArgumentLayout.test.ts`）：
- `toFlowNodes/toFlowEdges` 适配器：给定 ArgGraph → 正确的 Flow 结构（type、position、data、edge label）。
- undo/redo：upsertNode → undo 回退、redo 重做。
- `useArgumentLayout`：给定节点/边 → 每个节点拿到 position；rank 提示正确（claim 在更下层）。
- 边连接推断：给 (grounds→claim) 推出 `supports`；非法组合返回 null。
**再写实现**：`useArgumentMap.ts`、`useArgumentLayout.ts`、`ArgumentMapCanvas.vue`、`ArgNodeCard.vue`、`ArgEdge.vue`、`ArgInspector.vue`（先做节点/边 CRUD 部分，span/AI 部分留空占位）、`ArgumentMapView.vue`（先两栏：画布 + Inspector，原文面板 Phase 3 再加）、`ArgumentMapMini.vue`；`App.vue` 加 `argument` 模式；`EditorLayout.vue` 把 `<ArgumentMap>` 换 `<ArgumentMapMini>`；**删除 `src/components/ArgumentMap.vue`**。
**用户可见变化**：论证地图变成 Vue Flow 图，能手动建/连/删/编辑带类型的节点和边，能自动布局。还没有原文映射、没有 AI。
门禁：vitest 绿 + `npm run build` 成功 + 手工点一遍 CRUD。

### Phase 3 — 原文 span ↔ 节点映射
**先写测试**：
- 后端：span 端点已在 Phase 1 测过；这里补"`block_id` + char 偏移 round-trip"、"`quote` 必填"。
- 前端（`src/__tests__/ArgSourcePane.test.ts` 或 `useArgumentMap` 扩展测试）：从 `useTranslate().state.blocks` 载入 → 渲染出带 `data-block-id`/`data-sent-idx` 的 `.sent`；选中一句→`addSpan` 调用参数正确；`focusNode` 把对应 `.sent` 标 active；`focusSpan` 把对应节点加进 `highlightNodeIds`。
- `renderSentenceMarkedHtml` 已有的话补一个它的单测（若还没有）。
**再写实现**：`ArgSourcePane.vue`（三种来源载入 + 选中绑定 + 双向高亮）；`useArgumentMap` 加来源载入/`focusNode`/`focusSpan`/span CRUD；`ArgumentMapView.vue` 补上左侧原文栏；`ArgInspector` 补 span 列表 + 跳转 + 解绑；`ArgNodeCard` 点击触发 `focusNode`；（可选）`TranslateView.vue` 改用 `renderSentenceMarkedHtml`。
**用户可见变化**：能把原文句子绑到节点，点节点亮原文、点原文亮节点。
门禁：vitest + build + 手工 e2e（载入翻译结果→选句绑定→双向高亮）。

### Phase 4 — AI：提取 + 批判 + 建议
**先写测试**（`python/tests/unit/test_argument_ai_ops.py`、`test_argument_critique.py`，**LLM 用 mock/fake**）：
- `extract_argument`：给 mock LLM 返回一段合法 JSON → 产出对应 nodes/edges/spans，`verbatim_quote` 能定位算出 char 偏移；给"quote 不是精确子串"→ 模糊匹配兜底；给"非法 JSON"→ 重试一次→仍失败→`error` 事件且不写脏数据；给"非法边"→ 丢弃 + warning。
- `critique.py` 结构检查：构造 claim-无-grounds → 出 `missing_grounds`；warrant-无-backing → `missing_backing`；rebuttal-无-counters → `unaddressed_rebuttal`；孤立节点 → `orphan`。`critique_graph` 合并 LLM 路（mock 返回一条 fallacy）→ issue 写进图。
- `suggest_element`：mock LLM → 返回候选但**不落库**（store 里节点数不变）。
- 路由：`/extract` SSE 事件序列、`/critique` 返回体、`/suggest` 返回体。
**再写实现**：`ai_ops.py`（extract/suggest）、`critique.py`（结构检查 + 序列化图给 LLM）、`routers/argument.py` 加 `/extract` `/critique` `/suggest`；前端 `useArgumentMap` 加 `extractArgument`（SSE 消费）/`critiqueGraph`/`suggestElement`；`ArgSourcePane` 加「提取论证」按钮；`ArgInspector` 加问题清单渲染 + 「建议下一个元素」+ 候选「采纳」；`ArgNodeCard` 渲染问题徽标。
**收尾**：把 `config/default.yaml` 的 `features.argument_map_v2` 翻成 `true`（暗发布转正式）。
**用户可见变化**：完整功能——提取、批判、建议都能用。
门禁：pytest（含新 AI 测试）+ vitest + build + 手工 e2e（翻 PDF→载入→提取→看图→点节点跳原文→批判→看问题→补节点→重批判→问题消除）。

### Phase 5 — flatten 重写（图→草稿）+ 清理旧代码
**先写测试**（`python/tests/unit/test_argument_flatten_graph.py`）：构造一张含 claim+grounds+warrant+rebuttal+counters 的图 → `flatten_graph` 产出的 markdown 含主题句/依据/局限性段；格式函数 md/tex/docx 各能产出（docx 那个可标 `@pytest.mark.skipif` 没装 pandoc）。
**再写实现**：`flatten_graph.py`（复用旧 `flatten.py` 的 `_format_*` + `pandoc_templates`）；路由加 `/flatten` 异步任务 + SSE + `/download`；前端 `ArgInspector`/`ArgumentMapView` 加「导出草稿」（模板选择 + 进度）。
**清理**：删除 `python/src/argument/expander.py`、`logic_checker.py`、`feedback_generator.py`、旧 `flatten.py`（确认 `flatten_graph.py` 顶替了需要的格式函数后）；删除 `routers/argument.py` 里的旧树端点（`/api/argument/tree`、`/expand`、`/observe`、`/bind`、`/review`、`/recommendations` 等旧 CRUD）；删除 `CLAUDE.md` 里"进行中"约束节里 §0-3/4 的"暗发布/不提前删"两条（已完成），把 CLAUDE.md 的子系统成熟度矩阵里"论证地图"那行更新为新实现；`config` 里删 `features.argument_map_v2` flag（v2 成为唯一版本）或保留为 true。`observer.py` 保留（RAG 检索仍有用）。更新 `docs/argument-map-v2-spec.md` 标注"已完成"。
门禁：全量 pytest + vitest + build + 手工 e2e（含导出草稿）+ /review。

---

## §5 端到端验证清单

- 后端单测：`cd python && pytest tests/unit/test_argument_models.py tests/unit/test_argument_graph_store.py tests/unit/test_argument_router.py tests/unit/test_argument_ai_ops.py tests/unit/test_argument_critique.py tests/unit/test_argument_flatten_graph.py -v`
- 后端全量回归：`cd python && pytest tests/ -v`（确保没碰坏别的）
- 前端单测：`npx vitest`
- 前端构建：`npm run build`
- 手工 e2e（`npx tauri dev`，注意 Windows 用 `start_dev.bat` 清代理变量）：
  1. 翻译一篇 PDF → 进度跑完。
  2. 切到「论证地图」模式 → 「从上次翻译结果载入原文」→ 左栏显示按句的译文。
  3. 点「提取论证」→ 画布逐步长出带类型的节点和边；节点上有 AI 角标。
  4. 点某个 claim 节点 → 左栏滚动并高亮它对应的原文句子；点左栏另一句 → 对应节点描边变亮。
  5. 点「批判审查」→ 部分节点出现问题徽标；Inspector 列出"claim X 无 grounds 支撑"之类。
  6. 手动新建一个 Grounds 节点（用左栏选一句"新建并绑定→Grounds"）→ 从它拖一条边到那个 claim → 自动识别为 `supports`。
  7. 再点「批判审查」→ 那条 `missing_grounds` 问题消失。
  8. 选中 claim → Inspector 点「建议下一个元素」→ 出候选 warrant → 「采纳」→ 图里多一个 warrant 节点 + `warrants` 边。
  9.（Phase 5）点「导出草稿」→ 选 Generic 模板 → 下载得到 .docx，内容是按论证图组织的初稿。
  10. 切到编辑器模式 → 右侧 tab「论证」→ 看到只读缩略图，点节点能跳回论证模式。

---

## §6 风险与待定项（实施中如需用户拍板，在对应 Phase 提出）

1. **提取质量**：LLM 对真实论文做 Toulmin 抽取很难，`verbatim_quote` 常因译文改写不是精确子串 → 已用 difflib 模糊匹配 + "未锚定"标记兜底；若效果差，Phase 4 内迭代 prompt（分块、先骨架后填充），但不扩到本规范之外。
2. **长文本**：MVP 先单批截断；超长论文的分块提取作为 Phase 4 内的优化项，不阻塞。
3. **多图 vs 单图**：定为**多图**（一张图 = 对一篇论文/草稿的分析），`graphList` 让用户切换。
4. **`warrants` 边指向**：Toulmin 原义里 warrant 是"grounds→claim 这条推理"的保证，理论上该指向边。MVP 简化为 `warrant → claim`（指向节点），够用；若日后要更严谨再说。
5. **键盘交互**：Phase 2 先接 `useMindMapKeyboard` 的等价物（删除/重命名/撤销），Tab 加子节点这种树语义在图里不直接适用，按需裁剪。
6. **Mini 缩略图性能**：大图在右侧窄 tab 里渲染 Vue Flow 可能卡 → 节点数超阈值（如 >30）就只画一个静态 SVG 摘要，不挂完整 Vue Flow。

---

## 关键文件索引（实施时定位用）

**后端**：
- 重写：`python/src/argument/models.py`、`python/routers/argument.py`
- 新建：`python/src/argument/graph_store.py`、`python/src/argument/critique.py`、`python/src/argument/ai_ops.py`、`python/src/argument/flatten_graph.py`(P5)
- 改动：`python/api_factory.py`（注入 `ArgGraphStore`）、`config/default.yaml` + `python/config/default.yaml`（加 flag）
- 保留不动：`python/src/argument/observer.py`、`python/src/argument/llm_client.py`、`pandoc_templates`
- 删除(P5)：`python/src/argument/expander.py`、`logic_checker.py`、`feedback_generator.py`、`flatten.py`
- 测试新建：`python/tests/unit/test_argument_{models,graph_store,router,ai_ops,critique,flatten_graph}.py`

**前端**：
- 删除：`src/components/ArgumentMap.vue`
- 新建：`src/components/argument/{ArgumentMapView,ArgumentMapMini,ArgumentMapCanvas,ArgNodeCard,ArgEdge,ArgInspector,ArgSourcePane}.vue`、`src/composables/{useArgumentMap,useArgumentLayout}.ts`
- 改动：`src/App.vue`（加 argument 模式）、`src/components/EditorLayout.vue:88-112`（换 Mini）、`src/types/index.ts`（加 ArgGraph/ArgNode/ArgEdge/SpanMapping/ArgIssue TS 类型）、（可选）`src/components/TranslateView.vue`
- 复用：`src/utils/sentenceAlign.ts`（`renderSentenceMarkedHtml`/`splitSentences`）、`src/utils/streamReader.ts`、`src/utils/api.ts`、`src/components/mindmap/*`（参考）、`src/composables/useMindMap*.ts`（参考）
- 测试新建：`src/__tests__/{useArgumentMap,useArgumentLayout,ArgSourcePane}.test.ts`

**文档/约束**：
- 新建：`docs/argument-map-v2-spec.md`（= 本文件）
- 改动：`CLAUDE.md`（加约束节；P5 尾更新成熟度矩阵）
