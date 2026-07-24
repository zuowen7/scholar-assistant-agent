<template>
  <div class="arg-node" :class="[`type-${data.node_type}`, { selected, editing }]">
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
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import type { NodeType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'

const props = defineProps<
  NodeProps<{
    node_type: NodeType
    text: string
    label: string | null
    issueCount: number
    created_by: 'user' | 'ai'
  }>
>()

const { state, upsertNode } = useArgumentMap()
const selected = computed(() => state.selectedNodeId === props.id)

const TYPE_LABELS: Record<NodeType, string> = {
  claim: t('argument.claim'),
  grounds: t('argument.grounds'),
  warrant: t('argument.warrant'),
  backing: t('argument.backing'),
  qualifier: t('argument.qualifier'),
  rebuttal: t('argument.rebuttal'),
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

function cancel() {
  editing.value = false
}

function autosize(e: Event) {
  autosizeEl(e.target as HTMLTextAreaElement)
}
function autosizeEl(ta: HTMLTextAreaElement) {
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = ta.scrollHeight + 'px'
}
</script>

<style scoped>
/* Base node */
.arg-node {
  --arg-tone: var(--c-text-3);
  min-width: 168px;
  max-width: 280px;
  padding: 10px 12px;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  border-left: 3px solid var(--arg-tone);
  border-radius: 10px;
  box-shadow: var(--elevation-1);
  position: relative;
  cursor: grab;
  transition:
    transform 200ms var(--ease-spring),
    box-shadow 200ms var(--ease-out),
    border-color 200ms var(--ease-out);
}
.arg-node:hover {
  transform: translateY(-1px);
  box-shadow: var(--elevation-2);
}
.arg-node.selected {
  border-color: var(--c-accent);
  box-shadow:
    0 0 0 2px var(--c-accent-ring),
    var(--elevation-2);
}
.arg-node.editing {
  border-color: var(--c-accent);
}

/* Restrained semantic tones keep hierarchy without turning the canvas into badges. */
.arg-node.type-claim {
  --arg-tone: var(--c-accent);
  background: color-mix(in srgb, var(--c-accent-soft) 42%, var(--c-panel));
}
.arg-node.type-grounds {
  --arg-tone: #6f9276;
}
.arg-node.type-warrant {
  --arg-tone: #7182a6;
}
.arg-node.type-backing {
  --arg-tone: #94a3a5;
}
.arg-node.type-qualifier {
  --arg-tone: #aa8757;
}
.arg-node.type-rebuttal {
  --arg-tone: #a76f62;
}

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
.arg-node .arg-node-type-tag {
  color: var(--arg-tone);
  opacity: 1;
}

.arg-node-badges {
  display: flex;
  align-items: center;
  gap: 4px;
}

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
  border-radius: 4px;
  background: var(--c-surface-2);
  color: var(--c-text-2);
  border: 1px solid var(--c-border);
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
  background: var(--arg-tone);
  border: 2px solid var(--c-surface-1);
  border-radius: 50%;
  opacity: 0;
  transition:
    opacity 140ms,
    transform 120ms var(--ease-spring);
  transform: scale(0.6);
}
.arg-node:hover .arg-handle,
.arg-node.selected .arg-handle {
  opacity: 1;
  transform: scale(1);
}
.arg-handle--top {
  top: -5px;
}
.arg-handle--bottom {
  bottom: -5px;
}
.arg-handle--left {
  left: -5px;
}
.arg-handle--right {
  right: -5px;
}
</style>
