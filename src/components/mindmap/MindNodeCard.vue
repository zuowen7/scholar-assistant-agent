<template>
  <div class="mind-node" :class="[`depth-${data.depth}`, { selected, root: data.isRoot, editing }]">
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
const DEPTH_ICONS = ['●', '◆', '■', '●', '◆', '■']
const barColor = computed(() => DEPTH_COLORS[Math.min(props.data.depth, DEPTH_COLORS.length - 1)])
const icon = computed(() => props.data.isRoot ? '●' : DEPTH_ICONS[Math.min(props.data.depth, 5)])

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
  min-width: 132px;
  max-width: 276px;
  background: var(--c-surface-1);
  border: 1px solid var(--c-sent-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-1);
  overflow: hidden;
  position: relative;
  transition: transform 200ms var(--ease-spring), box-shadow 200ms var(--ease-out), border-color 200ms var(--ease-out);
  cursor: grab;
}
/* 墨韵涟漪 hover */
.mind-node::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at center, var(--c-accent) 0%, transparent 70%);
  opacity: 0;
  pointer-events: none;
  z-index: 0;
  transition: opacity 300ms var(--ease-brush);
}
.mind-node:hover::after { opacity: 0.04; }

.mind-node:hover {
  transform: translateY(-2px);
  box-shadow: var(--elevation-2);
  border-color: var(--c-surface-4);
}
.mind-node.selected {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-ring), var(--elevation-2);
}
.mind-node.editing {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 3px var(--c-accent-ring), var(--elevation-2);
}
.mind-node.root {
  min-width: 154px;
  max-width: 300px;
  background: linear-gradient(135deg, var(--c-surface-2) 0%, var(--c-accent-bg2) 100%);
  border-color: var(--c-surface-3);
}

.color-bar {
  width: 4px;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}
/* 光泽叠加 — 仿漆面高光 */
.color-bar::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, rgba(255,255,255,0.3) 0%, transparent 40%, rgba(0,0,0,0.15) 100%);
  opacity: 0.5;
}

.node-body {
  flex: 1;
  padding: 7px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-width: 0;
  position: relative;
  z-index: 1;
}

.node-header {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  min-width: 0;
  flex: 1;
}

.node-icon {
  color: var(--c-text-2);
  font-size: 10px;
  margin-top: 5px;
  flex-shrink: 0;
}

.node-text {
  font-size: 13px;
  color: var(--c-text-0);
  word-break: break-word;
  line-height: 1.38;
  cursor: default;
}
.mind-node.root .node-text {
  font-size: 14px;
  font-weight: 650;
  letter-spacing: var(--tracking-tight);
}

.node-input {
  flex: 1;
  min-width: 0;
  background: var(--c-surface-1);
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-xs);
  outline: none;
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  resize: none;
  line-height: 1.38;
  padding: 3px 5px;
}

.node-badge {
  background: var(--c-warn-bg);
  color: var(--c-warn-fg);
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid var(--c-warn-border);
  flex-shrink: 0;
  line-height: 1.4;
}

.mind-handle {
  width: 10px;
  height: 10px;
  background: var(--c-accent);
  border: 2px solid var(--c-surface-1);
  opacity: 0;
  border-radius: 50%;
  transition: opacity 160ms var(--ease-out), transform 120ms var(--ease-spring);
  transform: scale(0.6);
}
.mind-node:hover .mind-handle,
.mind-node.selected .mind-handle {
  opacity: 1;
  transform: scale(1);
}
.hidden-handle { opacity: 0 !important; pointer-events: none; }
</style>
