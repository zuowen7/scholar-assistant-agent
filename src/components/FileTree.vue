<template>
  <div class="file-tree">
    <div class="tree-header">
      <span class="tree-title" :title="rootDir || '资源管理器'">{{ rootDir ? rootDir.split(/[\\/]/).pop() : '资源管理器' }}</span>
      <div class="tree-actions">
        <button class="tree-btn" @click="handleNewFile" title="新建文件" aria-label="新建文件">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button class="tree-btn" @click="handleOpenFolder" title="打开文件夹" aria-label="打开文件夹">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
        <button class="tree-btn" :class="{ spinning: refreshing }" @click="handleRefresh" title="刷新" aria-label="刷新" :disabled="refreshing">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
        </button>
        <div class="tree-btn-sep" />
        <button class="tree-btn" @click="$emit('collapse')" title="折叠侧栏" aria-label="折叠侧栏">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
      </div>
    </div>

    <!-- 搜索框 -->
    <div class="tree-search" v-if="rootDir">
      <svg class="search-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="搜索文件..."
        @keydown.escape="searchQuery = ''"
      />
      <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>

    <div class="tree-body" v-if="rootDir">
      <!-- 目录加载骨架 -->
      <div v-if="loading" class="tree-loading">
        <div
          v-for="i in 8"
          :key="i"
          class="tree-loading-row"
          :style="{ paddingLeft: (i % 3 === 0 ? 24 : 8) + 'px', '--stagger-i': i - 1 } as any"
        >
          <UiSkeleton shape="circle" :width="13" :height="13" />
          <UiSkeleton shape="line" :width="`${48 + (i * 17) % 42}%`" :height="10" />
        </div>
      </div>
      <template v-else>
        <FileTreeNode
          v-for="(entry, i) in filteredFiles"
          :key="entry.path"
          :entry="entry"
          :depth="0"
          :active-file="activeFile"
          :style="{ '--stagger-i': Math.min(i, 14) } as any"
          class="anim-fade-in-up anim-stagger"
          @select="handleSelect"
          @action="handleAction"
        />
        <div v-if="searchQuery && filteredFiles.length === 0" class="tree-no-match anim-fade-in-up">
          没有匹配 "{{ searchQuery }}" 的文件
        </div>
      </template>
    </div>
    <UiEmpty
      v-else
      :icon="FolderOpen"
      :icon-size="28"
      title="未打开文件夹"
      subtitle="Open a folder to browse your files."
      action-label="打开文件夹"
      @action="handleOpenFolder"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import FileTreeNode from './FileTreeNode.vue'
import UiEmpty from './ui/UiEmpty.vue'
import UiSkeleton from './ui/UiSkeleton.vue'
import { FolderOpen } from './ui/icons'
import { useFileTree } from '../composables/useFileTree'
import { useEditor } from '../composables/useEditor'
import type { FileEntry } from '../types'

const { files, rootDir, openFolder, readFileContent, createFile, renameFile, deleteFile, copyFileTo, setClipboard, getClipboard, clearClipboard, refresh } = useFileTree()
const { openFile: openEditorFile, activeFile, renameTabPath, closeTab } = useEditor()

defineEmits<{ (e: 'collapse'): void }>()

const searchQuery = ref('')
const loading = ref(false)
const refreshing = ref(false)

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
  } catch { /* cancelled */ }
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
  const name = prompt('文件名：', 'untitled.md')
  if (!name) return
  const path = await createFile(rootDir.value, name)
  openEditorFile(path, '')
}

async function handleRefresh() {
  if (rootDir.value) {
    await openFolder(rootDir.value)
  }
}

async function handleAction(action: string, path: string, extra: string) {
  switch (action) {
    case 'cut':
      setClipboard('cut', path, extra, false)
      break

    case 'copy':
      setClipboard('copy', path, extra, false)
      break

    case 'paste': {
      const cb = getClipboard()
      if (!cb) return
      try {
        const newPath = await copyFileTo(cb.path, path)
        // If it was a cut, delete source and clear clipboard
        if (cb.action === 'cut') {
          await deleteFile(cb.path)
          closeTab(cb.path)
          clearClipboard()
        }
      } catch (e) {
        console.error('Paste failed:', e)
      }
      break
    }

    case 'rename':
      try {
        const newPath = await renameFile(path, extra)
        renameTabPath(path, newPath)
      } catch (e) {
        console.error('Rename failed:', e)
      }
      break

    case 'delete':
      if (!confirm(`Delete "${extra}"?`)) return
      try {
        await deleteFile(path)
        closeTab(path)
      } catch (e) {
        console.error('Delete failed:', e)
      }
      break

    case 'copy-path':
      try {
        await navigator.clipboard.writeText(path)
      } catch {
        // Fallback: not available in some environments
      }
      break
  }
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
  border-right: 1px solid var(--c-surface-3);
  user-select: none;
}

.tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--c-surface-3);
}

.tree-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--c-text-3);
}

.tree-actions { display: flex; gap: 4px; }

.tree-btn {
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  position: relative;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}
.tree-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
/* 墨韵涟漪 */
.tree-btn::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: inherit;
  background: radial-gradient(circle at center, var(--c-accent) 0%, transparent 70%);
  opacity: 0;
  transform: scale(0.7);
  transition: opacity 300ms var(--ease-brush), transform 340ms var(--ease-brush);
  pointer-events: none;
  filter: blur(4px);
}
.tree-btn:hover::after { opacity: 0.1; transform: scale(1.15); }

.tree-btn-sep {
  width: 1px;
  height: 14px;
  background: var(--c-surface-3);
  align-self: center;
}

.tree-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-bottom: 1px solid var(--c-surface-3);
  background: var(--sidebar-bg);
}

.search-icon { color: var(--c-text-3); flex-shrink: 0; }

.search-input {
  flex: 1;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-control);
  padding: 4px 8px;
  color: var(--c-text-0);
  font-size: 12px;
  outline: none;
  transition: border-color var(--motion-fast) var(--ease-out),
              box-shadow var(--motion-fast) var(--ease-out);
}
.search-input:focus {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-ring);
}
.search-input::placeholder { color: var(--c-text-3); }

.search-clear {
  background: none;
  border: none;
  color: var(--c-text-3);
  cursor: pointer;
  padding: 2px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  transition: color var(--motion-fast);
}
.search-clear:hover { color: var(--c-text-0); }

.tree-body { flex: 1; overflow-y: auto; padding: 4px 0; }

.tree-no-match {
  padding: 12px 16px;
  font-size: 12px;
  color: var(--c-text-3);
  font-style: italic;
}

</style>
