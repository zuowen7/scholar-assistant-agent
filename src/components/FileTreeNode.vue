<template>
  <div class="tree-node">
    <div
      class="tree-item"
      :class="{ active: activeFile === entry.path, dir: entry.isDir }"
      :style="{ paddingLeft: depth * 16 + 8 + 'px' }"
      @click="handleClick"
    >
      <span class="tree-icon">{{ entry.isDir ? (expanded ? '📂' : '📁') : '📄' }}</span>
      <span class="tree-name">{{ entry.name }}</span>
    </div>
    <template v-if="entry.isDir && expanded && entry.children">
      <FileTreeNode
        v-for="child in entry.children"
        :key="child.path"
        :entry="child"
        :depth="depth + 1"
        :active-file="activeFile"
        @select="(e: FileEntry) => $emit('select', e)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { FileEntry } from '../types'

const props = defineProps<{
  entry: FileEntry
  depth: number
  activeFile: string | null
}>()

const emit = defineEmits<{
  (e: 'select', entry: FileEntry): void
}>()

const expanded = ref(false)

function handleClick() {
  if (props.entry.isDir) {
    expanded.value = !expanded.value
  } else {
    emit('select', props.entry)
  }
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
</style>
