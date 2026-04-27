# Scholar Assistant 前端对接文档 v0.5.0

本文档说明后端新增接口，供前端开发参考。

---

## 1. 图片上传与展示

### 接口 1：上传图片
```
POST /api/upload/image
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | File | 图片文件 (PNG/JPG/GIF/WebP/BMP) |

**响应**
```json
{
  "path": "D:/.../data/assets/abc123.png",
  "filename": "abc123.png",
  "url": "/api/assets/abc123.png",
  "size": 37142
}
```

### 接口 2：访问图片
```
GET /api/assets/{filename}
```

返回图片文件，Content-Type 根据扩展名自动设置。

### 前端示例
```typescript
async function uploadImage(file: File): Promise<string | null> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const formData = new FormData()
  formData.append('file', file)

  const resp = await fetch(`${API}/api/upload/image`, {
    method: 'POST',
    body: formData,
  })

  if (!resp.ok) return null
  const { url } = await resp.json()
  return url  // "/api/assets/abc123.png"
}

// 在 Markdown 中插入图片
function insertImage(url: string, alt: string = 'image') {
  editor.executeEdits({
    text: `\n![${alt}](${url})\n`
  })
}
```

---

## 2. MCP Vision 图像分析

### 接口 1：通用图像分析（OCR + 理解）
```
POST /api/vision/analyze
Content-Type: multipart/form-data
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | File | 图片文件 |
| `analysis_type` | string | 分析类型（见下方）|

**analysis_type 选项：**
- `general`: 通用描述 + 文字识别
- `chart`: 图表分析（柱状图、折线图、饼图等）
- `table`: 表格提取
- `formula`: 公式识别

**响应**
```json
{
  "text": "这是一个柱状图，显示了2020-2024年的销售数据...",
  "chart_type": "bar",
  "chart_description": "年度销售趋势...",
  "table_data": [["年份", "销售额"], ["2020", "100万"], ...],
  "key_findings": ["2024年销售额最高", "年增长率约15%"],
  "raw_description": "完整API返回内容"
}
```

### 接口 2：专用 OCR
```
POST /api/vision/ocr
```
识别图片中的文字

### 接口 3：图表分析
```
POST /api/vision/chart
```
分析柱状图、折线图、饼图等

### 接口 4：表格提取
```
POST /api/vision/table
```
从图片中提取表格数据

### 前端示例
```typescript
async function ocrImage(file: File): Promise<string> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const formData = new FormData()
  formData.append('file', file)

  const resp = await fetch(`${API}/api/vision/ocr`, {
    method: 'POST',
    body: formData,
  })

  const data = await resp.json()
  return data.text  // 识别的文字
}

async function analyzeChart(file: File): Promise<any> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const formData = new FormData()
  formData.append('file', file)

  const resp = await fetch(`${API}/api/vision/chart`, {
    method: 'POST',
    body: formData,
  })

  return await resp.json()
}

// Agent 集成：图片发给 Agent 理解
async function analyzeForAgent(file: File): Promise<string> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const formData = new FormData()
  formData.append('file', file)
  formData.append('analysis_type', 'general')

  const resp = await fetch(`${API}/api/vision/analyze`, {
    method: 'POST',
    body: formData,
  })

  const data = await resp.json()
  // 返回描述，让 Agent 理解图片内容
  return `图片描述: ${data.text}\n图表类型: ${data.chart_type || '无'}\n关键发现: ${data.key_findings?.join('; ') || '无'}`
}
```

---

## 3. 文献引用索引

### 接口 1：处理文献引用
```
PUT /api/citation/index
```

**请求体**
```json
{
  "content": "根据 [@smith2020] 的研究...参见 [@jones2021, p.123]...",
  "bibliography": [
    {"key": "smith2020", "author": "Smith, J.", "title": "Deep Learning", "year": "2020"},
    {"key": "jones2021", "author": "Jones, A.", "title": "AI Advances", "year": "2021"}
  ],
  "style": "ieee"
}
```

**响应**
```json
{
  "text": "根据 [1] 的研究...参见 [2, p.123]...",
  "citations": [
    {"key": "smith2020", "number": 1, "raw_citation": "[@smith2020]", "found": true},
    {"key": "jones2021", "number": 2, "raw_citation": "[@jones2021, p.123]", "found": true}
  ],
  "index": {"smith2020": 1, "jones2021": 2},
  "bibliography": "\n---\n\n## 参考文献\n[1] Smith, J. \"Deep Learning.\" ...\n[2] Jones, A. \"AI Advances.\" ..."
}
```

### 接口 2：提取引用（预览）
```
GET /api/citation/extract?content=根据[@smith2020]的研究...
```

**响应**
```json
{
  "keys": ["smith2020"],
  "unique_count": 1,
  "index": {"smith2020": 1}
}
```

### 前端示例
```typescript
async function processCitations(content: string): Promise<any> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const resp = await fetch(`${API}/api/citation/index`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      bibliography: [],  // 或传入 BibTeX 文献库
      style: 'ieee',
    })
  })
  return await resp.json()
}

// 预览有多少引用
async function previewCitations(content: string) {
  const API = isTauri ? 'http://localhost:18088' : ''
  const resp = await fetch(`${API}/api/citation/extract?content=${encodeURIComponent(content)}`)
  const data = await resp.json()
  return `${data.unique_count} 个引用将被编号`
}
```

---

## 4. 表格插入

### 前端实现建议

使用 markdown-table-editor 或手写简单版：

```typescript
function insertTable(rows: number, cols: number) {
  const header = '| ' + Array(cols).fill('列标题').join(' | ') + ' |'
  const separator = '| ' + Array(cols).fill('---').join(' | ') + ' |'
  const emptyRows = Array(rows - 1).fill(0).map(
    () => '| ' + Array(cols).fill('').join(' | ') + ' |'
  ).join('\n')

  const table = [header, separator, emptyRows].join('\n')
  editor.executeEdits({ text: `\n${table}\n` })
}

// 示例：插入 3x3 表格
insertTable(3, 3)
```

---

## 5. 公式编辑器

### 前端实现建议

使用 `@hirthtalk/katex-editor` 或 `mathlive`：

```typescript
// 插入行内公式
function insertInlineFormula() {
  editor.executeEdits({ text: '$' })
  // 用户输入公式内容
}

// 插入块级公式
function insertBlockFormula() {
  editor.executeEdits({ text: '\n$$\n\n$$\n' })
}

// KaTeX 已在 MarkdownPreview.vue 中配置
// 显示时自动渲染
```

---

## 6. Agent 对话增强 — 支持选中文本和追加约束

### 现有接口
```
POST /api/chat
```

### 请求体变化（新增字段）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | string | ✅ | 用户消息 |
| `history` | array | ❌ | 最近对话历史 [{role, content}] |
| `context_text` | string | ❌ | 引用上下文（选中文本、文档片段等） |
| `constraints` | string | ❌ | 追加约束（格式/风格/字数限制等） |

### 示例请求

```json
POST /api/chat
{
  "message": "这段代码有什么问题？",
  "history": [
    {"role": "user", "content": "帮我优化这个函数"},
    {"role": "assistant", "content": "好的，请把代码发过来"}
  ],
  "context_text": "def hello():\n    print('world')\n    return None",
  "constraints": "请用中文回答，控制在200字以内，指出语法和风格问题"
}
```

### 前端改动建议

`useAgentChat.ts` 中 `sendMessage` 函数增加两个可选参数：

```typescript
async function sendMessage(
  text: string,
  contextText?: string,
  constraints?: string
): Promise<void>

// 调用示例
sendMessage(
  "这段代码有什么问题？",
  editor.getSelectedText(),    // 选中的代码或文本
  "请用中文回答，控制在200字以内"
)
```

请求体改为：
```typescript
body: JSON.stringify({
  message: text.trim(),
  history,
  context_text: contextText || undefined,
  constraints: constraints || undefined,
})
```

---

## 7. Agent 特殊元素理解与处理

### Agent 内置工具

Agent 现在能够理解和处理 Markdown 中的特殊元素：

| 工具名称 | 功能 |
|---------|------|
| `analyze_markdown_elements` | 分析文档中的特殊元素，返回结构化摘要 |
| `analyze_image_with_vision` | 使用 Vision API 理解图片内容（需要云端 API Key） |
| `analyze_chart_image` | 分析图表图片，提取数据趋势 |
| `parse_table_structure` | 解析 Markdown 表格为结构化数据 |
| `generate_table_markdown` | 从结构化数据生成 Markdown 表格 |
| `format_latex_formula` | 格式化 LaTeX 公式 |
| `get_citation_context` | 获取文献引用的上下文 |

### 前端集成示例

```typescript
// 1. 让 Agent 理解文档中的图片
// 用户在聊天框输入："帮我描述这张图的内容"
async function chatWithImageContext(message: string, imagePath: string) {
  // Agent 会自动调用 analyze_image_with_vision 工具
  // 图片路径通过 context_text 传递
  const resp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context_text: `[图片路径: ${imagePath}]`
    })
  })
  // 处理 SSE 流式响应...
}

// 2. 让 Agent 理解和修改表格
// 用户在聊天框输入："在第二列添加合计行"
async function chatWithTableContext(message: string, tableMarkdown: string) {
  const resp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context_text: `【表格内容】\n${tableMarkdown}`
    })
  })
  // Agent 会调用 parse_table_structure 和 generate_table_markdown
  // 返回修改后的表格
}

// 3. 让 Agent 理解图表数据
// 用户在聊天框输入："这张柱状图的趋势是什么？"
async function chatWithChartContext(message: string, chartPath: string) {
  const resp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context_text: `[图表路径: ${chartPath}]`
    })
  })
  // Agent 会调用 analyze_chart_image 获取图表分析结果
}

// 4. 让 Agent 理解引用文献
// 用户在聊天框输入："[@smith2020] 这篇论文的主要贡献是什么？"
async function chatWithCitation(message: string, documentText: string) {
  const resp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context_text: documentText  // 包含 [@smith2020] 引用的文档
    })
  })
  // Agent 会调用 get_citation_context 获取引用上下文
}
```

### Vision API 集成

Agent 可以调用 Vision API 分析图片内容：

```
用户: "这张图显示了什么？"
Agent: [调用 analyze_image_with_vision]
      ↓
后端调用 GPT-4o Vision / Claude Vision
      ↓
返回: "这是一张柱状图，显示了2020-2024年的销售额趋势，
      2024年销售额最高达到1000万元，同比增长15%"
```

### 前端触发图片分析

如果需要前端主动触发图片分析，可以：

```typescript
// 方案1：通过 Agent 对话
async function askAboutImage(question: string, imageFile: File) {
  // 先上传图片
  const formData = new FormData()
  formData.append('file', imageFile)
  const uploadResp = await fetch(`${API}/api/upload/image`, {
    method: 'POST',
    body: formData
  })
  const { path } = await uploadResp.json()

  // 通过 Agent 提问
  const chatResp = await fetch(`${API}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: question,
      context_text: `图片路径: ${path}`
    })
  })
  return chatResp
}

// 方案2：直接调用 Vision API
async function directVisionAnalysis(imageFile: File, type: string = 'general') {
  const formData = new FormData()
  formData.append('file', imageFile)
  formData.append('analysis_type', type)

  const resp = await fetch(`${API}/api/vision/analyze`, {
    method: 'POST',
    body: formData
  })
  return await resp.json()
}
```

---

## 8. Word 导出

### 接口 1：生成 .docx 文件
```
POST /api/export/word
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `content` | string | ✅ | Markdown 格式文本 |
| `title` | string | ❌ | 文档标题（默认 "Scholar Assistant Export"） |

**示例请求**
```json
POST /api/export/word
{
  "content": "# 标题\n\n这是一个**加粗**段落。\n\n## 二级标题\n\n- 列表项1\n- 列表项2",
  "title": "我的论文翻译"
}
```

**响应**
```json
{
  "path": "D:/.../data/output/export_a1b2c3d4.docx",
  "filename": "export_a1b2c3d4.docx",
  "size": 37142
}
```

### 接口 2：下载文件
```
GET /api/export/word/{filename}
```

参数 `filename` 为接口1返回的 `filename` 字段值。

**前端实现示例** (`useEditor.ts`)

```typescript
async function exportToWord(): Promise<string | null> {
  const API = isTauri ? 'http://localhost:18088' : ''
  const resp = await fetch(`${API}/api/export/word`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content: content.value,
      title: activeTab.value?.name || '导出文档'
    })
  })

  if (!resp.ok) return '导出失败'

  const { filename } = await resp.json()
  // 触发下载（方案1：直接跳转）
  window.location.href = `${API}/api/export/word/${filename}`

  // 或方案2：新窗口打开
  // window.open(`${API}/api/export/word/${filename}`)

  return null
}
```

**支持格式**
- 标题层级：`#` → 一级标题，`##` → 二级标题，`###` → 三级标题
- 加粗/斜体/代码：`**加粗**`、`*斜体*`、`\`行内代码\``
- 引用块：`> 引用文字`
- 列表：`- 无序列表`、`1. 有序列表`
- 代码块：``` ```代码``` ```
- 链接：`[文本](url)` 保留文本，超链接可选保留

---

## 3. 参考文献格式化（Agent 内置工具）

**无需前端改动**。Agent 已内置 `format_bibliography` 工具。

用户只需在 Agent 聊天框输入 BibTeX 条目并指定格式：

```
帮我把这篇 bibtex 格式化成 IEEE 引用格式：
@article{smith2020,
  author = {Smith, John},
  title = {Deep Learning Advances},
  journal = {AI Journal},
  year = {2020},
  volume = {10},
  pages = {1-15}
}
```

**支持的格式**：ieee / apa / gbt7714（国标）/ mla

---

## 7. 全部 API 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ollama/status` | Ollama 状态 |
| `GET` | `/api/cloud/status` | 云端 API 状态 |
| `GET` | `/api/cloud/providers` | 云端供应商列表 |
| `POST` | `/api/translate` | 上传文档翻译 |
| `POST` | `/api/translate/path` | 指定路径翻译 |
| `GET` | `/api/translate/{task_id}/stream` | SSE 进度流 |
| `GET` | `/api/download/{task_id}` | 下载翻译结果 |
| `GET/PUT` | `/api/config` | 读写配置 |
| `POST` | `/api/chat` | Agent 对话（SSE 流式） |
| `GET` | `/api/rag/documents` | RAG 文档列表 |
| `DELETE` | `/api/rag/documents/{doc_id}` | 删除 RAG 文档 |
| `POST` | `/api/rag/ingest` | 入库 RAG 文档 |
| `GET` | `/api/agent/stats` | Agent 统计信息 |
| `POST` | `/api/export/word` | Markdown → Word |
| `GET` | `/api/export/word/{filename}` | 下载 Word 文件 |
| `POST` | `/api/upload/image` | 上传图片 |
| `GET` | `/api/assets/{filename}` | 访问图片资源 |
| `POST` | `/api/vision/analyze` | MCP Vision 图像分析 |
| `POST` | `/api/vision/ocr` | OCR 文字识别 |
| `POST` | `/api/vision/chart` | 图表分析 |
| `POST` | `/api/vision/table` | 表格提取 |
| `PUT` | `/api/citation/index` | 文献引用索引处理 |
| `GET` | `/api/citation/extract` | 提取引用（预览） |
| `GET` | `/api/zotero/status` | Zotero 连接状态 |
| `POST` | `/api/zotero/search` | 搜索 Zotero 文献库 |
| `GET` | `/api/zotero/item/{key}` | 获取文献详情 |
| `GET` | `/api/zotero/item/{key}/bibtex` | 导出 BibTeX |
| `POST` | `/api/zotero/export` | 批量导出 BibTeX |
| `POST` | `/api/zotero/citations` | 获取多条文献引用 |

---

## 9. Zotero 文献管理

### 配置说明

在 `config/default.yaml` 中添加：

```yaml
zotero:
  api_key: "your-api-key"      # 从 https://www.zotero.org/settings/keys 获取
  user_id: "1234567"           # 你的 Zotero User ID
  style: "ieee"                # 引用格式: ieee/apa/gbt7714
```

### API 接口

#### 检查连接状态
```
GET /api/zotero/status
```
返回:
```json
{
  "connected": true,
  "user_id": "1234567",
  "style": "ieee"
}
```

#### 搜索文献
```
POST /api/zotero/search
```
请求体:
```json
{
  "query": "deep learning",
  "item_type": "journalArticle",  // 可选
  "limit": 20                     // 默认20
}
```
返回:
```json
{
  "count": 2,
  "items": [
    {
      "key": "ABC123",
      "citation_key": "smith2020",
      "title": "Deep Learning Advances",
      "authors": ["Smith, John"],
      "year": "2020",
      "journal": "AI Journal",
      "markdown_citation": "[@smith2020]"
    }
  ]
}
```

#### 获取文献详情
```
GET /api/zotero/item/{key}
```

#### 导出 BibTeX
```
GET /api/zotero/item/{key}/bibtex
```
返回:
```json
{
  "key": "ABC123",
  "bibtex": "@article{smith2020,\n  title = {Deep Learning},\n  ...\n}"
}
```

### 前端集成示例

```typescript
// 1. 检查 Zotero 连接状态
async function checkZoteroStatus() {
  const resp = await fetch(`${API}/api/zotero/status`)
  const data = await resp.json()
  if (!data.connected) {
    showSetupMessage("请配置 Zotero API Key")
  }
}

// 2. 搜索文献
async function searchZotero(query: string) {
  const resp = await fetch(`${API}/api/zotero/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit: 20 })
  })
  const { items } = await resp.json()
  return items
}

// 3. 选择文献并插入引用
async function insertCitation(itemKey: string) {
  const resp = await fetch(`${API}/api/zotero/item/${itemKey}`)
  const item = await resp.json()
  // 插入 Markdown 引用格式
  editor.executeEdits({
    text: item.markdown_citation
  })
}

// 4. 文献选择器组件示例
function ZoteroSearch({ onSelect }: { onSelect: (item: any) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])

  async function handleSearch() {
    const items = await searchZotero(query)
    setResults(items)
  }

  return (
    <div class="zotero-search">
      <input value={query} onChange={e => setQuery(e.target.value)} />
      <button onClick={handleSearch}>搜索</button>
      <div class="results">
        {results.map(item => (
          <div key={item.key} onClick={() => onSelect(item)}>
            <strong>{item.title}</strong>
            <span>{item.authors?.join(', ')}</span>
            <span>{item.year}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

### 支持的文献类型

| Zotero 类型 | BibTeX 类型 |
|-------------|-------------|
| journalArticle | @article |
| book | @book |
| bookSection | @incollection |
| conferencePaper | @inproceedings |
| thesis | @phdthesis |
| report | @techreport |
| webpage | @misc |

---

## 10. 注意事项

- Agent 对话的 `context_text` 和 `constraints` 字段是**可选**的，现有调用完全兼容
- Word 导出文件**30 分钟后自动过期**，前端应及时触发下载
- 所有 API 端口：**开发环境 18088**，通过 Tauri 运行时自动代理
- MCP Vision 需要配置云端 API Key 才能使用图像分析功能
- 图片上传大小限制：**50MB**；MCP Vision 分析限制：**20MB**
- Zotero 需要配置 API Key 和 User ID 才能使用