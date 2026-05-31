/**
 * useEditorState — 全局单例状态（唯一真实源）
 *
 * 单一模块级状态，所有 composable 共享同一个 ref 实例。
 * 禁止在此文件之外定义 tab / selection / monacoEditor 等状态。
 */
import { ref, shallowRef, computed } from 'vue'
import type { EditorSelection, EditorTab } from '../types'
import * as monaco from 'monaco-editor'

export const tabs = ref<EditorTab[]>([])
export const activeTabId = ref<string | null>(null)
export const selection = ref<EditorSelection>({ startLine: 0, endLine: 0, startCol: 0, endCol: 0, text: '' })
export const monacoEditor = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)
export const contentVersion = ref(0)  // 递增以强制触发 preview 更新

export const activeTab = computed(() =>
  tabs.value.find(t => t.id === activeTabId.value) ?? null
)
export const content = computed(() => activeTab.value?.content ?? '')
export const activeFile = computed(() => activeTab.value?.path ?? null)
export const isModified = computed(() => activeTab.value?.isModified ?? false)

// ── AI 编辑状态 ─────────────────────────────────────────────────────────
export const showAiPanel = ref(true)
export const aiLoading = ref(false)
export const aiResult = ref('')
export const previousContent = ref('')

// ── Monaco Range helper ──────────────────────────────────────────────────

// Monaco-compatible Range fallback — uses the correct IRange property names
// so executeEdits works even when the editor instance lacks a .monaco reference.
class _MonacoRange {
  startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number
  constructor(sl: number, sc: number, el: number, ec: number) {
    this.startLineNumber = sl; this.startColumn = sc; this.endLineNumber = el; this.endColumn = ec
  }
}

export function getRange(editor: any) {
  return (editor as any).monaco?.Range ?? _MonacoRange
}

// ── Text insertion helpers (依赖 Monaco editor 实例) ──────────────────

export function insertTextAtCursor(text: string): boolean {
  const editor = monacoEditor.value
  if (!editor) return false
  const Range = getRange(editor)
  const pos = editor.getPosition()
  const range = pos
    ? new Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column)
    : new Range(1, 1, 1, 1)
  editor.executeEdits('insert-markdown', [{ range, text }])
  editor.focus()
  return true
}

export function insertImage(url: string, alt = 'image') {
  return insertTextAtCursor(`\n![${alt}](${url})\n`)
}

export function useEditorState() {
  return {
    tabs,
    activeTabId,
    selection,
    monacoEditor,
    contentVersion,
    activeTab,
    content,
    activeFile,
    isModified,
    showAiPanel,
    aiLoading,
    aiResult,
    previousContent,
    insertTextAtCursor,
    insertImage,
  }
}
