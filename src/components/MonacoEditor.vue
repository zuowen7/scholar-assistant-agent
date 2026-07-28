<template>
  <div ref="editorWrapper" class="monaco-wrapper" :class="`presentation-${presentation}`">
    <div ref="editorContainer" class="monaco-container"></div>
    <div
      v-if="selectedText.trim() && presentation === 'document'"
      ref="selectionToolbar"
      class="selection-toolbar"
      :class="`placement-${selectionToolbarPosition.placement}`"
      :style="selectionToolbarStyle"
      role="toolbar"
      :aria-label="t('editor.selectionActions')"
      @mousedown.prevent
    >
      <button type="button" @click.stop="emitSelectionAction(t('editor.polish'))">
        <Sparkles :size="14" /> {{ t('editor.polish') }}
      </button>
      <button type="button" @click.stop="emitSelectionAction(t('editor.condense'))">
        {{ t('editor.condense') }}
      </button>
      <button type="button" @click.stop="emitSelectionAction(t('editor.expand'))">
        {{ t('editor.expand') }}
      </button>
      <button type="button" @click.stop="emitSelectionAction(t('editor.checkArgument'))">
        {{ t('editor.checkArgument') }}
      </button>
    </div>
    <CommandPalette
      v-if="showPalette"
      :position="palettePos"
      :loading="editLoading"
      :selected-text="selectedText"
      @submit="handlePaletteSubmit"
      @cancel="showPalette = false"
    />
    <!-- Inline diff overlay: rendered outside Monaco's DOM to avoid event interference -->
    <div
      v-if="diffOverlay.visible"
      ref="diffOverlayRef"
      class="ai-diff-overlay"
      :style="{
        top: diffOverlay.top + 'px',
        left: diffOverlay.left + 'px',
        width: diffOverlay.width + 'px',
      }"
    >
      <section
        class="ai-diff-card"
        :style="{
          maxHeight: diffOverlay.maxHeight + 'px',
          minHeight: Math.min(140, diffOverlay.maxHeight) + 'px',
        }"
      >
        <header class="ai-diff-header">
          <span class="ai-diff-title">{{ diffOverlay.title }}</span>
        </header>
        <div ref="diffContentRef" class="ai-diff-new ai-diff-scroll">{{ diffOverlay.text }}</div>
        <footer class="ai-diff-actions">
          <button class="ai-diff-accept" @click.stop="diffOverlay.onAccept()">
            {{ diffOverlay.acceptLabel }}
          </button>
          <button class="ai-diff-reject" @click.stop="diffOverlay.onReject()">
            {{ diffOverlay.rejectLabel }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import type { CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import { Sparkles } from 'lucide-vue-next'

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
import { fetchCompletion, buildContext, type CompletionModel } from '../utils/inlineCompletion'
import {
  computeSelectionToolbarPosition,
  type SelectionToolbarPosition,
} from '../utils/selectionToolbarPosition'
import { computeInlineDiffOverlayPosition } from '../utils/inlineDiffOverlayPosition'

// 配置 Monaco Web Worker（解决 Tauri 环境下 worker 无法创建的问题）
self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker()
  },
}

const props = defineProps<{
  theme?: 'vs-dark' | 'vs'
  presentation?: 'code' | 'document'
}>()
const emit = defineEmits<{
  selectionAction: [action: string]
}>()
const presentation = computed(() => props.presentation || 'code')

const editorWrapper = ref<HTMLElement>()
const editorContainer = ref<HTMLElement>()
const selectionToolbar = ref<HTMLElement>()
const { setEditorInstance, setContent, content, updateSelection, activeTabId, markDirty, aiEdit } =
  useEditor()
const { activeEdit, clearActiveEdit, setInlineDiffVisible, activeTab } = useEditorState()
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
  const flashDeco = editor.deltaDecorations(
    [],
    [
      {
        range,
        options: { className: 'arg-flash', isWholeLine: false },
      },
    ],
  )
  setTimeout(() => editor?.deltaDecorations(flashDeco, []), 1200)
}

// Ctrl+K Palette
const showPalette = ref(false)
const palettePos = ref({ x: 200, y: 200 })
const selectedText = ref('')
const editLoading = ref(false)
const selectionToolbarPosition = ref<SelectionToolbarPosition>({
  visible: false,
  left: 8,
  top: 8,
  placement: 'above',
})
const selectionToolbarStyle = computed<CSSProperties>(() => ({
  visibility: selectionToolbarPosition.value.visible ? 'visible' : 'hidden',
  left: `${selectionToolbarPosition.value.left}px`,
  top: `${selectionToolbarPosition.value.top}px`,
}))
let selectionToolbarFrame: number | null = null

function emitSelectionAction(action: string) {
  emit('selectionAction', action)
}

function scheduleSelectionToolbarUpdate() {
  if (selectionToolbarFrame !== null) cancelAnimationFrame(selectionToolbarFrame)
  nextTick(() => {
    selectionToolbarFrame = requestAnimationFrame(() => {
      selectionToolbarFrame = null
      updateSelectionToolbarPosition()
    })
  })
}

function updateSelectionToolbarPosition() {
  const wrapper = editorWrapper.value
  const container = editorContainer.value
  const toolbar = selectionToolbar.value
  const selection = editor?.getSelection()
  if (
    !editor ||
    !wrapper ||
    !container ||
    !toolbar ||
    !selection ||
    !selectedText.value.trim() ||
    presentation.value !== 'document'
  ) {
    selectionToolbarPosition.value = {
      ...selectionToolbarPosition.value,
      visible: false,
    }
    return
  }

  const activePosition =
    selection.getDirection() === monaco.SelectionDirection.RTL
      ? selection.getStartPosition()
      : selection.getEndPosition()
  const anchor = editor.getScrolledVisiblePosition(activePosition)
  const wrapperRect = wrapper.getBoundingClientRect()
  const containerRect = container.getBoundingClientRect()
  selectionToolbarPosition.value = computeSelectionToolbarPosition(anchor, {
    viewportWidth: wrapper.clientWidth,
    viewportHeight: wrapper.clientHeight,
    toolbarWidth: toolbar.offsetWidth,
    toolbarHeight: toolbar.offsetHeight,
    containerLeft: containerRect.left - wrapperRect.left,
    containerTop: containerRect.top - wrapperRect.top,
  })
}

// Ghost text: cached completion + debounced trigger
let _inlineCompletionsDisposable: { dispose(): void } | null = null
let ghostTimer: ReturnType<typeof setTimeout> | null = null
let ghostAbort: AbortController | null = null
let cachedCompletion: string = ''
let cachedPosition: { lineNumber: number; column: number } | null = null
let _monacoUpdating = false

function activeLanguage() {
  return /\.tex$/i.test(activeTab.value?.name || activeTab.value?.path || '') ? 'latex' : 'markdown'
}

function applyPresentation() {
  if (!editor) return
  const documentMode = presentation.value === 'document'
  editor.updateOptions({
    lineNumbers: documentMode ? 'off' : 'on',
    glyphMargin: !documentMode,
    folding: !documentMode,
    minimap: { enabled: !documentMode },
    fontSize: documentMode ? 16 : 14,
    lineHeight: documentMode ? 30 : 22,
    fontFamily: documentMode
      ? "'Noto Serif SC', 'Songti SC', 'SimSun', serif"
      : "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
    padding: documentMode ? { top: 38, bottom: 56 } : { top: 16, bottom: 16 },
    renderLineHighlight: documentMode ? 'none' : 'line',
    overviewRulerLanes: documentMode ? 0 : 3,
    hideCursorInOverviewRuler: documentMode,
    scrollbar: { verticalScrollbarSize: 9, horizontalScrollbarSize: 9 },
  })
}

onMounted(() => {
  if (!editorContainer.value) return

  editor = monaco.editor.create(editorContainer.value, {
    value: content.value,
    language: activeLanguage(),
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
  applyPresentation()

  // ── AI Inline Completions Provider ──────────────────────
  // Returns cached completion when Monaco requests it.
  // The actual fetch is debounced in onDidChangeModelContent.
  _inlineCompletionsDisposable = monaco.languages.registerInlineCompletionsProvider('markdown', {
    provideInlineCompletions: async (_model, position, _context) => {
      if (showPalette.value) return { items: [] }
      if (!cachedCompletion || !cachedPosition) return { items: [] }
      if (
        position.lineNumber !== cachedPosition.lineNumber ||
        position.column !== cachedPosition.column
      ) {
        return { items: [] }
      }
      return {
        items: [
          {
            insertText: cachedCompletion,
            range: new monaco.Range(
              position.lineNumber,
              position.column,
              position.lineNumber,
              position.column,
            ),
          },
        ],
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
        const anchor = companion.state.ledger.anchors.find((a) => a.id === promise.source_anchor_id)
        if (
          anchor?.char_start !== null &&
          anchor?.char_start !== undefined &&
          anchor.status !== 'lost'
        ) {
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
        const anchor = companion.state.review.anchors.find((a) => a.id === point.anchor_id)
        if (
          anchor?.char_start !== null &&
          anchor?.char_start !== undefined &&
          anchor.status !== 'lost'
        ) {
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
    // Switching tabs and restoring a tab's model are programmatic updates.
    // They must not make a clean file look modified or overwrite the tab's
    // clean state before the user has actually edited anything.
    if (!editor || _monacoUpdating) return
    const nextValue = editor.getValue()
    // Monaco can deliver setValue's content event after Vue's nextTick guard
    // has cleared. Equality against the active tab is the second, durable
    // boundary between model restoration and an actual user edit.
    if (nextValue === activeTab.value?.content) return
    _monacoUpdating = true
    setContent(nextValue)
    markDirty()
    // Clear stale cache and schedule new completion
    cachedCompletion = ''
    cachedPosition = null
    ghostAbort?.abort()
    if (ghostTimer) clearTimeout(ghostTimer)
    ghostTimer = setTimeout(() => triggerGhostCompletion(), 1500)
    nextTick(() => {
      _monacoUpdating = false
    })
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
    scheduleSelectionToolbarUpdate()
  })

  editor.onDidScrollChange(() => scheduleSelectionToolbarUpdate())
  editor.onDidLayoutChange(() => {
    scheduleSelectionToolbarUpdate()
    _updateDiffOverlayPosition(true)
  })

  // 重新聚焦时恢复缓存的 ghost text
  editor.onDidFocusEditorWidget(() => {
    if (!editor || !cachedCompletion || !cachedPosition) return
    const pos = editor.getPosition()
    if (!pos) return
    if (pos.lineNumber !== cachedPosition.lineNumber || pos.column !== cachedPosition.column) return
    try {
      editor.trigger('ghost', 'editor.action.inlineSuggest.trigger', undefined)
    } catch {
      /* ignore */
    }
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
        editor.setSelection(
          new monaco.Range(
            sel.startLineNumber,
            1,
            sel.startLineNumber,
            editor.getModel()!.getLineMaxColumn(sel.startLineNumber),
          ),
        )
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

  const ctx = buildContext(model as CompletionModel, {
    lineNumber: pos.lineNumber,
    column: pos.column,
  })
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
    editor.trigger('ghost', 'editor.action.inlineSuggest.trigger', undefined)
  } catch {
    /* Monaco may cancel if content changed */
  }
}

async function handlePaletteSubmit(payload: {
  instruction: string
  taskType: string
  previous: string
}) {
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
      editor.executeEdits('ai-edit', [
        {
          range: new monaco.Range(
            sel.startLineNumber,
            sel.startColumn,
            sel.endLineNumber,
            sel.endColumn,
          ),
          text: aiResult.value,
        },
      ])
      aiResult.value = ''
    }
  } catch (e) {
    console.error('AI edit failed:', e)
  } finally {
    editLoading.value = false
    showPalette.value = false
  }
}

watch(
  () => props.theme,
  (t) => {
    if (t) monaco.editor.setTheme(t)
  },
)
watch(
  () => props.presentation,
  () => {
    applyPresentation()
    scheduleSelectionToolbarUpdate()
  },
)

watch([() => companion.state.ledger, () => companion.state.review], () =>
  updateCompanionDecorations(),
)

watch(
  () => companion.state.flashAnchor,
  (v) => {
    if (v) revealAnchor(v.start, v.end)
  },
)

watch(activeTabId, () => {
  if (!editor) return
  _monacoUpdating = true
  const tab = useEditor().activeTab.value
  if (tab && editor.getValue() !== tab.content) {
    editor.setValue(tab.content)
  }
  const model = editor.getModel()
  if (model) monaco.editor.setModelLanguage(model, activeLanguage())
  applyPresentation()
  nextTick(() => {
    _monacoUpdating = false
  })
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

// ── Inline Diff Approval (overlay, outside Monaco DOM) ──────────────────
let _diffDecorations: string[] = []
let _diffAfterLine = 0
let _scrollDisposable: monaco.IDisposable | null = null

const diffContentRef = ref<HTMLElement>()
const diffOverlayRef = ref<HTMLElement>()

const diffOverlay = reactive({
  visible: false,
  top: 0,
  left: 0,
  width: 640, // safe default, updated by _updateDiffOverlayPosition
  maxHeight: 360,
  title: '',
  text: '',
  acceptLabel: '',
  rejectLabel: '',
  onAccept: () => {},
  onReject: () => {},
})

function _updateDiffOverlayPosition(remeasureAfterLayout = false) {
  if (!editor || !diffOverlay.visible) return
  const wrapper = editorWrapper.value
  if (!wrapper) return

  const rect = wrapper.getBoundingClientRect()
  if (rect.width < 100) return // wrapper not yet laid out

  const model = editor.getModel()
  const lineCount = model?.getLineCount() ?? 0
  const targetLine = Math.min(_diffAfterLine + 1, Math.max(1, lineCount))
  const lineTop = editor.getTopForLineNumber(targetLine)
  const scrollTop = editor.getScrollTop()
  const overlayTop = lineTop - scrollTop

  const position = computeInlineDiffOverlayPosition({
    anchorTop: overlayTop,
    viewportHeight: rect.height,
    overlayHeight: diffOverlayRef.value?.getBoundingClientRect().height ?? 360,
  })

  diffOverlay.top = position.top
  diffOverlay.maxHeight = position.maxHeight
  diffOverlay.left = Math.max(0, (rect.width - 720) / 2)
  diffOverlay.width = Math.max(280, Math.min(720, rect.width - 48))

  if (remeasureAfterLayout) {
    nextTick(() => _updateDiffOverlayPosition())
  }
}

function _clearDiffDecorations() {
  setInlineDiffVisible(false)
  diffOverlay.visible = false
  if (_scrollDisposable) {
    _scrollDisposable.dispose()
    _scrollDisposable = null
  }
  if (editor && _diffDecorations.length) {
    editor.deltaDecorations(_diffDecorations, [])
    _diffDecorations = []
  }
}

function _showInlineDiff(afterLineNumber: number, newText: string) {
  if (!editor) return
  _diffAfterLine = afterLineNumber

  diffOverlay.title = t('agent.inlineDiff.new', 'Suggested change')
  diffOverlay.text = newText
  diffOverlay.acceptLabel = t('agent.inlineDiff.accept', 'Accept')
  diffOverlay.rejectLabel = t('agent.inlineDiff.reject', 'Reject')
  diffOverlay.onAccept = () => _dispatchInlineDecision('allow_once')
  diffOverlay.onReject = () => _dispatchInlineDecision('deny')
  diffOverlay.visible = true

  // Update position now + track editor scroll
  nextTick(() => _updateDiffOverlayPosition(true))
  _scrollDisposable?.dispose()
  _scrollDisposable = editor.onDidScrollChange(() => {
    _updateDiffOverlayPosition()
  })

  setInlineDiffVisible(true)
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
      true, // exactMatch
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
    _diffDecorations = editor.deltaDecorations(
      [],
      [
        {
          range: matchRange,
          options: {
            className: 'ai-diff-deleted',
            isWholeLine: false,
            hoverMessage: { value: `**${t('agent.inlineDiff.old', 'Original')}**` },
          },
        },
      ],
    )

    _showInlineDiff(matchRange.endLineNumber, edit.newText)
    editor.revealRangeInCenter(matchRange)
    // Re-position after reveal animation completes
    setTimeout(() => _updateDiffOverlayPosition(true), 150)
  } else if (edit.operation === 'write_file' && edit.newText) {
    // Whole-file previews reserve space before the first line.
    _showInlineDiff(0, edit.newText)
    editor.revealLineInCenter(1)
    setTimeout(() => _updateDiffOverlayPosition(true), 150)
  }
})

function _dispatchInlineDecision(decision: 'allow_once' | 'deny') {
  const edit = activeEdit.value
  if (!edit) return
  sendApproval(edit.eventId, decision, undefined, edit.sessionId).then((ok) => {
    if (ok) clearActiveEdit()
    // On failure, widget stays visible for retry
  })
}

onBeforeUnmount(() => {
  _clearDiffDecorations()
  if (selectionToolbarFrame !== null) {
    cancelAnimationFrame(selectionToolbarFrame)
    selectionToolbarFrame = null
  }
  if (ghostTimer) {
    clearTimeout(ghostTimer)
    ghostTimer = null
  }
  ghostAbort?.abort()
  _inlineCompletionsDisposable?.dispose()
  _inlineCompletionsDisposable = null
  editor?.dispose()
  editor = null
})
</script>

<style scoped>
.monaco-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden; /* clip diff overlay */
}
.monaco-container {
  width: 100%;
  height: 100%;
  min-height: 0;
}
.presentation-document {
  background: #fbfaf7;
}
.presentation-document .monaco-container {
  max-width: 820px;
  margin: 0 auto;
  border-left: 1px solid var(--c-border);
  border-right: 1px solid var(--c-border);
  background: var(--c-panel);
}
.selection-toolbar {
  position: absolute;
  z-index: 30;
  display: flex;
  max-width: calc(100% - 16px);
  align-items: center;
  gap: 2px;
  padding: 5px;
  overflow-x: auto;
  border: 1px solid var(--c-border);
  border-radius: 9px;
  background: var(--c-panel);
  box-shadow: 0 7px 22px rgba(50, 43, 31, 0.16);
  scrollbar-width: none;
}
.selection-toolbar::-webkit-scrollbar {
  display: none;
}
.selection-toolbar button {
  flex: 0 0 auto;
  height: 29px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--c-text-1);
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}
.selection-toolbar button:hover {
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
.selection-toolbar button:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
</style>

<style>
/* Argument companion gutter glyphs */
.monaco-editor .arg-gutter-promise-unpaid {
  background: #f87171;
  border-radius: 50%;
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}
.monaco-editor .arg-gutter-promise-mismatch {
  background: #fb923c;
  border-radius: 50%;
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}
.monaco-editor .arg-gutter-promise-partial {
  background: #fbbf24;
  border-radius: 50%;
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}
.monaco-editor .arg-gutter-review-fatal {
  background: #f87171;
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}
.monaco-editor .arg-gutter-review-major {
  background: #fb923c;
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}
.monaco-editor .arg-gutter-review-minor {
  background: #6b7280;
  clip-path: polygon(50% 0%, 0% 100%, 100% 100%);
  width: 10px !important;
  height: 10px !important;
  margin-top: 6px;
}

/* Flash highlight when jumping to anchor */
.monaco-editor .arg-flash {
  background: var(--c-accent-soft) !important;
  border-radius: 3px;
  animation: arg-flash-pulse 1.2s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)) 1;
}
@keyframes arg-flash-pulse {
  0% {
    background: color-mix(in srgb, var(--c-accent) 45%, transparent) !important;
    box-shadow: 0 0 0 3px var(--c-accent-soft);
  }
  30% {
    background: color-mix(in srgb, var(--c-accent) 35%, transparent) !important;
  }
  100% {
    background: transparent !important;
    box-shadow: 0 0 0 0 transparent;
  }
}
@media (prefers-reduced-motion: reduce) {
  .monaco-editor .arg-flash {
    animation: none;
  }
}

/* Inline diff approval — overlay outside Monaco DOM */
.monaco-editor .ai-diff-deleted {
  background: color-mix(in srgb, var(--c-danger) 25%, transparent) !important;
  border-bottom: 2px wavy var(--c-danger) !important;
}
.ai-diff-overlay {
  position: absolute;
  z-index: 50;
  pointer-events: auto;
  /* Reserve breathing room so the card doesn't cover line numbers */
  padding: 0 16px;
  box-sizing: border-box;
}
.ai-diff-card {
  display: flex;
  width: 100%;
  max-height: 360px;
  min-height: 140px;
  box-sizing: border-box;
  flex-direction: column;
  overflow: hidden;
  pointer-events: auto;
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-left: 3px solid var(--c-success);
  border-radius: var(--radius-md, 8px);
  box-shadow: var(--elevation-4, 0 12px 40px rgba(0, 0, 0, 0.35));
  font-family: var(--font-mono, monospace);
  font-size: 13px;
}
.ai-diff-header {
  display: flex;
  flex: 0 0 auto;
  min-height: 36px;
  box-sizing: border-box;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--c-surface-3);
  background: color-mix(in srgb, var(--c-success) 8%, var(--c-surface-1));
}
.ai-diff-title {
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 650;
}
.ai-diff-new {
  min-width: 0;
  min-height: 0;
  flex: 1;
  background: color-mix(in srgb, var(--c-success) 12%, transparent);
  padding: 10px 12px;
  color: var(--c-text-0);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.5;
}
.ai-diff-scroll {
  overflow: auto;
  overscroll-behavior: contain;
  touch-action: pan-y;
  cursor: text;
  scrollbar-gutter: stable;
}
.ai-diff-scroll:focus-visible {
  outline: 2px solid var(--c-accent);
  outline-offset: -2px;
}
.ai-diff-actions {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--c-surface-3);
  background: var(--c-surface-1);
}
.ai-diff-accept,
.ai-diff-reject {
  min-width: 72px;
  padding: 5px 14px;
  border-radius: var(--radius-sm, 4px);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
}
.ai-diff-accept {
  border: 1px solid var(--c-success);
  background: var(--c-success);
  color: #fff;
}
.ai-diff-accept:hover {
  background: color-mix(in srgb, var(--c-success) 85%, #000);
}
.ai-diff-reject {
  border: 1px solid var(--c-border);
  background: var(--c-panel);
  color: var(--c-text-1);
}
.ai-diff-reject:hover {
  border-color: var(--c-danger);
  color: var(--c-danger);
  background: var(--c-danger-bg);
}
</style>
