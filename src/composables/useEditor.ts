import { ref, shallowRef, computed } from 'vue'
import type { EditorSelection, EditorTab } from '../types'
import * as monaco from 'monaco-editor'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
const API = isTauri ? 'http://localhost:18088' : ''

// ── 全局单例状态 ──────────────────────────────────────────────────

const tabs = ref<EditorTab[]>([])
const activeTabId = ref<string | null>(null)
const selection = ref<EditorSelection>({ startLine: 0, endLine: 0, startCol: 0, endCol: 0, text: '' })
const showPreview = ref(true)
const showAiPanel = ref(false)
const aiLoading = ref(false)
const aiResult = ref('')
const monacoEditor = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)
const previousContent = ref('')
const contentVersion = ref(0)  // 递增来强制触发 preview 更新

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) ?? null)
const content = computed(() => activeTab.value?.content ?? '')
const activeFile = computed(() => activeTab.value?.path ?? null)
const isModified = computed(() => activeTab.value?.isModified ?? false)

// ── useEditor ─────────────────────────────────────────────────────

export function useEditor() {

  function setEditorInstance(editor: monaco.editor.IStandaloneCodeEditor) {
    monacoEditor.value = editor
  }

  function setContent(text: string) {
    const tab = activeTab.value
    if (tab) {
      tab.content = text
      contentVersion.value++  // 触发 preview 更新
      // mark modified only after initial load; use markClean to reset
    }
  }

  function updateSelection(sel: EditorSelection) {
    selection.value = sel
  }

  function markClean() {
    const tab = activeTab.value
    if (tab) tab.isModified = false
  }

  // ── Tab 管理 ───────────────────────────────────────────────────

  function openFile(path: string, text: string = '') {
    // 已打开则激活
    const existing = tabs.value.find(t => t.path === path)
    if (existing) {
      activeTabId.value = existing.id
      if (text) existing.content = text
      return
    }
    // 新建 tab
    const name = path.split(/[\\/]/).pop() || 'Untitled'
    const tab: EditorTab = {
      id: path,
      path,
      name,
      content: text,
      isModified: false,
    }
    tabs.value.push(tab)
    activeTabId.value = tab.id
  }

  function openNewUntitled() {
    const id = `untitled-${Date.now()}`
    const tab: EditorTab = {
      id,
      path: null,
      name: 'Untitled',
      content: '',
      isModified: false,
    }
    tabs.value.push(tab)
    activeTabId.value = tab.id
  }

  function closeTab(id: string) {
    const idx = tabs.value.findIndex(t => t.id === id)
    if (idx === -1) return

    tabs.value.splice(idx, 1)

    // 尝试激活邻居 tab
    if (activeTabId.value === id) {
      if (tabs.value.length === 0) {
        activeTabId.value = null
      } else if (idx >= tabs.value.length) {
        // 关闭的是最后一个，激活前一个
        activeTabId.value = tabs.value[tabs.value.length - 1].id
      } else {
        // 激活下一个
        activeTabId.value = tabs.value[idx].id
      }
    }
  }

  function setActiveTab(id: string) {
    if (tabs.value.some(t => t.id === id)) {
      activeTabId.value = id
    }
  }

  async function saveFile(): Promise<string | null> {
    const tab = activeTab.value
    if (!tab || !tab.path) {
      return '无法保存：请先导出到文件（未命名文件暂不支持直接保存）'
    }
    const { writeTextFile } = await import('@tauri-apps/plugin-fs')
    await writeTextFile(tab.path, tab.content)
    tab.isModified = false
    return null
  }

  // 内容变化时标记 dirty（由 Monaco 的 onDidChangeModelContent 调用）
  function markDirty() {
    const tab = activeTab.value
    if (tab) {
      tab.isModified = true
      contentVersion.value++  // 每次变化触发 preview 刷新
    }
  }

  // ── AI Edit ────────────────────────────────────────────────────

  let abortController: AbortController | null = null

  async function aiEdit(instruction: string, text?: string, taskType?: string, previous?: string) {
    const targetText = text || selection.value.text
    if (!instruction) return

    // 保存当前内容用于 undo
    previousContent.value = content.value

    // 取消上一次未完成的请求
    if (abortController) abortController.abort()
    abortController = new AbortController()

    aiLoading.value = true
    aiResult.value = ''

    try {
      const payload: Record<string, string> = { text: targetText, instruction }
      if (taskType) payload.task_type = taskType
      if (previous) payload.previous = previous

      const resp = await fetch(`${API}/api/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: abortController.signal,
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('No response body')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw)
            if (evt.content) {
              aiResult.value = evt.content
            }
          } catch {
            // ignore parse errors
          }
        }
      }
      if (!aiResult.value) {
        aiResult.value = 'AI 未返回结果，请重试。'
      }
    } catch (e: any) {
      if (e.name === 'AbortError') {
        // 用户主动取消，不清空结果
        return
      }
      aiResult.value = `请求失败: ${e}`
    } finally {
      aiLoading.value = false
      abortController = null
    }
  }

  // ── AI Inline Edit ─────────────────────────────────────────────
  // 直接替换 Monaco 选中文本，流式写入，带高亮动画

  let inlineDecoration: string[] = []

  function applyInlineDecoration(editor: monaco.editor.IStandaloneCodeEditor, startLine: number, startCol: number, endLine: number, endCol: number) {
    inlineDecoration = editor.deltaDecorations([], [{
      range: new monaco.Range(startLine, startCol, endLine, endCol),
      options: {
        className: 'ai-inline-edit',
        inlineClassName: 'ai-inline-edit-char',
      },
    }])
  }

  function clearInlineDecoration(editor: monaco.editor.IStandaloneCodeEditor) {
    if (inlineDecoration.length) {
      editor.deltaDecorations(inlineDecoration, [])
      inlineDecoration = []
    }
  }

  async function inlineEdit(instruction: string, taskType?: string): Promise<string | null> {
    const editor = monacoEditor.value
    const sel = selection.value
    if (!editor || !sel.text) return null

    const startLine = sel.startLine
    const startCol = sel.startCol
    const endLine = sel.endLine
    const endCol = sel.endCol

    // 保存原文用于 undo
    previousContent.value = content.value

    if (abortController) abortController.abort()
    abortController = new AbortController()

    aiLoading.value = true
    aiResult.value = ''

    try {
      const resp = await fetch(`${API}/api/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: sel.text, instruction, task_type: taskType || 'expand' }),
        signal: abortController.signal,
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('No response body')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      applyInlineDecoration(editor, startLine, startCol, endLine, endCol)

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw) continue
          try {
            const evt = JSON.parse(raw)
            if (evt.content) {
              aiResult.value = (aiResult.value || '') + evt.content
              // 实时替换选中文本
              editor.executeEdits('ai-inline', [{
                range: new monaco.Range(startLine, startCol, endLine, endCol),
                text: aiResult.value,
              }])
              // 更新 range 以便下次追加
              const newEndLine = startLine + (aiResult.value.match(/\n/g) || []).length
              const newEndCol = newEndLine === startLine ? startCol + aiResult.value.length : aiResult.value.length - aiResult.value.lastIndexOf('\n') - 1
              clearInlineDecoration(editor)
              applyInlineDecoration(editor, startLine, startCol, newEndLine, newEndCol + 1)
            }
          } catch {
            // ignore parse errors
          }
        }
      }

      clearInlineDecoration(editor)
      if (!aiResult.value) {
        aiResult.value = sel.text
        editor.executeEdits('ai-inline', [{
          range: new monaco.Range(startLine, startCol, endLine, endCol),
          text: sel.text,
        }])
      }
      return aiResult.value
    } catch (e: any) {
      clearInlineDecoration(editor)
      return null
    } finally {
      aiLoading.value = false
      abortController = null
    }
  }

  function cancelAiEdit() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    aiLoading.value = false
  }

  function applyAiResult() {
    if (!monacoEditor.value || !aiResult.value) return
    const editor = monacoEditor.value
    const sel = selection.value

    if (sel.text) {
      const range = {
        startLineNumber: sel.startLine,
        startColumn: sel.startCol,
        endLineNumber: sel.endLine,
        endColumn: sel.endCol,
      }
      editor.executeEdits('ai-edit', [{ range, text: aiResult.value }])
    } else {
      const pos = editor.getPosition()
      if (pos) {
        editor.executeEdits('ai-edit', [{
          range: {
            startLineNumber: pos.lineNumber,
            startColumn: pos.column,
            endLineNumber: pos.lineNumber,
            endColumn: pos.column,
          },
          text: aiResult.value,
        }])
      }
    }
    // 插入后不清除结果、不关闭面板，用户可以继续操作
    aiResult.value = ''
  }

  function rejectAiResult() {
    aiResult.value = ''
    // 不关闭面板
  }

  function undoEdit() {
    if (!previousContent.value) return
    const tab = activeTab.value
    if (tab) tab.content = previousContent.value
    previousContent.value = ''
    if (monacoEditor.value) {
      monacoEditor.value.setValue(activeTab.value?.content ?? '')
    }
    showAiPanel.value = false
    aiResult.value = ''
  }

  return {
    // state
    tabs,
    activeTabId,
    activeTab,
    content,
    activeFile,
    isModified,
    selection,
    showPreview,
    showAiPanel,
    aiLoading,
    aiResult,
    monacoEditor,
    previousContent,
    contentVersion,
    // methods
    setEditorInstance,
    setContent,
    updateSelection,
    markClean,
    markDirty,
    openFile,
    openNewUntitled,
    closeTab,
    setActiveTab,
    saveFile,
    aiEdit,
    inlineEdit,
    cancelAiEdit,
    applyAiResult,
    rejectAiResult,
    undoEdit,
  }
}
