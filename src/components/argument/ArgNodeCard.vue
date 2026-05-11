<template>
  <div
    class="arg-node"
    :class="[`type-${data.node_type}`, { selected, editing }]"
  >
    <div class="arg-node-header">
      <span class="arg-node-type-tag">{{ typeLabel }}</span>
      <div class="arg-node-badges">
        <span v-if="data.issueCount" class="arg-node-issue-badge">{{ data.issueCount }}</span>
        <span v-if="data.created_by === 'ai'" class="arg-node-ai-badge">AI</span>
      </div>
    </div>

    <textarea
      v-if="editing"
      ref="inputRef"
      v-model="draftText"
      class="arg-node-input nodrag nowheel"
      rows="2"
      @blur="commit"
      @keydown.enter.exact.prevent="commit"
      @keydown.escape.prevent="cancel"
      @keydown.shift.enter.stop
      @input="autosize"
    />
    <p v-else class="arg-node-text nodrag" @dblclick="startEdit">{{ displayText }}</p>

    <Handle type="target" :position="Position.Top" class="arg-handle arg-handle--top" />
    <Handle type="source" :position="Position.Bottom" class="arg-handle arg-handle--bottom" />
    <Handle type="target" :position="Position.Left" class="arg-handle arg-handle--left" />
    <Handle type="source" :position="Position.Right" class="arg-handle arg-handle--right" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import type { NodeType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'

const props = defineProps<NodeProps<{
  node_type: NodeType
  text: string
  label: string | null
  issueCount: number
  created_by: 'user' | 'ai'
}>>()

const { state, upsertNode } = useArgumentMap()
const selected = computed(() => state.selectedNodeId === props.id)

const TYPE_LABELS: Record<NodeType, string> = {
  claim: '主张',
  grounds: '依据',
  warrant: '论证保证',
  backing: '支撑',
  qualifier: '限定',
  rebuttal: '反驳',
}
const typeLabel = computed(() => TYPE_LABELS[props.data.node_type])
const displayText = computed(() => props.data.label || props.data.text)

const editing = ref(false)
const draftText = ref('')
const inputRef = ref<HTMLTextAreaElement>()

function startEdit() {
  editing.value = true
  draftText.value = props.data.text
  nextTick(() => {
    inputRef.value?.focus()
    inputRef.value?.select()
    autosizeEl(inputRef.value!)
  })
}

async function commit() {
  if (!editing.value) return
  editing.value = false
  if (draftText.value.trim() && draftText.value !== props.data.text) {
    await upsertNode({
      id: props.id,
      node_type: props.data.node_type,
      text: draftText.value.trim(),
    } as any)
  }
}

function cancel() { editing.value = false }

function autosize(e: Event) { autosizeEl(e.target as HTMLTextAreaElement) }
function autosizeEl(ta: HTMLTextAreaElement) {
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = ta.scrollHeight + 'px'
}
</script>

<style scoped>
/* Base node */
.arg-node {
  min-width: 140px;
  max-width: 260px;
  padding: 8px 10px;
  background: var(--c-surface-1);
  border: 1.5px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-1);
  position: relative;
  cursor: grab;
  transition: transform 200ms var(--ease-spring), box-shadow 200ms var(--ease-out), border-color 200ms var(--ease-out);
}
.arg-node:hover { transform: translateY(-2px); box-shadow: var(--elevation-2); }
.arg-node.selected {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-ring), var(--elevation-2);
}
.arg-node.editing { border-color: var(--c-accent); }

/* Per-type colors */
.arg-node.type-claim { border-color: var(--c-accent); border-width: 2.5px; background: linear-gradient(135deg, var(--c-surface-1) 0%, var(--c-accent-bg2) 100%); }
.arg-node.type-grounds { border-color: #10b981; }
.arg-node.type-warrant { border-color: #3b82f6; border-style: dashed; }
.arg-node.type-backing { border-color: #93c5fd; }
.arg-node.type-qualifier { border-color: #f59e0b; border-radius: 999px; }
.arg-node.type-rebuttal { border-color: var(--c-danger); border-style: dashed; }

/* Header */
.arg-node-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.arg-node-type-tag {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--c-text-2);
  opacity: 0.8;
}
.type-claim .arg-node-type-tag { color: var(--c-accent); opacity: 1; }
.type-grounds .arg-node-type-tag { color: #10b981; opacity: 1; }
.type-warrant .arg-node-type-tag { color: #3b82f6; opacity: 1; }
.type-backing .arg-node-type-tag { color: #93c5fd; opacity: 1; }
.type-qualifier .arg-node-type-tag { color: #f59e0b; opacity: 1; }
.type-rebuttal .arg-node-type-tag { color: var(--c-danger); opacity: 1; }

.arg-node-badges { display: flex; align-items: center; gap: 4px; }

.arg-node-issue-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 999px;
  background: var(--c-warn-bg);
  color: var(--c-warn-fg);
  border: 1px solid var(--c-warn-border);
}

.arg-node-ai-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--c-accent-bg2);
  color: var(--c-accent);
  border: 1px solid var(--c-accent-ring);
}

/* Text */
.arg-node-text {
  font-size: 13px;
  color: var(--c-text-0);
  line-height: 1.4;
  word-break: break-word;
  margin: 0;
  cursor: default;
}

.arg-node-input {
  width: 100%;
  background: var(--c-surface-1);
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-xs);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  resize: none;
  line-height: 1.4;
  padding: 3px 5px;
  outline: none;
}

/* Handles */
.arg-handle {
  width: 9px;
  height: 9px;
  background: var(--c-accent);
  border: 2px solid var(--c-surface-1);
  border-radius: 50%;
  opacity: 0;
  transition: opacity 140ms, transform 120ms var(--ease-spring);
  transform: scale(0.6);
}
.arg-node:hover .arg-handle,
.arg-node.selected .arg-handle {
  opacity: 1;
  transform: scale(1);
}
.arg-handle--top { top: -5px; }
.arg-handle--bottom { bottom: -5px; }
.arg-handle--left { left: -5px; }
.arg-handle--right { right: -5px; }
</style>
