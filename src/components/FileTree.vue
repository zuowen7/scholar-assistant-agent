<template>
  <div class="file-tree">
    <div class="tree-header">
      <span class="tree-title">Explorer</span>
      <div class="tree-actions">
        <button class="tree-btn" @click="handleNewFile" title="New File">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button class="tree-btn" @click="handleOpenFolder" title="Open Folder">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
      </div>
    </div>

    <!-- 搜索框 -->
    <div class="tree-search" v-if="rootDir">
      <svg class="search-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="Search files..."
        @keydown.escape="searchQuery = ''"
      />
      <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>

    <div class="tree-body" v-if="rootDir">
      <FileTreeNode
        v-for="entry in filteredFiles"
        :key="entry.path"
        :entry="entry"
        :depth="0"
        :active-file="activeFile"
        @select="handleSelect"
      />
      <div v-if="searchQuery && filteredFiles.length === 0" class="tree-no-match">
        No matches for "{{ searchQuery }}"
      </div>
    </div>
    <div class="tree-empty" v-else>
      <p>No folder opened</p>
      <button class="tree-btn-open" @click="handleOpenFolder">Open Folder</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import FileTreeNode from './FileTreeNode.vue'
import { useFileTree } from '../composables/useFileTree'
import { useEditor } from '../composables/useEditor'
import type { FileEntry } from '../types'

const { files, rootDir, openFolder, readFileContent, createFile } = useFileTree()
const { openFile: openEditorFile, activeFile } = useEditor()

const searchQuery = ref('')

// 递归过滤：匹配的文件/目录 + 包含匹配子孙的目录
function filterTree(entries: FileEntry[], query: string): FileEntry[] {
  if (!query) return entries
  const q = query.toLowerCase()
  const result: FileEntry[] = []
  for (const entry of entries) {
    if (entry.name.toLowerCase().includes(q)) {
      result.push(entry)
    } else if (entry.isDir && entry.children) {
      const sub = filterTree(entry.children, query)
      if (sub.length > 0) {
        result.push({ ...entry, children: sub })
      }
    }
  }
  return result
}

const filteredFiles = computed(() => filterTree(files.value, searchQuery.value))

async function handleOpenFolder() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, multiple: false })
    if (selected && typeof selected === 'string') {
      await openFolder(selected)
    }
  } catch {
    // dialog cancelled
  }
}

async function handleOpenWorkspaceFolder(e: Event) {
  const path = (e as CustomEvent<{ path?: string | string[] }>).detail?.path
  if (typeof path === 'string') {
    await openFolder(path)
  }
}

async function handleSelect(entry: FileEntry) {
  if (entry.isDir) return
  const text = await readFileContent(entry.path)
  openEditorFile(entry.path, text)
}

async function handleNewFile() {
  if (!rootDir.value) {
    await handleOpenFolder()
    return
  }
  const name = prompt('File name:', 'untitled.md')
  if (!name) return
  const path = await createFile(rootDir.value, name)
  openEditorFile(path, '')
}

onMounted(() => {
  window.addEventListener('open-workspace-folder', handleOpenWorkspaceFolder as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('open-workspace-folder', handleOpenWorkspaceFolder as EventListener)
})
</script>

<style scoped>
.file-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-color);
  user-select: none;
}

.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.tree-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-secondary);
}

.tree-actions { display: flex; gap: 4px; }

.tree-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
}
.tree-btn:hover { background: var(--hover-bg); color: var(--text-primary); }

.tree-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-bottom: 1px solid var(--border-color);
  background: var(--sidebar-bg);
}

.search-icon { color: var(--text-secondary); flex-shrink: 0; }

.search-input {
  flex: 1;
  background: var(--input-bg);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  padding: 3px 8px;
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
}
.search-input:focus { border-color: var(--accent); }
.search-input::placeholder { color: var(--text-secondary); }

.search-clear {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px;
  border-radius: 3px;
  display: flex;
  align-items: center;
}
.search-clear:hover { color: var(--text-primary); }

.tree-body { flex: 1; overflow-y: auto; padding: 4px 0; }

.tree-no-match {
  padding: 12px 16px;
  font-size: 12px;
  color: var(--text-secondary);
  font-style: italic;
}

.tree-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.tree-btn-open {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 6px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.tree-btn-open:hover { opacity: 0.9; }
</style>
