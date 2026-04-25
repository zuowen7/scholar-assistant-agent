# Dynamic Argument Mapping — 项目方案

> 版本：v1.0
> 日期：2026/04/25
> 状态：待实施

---

## 一、我们为什么要做这个

传统 AI 写作工具是"黑盒代写"——用户输入需求，AI 吐出文本。研究者失去了对论证过程的掌控，而且生成的内容无法溯源、无法验证逻辑。

我们要做的是另一件事：**把大模型重塑为交互式思维画板**。

- AI 帮用户搭骨架（发散思维、结构化论证）
- 用户自己定逻辑（挂文献、调顺序、补节点）
- 系统自动降维成学术论文（LaTeX 初稿）

数据的隐私留在本地显卡里，思考的掌控权留在作者手里。

---

## 二、核心工作流（四阶段）

### Phase 1 — 灵感发散：人给锚点，AI 延伸

用户面对空白文档不需要从头写。在思维导图画布中央建一个根节点，写下核心议题，点击 **"AI Expand"**。

AI 基于学术 Prompt 向外伸出几个标准分支节点。用户可以继续在任意节点上再点 Expand，层层展开。

```
用户输入："针对某工况的超前校正器设计优化"
        ↓ AI Expand
┌─ 系统建模
│   └─ 被控对象数学模型
├─ 稳定性分析
│   ├─ 频域响应分析（Bode Plot）
│   └─ 奈奎斯特判据
├─ 仿真验证
└─ 对比实验
```

**技术实现**：调用现有 `_tool_generate_outline`（`builtin.py:171`），改为输出 JSON 树结构。前端用 **Vue Flow** 渲染为可视化思维导图。

### Phase 2 — 证据绑定：知识库挂载（RAG 联动）

写论文最怕写着写着忘了逻辑出处。当用户选中某个节点细化内容时，系统通过 ChromaDB 检索本地知识库，主动弹出相关文献推荐。用户点击即可将文献"挂载"到该节点。

此时，节点不仅有文字，还有了**文献依据**。

**技术实现**：
- 前端 ContextObserver：Debounce 2s + 标点触发，只提取当前段落（不是全文）
- 后端 `/api/argument/observe`：纯 ChromaDB 相似度检索，**不调用 LLM**
- 余弦相似度 > 0.85 触发推荐，气泡提示"找到 N 篇相关文献"

**关键**：这一步完全不用大模型。纯本地 Python + ChromaDB，省算力、不卡顿。

### Phase 3 — 逻辑推演：规则引擎 + Agent 反馈生成（折中方案）

提供"一键审查逻辑连贯性"按钮。底层规则引擎做确定性结构性检查，Agent 只负责把诊断结果润色成自然语言反馈。

**两步流程**：
1. **规则引擎扫描**（毫秒级，确定性）— 快速识别节点树的结构性问题
2. **Agent 生成反馈文字**（受诊断结果约束）— 把结构化诊断润色为自然的学术语言

**反馈示例**：
> "您的仿真结果节点与前文的参数设定节点缺乏过渡，是否需要补充补偿器参数的推导过程？"

> "提及了补偿器设计，但未见系统稳定裕度（Phase Margin / Gain Margin）的仿真节点"

**规则引擎检查项**：

| 检查类型 | 说明 |
|----------|------|
| 链路完整性 | 经典论证链条是否存在（问题→建模→分析→验证→结论） |
| 术语定义 | 引入的术语是否在树中某节点定义过 |
| 引用闭环 | 挂载了文献的节点是否在下游有对应结论 |
| 逻辑跳跃 | 相邻节点间是否缺乏过渡节点 |
| 领域覆盖 | 根据 `domain_tags` 检查是否覆盖领域必备节点 |

**Agent 的职责**：只生成自然语言反馈，输出受规则引擎诊断结果的约束，不会跑偏。

**技术实现**：
- `python/src/argument/logic_checker.py` — 规则引擎，基于节点树结构做确定性扫描
- 规则扫描结果注入 prompt，Agent 负责把 dry 的诊断润色为学术语言
- Agent 的 thinking 过程展示给评委（保留"AI 在思考"的演示效果）

### Phase 4 — 降维展开：从思维导图到学术论文

当树状结构、节点逻辑和挂载的文献都确认无误后，系统沿着思维导图路径进行**降维展开**，把挂满了思想和文献的"树"编译成带引用格式的 LaTeX 初稿。

因为逻辑框架是用户自己定的，文献是用户自己绑的，所以这篇初稿**不会有幻觉，且完全契合用户意图**。

**技术实现**：沿树 DFS 顺序调用 `_tool_expand_section`（`builtin.py:180`），注入节点挂载的 references，用 Pandoc + `paper_assets/` 模板输出 LaTeX。

---

## 三、UI 设计

### 布局

右侧面板新增 Tab，和现有 AI Chat 并列：

```
右侧面板
├── Tab 1: AI Chat（现有）
└── Tab 2: Argument Map（新增）
```

Argument Map Tab 内部：

```
┌──────────────────────────────────────────┐
│  [AI Expand]  [审查逻辑]  [生成初稿]      │  ← 工具栏
├──────────────────────────────────────────┤
│                                          │
│        Vue Flow 思维导图画布              │
│                                          │
│          ┌─ 系统建模 ◉                  │
│          ├─ 稳定性分析 ◉                 │  ← ◉ = 已挂载文献
│          ├─ 仿真验证                     │
│          └─ 对比实验                     │
│                                          │
├──────────────────────────────────────────┤
│  📄 推荐文献: [Smith2023] [Zhang2024]    │  ← RAG 推荐区
└──────────────────────────────────────────┘
```

### 节点视觉状态

| 状态 | 颜色 | 含义 |
|------|------|------|
| 默认 | 白色 | 普通节点 |
| 已挂文献 | 蓝色边框 + 📎图标 | 有文献依据 |
| ⚠ Warning | 黄色 | 逻辑可能有断层 |
| ✅ Pass | 绿色 | 审查通过 |

### 技术选型

- **Vue Flow**（`@vue-flow/core`）— 可视化思维导图渲染
- 节点可拖拽、可折叠、可编辑
- 连线自动布局

---

## 四、数据结构

数据结构及所有字段定义见 **第五节 5.1 数据结构**。此处仅说明补充规则：

### domain_tags 赋值

- AI Expand 时自动打标（prompt 要求模型输出 tags）
- 用户可手动覆盖

### binding_type 枚举

| 值 | 含义 |
|----|------|
| `auto_suggested` | 系统推荐，用户确认 |
| `user_manual` | 用户手动挂载 |

---

## 五、API 设计

### 5.1 数据结构

#### ArgumentNode（思维导图节点）

```json
{
  "id": "node_7b9a",
  "parent_id": "node_3c2f",
  "topic": "稳定性分析",
  "content": "采用闭环控制架构，对超前校正器进行频域设计...",
  "depth": 2,
  "position": { "x": 400, "y": 300 },
  "domain_tags": ["control_theory", "frequency_domain"],
  "references": [
    {
      "doc_id": "chroma_doc_12",
      "citation_key": "Smith2023",
      "relevance_score": 0.88,
      "binding_type": "auto_suggested",
      "bound_at": "2026-04-25T10:30:00Z"
    }
  ],
  "logic_status": "warning",
  "rule_issues": ["MISSING_MARGIN_ANALYSIS"],
  "agent_feedback": "提及了补偿器设计，但未见系统稳定裕度（Phase Margin / Gain Margin）的仿真节点",
  "status": "expanded",
  "children": [],
  "created_at": "2026-04-25T09:00:00Z",
  "updated_at": "2026-04-25T10:30:00Z"
}
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 节点唯一 ID（格式：`node_` + 4 位随机字符串） |
| `parent_id` | string | 否 | 父节点 ID，根节点为空 |
| `topic` | string | 是 | 节点主题/标题（简短关键词） |
| `content` | string | 否 | 节点详细内容（展开后填充） |
| `depth` | integer | 是 | 树深度（根节点=0） |
| `position` | object | 是 | 画布坐标 `{x, y}` |
| `domain_tags` | string[] | 否 | 领域标签（AI Expand 时自动打标，用户可覆盖） |
| `references` | Reference[] | 否 | 挂载的文献列表 |
| `logic_status` | enum | 是 | 逻辑状态：`pass` / `warning` / `error` |
| `rule_issues` | string[] | 否 | 规则引擎识别的问题代码（如 `MISSING_MARGIN_ANALYSIS`） |
| `agent_feedback` | string | 否 | Agent 生成的自然语言反馈 |
| `status` | enum | 是 | 节点状态：`draft`（草稿）/ `expanded`（已展开）/ `final`（已定稿） |
| `children` | string[] | 是 | 子节点 ID 列表 |
| `created_at` | string | 是 | 创建时间（ISO 8601） |
| `updated_at` | string | 是 | 更新时间（ISO 8601） |

#### Reference（文献引用）

```json
{
  "doc_id": "chroma_doc_12",
  "citation_key": "Smith2023",
  "relevance_score": 0.88,
  "binding_type": "auto_suggested",
  "bound_at": "2026-04-25T10:30:00Z"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `doc_id` | string | 是 | ChromaDB 文档 ID |
| `citation_key` | string | 是 | 引用键（如 `Smith2023`） |
| `relevance_score` | float | 是 | 相关性得分（0.0–1.0） |
| `binding_type` | enum | 是 | `auto_suggested`（系统推荐）/ `user_manual`（用户手动） |
| `bound_at` | string | 是 | 绑定时间（ISO 8601） |

#### ArgumentTree（完整树）

```json
{
  "root_id": "node_root",
  "nodes": {
    "node_root": { ... },
    "node_3c2f": { ... },
    "node_7b9a": { ... }
  },
  "created_at": "2026-04-25T09:00:00Z",
  "updated_at": "2026-04-25T10:30:00Z"
}
```

#### RuleIssue（规则引擎诊断结果）

```json
{
  "issue_code": "MISSING_MARGIN_ANALYSIS",
  "severity": "warning",
  "node_ids": ["node_7b9a"],
  "related_nodes": ["node_3c2f"],
  "description": "提及了补偿器设计，但未见系统稳定裕度分析节点",
  "suggestion": "建议在补偿器设计节点下增加 Phase Margin / Gain Margin 分析子节点",
  "template": "提及了{topic}，但未见{required}节点"
}
```

**issue_code 枚举**：

| code | 含义 | severity |
|------|------|----------|
| `MISSING_CLASSIC_CHAIN` | 缺少经典论证链条节点 | warning |
| `MISSING_MARGIN_ANALYSIS` | 缺少稳定裕度分析 | warning |
| `UNDEFINED_TERM` | 引入未定义术语 | error |
| `ORPHAN_REFERENCE` | 文献引用无对应结论 | warning |
| `LOGIC_JUMP` | 相邻节点逻辑跳跃 | warning |
| `DOMAIN_GAP` | 领域必备节点缺失 | warning |

---

### 5.2 端点详细规格

#### 5.2.1 获取完整节点树

```
GET /api/argument/tree
```

**Response 200**：

```json
{
  "root_id": "node_root",
  "nodes": {
    "node_root": {
      "id": "node_root",
      "parent_id": null,
      "topic": "针对某工况的超前校正器设计优化",
      "content": "",
      "depth": 0,
      "position": { "x": 400, "y": 50 },
      "domain_tags": ["control_theory"],
      "references": [],
      "logic_status": "warning",
      "rule_issues": ["MISSING_CLASSIC_CHAIN"],
      "agent_feedback": null,
      "status": "draft",
      "children": ["node_3c2f", "node_8d1a", "node_2e5b"],
      "created_at": "2026-04-25T09:00:00Z",
      "updated_at": "2026-04-25T09:00:00Z"
    },
    "node_3c2f": { ... }
  },
  "created_at": "2026-04-25T09:00:00Z",
  "updated_at": "2026-04-25T10:30:00Z"
}
```

**Response 404**：`{ "detail": "Argument tree not found" }`

---

#### 5.2.2 创建/更新节点

```
PUT /api/argument/node
```

**Request Body**：

```json
{
  "topic": "稳定性分析",
  "parent_id": "node_3c2f",
  "content": "",
  "domain_tags": ["control_theory"],
  "position": { "x": 600, "y": 300 }
}
```

**Response 201**（创建）/ **200**（更新）：

```json
{
  "id": "node_7b9a",
  "parent_id": "node_3c2f",
  "topic": "稳定性分析",
  "content": "",
  "depth": 2,
  "position": { "x": 600, "y": 300 },
  "domain_tags": ["control_theory"],
  "references": [],
  "logic_status": "draft",
  "rule_issues": [],
  "agent_feedback": null,
  "status": "draft",
  "children": [],
  "created_at": "2026-04-25T11:00:00Z",
  "updated_at": "2026-04-25T11:00:00Z"
}
```

**Response 400**：`{ "detail": "Invalid parent_id" }`

---

#### 5.2.3 删除节点

```
DELETE /api/argument/node/{node_id}
```

**Query Parameters**：
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `cascade` | boolean | `false` | 是否递归删除子节点 |

**Response 200**：

```json
{
  "deleted": ["node_7b9a", "node_child1", "node_child2"],
  "message": "Deleted 3 nodes"
}
```

**Response 404**：`{ "detail": "Node not found" }`

---

#### 5.2.4 AI Expand（LLM 生成子节点）

```
POST /api/argument/expand
```

**Request Body**：

```json
{
  "node_id": "node_3c2f",
  "max_children": 4,
  "direction": "expand"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `node_id` | string | 是 | 要展开的节点 ID |
| `max_children` | integer | 否 | 最大子节点数（默认 4） |
| `direction` | enum | 否 | `expand`（向下展开）/ `refine`（深化当前节点），默认 `expand` |

**Response 200**：

```json
{
  "parent_id": "node_3c2f",
  "children": [
    {
      "id": "node_new1",
      "topic": "频域响应分析（Bode Plot）",
      "domain_tags": ["frequency_domain", "bode_plot"],
      "depth": 3,
      "position": { "x": 300, "y": 450 }
    },
    {
      "id": "node_new2",
      "topic": "奈奎斯特判据",
      "domain_tags": ["nyquist", "stability_criterion"],
      "depth": 3,
      "position": { "x": 500, "y": 450 }
    }
  ],
  "expanded_node": {
    "id": "node_3c2f",
    "status": "expanded",
    "updated_at": "2026-04-25T11:05:00Z"
  }
}
```

**技术实现**：复用 `_tool_generate_outline`（builtin.py），改 prompt 输出 JSON 树结构。

---

#### 5.2.5 ChromaDB 文献推荐（无 LLM）

```
POST /api/argument/observe
```

**Request Body**：

```json
{
  "node_id": "node_7b9a",
  "content_hint": "可选：当前节点内容片段，用于更精准检索"
}
```

**Response 200**：

```json
{
  "node_id": "node_7b9a",
  "recommendations": [
    {
      "doc_id": "chroma_doc_12",
      "citation_key": "Smith2023",
      "title": "Design of Feedback Control Systems",
      "authors": ["R. C. Smith"],
      "year": 2023,
      "relevance_score": 0.88,
      "excerpt": "...phase margin and gain margin are key indicators...",
      "match_type": "domain_tag"
    },
    {
      "doc_id": "chroma_doc_45",
      "citation_key": "Kuo1995",
      "title": "Automatic Control Systems",
      "authors": ["B. C. Kuo", "M. F. Golnaraghi"],
      "year": 1995,
      "relevance_score": 0.82,
      "excerpt": "...Bode plot technique for lead-lag compensation...",
      "match_type": "keyword"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `relevance_score` | float | ChromaDB 余弦相似度（阈值 > 0.85 才推荐） |
| `match_type` | enum | `domain_tag`（标签匹配）/ `keyword`（内容匹配） |

**技术实现**：纯 ChromaDB 检索，不调用 LLM。`match_type` 用于前端显示推荐来源。

---

#### 5.2.6 绑定文献到节点

```
POST /api/argument/bind
```

**Request Body**：

```json
{
  "node_id": "node_7b9a",
  "doc_id": "chroma_doc_12",
  "binding_type": "user_manual",
  "relevance_score": 0.88
}
```

**Response 200**：

```json
{
  "node_id": "node_7b9a",
  "reference": {
    "doc_id": "chroma_doc_12",
    "citation_key": "Smith2023",
    "relevance_score": 0.88,
    "binding_type": "user_manual",
    "bound_at": "2026-04-25T11:10:00Z"
  }
}
```

---

#### 5.2.7 逻辑审查（规则引擎 + Agent 生成反馈）

```
POST /api/argument/review
```

**Request Body**：

```json
{
  "node_id": "node_7b9a",
  "include_subtree": true
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `node_id` | string | 是 | 审查起始节点（传入 `root` 则审查全树） |
| `include_subtree` | boolean | `true` | 是否包含所有子节点 |

**Response 200**：

```json
{
  "reviewed_node_id": "node_root",
  "reviewed_subtree": ["node_root", "node_3c2f", "node_7b9a"],
  "overall_status": "warning",
  "rule_results": [
    {
      "issue_code": "MISSING_MARGIN_ANALYSIS",
      "severity": "warning",
      "node_ids": ["node_7b9a"],
      "related_nodes": [],
      "description": "提及了补偿器设计，但未见系统稳定裕度分析节点",
      "suggestion": "建议在补偿器设计节点下增加 Phase Margin / Gain Margin 分析子节点",
      "template": "提及了{topic}，但未见{required}节点"
    },
    {
      "issue_code": "DOMAIN_GAP",
      "severity": "warning",
      "node_ids": ["node_root"],
      "related_nodes": [],
      "description": "控制理论论文缺少仿真验证节点",
      "suggestion": "建议增加仿真验证节点，包括时域响应和频域响应验证",
      "template": null
    }
  ],
  "node_feedbacks": {
    "node_7b9a": {
      "logic_status": "warning",
      "rule_issues": ["MISSING_MARGIN_ANALYSIS"],
      "agent_feedback": "提及了补偿器设计，但未见系统稳定裕度（Phase Margin / Gain Margin）的仿真节点"
    },
    "node_3c2f": {
      "logic_status": "pass",
      "rule_issues": [],
      "agent_feedback": null
    }
  },
  "reviewed_at": "2026-04-25T11:15:00Z"
}
```

**技术实现**：
- **步骤 1**：规则引擎（`logic_checker.py`）对节点树做确定性扫描，返回 `rule_results`
- **步骤 2**：`feedback_generator.py` 注入 `rule_results`，Agent 生成 `node_feedbacks`

**前端使用**：
1. 根据 `node_feedbacks[node_id].logic_status` 设置节点颜色
2. 根据 `node_feedbacks[node_id].agent_feedback` 显示气泡提示

---

#### 5.2.8 降维展开（思维导图 → Markdown/LaTeX）

```
POST /api/argument/flatten
```

**Request Body**：

```json
{
  "node_id": "root",
  "template": "latex",
  "include_references": true,
  "style": "IEEE"
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `node_id` | string | `root` | 展开起始节点 |
| `template` | enum | `markdown` | `markdown` / `latex` / `docx` |
| `include_references` | boolean | `true` | 是否包含参考文献 |
| `style` | enum | `IEEE` | LaTeX 输出风格：`IEEE` / `ACM` / `NeurIPS` / `LNCS` / `Elsevier` |

**Response 200**：

```json
{
  "task_id": "flatten_task_abc123",
  "status": "processing"
}
```

**流式响应**（SSE）：

```
GET /api/argument/flatten/{task_id}/stream
```

**SSE 事件**：

```
event: node_processing
data: {"node_id": "node_3c2f", "status": "processing"}

event: node_complete
data: {"node_id": "node_3c2f", "word_count": 350}

event: reference_processing
data: {"count": 5, "total": 12}

event: complete
data: {"output_path": "/data/output/paper_draft.md", "word_count": 5200, "reference_count": 12}
```

**最终下载**：

```
GET /api/argument/download/{task_id}
```

**Response**：文件流（Content-Type 根据 template 设置）

---

#### 5.2.9 创建新思维导图（初始化）

```
POST /api/argument/tree
```

**Request Body**：

```json
{
  "topic": "针对某工况的超前校正器设计优化",
  "domain_tags": ["control_theory"],
  "position": { "x": 400, "y": 50 }
}
```

**Response 201**：

```json
{
  "root_id": "node_root",
  "nodes": {
    "node_root": {
      "id": "node_root",
      "topic": "针对某工况的超前校正器设计优化",
      "depth": 0,
      "status": "draft",
      "logic_status": "warning",
      "rule_issues": ["MISSING_CLASSIC_CHAIN"],
      ...
    }
  },
  "created_at": "2026-04-25T09:00:00Z"
}
```

---

#### 5.2.10 获取节点详情

```
GET /api/argument/node/{node_id}
```

**Response 200**：返回完整的 `ArgumentNode` 对象。

**Response 404**：`{ "detail": "Node not found" }`

---

#### 5.2.11 获取推荐文献列表

```
GET /api/argument/recommendations/{node_id}
```

返回该节点所有已挂载的文献列表（不触发新检索）。

**Response 200**：

```json
{
  "node_id": "node_7b9a",
  "references": [
    {
      "doc_id": "chroma_doc_12",
      "citation_key": "Smith2023",
      "title": "Design of Feedback Control Systems",
      "relevance_score": 0.88,
      "binding_type": "user_manual",
      "bound_at": "2026-04-25T10:30:00Z"
    }
  ]
}
```

---

#### 5.2.12 解绑文献

```
DELETE /api/argument/bind/{node_id}/{doc_id}
```

**Response 200**：

```json
 {
  "node_id": "node_7b9a",
  "doc_id": "chroma_doc_12",
  "message": "Reference unbound successfully"
}
```

---

### 5.3 错误响应格式

所有错误响应遵循以下格式：

```json
{
  "detail": "错误描述",
  "error_code": "NODE_NOT_FOUND",
  "timestamp": "2026-04-25T11:00:00Z"
}
```

**error_code 枚举**：

| code | HTTP 状态 | 说明 |
|------|-----------|------|
| `TREE_NOT_FOUND` | 404 | 思维导图树不存在 |
| `NODE_NOT_FOUND` | 404 | 节点不存在 |
| `DOC_NOT_FOUND` | 404 | 文献文档不存在 |
| `INVALID_PARENT` | 400 | 父节点 ID 无效（循环引用） |
| `TASK_NOT_FOUND` | 404 | 降维展开任务不存在 |
| `INTERNAL_ERROR` | 500 | 内部错误 |

---

### 5.4 前端-后端交互流程

#### 流程 A：用户新建思维导图

```
1. POST /api/argument/tree         → 创建根节点
2. GET  /api/argument/tree         → 获取完整树（前端渲染）
```

#### 流程 B：AI Expand

```
1. PUT  /api/argument/node          → 用户创建根节点（可选）
2. POST /api/argument/expand        → AI 生成子节点
3. PUT  /api/argument/node (xN)     → 用户编辑/确认子节点
4. GET  /api/argument/tree          → 刷新全树
```

#### 流程 C：文献绑定

```
1. POST /api/argument/observe       → 获取推荐文献（无 LLM）
2. POST /api/argument/bind          → 绑定文献到节点
3. GET  /api/argument/recommendations/{node_id}  → 查看已挂载文献
```

#### 流程 D：逻辑审查

```
1. POST /api/argument/review        → 规则引擎 + Agent 审查
2. GET  /api/argument/node/{node_id} → 获取单个节点详情（含反馈）
```

#### 流程 E：降维展开

```
1. POST /api/argument/flatten      → 提交降维任务
2. GET  /api/argument/flatten/{task_id}/stream  → SSE 进度流
3. GET  /api/argument/download/{task_id}         → 下载结果
```

---

## 六、与现有系统的复用关系

| 本方案需要 | 现有模块 | 复用方式 |
|-----------|---------|---------|
| AI 大纲生成 | `_tool_generate_outline`（builtin.py） | 改 prompt 输出 JSON |
| 文献检索 | `rag.py` RAGStore | 直接调用 `retrieve_context()` |
| 逻辑审查（底层） | **新增 `logic_checker.py`** | 规则引擎，不调用 LLM |
| 反馈文字生成 | `agent.py` ReAct 循环 | 注入规则诊断结果，Agent 只润色文字 |
| 段落扩写 | `_tool_expand_section`（builtin.py） | 沿树路径顺序调用 |
| LaTeX 输出 | `paper_assets/` 模板 + Pandoc | 直接复用 |
| 引用格式化 | `_tool_format_bibliography`（builtin.py） | 直接复用 |
| 知识库入库 | `/api/rag/upload` + 翻译自动入库 | 已实现 |
| 双引擎 | `cloud_client.py` + `ollama_client.py` | 直接复用 |

**真正要新写的**：
- `python/src/argument/` — 节点树 CRUD + 持久化
  - `logic_checker.py` — 确定性规则审查引擎（不调用 LLM，5 类检查项）
  - `feedback_generator.py` — Agent 包装器（基于规则诊断生成反馈文字）
- `src/components/ArgumentMap.vue` — Vue Flow 思维导图组件

---

## 七、演示策略（双引擎）

**现场演示**："云端演示，本地背书"

1. 后台开着 Ollama（11434 端口），评委看到本地大模型在跑
2. 前台连云端 API，展示流畅的 Expand + 审查效果
3. 准备 3 分钟纯本地离线录屏作为断网备用

**Fallback 链**：Cloud API → Ollama → 纯规则引擎（三层降级）

---

## 八、实施计划

| 天 | 后端 | 前端 |
|----|------|------|
| Day 1 | ArgumentNode 数据结构 + CRUD API | 安装 Vue Flow + 组件骨架 |
| Day 2 | `/api/argument/expand`（LLM JSON 输出） | 思维导图渲染 + 节点编辑 |
| Day 3 | `/api/argument/observe`（ChromaDB） | ContextObserver + 推荐气泡 |
| Day 4 | `logic_checker.py` 规则引擎 + `/api/argument/review` | 节点状态高亮 + 反馈气泡 |
| Day 5 | `/api/argument/flatten` + LaTeX | "生成初稿"按钮 |
| Day 6 | 联调 + 演示流程跑通 | 同左 |
| Day 7 | 打磨 + 备用录屏 | 同左 |

---

## 九、向评委讲的故事

> "传统的 AI 写作工具是'黑盒代写'，剥夺了研究者的思考权。而我们的系统，将大模型重塑为一个'交互式思维画板'。它通过 ReAct Agent 协助发散思维，通过本地 RAG 固化文献证据，最终将人类的逻辑树自动降维成排版精美的学术论文。在这个过程中，数据的隐私留在了本地显卡里，而思考的掌控权始终留在了作者手里。"
