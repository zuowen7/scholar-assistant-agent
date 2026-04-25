<template>
  <div class="monaco-wrapper">
    <div ref="editorContainer" class="monaco-container"></div>
    <CommandPalette
      v-if="showPalette"
      :position="palettePos"
      :loading="editLoading"
      :selected-text="selectedText"
      @submit="handlePaletteSubmit"
      @cancel="showPalette = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import CommandPalette from './CommandPalette.vue'
import { useEditor } from '../composables/useEditor'
import { API_BASE } from '../utils/api'

// 配置 Monaco Web Worker（解决 Tauri 环境下 worker 无法创建的问题）
self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker()
  },
}

const props = defineProps<{
  theme?: 'vs-dark' | 'vs'
}>()

const editorContainer = ref<HTMLElement>()
const {
  setEditorInstance, setContent, content, updateSelection,
  activeTabId, markDirty, aiEdit, openNewUntitled,
} = useEditor()

let editor: monaco.editor.IStandaloneCodeEditor | null = null

// Ctrl+K Palette
const showPalette = ref(false)
const COMPLETE_API = API_BASE
const palettePos = ref({ x: 200, y: 200 })
const selectedText = ref('')
const editLoading = ref(false)

// Ghost text 状态（模块级别，供 onBeforeUnmount 访问）
let ghostDebounceTimer: ReturnType<typeof setTimeout> | null = null
let ghostDecoration: string[] = []
let ghostText = ''
let lastGhostTrigger = 0

onMounted(() => {
  if (!editorContainer.value) return

  editor = monaco.editor.create(editorContainer.value, {
    value: content.value,
    language: 'markdown',
    theme: props.theme || 'vs-dark',
    wordWrap: 'on',
    minimap: { enabled: true },
    fontSize: 14,
    lineHeight: 22,
    fontFamily: "'Consolas', 'Courier New', monospace",
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    padding: { top: 16, bottom: 16 },
    automaticLayout: true,
    tabSize: 2,
    suggestOnTriggerCharacters: true,
    quickSuggestions: { other: true, comments: false, strings: false },
    inlineSuggest: { enabled: true, mode: 'subword' },
    parameterHints: { enabled: true },
    acceptSuggestionOnEnter: 'on',
  })

  // ── 注册 AI Inline Completions Provider ──────────────────────
  // 让 Monaco 的内联补全直接走 AI 补全 API，实现 VS Code/Cursor 风格
  monaco.languages.registerInlineCompletionsProvider('markdown', {
    provideInlineCompletions: async (model, position, _context) => {
      if (showPalette.value) return { items: [] }
      const lineContent = model.getLineContent(position.lineNumber)
      const isAtLineEnd = position.column >= lineContent.length
      if (!isAtLineEnd) return { items: [] }

      const ctx = lineContent.slice(0, position.column - 1)
      if (ctx.length < 5) return { items: [] }

      try {
        const resp = await fetch(`${COMPLETE_API}/api/complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context: ctx, max_tokens: 128 }),
          signal: AbortSignal.timeout(5000),
        })
        if (!resp.ok) return { items: [] }
        const data = await resp.json()
        const completion = (data as { completion?: string }).completion || ''
        if (!completion) return { items: [] }

        return {
          items: [{
            insertText: completion,
            range: new monaco.Range(
              position.lineNumber, position.column,
              position.lineNumber, position.column,
            ),
          }],
        }
      } catch {
        return { items: [] }
      }
    },
    disposeInlineCompletions: () => {},
  })

  setEditorInstance(editor)

  editor.onDidChangeModelContent(() => {
    if (!editor) return
    setContent(editor.getValue())
    markDirty()
  })

  editor.onDidChangeCursorSelection(() => {
    if (!editor) return
    // 光标移动时清除 ghost text（用户移开光标）
    clearGhost()
    const sel = editor.getSelection()
    if (!sel) return
    const text = editor.getModel()?.getValueInRange(sel) || ''
    selectedText.value = text
    updateSelection({
      startLine: sel.startLineNumber,
      endLine: sel.endLineNumber,
      startCol: sel.startColumn,
      endCol: sel.endColumn,
      text,
    })
  })

  // Ctrl+K → AI Edit
  editor.addAction({
    id: 'ai-edit',
    label: 'AI Edit',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK],
    run: () => {
      if (!editor) return
      const sel = editor.getSelection()
      if (!sel) return
      const text = editor.getModel()?.getValueInRange(sel) || ''

      // 没选中文字时，选中当前整行
      if (!text) {
        editor.setSelection(new monaco.Range(
          sel.startLineNumber, 1,
          sel.startLineNumber, editor.getModel()!.getLineMaxColumn(sel.startLineNumber),
        ))
        const newSel = editor.getSelection()!
        selectedText.value = editor.getModel()?.getValueInRange(newSel) || ''
      } else {
        selectedText.value = text
      }

      if (!selectedText.value) return

      // 浮窗位置：屏幕中间偏上
      palettePos.value = {
        x: Math.max(100, window.innerWidth / 2 - 200),
        y: 80,
      }
      showPalette.value = true
      console.log('[AI Edit] palette opened, text length:', selectedText.value.length)
    },
  })

  // ── Ghost Text (AI 行内补全) ─────────────────────────────────
  // 手动触发：Alt+\ 请求补全，按 Tab 接受，Esc 清除

  function getLineContext(lineNumber: number, column: number): string {
    const model = editor!.getModel()
    if (!model) return ''
    return model.getLineContent(lineNumber).slice(0, column - 1)
  }

  function clearGhost() {
    if (ghostDecoration.length && editor) {
      editor.deltaDecorations(ghostDecoration, [])
      ghostDecoration = []
    }
    ghostText = ''
  }

  function showGhost(pos: monaco.IPosition, text: string) {
    clearGhost()
    ghostText = text
    ghostDecoration = editor!.deltaDecorations([], [{
      range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column + text.length),
      options: {
        inlineClassName: 'ghost-text-suggestion',
        hoverMessage: { value: '**AI 补全** — 按 Tab 接受，Esc 清除' },
        stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      },
    }])
  }

  // 手动触发：Alt+\ 请求 AI 补全
  editor.addAction({
    id: 'trigger-ghost-text',
    label: 'Trigger AI Completion',
    keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.Backslash],
    run: async () => {
      const pos = editor!.getPosition()
      if (!pos) return
      const model = editor!.getModel()
      if (!model) return
      const lineContent = model.getLineContent(pos.lineNumber)
      const isAtLineEnd = pos.column >= lineContent.length
      if (!isAtLineEnd) return
      const ctx = getLineContext(pos.lineNumber, pos.column)
      if (ctx.length < 5) return
      try {
        lastGhostTrigger = Date.now()
        const resp = await fetch(`${COMPLETE_API}/api/complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context: ctx, max_tokens: 128 }),
          signal: AbortSignal.timeout(6000),
        })
        if (!resp.ok) return
        const data = await resp.json()
        const completion = (data as { completion?: string }).completion || ''
        if (!completion) return
        const currentPos = editor!.getPosition()
        if (currentPos && currentPos.lineNumber === pos.lineNumber && currentPos.column === pos.column) {
          showGhost(currentPos, completion)
        }
      } catch { /* ghost text fetch cancelled or failed */ }
    },
  })

  // Esc → 清除 ghost text
  editor.addAction({
    id: 'dismiss-ghost-text',
    label: 'Dismiss Ghost Text',
    keybindings: [monaco.KeyCode.Escape],
    run: (ed) => {
      if (ghostText) clearGhost()
    },
  })

  // Tab → 接受 ghost text（ghost 是装饰，插入实际文本）
  editor.addAction({
    id: 'accept-ghost-text',
    label: 'Accept Ghost Text',
    keybindings: [monaco.KeyCode.Tab],
    run: (ed) => {
      if (!ghostText) return
      const pos = ed.getPosition()
      if (!pos) return
      const model = ed.getModel()
      if (!model) return
      const lineContent = model.getLineContent(pos.lineNumber)
      const ghostLen = ghostText.length
      const afterCursor = lineContent.slice(pos.column - 1, pos.column - 1 + ghostLen)
      if (afterCursor === ghostText) {
        ed.executeEdits('accept-ghost', [{
          range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column + ghostLen),
          text: ghostText,
        }])
      } else {
        // ghost 已过期但仍有内容，直接插入
        ed.executeEdits('accept-ghost', [{
          range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
          text: ghostText,
        }])
      }
      clearGhost()
    },
  })

  // 光标移动 → 清除 ghost
  editor.onDidChangeCursorSelection(() => { clearGhost() })

})

async function handlePaletteSubmit(payload: { instruction: string; taskType: string; previous: string }) {
  if (!editor || !selectedText.value) return
  const sel = editor.getSelection()!

  // Coherence 模式：从 Monaco 读取前一段作为 previous
  let previous = payload.previous
  if (payload.taskType === 'coherence' && !previous) {
    const prevLine = sel.startLineNumber - 1
    if (prevLine >= 1) {
      previous = editor.getModel()?.getLineContent(prevLine) || ''
    }
  }

  editLoading.value = true
  try {
    await aiEdit(payload.instruction, selectedText.value, payload.taskType, previous)
    // aiEdit() 执行完成后 aiResult 已填充，直接写回编辑器
    const { aiResult } = useEditor()
    if (aiResult.value) {
      editor.executeEdits('ai-edit', [{
        range: new monaco.Range(
          sel.startLineNumber, sel.startColumn,
          sel.endLineNumber, sel.endColumn,
        ),
        text: aiResult.value,
      }])
      aiResult.value = ''
    }
  } catch (e) {
    console.error('AI edit failed:', e)
  } finally {
    editLoading.value = false
    showPalette.value = false
  }
}

watch(() => props.theme, (t) => { if (t) monaco.editor.setTheme(t) })

// 切换 tab 时加载对应内容
watch(activeTabId, () => {
  if (!editor) return
  const tab = useEditor().activeTab.value
  if (tab && editor.getValue() !== tab.content) {
    editor.setValue(tab.content)
  }
})

// content 变化时同步到 Monaco（来自 undo/其他 tab 等外部来源）
watch(content, (v) => {
  if (!editor) return
  const model = editor.getModel()
  if (model && model.getValue() !== v) model.setValue(v)
})

onBeforeUnmount(() => {
  if (ghostDebounceTimer) clearTimeout(ghostDebounceTimer)
  editor?.dispose()
})
</script>

<style scoped>
.monaco-wrapper { position: relative; width: 100%; height: 100%; min-height: 0; }
.monaco-container { width: 100%; height: 100%; min-height: 0; }
</style>

<!-- ghost text 样式（需要全局作用域，不能 scoped）-->
<style>
.ghost-text-suggestion {
  color: #888888 !important;
  opacity: 0.8;
}
/* AI inline edit 蓝色高亮动画 */
.ai-inline-edit { background: rgba(33, 150, 243, 0.15); border-radius: 2px; }
@keyframes ai-inline-flash {
  0% { background: rgba(33, 150, 243, 0.4); }
  100% { background: rgba(33, 150, 243, 0.15); }
}
.ai-inline-edit-char { animation: ai-inline-flash 0.4s ease-out; }
</style>
