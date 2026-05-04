<template>
  <div class="tree-node" @contextmenu.prevent="showContextMenu">
    <div
      class="tree-item"
      :class="{ active: activeFile === entry.path, dir: entry.isDir }"
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
        @action="(a: string, p: string, n: string) => $emit('action', a, p, n)"
      />
    </template>
  </div>

  <!-- Context menu -->
  <Teleport to="body">
    <div v-if="ctx.visible" class="ctx-menu" :style="{ left: ctx.x + 'px', top: ctx.y + 'px' }">
      <button class="ctx-item" @click="action('cut')">剪切</button>
      <button class="ctx-item" @click="action('copy')">复制</button>
      <button v-if="canPaste" class="ctx-item" @click="action('paste')">粘贴</button>
      <div v-if="canPaste" class="ctx-sep" />
      <button class="ctx-item" @click="action('rename')">重命名</button>
      <button class="ctx-item ctx-danger" @click="action('delete')">删除</button>
      <div class="ctx-sep" />
      <button class="ctx-item" @click="action('copy-path')">复制路径</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, nextTick, reactive, computed } from 'vue'
import type { FileEntry } from '../types'
import { useFileTree } from '../composables/useFileTree'

const props = defineProps<{
  entry: FileEntry
  depth: number
  activeFile: string | null
}>()

const emit = defineEmits<{
  (e: 'select', entry: FileEntry): void
  (e: 'action', action: string, path: string, extra: string): void
}>()

const { getClipboard } = useFileTree()

const expanded = ref(false)
const isRenaming = ref(false)
const newName = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

const ctx = reactive({ visible: false, x: 0, y: 0 })
const canPaste = computed(() => {
  if (!props.entry.isDir) return false
  const cb = getClipboard()
  return cb !== null
})

function handleClick() {
  if (props.entry.isDir) {
    expanded.value = !expanded.value
  } else {
    emit('select', props.entry)
  }
}

function showContextMenu(e: MouseEvent) {
  ctx.x = e.clientX
  ctx.y = e.clientY
  // Clamp to viewport
  nextTick(() => {
    if (ctx.y + 240 > window.innerHeight) ctx.y = window.innerHeight - 250
    if (ctx.x + 160 > window.innerWidth) ctx.x = window.innerWidth - 170
  })
  ctx.visible = true
  const close = () => { ctx.visible = false; document.removeEventListener('click', close); document.removeEventListener('contextmenu', close) }
  setTimeout(() => { document.addEventListener('click', close); document.addEventListener('contextmenu', close) }, 0)
}

function action(a: string) {
  ctx.visible = false
  if (a === 'rename') {
    newName.value = props.entry.name
    isRenaming.value = true
    nextTick(() => {
      renameInput.value?.focus()
      const dotIdx = props.entry.name.lastIndexOf('.')
      renameInput.value?.setSelectionRange(0, dotIdx > 0 ? dotIdx : props.entry.name.length)
    })
    return
  }
  emit('action', a, props.entry.path, props.entry.name)
}

async function confirmRename() {
  if (!isRenaming.value) return
  isRenaming.value = false
  const trimmed = newName.value.trim()
  if (trimmed && trimmed !== props.entry.name) {
    emit('action', 'rename', props.entry.path, trimmed)
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
  transition: background var(--motion-fast) var(--ease-out),
              box-shadow var(--motion-fast) var(--ease-out);
}
.tree-item:hover {
  background: var(--hover-bg, #2a2a2a);
  box-shadow: inset 2px 0 0 var(--c-accent);
}
.tree-item.active { background: var(--active-bg, #37373d); color: var(--c-text-0); box-shadow: inset 2px 0 0 var(--c-accent); }
.tree-icon { font-size: 12px; flex-shrink: 0; }
.tree-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.rename-input {
  flex: 1;
  min-width: 0;
  background: var(--input-bg);
  border: 1px solid var(--accent);
  border-radius: 3px;
  color: var(--text-primary);
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
  min-width: 160px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
}
.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: var(--text-primary, #ccc);
  font-size: 13px;
  padding: 6px 16px;
  cursor: pointer;
  white-space: nowrap;
}
.ctx-item:hover { background: var(--hover-bg, #2a2a2a); }
.ctx-item.ctx-danger { color: #e06c75; }
.ctx-item.ctx-danger:hover { background: rgba(224,108,117,0.12); }
.ctx-sep { height: 1px; background: var(--border-color, #3c3c3c); margin: 4px 8px; }
</style>
