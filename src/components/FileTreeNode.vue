<template>
  <div class="tree-node" @contextmenu.prevent="showContextMenu">
    <div
      class="tree-item"
      :class="{ active: activeFile === entry.path, dir: entry.isDir, renaming: isRenaming }"
      :style="{ paddingLeft: depth * 16 + 8 + 'px' }"
      @click="handleClick"
    >
      <span class="tree-icon">{{ entry.isDir ? (expanded ? '📂' : '📁') : '📄' }}</span>
      <template v-if="isRenaming">
        <input
          ref="renameInput"
          class="rename-input"
          :value="newName"
          @input="newName = ($event.target as HTMLInputElement).value"
          @keydown.enter="confirmRename"
          @keydown.escape="cancelRename"
          @blur="confirmRename"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="tree-name">{{ entry.name }}</span>
      </template>
    </div>
    <template v-if="entry.isDir && expanded && entry.children">
      <FileTreeNode
        v-for="child in entry.children"
        :key="child.path"
        :entry="child"
        :depth="depth + 1"
        :active-file="activeFile"
        @select="(e: FileEntry) => $emit('select', e)"
        @rename="(p: string, n: string) => $emit('rename', p, n)"
        @delete="(p: string) => $emit('delete', p)"
      />
    </template>
  </div>

  <!-- Context menu -->
  <Teleport to="body">
    <div v-if="contextMenu.visible" class="ctx-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click="contextMenu.visible = false">
      <button class="ctx-item" @click="startRename">Rename</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, nextTick, reactive } from 'vue'
import type { FileEntry } from '../types'

const props = defineProps<{
  entry: FileEntry
  depth: number
  activeFile: string | null
}>()

const emit = defineEmits<{
  (e: 'select', entry: FileEntry): void
  (e: 'rename', oldPath: string, newName: string): void
  (e: 'delete', path: string): void
}>()

const expanded = ref(false)
const isRenaming = ref(false)
const newName = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const contextMenu = reactive({ visible: false, x: 0, y: 0 })

function handleClick() {
  if (props.entry.isDir) {
    expanded.value = !expanded.value
  } else {
    emit('select', props.entry)
  }
}

function showContextMenu(e: MouseEvent) {
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.visible = true

  const close = () => { contextMenu.visible = false; document.removeEventListener('click', close) }
  setTimeout(() => document.addEventListener('click', close), 0)
}

function startRename() {
  newName.value = props.entry.name
  isRenaming.value = true
  nextTick(() => {
    renameInput.value?.focus()
    // Select name without extension
    const dotIdx = props.entry.name.lastIndexOf('.')
    renameInput.value?.setSelectionRange(0, dotIdx > 0 ? dotIdx : props.entry.name.length)
  })
}

async function confirmRename() {
  if (!isRenaming.value) return
  isRenaming.value = false
  const trimmed = newName.value.trim()
  if (trimmed && trimmed !== props.entry.name) {
    emit('rename', props.entry.path, trimmed)
  }
}

function cancelRename() {
  isRenaming.value = false
}
</script>

<style scoped>
.tree-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary, #ccc);
}
.tree-item:hover { background: var(--hover-bg, #2a2a2a); }
.tree-item.active { background: var(--active-bg, #37373d); color: #fff; }
.tree-icon { font-size: 12px; flex-shrink: 0; }
.tree-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.rename-input {
  flex: 1;
  min-width: 0;
  background: var(--input-bg, #1e1e1e);
  border: 1px solid var(--accent, #0078d4);
  border-radius: 3px;
  color: var(--text-primary, #ccc);
  font-size: 13px;
  font-family: inherit;
  padding: 0 4px;
  outline: none;
  height: 20px;
}

.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--panel-bg, #252526);
  border: 1px solid var(--border-color, #3c3c3c);
  border-radius: 6px;
  padding: 4px 0;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.ctx-item {
  display: block;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: var(--text-primary, #ccc);
  font-size: 13px;
  padding: 6px 16px;
  cursor: pointer;
}
.ctx-item:hover { background: var(--hover-bg, #2a2a2a); }
</style>
