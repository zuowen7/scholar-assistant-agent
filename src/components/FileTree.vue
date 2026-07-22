<template>
  <div class="file-tree">
    <div class="tree-header">
      <span class="tree-title" :title="rootDir || t('files.explorer')">{{ rootDir ? rootDir.split(/[\\/]/).pop() : t('files.explorer') }}</span>
      <div class="tree-actions">
        <button class="tree-btn" @click="handleNewFile" :title="t('files.newFile')" :aria-label="t('files.newFile')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button class="tree-btn" @click="handleNewFolder" :title="t('files.newFolder')" :aria-label="t('files.newFolder')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 10v6M9 13h6"/><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
        <button class="tree-btn" @click="handleOpenFolder" :title="t('files.openFolder2')" :aria-label="t('files.openFolder2')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
        <button class="tree-btn" :class="{ spinning: refreshing }" @click="handleRefresh" :title="t('files.refresh')" :aria-label="t('files.refresh')" :disabled="refreshing">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
        </button>
        <div class="tree-btn-sep" />
        <button class="tree-btn" @click="$emit('collapse')" :title="t('files.collapseSidebar')" :aria-label="t('files.collapseSidebar')">
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
        :placeholder="t('files.searchPlaceholder')"
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
          {{ t('files.noMatch', { query: searchQuery }) }}
        </div>
      </template>
    </div>
    <UiEmpty
      v-else
      :icon="FolderOpen"
      :icon-size="28"
      :title="t('files.noFolderOpen')"
      :subtitle="t('files.noFolderSubtitle')"
      :action-label="t('files.openFolder2')"
      @action="handleOpenFolder"
    />

    <AppPromptDialog
      v-model="showCreatePrompt"
      :title="createKind === 'file' ? t('files.newFile') : t('files.newFolder')"
      :description="t('files.createDescription')"
      :label="t('files.fileName')"
      :initial-value="createKind === 'file' ? 'untitled.md' : 'new_folder'"
      :confirm-label="t('general.create')"
      :cancel-label="t('general.cancel')"
      :error="createError"
      :busy="createBusy"
      @submit="confirmCreate"
    />

    <AppConfirmDialog
      v-model="showDeleteConfirm"
      :title="t('files.deleteConfirmTitle')"
      :description="t('files.deleteConfirmDescription')"
      :detail="t('files.deleteConfirmDetail', { name: pendingDelete?.name || '' })"
      :confirm-label="t('files.delete')"
      :cancel-label="t('general.cancel')"
      tone="danger"
      :busy="deleteBusy"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import FileTreeNode from './FileTreeNode.vue'
import UiEmpty from './ui/UiEmpty.vue'
import UiSkeleton from './ui/UiSkeleton.vue'
import AppPromptDialog from './shell/AppPromptDialog.vue'
import AppConfirmDialog from './shell/AppConfirmDialog.vue'
import { FolderOpen } from './ui/icons'
import { useFileTree } from '../composables/useFileTree'
import { useEditor } from '../composables/useEditor'
import { useToast } from '../composables/useToast'
import type { FileEntry } from '../types'
import { open as openDialog } from '@tauri-apps/plugin-dialog'

const { files, rootDir, openFolder, readFileContent, createFile, createFolder, renameFile, deleteFile, copyFileTo, setClipboard, getClipboard, clearClipboard } = useFileTree()
const { openFile: openEditorFile, activeFile, renameTabPath, closeTab } = useEditor()
const { success, pushError } = useToast()

defineEmits<{ (e: 'collapse'): void }>()

const searchQuery = ref('')
const deferredSearchQuery = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null
const loading = ref(false)
const refreshing = ref(false)
const showCreatePrompt = ref(false)
const createKind = ref<'file' | 'folder'>('file')
const createTarget = ref('')
const createBusy = ref(false)
const createError = ref('')
const showDeleteConfirm = ref(false)
const pendingDelete = ref<{ path: string; name: string } | null>(null)
const deleteBusy = ref(false)

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

watch(searchQuery, (query) => {
  if (searchTimer !== null) clearTimeout(searchTimer)
  if (!query) {
    searchTimer = null
    deferredSearchQuery.value = ''
    return
  }
  searchTimer = setTimeout(() => {
    searchTimer = null
    deferredSearchQuery.value = query
  }, 100)
})

const filteredFiles = computed(() => filterTree(files.value, deferredSearchQuery.value))

async function handleOpenFolder() {
  try {
    const selected = await openDialog({ directory: true, multiple: false })
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
  openCreatePrompt('file', rootDir.value)
}

async function handleNewFolder() {
  if (!rootDir.value) {
    await handleOpenFolder()
    return
  }
  openCreatePrompt('folder', rootDir.value)
}

function openCreatePrompt(kind: 'file' | 'folder', target: string) {
  createKind.value = kind
  createTarget.value = target
  createError.value = ''
  showCreatePrompt.value = true
}

async function confirmCreate(name: string) {
  createBusy.value = true
  createError.value = ''
  try {
    if (createKind.value === 'file') {
      const path = await createFile(createTarget.value, name)
      openEditorFile(path, '')
    } else {
      await createFolder(createTarget.value, name)
    }
    showCreatePrompt.value = false
  } catch (error) {
    createError.value = error instanceof Error ? error.message : String(error)
  } finally {
    createBusy.value = false
  }
}

async function confirmDelete() {
  if (!pendingDelete.value) return
  deleteBusy.value = true
  try {
    await deleteFile(pendingDelete.value.path)
    closeTab(pendingDelete.value.path)
    showDeleteConfirm.value = false
    pendingDelete.value = null
  } catch (error) {
    pushError(t('files.operationFailed', { message: error instanceof Error ? error.message : String(error) }))
  } finally {
    deleteBusy.value = false
  }
}

async function handleRefresh() {
  if (rootDir.value) {
    await openFolder(rootDir.value)
  }
}

async function handleAction(action: string, path: string, extra: string) {
  switch (action) {
    case 'new-file': {
      if (!extra) {
        openCreatePrompt('file', path)
        break
      }
      const newFile = await createFile(path, extra)
      openEditorFile(newFile, '')
      break
    }

    case 'new-folder':
      if (!extra) openCreatePrompt('folder', path)
      else await createFolder(path, extra)
      break

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
        await copyFileTo(cb.path, path)
        // If it was a cut, delete source and clear clipboard
        if (cb.action === 'cut') {
          await deleteFile(cb.path)
          closeTab(cb.path)
          clearClipboard()
        }
      } catch (e) {
        pushError(t('files.operationFailed', { message: e instanceof Error ? e.message : String(e) }))
      }
      break
    }

    case 'rename':
      try {
        const newPath = await renameFile(path, extra)
        renameTabPath(path, newPath)
      } catch (e) {
        pushError(t('files.operationFailed', { message: e instanceof Error ? e.message : String(e) }))
      }
      break

    case 'delete':
      pendingDelete.value = { path, name: extra }
      showDeleteConfirm.value = true
      break

    case 'copy-path':
      try {
        await navigator.clipboard.writeText(path)
        success(t('files.pathCopied'))
      } catch {
        pushError(t('files.operationFailed', { message: t('files.clipboardUnavailable') }))
      }
      break
  }
}

onMounted(() => {
  window.addEventListener('open-workspace-folder', handleOpenWorkspaceFolder as EventListener)
})

onBeforeUnmount(() => {
  if (searchTimer !== null) clearTimeout(searchTimer)
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
