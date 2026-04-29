/**
 * useEditor — AI Edit / Inline Edit / Ghost Text 补全
 *
 * 状态来源：useEditorState（单一真实源）
 *
 * `insertTextAtCursor` / `insertImage` 也放在这里，
 * 因为两者依赖 Monaco editor 实例，属于 AI 编辑子系统。
 */
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import {
  tabs, activeTabId, monacoEditor, contentVersion, activeTab, content, activeFile, isModified,
  selection, showAiPanel, aiLoading, aiResult, previousContent,
  insertTextAtCursor, insertImage,
} from './useEditorState'
import {
  setEditorInstance, setContent, updateSelection, markClean, markDirty,
  openFile, openNewUntitled, closeTab, setActiveTab, renameTabPath, saveFile,
} from './useEditorTabs'

// ── AI Edit ──────────────────────────────────────────────────────────────

const _abortMap = new Map<string, AbortController>()

function _abortOp(key: string): void {
  _abortMap.get(key)?.abort()
  _abortMap.delete(key)
}

function _signalFor(key: string): AbortSignal {
  _abortOp(key)
  const ctrl = new AbortController()
  _abortMap.set(key, ctrl)
  return ctrl.signal
}

export async function aiEdit(
  instruction: string,
  text?: string,
  taskType?: string,
  previous?: string,
) {
  const targetText = text || selection.value.text
  if (!instruction) return
  previousContent.value = content.value
  const signal = _signalFor('aiEdit')
  aiLoading.value = true
  aiResult.value = ''
  try {
    const payload: Record<string, string> = { text: targetText, instruction }
    if (taskType) payload.task_type = taskType
    if (previous) payload.previous = previous
    const resp = await fetch(`${API_BASE}/api/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    if (!resp.body) throw new Error('No response body')
    const reader = resp.body.getReader()
    await readSseStream(reader, (_type, evt) => {
      if (evt.content) aiResult.value = evt.content as string
    })
    if (!aiResult.value) aiResult.value = 'AI 未返回结果，请重试。'
  } catch (e: unknown) {
    if ((e as Error).name === 'AbortError') return
    aiResult.value = `请求失败: ${e}`
  } finally {
    aiLoading.value = false
    _abortMap.delete('aiEdit')
  }
}

// ── AI Inline Edit ────────────────────────────────────────────────────────

let inlineDecoration: string[] = []

function applyInlineDecoration(
  startLine: number, startCol: number,
  endLine: number, endCol: number,
) {
  const editor = monacoEditor.value
  if (!editor) return
  const Range = (editor as any).monaco?.Range ??
    class R { constructor(public a: number, public b: number, public c: number, public d: number) {} }
  inlineDecoration = editor.deltaDecorations([], [{
    range: new Range(startLine, startCol, endLine, endCol),
    options: { className: 'ai-inline-edit', inlineClassName: 'ai-inline-edit-char' },
  }])
}

function clearInlineDecoration() {
  const editor = monacoEditor.value
  if (editor && inlineDecoration.length) {
    editor.deltaDecorations(inlineDecoration, [])
    inlineDecoration = []
  }
}

export async function inlineEdit(instruction: string, taskType?: string): Promise<string | null> {
  const editor = monacoEditor.value
  const sel = selection.value
  if (!editor || !sel.text) return null
  previousContent.value = content.value
  const signal = _signalFor('inlineEdit')
  aiLoading.value = true
  aiResult.value = ''
  try {
    const resp = await fetch(`${API_BASE}/api/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: sel.text, instruction, task_type: taskType || 'expand' }),
      signal,
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    if (!resp.body) throw new Error('No response body')
    const Range = (editor as any).monaco?.Range ??
      class R { constructor(public a: number, public b: number, public c: number, public d: number) {} }
    const reader = resp.body.getReader()
    applyInlineDecoration(sel.startLine, sel.startCol, sel.endLine, sel.endCol)
    await readSseStream(reader, (_type, evt) => {
      if (evt.content) {
        aiResult.value = (aiResult.value || '') + (evt.content as string)
        editor.executeEdits('ai-inline', [{
          range: new Range(sel.startLine, sel.startCol, sel.endLine, sel.endCol),
          text: aiResult.value,
        }])
        const newEndLine = sel.startLine + (aiResult.value.match(/\n/g) || []).length
        const newEndCol = newEndLine === sel.startLine
          ? sel.startCol + aiResult.value.length
          : aiResult.value.length - aiResult.value.lastIndexOf('\n') - 1
        clearInlineDecoration()
        applyInlineDecoration(sel.startLine, sel.startCol, newEndLine, newEndCol + 1)
      }
    })
    clearInlineDecoration()
    if (!aiResult.value) {
      aiResult.value = sel.text
      editor.executeEdits('ai-inline', [{
        range: new Range(sel.startLine, sel.startCol, sel.endLine, sel.endCol),
        text: sel.text,
      }])
    }
    return aiResult.value
  } catch { return null } finally { aiLoading.value = false; _abortMap.delete('inlineEdit') }
}

export function cancelAiEdit() { _abortOp('aiEdit'); aiLoading.value = false }

export function applyAiResult() {
  const editor = monacoEditor.value
  if (!editor || !aiResult.value) return
  const sel = selection.value
  const Range = (editor as any).monaco?.Range ??
    class R { constructor(public a: number, public b: number, public c: number, public d: number) {} }
  if (sel.text) {
    editor.executeEdits('ai-edit', [{
      range: new Range(sel.startLine, sel.startCol, sel.endLine, sel.endCol),
      text: aiResult.value,
    }])
  } else {
    const pos = editor.getPosition()
    if (pos) {
      editor.executeEdits('ai-edit', [{
        range: new Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
        text: aiResult.value,
      }])
    }
  }
  aiResult.value = ''
}

export function rejectAiResult() { aiResult.value = '' }

export function undoEdit() {
  if (!previousContent.value) return
  const tab = activeTab.value
  if (tab) tab.content = previousContent.value
  previousContent.value = ''
  if (monacoEditor.value) monacoEditor.value.setValue(activeTab.value?.content ?? '')
  showAiPanel.value = false
  aiResult.value = ''
}

// ── Ghost text completion ────────────────────────────────────────────────
let ghostDecoration: string[] = []
let completionTimer: ReturnType<typeof setTimeout> | null = null
let currentSuggestion = ''
let _clearingGhost = false

function clearGhostText() {
  if (_clearingGhost) return
  const editor = monacoEditor.value
  if (!editor) return
  if (ghostDecoration.length) {
    try { _clearingGhost = true; editor.deltaDecorations(ghostDecoration, []) } finally {
      ghostDecoration = []; _clearingGhost = false
    }
  }
  currentSuggestion = ''
}

async function requestCompletion() {
  const editor = monacoEditor.value
  if (!editor) return
  const model = editor.getModel()
  if (!model) return
  const pos = editor.getPosition()
  if (!pos) return
  const startLine = Math.max(1, pos.lineNumber - 15)
  const textBefore = model.getValueInRange({
    startLineNumber: startLine, startColumn: 1,
    endLineNumber: pos.lineNumber, endColumn: pos.column,
  })
  if (textBefore.trim().length < 10) { clearGhostText(); return }
  const signal = _signalFor('completion')
  try {
    const resp = await fetch(`${API_BASE}/api/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: textBefore, max_tokens: 200 }),
      signal,
    })
    if (!resp.ok) { clearGhostText(); return }
    const data = await resp.json()
    const suggestion = (data.completion || '').trim()
    if (!suggestion || suggestion.length < 3) { clearGhostText(); return }
    const currentContent = model.getValueInRange({
      startLineNumber: startLine, startColumn: 1,
      endLineNumber: pos.lineNumber, endColumn: pos.column,
    })
    if (currentContent !== textBefore) { clearGhostText(); return }
    currentSuggestion = suggestion
    const Range = (editor as any).monaco?.Range ??
      class R { constructor(public a: number, public b: number, public c: number, public d: number) {} }
    ghostDecoration = editor.deltaDecorations(ghostDecoration, [{
      range: new Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
      options: {
        after: { content: suggestion, inlineClassName: 'ghost-text-suggestion' },
        className: 'ghost-text-line',
      },
    }])
  } catch { clearGhostText() } finally { _abortMap.delete('completion') }
}

export function triggerCompletion() {
  if (completionTimer) clearTimeout(completionTimer)
  completionTimer = setTimeout(requestCompletion, 1500)
}

export function acceptGhostText(): boolean {
  const editor = monacoEditor.value
  if (!editor || !currentSuggestion) return false
  const pos = editor.getPosition()
  if (!pos) return false
  const Range = (editor as any).monaco?.Range ??
    class R { constructor(public a: number, public b: number, public c: number, public d: number) {} }
  editor.executeEdits('inline-completion', [{
    range: new Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
    text: currentSuggestion,
  }])
  clearGhostText()
  return true
}

export function onDidChangeContent() { triggerCompletion() }

export function cleanup() {
  if (completionTimer) { clearTimeout(completionTimer); completionTimer = null }
  const editor = monacoEditor.value
  if (editor) {
    if (ghostDecoration.length) { try { editor.deltaDecorations(ghostDecoration, []) } catch { /* disposed */ } ghostDecoration = [] }
    if (inlineDecoration.length) { try { editor.deltaDecorations(inlineDecoration, []) } catch { /* disposed */ } inlineDecoration = [] }
  }
  for (const ctrl of _abortMap.values()) ctrl.abort()
  _abortMap.clear()
}
// ── Facade function (returns module-level singletons) ─────────────────────
export function useEditor() {
  return {
    tabs, activeTabId, activeFile, isModified,
    showAiPanel, aiLoading, aiResult, previousContent,
    insertTextAtCursor, insertImage,
    monacoEditor, contentVersion, activeTab, content, selection,
    setEditorInstance, setContent, updateSelection, markClean, markDirty,
    openFile, openNewUntitled, closeTab, setActiveTab, renameTabPath, saveFile,
    aiEdit, inlineEdit, cancelAiEdit, applyAiResult, rejectAiResult, undoEdit,
    triggerCompletion, acceptGhostText, onDidChangeContent, clearGhostText, cleanup,
  }
}
