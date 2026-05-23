<template>
  <div
    class="mind-node anim-pop-in"
    :class="[`depth-${data.depth}`, { selected, root: data.isRoot, editing, expanding }]"
  >
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
        <button
          v-if="!editing"
          class="body-toggle nodrag"
          :class="{ 'has-body': bodyPreview }"
          @click="toggleBody"
          :title="bodyExpanded ? '收起正文' : '编辑正文'"
        >{{ bodyExpanded ? '▾' : '▸' }}</button>
      </div>
      <span v-if="expanding" class="node-spinner" role="status" aria-label="AI 展开中">
        <UiSpinner size="sm" />
      </span>
      <span v-else-if="issueCount" class="node-badge">{{ issueCount }}</span>
    </div>

    <!-- Body text area -->
    <Transition name="v-fade">
      <div v-if="bodyExpanded" class="node-content-area nodrag nowheel" @mousedown.stop @wheel.stop>
        <textarea
          ref="bodyRef"
          v-model="draftBody"
          class="body-textarea nodrag nowheel"
          placeholder="正文内容..."
          rows="2"
          @blur="commitBody"
          @input="autosizeBody"
        />
      </div>
    </Transition>

    <!-- Body preview (collapsed) -->
    <div v-if="!bodyExpanded && bodyPreview" class="node-body-preview nodrag" @dblclick="toggleBody">
      {{ bodyPreview }}
    </div>

    <!-- AI 展开加载反馈：底部扫描条 + 微光文字 -->
    <Transition name="v-fade">
      <div v-if="expanding" class="node-expanding-overlay">
        <span class="node-expanding-label anim-shimmer-text">AI 生成子主题</span>
        <span class="anim-scan-bar node-expanding-scan" />
      </div>
    </Transition>

    <Handle type="target" :position="Position.Left" class="mind-handle" />
    <Handle type="source" :position="Position.Right" class="mind-handle" />
    <Handle type="source" :position="Position.Top" class="mind-handle hidden-handle" id="top" />
    <Handle type="source" :position="Position.Bottom" class="mind-handle hidden-handle" id="bottom" />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, ref, type Ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { useMindMap } from '../../composables/useMindMap'
import UiSpinner from '../ui/UiSpinner.vue'

const props = defineProps<NodeProps<{
  text: string
  body: string
  depth: number
  isRoot: boolean
  hasChildren: boolean
}>>()

const { commitNodeText, updateNodeBody, selectedNodeId, analysisIssuesByNode } = useMindMap()

const expandingNodeId = inject<Ref<string>>('expandingNodeId', ref(''))

const editing = ref(false)
const draftText = ref('')
const inputRef = ref<HTMLTextAreaElement>()

const bodyExpanded = ref(false)
const draftBody = ref('')
const bodyRef = ref<HTMLTextAreaElement>()

const selected = computed(() => selectedNodeId.value === props.id)
const expanding = computed(() => !!expandingNodeId.value && expandingNodeId.value === props.id)
const issueCount = computed(() => analysisIssuesByNode.value[props.id] ?? 0)

const bodyPreview = computed(() => {
  const b = props.data.body ?? ''
  if (!b) return ''
  const firstLine = b.split('\n')[0]
  return firstLine.length > 40 ? firstLine.slice(0, 40) + '...' : firstLine
})

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

function toggleBody() {
  bodyExpanded.value = !bodyExpanded.value
  if (bodyExpanded.value) {
    draftBody.value = props.data.body ?? ''
    nextTick(() => {
      bodyRef.value?.focus()
      autosizeEl(bodyRef.value!)
    })
  }
}

function commitBody() {
  updateNodeBody(props.id, draftBody.value)
}

function autosize(e: Event) {
  autosizeEl(e.target as HTMLTextAreaElement)
}

function autosizeBody() {
  autosizeEl(bodyRef.value!)
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
  flex-direction: column;
  min-width: 132px;
  max-width: 276px;
  background: var(--c-surface-1);
  border: 1px solid var(--c-sent-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-1);
  overflow: hidden;
  position: relative;
  transition: transform 200ms var(--ease-spring),
              box-shadow 220ms var(--ease-out),
              border-color 200ms var(--ease-out),
              background 200ms var(--ease-out);
  cursor: grab;
}
.mind-node:active { cursor: grabbing; }
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
.mind-node:hover::after { opacity: 0.05; }

.mind-node:hover {
  transform: translateY(-2px);
  box-shadow: var(--elevation-2);
  border-color: var(--c-surface-4);
}
.mind-node:active { transform: scale(0.985); }
.mind-node:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus), var(--elevation-2);
  border-color: var(--c-accent);
}
.mind-node.selected {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 2px var(--c-accent-ring), var(--elevation-2);
}
.mind-node.selected:hover {
  box-shadow: 0 0 0 2px var(--c-accent-ring), var(--elevation-3);
}
.mind-node.editing {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 3px var(--c-accent-ring), var(--elevation-2);
}
/* AI 展开中：脉动光环包裹整张卡片 */
.mind-node.expanding {
  border-color: var(--c-accent);
  animation: node-busy-pulse 1.4s var(--ease-smooth) infinite;
}
@keyframes node-busy-pulse {
  0%, 100% { box-shadow: 0 0 0 1px var(--c-accent-soft), var(--elevation-2); }
  50%      { box-shadow: 0 0 0 4px var(--c-accent-soft), var(--elevation-3); }
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
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
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
  padding: 7px 10px 7px 14px;
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

.body-toggle {
  background: none;
  border: none;
  color: var(--c-text-2);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 3px;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  line-height: 1;
  opacity: 0.5;
  transition: opacity 150ms var(--ease-out), color 150ms var(--ease-out);
}
.body-toggle:hover { opacity: 1; color: var(--c-accent); }
.body-toggle.has-body { opacity: 0.8; color: var(--c-accent); }

.node-content-area {
  padding: 0 10px 6px 14px;
  position: relative;
  z-index: 1;
}

.body-textarea {
  width: 100%;
  min-height: 36px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-xs);
  outline: none;
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  resize: none;
  line-height: 1.4;
  padding: 4px 6px;
  transition: border-color 150ms var(--ease-out);
}
.body-textarea:focus {
  border-color: var(--c-accent);
}

.node-body-preview {
  padding: 0 10px 5px 14px;
  font-size: 11px;
  color: var(--c-text-2);
  line-height: 1.35;
  word-break: break-word;
  cursor: pointer;
  position: relative;
  z-index: 1;
  max-height: 32px;
  overflow: hidden;
}
.node-body-preview:hover {
  color: var(--c-accent);
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
  animation: anim-pop-in 360ms var(--ease-spring) both;
}

.node-spinner {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
}

/* AI 展开加载条 — 覆盖于卡片底部 */
.node-expanding-overlay {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 3px 8px 4px;
  background: linear-gradient(to top, var(--c-accent-soft), transparent);
  pointer-events: none;
}
.node-expanding-label {
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
}
.node-expanding-scan {
  width: 100%;
  border-radius: var(--radius-pill);
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
.mind-node:hover .mind-handle { transform: scale(1.12); }
.mind-handle:hover {
  transform: scale(1.35) !important;
  box-shadow: 0 0 0 4px var(--c-accent-soft);
}
.hidden-handle { opacity: 0 !important; pointer-events: none; }

@media (prefers-reduced-motion: reduce) {
  .mind-node,
  .mind-node.expanding { animation: none; transition: none; }
  .mind-node:hover { transform: none; }
  .mind-node:active { transform: none; }
  .node-badge { animation: none; }
}
</style>
