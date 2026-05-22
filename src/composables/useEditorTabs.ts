/**
 * useEditorTabs — Tab 管理、Monaco 实例注入、文件操作
 *
 * 状态来源：useEditorState（单一真实源）
 * 导出的函数构成 EditorLayout / MonacoEditor 等组件的 API。
 */
import type { EditorSelection } from '../types'
import {
  tabs, activeTabId, selection, monacoEditor, contentVersion,
  activeTab, content, activeFile, isModified,
} from './useEditorState'

function setContent(text: string) {
  const tab = activeTab.value
  if (tab) { tab.content = text; contentVersion.value++ }
}

function updateSelection(sel: EditorSelection) {
  selection.value = sel
}

function markClean() {
  const tab = activeTab.value
  if (tab) tab.isModified = false
}

function markDirty() {
  const tab = activeTab.value
  if (tab) { tab.isModified = true; contentVersion.value++ }
}

function openFile(path: string, text = '') {
  const existing = tabs.value.find(t => t.path === path)
  if (existing) {
    activeTabId.value = existing.id
    if (text) existing.content = text
    return
  }
  const name = path.split(/[\\/]/).pop() || 'Untitled'
  tabs.value.push({ id: path, path, name, content: text, isModified: false, docId: path })
  activeTabId.value = path
}

function openNewUntitled() {
  const id = `untitled-${Date.now()}`
  const docId = `untitled-${crypto.randomUUID()}`
  tabs.value.push({ id, path: null, name: 'Untitled', content: '', isModified: false, docId })
  activeTabId.value = id
}

function closeTab(id: string) {
  const idx = tabs.value.findIndex(t => t.id === id)
  if (idx === -1) return
  tabs.value.splice(idx, 1)
  if (activeTabId.value === id) {
    if (tabs.value.length === 0) {
      activeTabId.value = null
    } else if (idx >= tabs.value.length) {
      activeTabId.value = tabs.value[tabs.value.length - 1].id
    } else {
      activeTabId.value = tabs.value[idx].id
    }
  }
}

function setActiveTab(id: string) {
  if (tabs.value.some(t => t.id === id)) activeTabId.value = id
}

function renameTabPath(oldPath: string, newPath: string) {
  const tab = tabs.value.find(t => t.path === oldPath)
  if (tab) {
    tab.path = newPath; tab.id = newPath
    tab.name = newPath.split(/[\\/]/).pop() || tab.name
    if (activeTabId.value === oldPath) activeTabId.value = newPath
  }
}

function setEditorInstance(editor: import('monaco-editor').editor.IStandaloneCodeEditor) {
  monacoEditor.value = editor
}

/**
 * Reload all open tabs that have a path by re-reading from disk.
 * Called after the Agent writes/modifies files so Monaco shows fresh content.
 * Only reloads tabs that are NOT modified (unsaved user edits are preserved).
 * For the active tab the Monaco model value is also updated in-place.
 */
async function reloadOpenTabs(): Promise<void> {
  let readTextFile: ((path: string) => Promise<string>) | null = null
  try {
    const fs = await import('@tauri-apps/plugin-fs')
    readTextFile = fs.readTextFile
  } catch {
    return  // Not running in Tauri — file reload not available in web mode
  }
  for (const tab of tabs.value) {
    if (!tab.path) continue
    // Skip tabs with unsaved user edits to avoid clobbering their work.
    if (tab.isModified) continue
    try {
      const fresh = await readTextFile!(tab.path)
      if (fresh === tab.content) continue  // no change — skip expensive Monaco update
      tab.content = fresh
      contentVersion.value++
      // If this is the active tab, push the new content into Monaco immediately.
      if (tab.id === activeTabId.value && monacoEditor.value) {
        const model = monacoEditor.value.getModel()
        if (model) {
          // Preserve cursor position across the reload.
          const pos = monacoEditor.value.getPosition()
          model.setValue(fresh)
          if (pos) monacoEditor.value.setPosition(pos)
        }
      }
    } catch {
      // File may have been deleted or path changed — silently skip.
    }
  }
}

async function saveFile(): Promise<string | null> {
  const tab = activeTab.value
  if (!tab) return null

  // Untitled tab — prompt Save As dialog
  if (!tab.path) {
    try {
      const { save } = await import('@tauri-apps/plugin-dialog')
      const chosen = await save({
        defaultPath: `${tab.name || 'untitled'}.md`,
        filters: [{ name: 'Markdown', extensions: ['md'] }],
      })
      if (!chosen) return null  // user cancelled
      const { writeTextFile } = await import('@tauri-apps/plugin-fs')
      await writeTextFile(chosen, tab.content)
      tab.path = chosen
      tab.id = chosen
      tab.name = chosen.split(/[\\/]/).pop() || tab.name
      tab.isModified = false
      return null
    } catch {
      return '无法保存：请先导出到文件'
    }
  }

  // Named tab — save in place
  const { writeTextFile } = await import('@tauri-apps/plugin-fs')
  await writeTextFile(tab.path, tab.content)
  tab.isModified = false
  return null
}

export {
  tabs, activeTabId, activeTab, content, activeFile, isModified,
  monacoEditor, contentVersion, selection,
  setEditorInstance, setContent, updateSelection, markClean, markDirty,
  openFile, openNewUntitled, closeTab, setActiveTab, renameTabPath, saveFile,
  reloadOpenTabs,
}