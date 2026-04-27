<template>
  <div class="mind-node" :class="[`depth-${data.depth}`, { selected, root: data.isRoot }]">
    <div class="color-bar" :style="{ background: barColor }"></div>
    <div class="node-body">
      <div class="node-header">
        <span class="node-icon">{{ icon }}</span>
        <textarea
          v-if="editing"
          ref="inputRef"
          v-model="draftText"
          class="node-input nodrag nowheel"
          rows="1"
          @blur="commit"
          @keydown.enter.exact.prevent="commit"
          @keydown.escape.prevent="cancel"
          @keydown.shift.enter.stop
          @input="autosize"
        />
        <span v-else class="node-text nodrag" @dblclick="startEdit">{{ data.text }}</span>
      </div>
      <span v-if="issueCount" class="node-badge">{{ issueCount }}</span>
    </div>

    <Handle type="target" :position="Position.Left" class="mind-handle" />
    <Handle type="source" :position="Position.Right" class="mind-handle" />
    <Handle type="source" :position="Position.Top" class="mind-handle hidden-handle" id="top" />
    <Handle type="source" :position="Position.Bottom" class="mind-handle hidden-handle" id="bottom" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { useMindMap } from '../../composables/useMindMap'

const props = defineProps<NodeProps<{
  text: string
  depth: number
  isRoot: boolean
  hasChildren: boolean
}>>()

const { commitNodeText, selectedNodeId, analysisIssuesByNode } = useMindMap()

const editing = ref(false)
const draftText = ref('')
const inputRef = ref<HTMLTextAreaElement>()

const selected = computed(() => selectedNodeId.value === props.id)
const issueCount = computed(() => analysisIssuesByNode.value[props.id] ?? 0)

const DEPTH_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
const barColor = computed(() => DEPTH_COLORS[Math.min(props.data.depth, DEPTH_COLORS.length - 1)])

const DEPTH_ICONS = ['◆', '▶', '●', '◇', '▷', '○']
const icon = computed(() => props.data.isRoot ? '◆' : DEPTH_ICONS[Math.min(props.data.depth, 5)])

function startEdit() {
  editing.value = true
  draftText.value = props.data.text
  nextTick(() => {
    inputRef.value?.focus()
    inputRef.value?.select()
    autosizeEl(inputRef.value!)
  })
}

function commit() {
  if (editing.value) commitNodeText(props.id, draftText.value)
  editing.value = false
}

function cancel() { editing.value = false }

function autosize(e: Event) {
  autosizeEl(e.target as HTMLTextAreaElement)
}

function autosizeEl(ta: HTMLTextAreaElement) {
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = ta.scrollHeight + 'px'
}

defineExpose({ startEdit })
</script>

<style scoped>
.mind-node {
  display: flex;
  min-width: 180px;
  max-width: 300px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: all 160ms var(--ease-out);
  cursor: grab;
}
.mind-node:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
  border-color: var(--c-surface-4);
}
.mind-node.selected {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-bg), var(--shadow-md);
}
.mind-node.root {
  background: linear-gradient(135deg, var(--c-surface-2), var(--c-accent-bg));
}

.color-bar {
  width: 4px;
  flex-shrink: 0;
}

.node-body {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 0;
}

.node-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  min-width: 0;
  flex: 1;
}

.node-icon {
  color: var(--c-text-2);
  font-size: var(--text-sm);
  margin-top: 2px;
}

.node-text {
  font-size: var(--text-base);
  color: var(--c-text-0);
  word-break: break-word;
  line-height: 1.4;
  cursor: default;
}
.mind-node.root .node-text {
  font-size: var(--text-lg);
  font-weight: 600;
}

.node-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--c-text-0);
  font: inherit;
  font-size: var(--text-base);
  resize: none;
  line-height: 1.4;
  padding: 0;
}

.node-badge {
  background: var(--c-warn);
  color: var(--c-surface-0);
  font-size: var(--text-xs);
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  flex-shrink: 0;
}

.mind-handle {
  width: 10px;
  height: 10px;
  background: var(--c-accent);
  border: 2px solid var(--c-surface-1);
  opacity: 0;
  transition: opacity 160ms var(--ease-out);
}
.mind-node:hover .mind-handle,
.mind-node.selected .mind-handle { opacity: 1; }
.hidden-handle { opacity: 0 !important; pointer-events: none; }
</style>
