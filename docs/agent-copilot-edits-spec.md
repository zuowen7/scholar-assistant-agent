# Agent Copilot Edits — 内联 diff 接受/拒绝 规格

## 目标

Agent 修改打开论文时，用户能在编辑器中看到每个改动的 diff，像 Copilot 一样逐条接受或拒绝。

## 当前痛点

Agent 通过 `write_file`/`str_replace` 直接修改文件 → `reloadOpenTabs()` 刷新 → 用户不知道改了什么、无法撤销单个改动。已有的 `await_approval` 只在 AgentPanel 显示文字，编辑器里看不到改动。

## 核心流程

```
用户: "帮我把第三段扩写成 300 字"
  → Agent 调 str_replace(file, old_string, new_string)
  → SecurityGate → DESTRUCTIVE → send await_approval SSE (含 diff preview)
  → 前端收到 event:
      1. Monaco 定位到改动行
      2. 用 decorations 高亮改动区域（红色删除、绿色新增）
      3. 弹出内联悬浮按钮 [ Accept ] [ Reject ]
  → 用户点 Accept → POST /approve(allow_once) → 工具执行 → 编辑器刷新
  → 用户点 Reject  → POST /approve(deny)     → 工具调用取消
```

## 改动范围

### 后端 (2 files)

#### `security_gate.py` — `_classify_write_file` / `_classify_str_replace`
在 `await_approval` 的 `preview` 字段中附带到 diff 信息：
```python
# 当前: preview 为空或只有简单 summary
# 改为: preview = {
#   "type": "str_replace" | "write_file",
#   "file_path": "...",
#   "old_text": "...",        # str_replace 的 old_string（前 500 字符）
#   "new_text": "...",        # str_replace 的 new_string / write_file 的 content
#   "old_line_count": N,
#   "new_line_count": N,
# }
```

#### `session.py` — `_handle_tool_call_approval`
在构造 `await_approval` SSE 事件时，从 `GateResult` 提取 preview 信息注入到 event metadata。
- 已有字段 `preview` 在 `GateResult` 中，确保传到前端的 `metadata.preview` 包含 diff 数据。
- `write_file` 场景：preview 传全文 content（前端以文件 diff 方式展示）
- `str_replace` 场景：preview 传 old_string + new_string + 前后上下文

### 前端 (5 files)

#### 1. `useEditorState.ts` — 新增状态
```ts
// 待处理的编辑建议
interface PendingEdit {
  editId: string
  eventId: string           // 对应 await_approval 的 event_id
  sessionId: string
  operation: 'str_replace' | 'write_file'
  filePath: string
  oldText: string
  newText: string
  decorations: string[]     // Monaco decoration IDs（用于清除）
}
const pendingEdits = ref<PendingEdit[]>([])
const activeEditId = ref<string | null>(null)  // 当前查看的建议

function addPendingEdit(e: PendingEdit): void
function removePendingEdit(editId: string): void
function clearPendingEdits(): void
```

#### 2. `useEditor.ts` — 新增方法
```ts
// 在编辑器中显示 diff 建议
function showDiffSuggestion(edit: PendingEdit): void {
  // 1. 用 Monaco decorations 高亮 oldText 区域（红色背景）
  // 2. 在改动区域下方插入 ghost/inline view 显示 newText（绿色背景）
  // 3. 在改动区域末尾添加悬浮接受/拒绝按钮
  // 复用 applyInlineDecoration 的 decoration 模式
}

function acceptSuggestion(editId: string): void {
  // POST /approve(allow_once) → 后端执行改动 → 编辑器刷新
}

function rejectSuggestion(editId: string): void {
  // POST /approve(deny) → 取消改动 → 移除 decorations
}
```

#### 3. `MonacoEditor.vue` — 渲染 Diff Decorations
新增：
- `suggestionDecorations: string[]` — 当前建议的 decoration IDs
- 为每个 pending edit 渲染两种 decoration：
  - **删除区域** (red)：`className: 'ai-diff-deleted'`，覆盖 old_text 范围
  - **新增区域** (green)：`after: { content: new_text, className: 'ai-diff-inserted' }` 或独立的 ghost line
- 在改动区域下方用 `contentWidget` 或 `overlayWidget` 显示 [ Accept ] [ Reject ] 按钮

CSS 新增：
```css
.ai-diff-deleted { background: color-mix(in srgb, var(--c-danger) 25%, transparent); border-bottom: 2px wavy var(--c-danger); }
.ai-diff-inserted { background: color-mix(in srgb, var(--c-success) 25%, transparent); border-bottom: 2px solid var(--c-success); }
.ai-diff-widget { /* Copilot 风格的浮动操作栏 */ }
```

#### 4. `AgentPanel.vue` — 接管道
在 `createEventHandler` 中新增：
```ts
case 'await_approval': {
  const toolName = meta?.tool_name as string
  const preview = meta?.preview as Record<string, unknown> | undefined
  // 如果是对编辑器打开文件的 str_replace/write_file，转为编辑器 diff
  if (preview && (toolName === 'str_replace' || toolName === 'write_file')) {
    const filePath = preview.file_path as string
    // 检查该文件是否在编辑器打开
    const isOpen = tabs.find(t => t.path === filePath || t.name === filePath)
    if (isOpen) {
      // 不显示 AgentPanel 文字审批，改为编辑器内 diff
      showDiffSuggestion({
        editId: eventId,
        eventId,
        sessionId: sessionId.value,
        operation: toolName,
        filePath,
        oldText: preview.old_text as string,
        newText: preview.new_text as string,
      })
      return  // 不在 AgentPanel 显示通用审批
    }
  }
  // 其他工具（run_command, web_search 等）走原来的 GeneralPanel 审批
  _setApproval({...})
  break
}
```

#### 5. `useAgentChat.ts` — 小调整
`sendApproval` 改为接受一个可选 callback，批准后通知 `useEditor.removePendingEdit()`。

### 跨层协定：SSE Event 格式

`await_approval` 事件新增 `metadata.preview` 字段：
```json
{
  "type": "await_approval",
  "event_id": "evt_xxx",
  "metadata": {
    "tool_name": "str_replace",
    "args": {"file_path": "paper.md", "old_string": "...", "new_string": "..."},
    "risk": "destructive",
    "reason": "SmartPause: str_replace deletes 5 lines",
    "force_approval": true,
    "preview": {
      "type": "str_replace",
      "file_path": "paper.md",
      "old_text": "被替换的原文（前 800 字符）",
      "new_text": "替换后的新文（前 800 字符）",
      "old_range": {"startLine": 10, "endLine": 14},
      "new_line_count": 7
    }
  }
}
```

`old_range` 由后端通过 workspace 文件搜索 `old_string` 定位（或由 `str_replace` 工具执行前搜索返回）。

### Monaco Inline Widget 细节

不使用 Monaco 的 `diffEditor`（它需要两个 model），而是用 `IOverlayWidget` 在当前 editor 内浮动显示 diff。

参考 VS Code Copilot Inline Chat 的布局：
```
  原文行 1
  原文行 2         ← red 背景（即将删除）
  ┌─────────────────────────────────┐
  │ 建议新文本 行 1                  │  ← green 背景（新增预览）
  │ 建议新文本 行 2                  │
  │ 建议新文本 行 3                  │
  │           [ Accept ] [ Reject ] │  ← 浮动按钮
  └─────────────────────────────────┘
  原文行 5         ← 未被改动
  原文行 6
```

技术实现：
- 删除区域用 `deltaDecorations` + `className: 'ai-diff-deleted'`
- 新增区域用 `contentWidget` 插入在删除区域下方，渲染预览文本和操作按钮
- 也考虑用 `after` decoration + `inlineClassName` 做简单版（只适合单行改动）

## 实施顺序

### Phase A — 后端预览数据 (半天)
1. `security_gate.py`: `_classify_write_file` / `_classify_str_replace` 填充 `preview` 字段
2. `session.py`: 确保 `await_approval` metadata 包含 preview
3. 验证：curl 看 SSE 事件中 preview 数据正确

### Phase B — 编辑器状态 (半天)
1. `useEditorState.ts`: 新增 `pendingEdits` state
2. `useEditor.ts`: `showDiffSuggestion` / `acceptSuggestion` / `rejectSuggestion`
3. 验证：单测 + 手动注入数据看 state 变化

### Phase C — Monaco 渲染 (1天)
1. `MonacoEditor.vue`: decorations + contentWidget + Accept/Reject 按钮
2. CSS: diff 配色（适配深色/浅色主题）
3. 验证：手动触发 showDiffSuggestion 看视觉效果

### Phase D — 接管道 (半天)
1. `AgentPanel.vue` / `useAgentChat.ts`: 对接 `await_approval` → `showDiffSuggestion`
2. 审批后清理 decorations
3. 验证：完整端到端跑一遍

---

## 不变更清单

- 不引入新的 Agent 工具（复用 `str_replace` / `write_file`）
- 不修改 Agent ReAct 循环逻辑
- 不影响非文件编辑场景的 `await_approval`（通用审批照常走）
- 不修改 `/api/edit` 端点（预设润色/翻译保持聊天面板展示）
- 不破坏现有的 auto_approve 模式（force_approval 场景仍触发审批）

---

> 最后更新: 2026-06-01
> 状态: 设计阶段，待实现
