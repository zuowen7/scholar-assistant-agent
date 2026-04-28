/**
 * useEditorTabs — Tab 管理、Monaco 实例注入、文件操作
 *
 * 状态来源：useEditorState（单一真实源）
 * 导出的函数构成 EditorLayout / MonacoEditor 等组件的 API。
 */
import type { EditorSelection, EditorTab } from '../types'
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
  tabs.value.push({ id: path, path, name, content: text, isModified: false })
  activeTabId.value = path
}

function openNewUntitled() {
  const id = `untitled-${Date.now()}`
  tabs.value.push({ id, path: null, name: 'Untitled', content: '', isModified: false })
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

async function saveFile(): Promise<string | null> {
  const tab = activeTab.value
  if (!tab || !tab.path) return '无法保存：请先导出到文件'
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
}