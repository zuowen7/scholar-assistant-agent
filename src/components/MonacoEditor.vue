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
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import * as monaco from 'monaco-editor'
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import CommandPalette from './CommandPalette.vue'
import { useEditor } from '../composables/useEditor'
import { useEditorState } from '../composables/useEditorState'
import { useAgentChat } from '../composables/useAgentChat'
import { API_BASE } from '../utils/api'
import { useArgumentCompanion } from '../composables/useArgumentCompanion'
import { computeCompanionDecorations } from '../composables/companionGutter'
import { fetchCompletion, buildContext } from '../utils/inlineCompletion'

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
const { activeEdit, clearActiveEdit } = useEditorState()
const { sendApproval } = useAgentChat()

let editor: monaco.editor.IStandaloneCodeEditor | null = null
const companion = useArgumentCompanion()

// Gutter decorations for argument companion
let companionDecorations: string[] = []

function updateCompanionDecorations() {
  if (!editor) return
  const model = editor.getModel()
  if (!model) return
  const decos = computeCompanionDecorations(
    companion.state.ledger,
    companion.state.review,
    monaco,
    model,
  )
  companionDecorations = editor.deltaDecorations(companionDecorations, decos)
}

// Reveal + flash an anchor range in the editor
function revealAnchor(start: number, end: number) {
  if (!editor) return
  const model = editor.getModel()
  if (!model) return
  const p1 = model.getPositionAt(start)
  const p2 = model.getPositionAt(end)
  const range = new monaco.Range(p1.lineNumber, p1.column, p2.lineNumber, p2.column)
  editor.revealRangeInCenter(range)
  const flashDeco = editor.deltaDecorations([], [{
    range,
    options: { className: 'arg-flash', isWholeLine: false },
  }])
  setTimeout(() => editor?.deltaDecorations(flashDeco, []), 1200)
}

// Ctrl+K Palette
const showPalette = ref(false)
const palettePos = ref({ x: 200, y: 200 })
const selectedText = ref('')
const editLoading = ref(false)

// Ghost text: cached completion + debounced trigger
let _inlineCompletionsDisposable: { dispose(): void } | null = null
let ghostTimer: ReturnType<typeof setTimeout> | null = null
let ghostAbort: AbortController | null = null
let cachedCompletion: string = ''
let cachedPosition: { lineNumber: number; column: number } | null = null
let _monacoUpdating = false

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
    glyphMargin: true,
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    padding: { top: 16, bottom: 16 },
    automaticLayout: true,
    tabSize: 2,
    suggestOnTriggerCharacters: true,
    quickSuggestions: { other: true, comments: false, strings: false },
    inlineSuggest: { enabled: true },
    parameterHints: { enabled: true },
    acceptSuggestionOnEnter: 'on',
  })

  // ── AI Inline Completions Provider ──────────────────────
  // Returns cached completion when Monaco requests it.
  // The actual fetch is debounced in onDidChangeModelContent.
  _inlineCompletionsDisposable = monaco.languages.registerInlineCompletionsProvider('markdown', {
    provideInlineCompletions: async (model, position, _context) => {
      if (showPalette.value) return { items: [] }
      if (!cachedCompletion || !cachedPosition) return { items: [] }
      if (position.lineNumber !== cachedPosition.lineNumber || position.column !== cachedPosition.column) {
        return { items: [] }
      }
      return {
        items: [{
          insertText: cachedCompletion,
          range: new monaco.Range(
            position.lineNumber, position.column,
            position.lineNumber, position.column,
          ),
        }],
      }
    },
    disposeInlineCompletions: () => {},
  })

  setEditorInstance(editor)

  // ── Argument companion gutter ─────────────────────────────────────────
  editor.onMouseDown((e) => {
    if (e.target.type !== monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN) return
    const lineNumber = e.target.position?.lineNumber
    if (!lineNumber) return
    const model = editor!.getModel()
    if (!model) return
    if (companion.state.ledger) {
      for (const promise of companion.state.ledger.promises) {
        const anchor = companion.state.ledger.anchors.find(a => a.id === promise.source_anchor_id)
        if (anchor?.char_start !== null && anchor?.char_start !== undefined && anchor.status !== 'lost') {
          const pos = model.getPositionAt(anchor.char_start)
          if (pos.lineNumber === lineNumber) {
            companion.focusFromGutter('promise', promise.id)
            return
          }
        }
      }
    }
    if (companion.state.review) {
      for (const point of companion.state.review.points) {
        if (!point.anchor_id) continue
        const anchor = companion.state.review.anchors.find(a => a.id === point.anchor_id)
        if (anchor?.char_start !== null && anchor?.char_start !== undefined && anchor.status !== 'lost') {
          const pos = model.getPositionAt(anchor.char_start)
          if (pos.lineNumber === lineNumber) {
            companion.focusFromGutter('point', point.id)
            return
          }
        }
      }
    }
  })

  // ── 质疑这句 — scoped Reviewer-2 review ─────────────────────────────────
  editor.addAction({
    id: 'companion-scoped-review',
    label: t('editor.scopedReview'),
    contextMenuGroupId: 'argument',
    contextMenuOrder: 1,
    precondition: 'editorHasSelection',
    run: async (ed) => {
      const sel = ed.getSelection()
      if (!sel) return
      const selectedText = ed.getModel()?.getValueInRange(sel) || ''
      if (!selectedText.trim()) return
      const fullText = ed.getModel()?.getValue() || ''
      await companion.scopedReview(selectedText, fullText)
    },
  })

  editor.onDidChangeModelContent(() => {
    if (!editor) return
    _monacoUpdating = true
    setContent(editor.getValue())
    markDirty()
    // Clear stale cache and schedule new completion
    cachedCompletion = ''
    cachedPosition = null
    ghostAbort?.abort()
    if (ghostTimer) clearTimeout(ghostTimer)
    ghostTimer = setTimeout(() => triggerGhostCompletion(), 1500)
    nextTick(() => { _monacoUpdating = false })
  })

  editor.onDidChangeCursorSelection(() => {
    if (!editor) return
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

  // 重新聚焦时恢复缓存的 ghost text
  editor.onDidFocusEditorWidget(() => {
    if (!editor || !cachedCompletion || !cachedPosition) return
    const pos = editor.getPosition()
    if (!pos) return
    if (pos.lineNumber !== cachedPosition.lineNumber || pos.column !== cachedPosition.column) return
    try {
      editor.trigger('ghost', 'editor.action.inlineSuggest.trigger')
    } catch { /* ignore */ }
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

      palettePos.value = {
        x: Math.max(100, window.innerWidth / 2 - 200),
        y: 80,
      }
      showPalette.value = true
    },
  })

  // Alt+\ → 手动触发 AI 补全
  editor.addAction({
    id: 'trigger-ghost-text',
    label: 'Trigger AI Completion',
    keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.Backslash],
    run: () => {
      ghostAbort?.abort()
      if (ghostTimer) clearTimeout(ghostTimer)
      ghostTimer = setTimeout(() => triggerGhostCompletion(), 100)
    },
  })
})

async function triggerGhostCompletion() {
  if (!editor || showPalette.value) return
  const pos = editor.getPosition()
  const model = editor?.getModel()
  if (!pos || !model) return

  const ctx = buildContext(model as any, { lineNumber: pos.lineNumber, column: pos.column })
  if (!ctx) return

  ghostAbort?.abort()
  const ctrl = new AbortController()
  ghostAbort = ctrl

  const result = await fetchCompletion(
    ctx,
    { lineNumber: pos.lineNumber, column: pos.column },
    { apiBase: API_BASE },
    ctrl.signal,
  )
  if (!result || ctrl.signal.aborted) return

  // Verify cursor hasn't moved
  const cur = editor.getPosition()
  if (!cur || cur.lineNumber !== pos.lineNumber || cur.column !== pos.column) return

  // Cache result and trigger Monaco to show it
  cachedCompletion = result.completion
  cachedPosition = { lineNumber: pos.lineNumber, column: pos.column }
  try {
    editor.trigger('ghost', 'editor.action.inlineSuggest.trigger')
  } catch { /* Monaco may cancel if content changed */ }
}

async function handlePaletteSubmit(payload: { instruction: string; taskType: string; previous: string }) {
  if (!editor || !selectedText.value) return
  const sel = editor.getSelection()!

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

watch(
  [() => companion.state.ledger, () => companion.state.review],
  () => updateCompanionDecorations(),
)

watch(
  () => companion.state.flashAnchor,
  (v) => { if (v) revealAnchor(v.start, v.end) },
)

watch(activeTabId, () => {
  if (!editor) return
  _monacoUpdating = true
  const tab = useEditor().activeTab.value
  if (tab && editor.getValue() !== tab.content) {
    editor.setValue(tab.content)
  }
  nextTick(() => { _monacoUpdating = false })
})

watch(content, (v) => {
  if (!editor || _monacoUpdating) return
  const model = editor.getModel()
  if (model && model.getValue() !== v) {
    const pos = editor.getPosition()
    model.setValue(v)
    if (pos) editor.setPosition(pos)
  }
})

// ── Inline Diff Approval ────────────────────────────────────────────────
let _diffDecorations: string[] = []
let _diffWidget: monaco.editor.IContentWidget | null = null

function _clearDiffDecorations() {
  if (editor && _diffDecorations.length) {
    editor.deltaDecorations(_diffDecorations, [])
    _diffDecorations = []
  }
  if (_diffWidget && editor) {
    try { editor.removeContentWidget(_diffWidget) } catch { /* already disposed */ }
    _diffWidget = null
  }
}

watch(activeEdit, (edit) => {
  _clearDiffDecorations()
  if (!edit || !editor) return

  const model = editor.getModel()
  if (!model) return

  // For str_replace: search oldText in model to find range
  if (edit.operation === 'str_replace' && edit.oldText) {
    const matches = model.findMatches(
      edit.oldText,
      false,
      false,
      true,  // exactMatch
      null,
      true,
    )
    if (matches.length !== 1) {
      // Not found or ambiguous — skip inline diff (AgentPanel text approval will show)
      clearActiveEdit()
      return
    }
    const matchRange = matches[0].range

    // Red decoration over old text
    _diffDecorations = editor.deltaDecorations([], [{
      range: matchRange,
      options: {
        className: 'ai-diff-deleted',
        isWholeLine: false,
        hoverMessage: { value: `**${t('agent.inlineDiff.old', 'Original')}**` },
      },
    }])

    // Content widget below deletion showing new text + Accept/Reject
    const widgetId = `inline-diff-${edit.editId}`
    const widgetEl = document.createElement('div')
    widgetEl.className = 'ai-diff-widget'
    const newLines = edit.newText.split('\n')
    const previewLines = newLines.slice(0, 15)
    const truncated = newLines.length > 15
    widgetEl.innerHTML = `
      <div class="ai-diff-new">
        ${previewLines.map((l: string) => `<div class="ai-diff-new-line">${_escapeHtml(l)}</div>`).join('')}
        ${truncated ? `<div class="ai-diff-truncated">... ${newLines.length - 15} ${t('agent.inlineDiff.moreLines', 'more lines')}</div>` : ''}
      </div>
      <div class="ai-diff-actions">
        <button class="ai-diff-accept" data-action="accept">${t('agent.inlineDiff.accept', 'Accept')}</button>
        <button class="ai-diff-reject" data-action="reject">${t('agent.inlineDiff.reject', 'Reject')}</button>
      </div>
    `
    widgetEl.querySelector('.ai-diff-accept')!.addEventListener('click', () => {
      _dispatchInlineDecision('allow_once')
    })
    widgetEl.querySelector('.ai-diff-reject')!.addEventListener('click', () => {
      _dispatchInlineDecision('deny')
    })

    _diffWidget = {
      getId: () => widgetId,
      getDomNode: () => widgetEl,
      getPosition: () => ({
        position: { lineNumber: matchRange.endLineNumber, column: matchRange.endColumn },
        preference: [monaco.editor.ContentWidgetPositionPreference.BELOW],
      }),
    }
    editor.addContentWidget(_diffWidget)
    editor.revealRangeInCenter(matchRange)
  } else if (edit.operation === 'write_file' && edit.newText) {
    // write_file: show new content preview at top of file
    const widgetId = `inline-diff-${edit.editId}`
    const widgetEl = document.createElement('div')
    widgetEl.className = 'ai-diff-widget'
    const newLines = edit.newText.split('\n')
    const previewLines = newLines.slice(0, 15)
    const truncated = newLines.length > 15
    widgetEl.innerHTML = `
      <div class="ai-diff-new">
        ${previewLines.map((l: string) => `<div class="ai-diff-new-line">${_escapeHtml(l)}</div>`).join('')}
        ${truncated ? `<div class="ai-diff-truncated">... ${newLines.length - 15} ${t('agent.inlineDiff.moreLines', 'more lines')}</div>` : ''}
      </div>
      <div class="ai-diff-actions">
        <button class="ai-diff-accept" data-action="accept">${t('agent.inlineDiff.accept', 'Accept')}</button>
        <button class="ai-diff-reject" data-action="reject">${t('agent.inlineDiff.reject', 'Reject')}</button>
      </div>
    `
    widgetEl.querySelector('.ai-diff-accept')!.addEventListener('click', () => {
      _dispatchInlineDecision('allow_once')
    })
    widgetEl.querySelector('.ai-diff-reject')!.addEventListener('click', () => {
      _dispatchInlineDecision('deny')
    })

    _diffWidget = {
      getId: () => widgetId,
      getDomNode: () => widgetEl,
      getPosition: () => ({
        position: { lineNumber: 1, column: 1 },
        preference: [monaco.editor.ContentWidgetPositionPreference.BELOW],
      }),
    }
    editor.addContentWidget(_diffWidget)
    editor.revealLineInCenter(1)
  }
})

function _dispatchInlineDecision(decision: 'allow_once' | 'deny') {
  const edit = activeEdit.value
  if (!edit) return
  sendApproval(edit.eventId, decision).then(ok => {
    if (ok) clearActiveEdit()
    // On failure, widget stays visible for retry
  })
}

function _escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

onBeforeUnmount(() => {
  _clearDiffDecorations()
  if (ghostTimer) { clearTimeout(ghostTimer); ghostTimer = null }
  ghostAbort?.abort()
  _inlineCompletionsDisposable?.dispose()
  _inlineCompletionsDisposable = null
  editor?.dispose()
  editor = null
})
</script>

<style scoped>
.monaco-wrapper { position: relative; width: 100%; height: 100%; min-height: 0; }
.monaco-container { width: 100%; height: 100%; min-height: 0; }
</style>

<style>
/* Argument companion gutter glyphs */
.monaco-editor .arg-gutter-promise-unpaid { background: #f87171; border-radius: 50%; width: 10px !important; height: 10px !important; margin-top: 6px; }
.monaco-editor .arg-gutter-promise-mismatch { background: #fb923c; border-radius: 50%; width: 10px !important; height: 10px !important; margin-top: 6px; }
.monaco-editor .arg-gutter-promise-partial { background: #fbbf24; border-radius: 50%; width: 10px !important; height: 10px !important; margin-top: 6px; }
.monaco-editor .arg-gutter-review-fatal { background: #f87171; clip-path: polygon(50% 0%, 0% 100%, 100% 100%); width: 10px !important; height: 10px !important; margin-top: 6px; }
.monaco-editor .arg-gutter-review-major { background: #fb923c; clip-path: polygon(50% 0%, 0% 100%, 100% 100%); width: 10px !important; height: 10px !important; margin-top: 6px; }
.monaco-editor .arg-gutter-review-minor { background: #6b7280; clip-path: polygon(50% 0%, 0% 100%, 100% 100%); width: 10px !important; height: 10px !important; margin-top: 6px; }

/* Flash highlight when jumping to anchor */
.monaco-editor .arg-flash {
  background: var(--c-accent-soft) !important;
  border-radius: 3px;
  animation: arg-flash-pulse 1.2s var(--ease-out, cubic-bezier(0.16,1,0.3,1)) 1;
}
@keyframes arg-flash-pulse {
  0%   { background: color-mix(in srgb, var(--c-accent) 45%, transparent) !important; box-shadow: 0 0 0 3px var(--c-accent-soft); }
  30%  { background: color-mix(in srgb, var(--c-accent) 35%, transparent) !important; }
  100% { background: transparent !important; box-shadow: 0 0 0 0 transparent; }
}
@media (prefers-reduced-motion: reduce) {
  .monaco-editor .arg-flash { animation: none; }
}

/* Inline diff approval */
.monaco-editor .ai-diff-deleted {
  background: color-mix(in srgb, var(--c-danger) 25%, transparent) !important;
  border-bottom: 2px wavy var(--c-danger) !important;
}
.ai-diff-widget {
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md, 8px);
  box-shadow: var(--elevation-3, 0 8px 24px rgba(0,0,0,.18));
  padding: 12px 16px;
  margin-top: 4px;
  max-width: 600px;
  max-height: 320px;
  overflow-y: auto;
  font-family: var(--font-mono, monospace);
  font-size: 13px;
  z-index: 100;
}
.ai-diff-new {
  background: color-mix(in srgb, var(--c-success) 12%, transparent);
  border-radius: 4px;
  padding: 6px 8px;
}
.ai-diff-new-line {
  color: var(--c-text-0);
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.ai-diff-truncated {
  color: var(--c-text-2);
  font-style: italic;
  font-size: 12px;
  margin-top: 4px;
}
.ai-diff-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.ai-diff-accept, .ai-diff-reject {
  padding: 5px 14px;
  border: none;
  border-radius: var(--radius-sm, 4px);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.ai-diff-accept {
  background: var(--c-success);
  color: #fff;
}
.ai-diff-accept:hover { background: color-mix(in srgb, var(--c-success) 85%, #000); }
.ai-diff-reject {
  background: var(--c-danger);
  color: #fff;
}
.ai-diff-reject:hover { background: color-mix(in srgb, var(--c-danger) 85%, #000); }
</style>
