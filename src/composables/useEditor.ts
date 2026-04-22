import { ref, shallowRef, computed } from 'vue'
import type { EditorSelection, EditorTab } from '../types'

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
const monacoEditor = shallowRef<any>(null)
const previousContent = ref('')

const activeTab = computed(() => tabs.value.find(t => t.id === activeTabId.value) ?? null)
const content = computed(() => activeTab.value?.content ?? '')
const activeFile = computed(() => activeTab.value?.path ?? null)
const isModified = computed(() => activeTab.value?.isModified ?? false)

// ── useEditor ─────────────────────────────────────────────────────

export function useEditor() {

  function setEditorInstance(editor: any) {
    monacoEditor.value = editor
  }

  function setContent(text: string) {
    const tab = activeTab.value
    if (tab) {
      tab.content = text
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

  async function saveFile(): Promise<void> {
    const tab = activeTab.value
    if (!tab || !tab.path) return
    const { writeTextFile } = await import('@tauri-apps/plugin-fs')
    await writeTextFile(tab.path, tab.content)
    tab.isModified = false
  }

  // 内容变化时标记 dirty（由 Monaco 的 onDidChangeModelContent 调用）
  function markDirty() {
    const tab = activeTab.value
    if (tab) tab.isModified = true
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
    cancelAiEdit,
    applyAiResult,
    rejectAiResult,
    undoEdit,
  }
}
