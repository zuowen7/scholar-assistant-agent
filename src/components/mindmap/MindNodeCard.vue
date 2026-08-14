<template>
  <div
    class="mind-node anim-pop-in"
    :class="[`depth-${data.depth}`, { selected, root: data.isRoot, editing, expanding }]"
    @contextmenu.prevent="onContextMenu"
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
          :title="bodyExpanded ? t('mindmap.collapseBody') : t('mindmap.editBody')"
          @click="toggleBody"
        >
          {{ bodyExpanded ? '▾' : '▸' }}
        </button>
      </div>
      <span
        v-if="expanding"
        class="node-spinner"
        role="status"
        :aria-label="t('mindmap.aiExpanding')"
      >
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
          :placeholder="t('mindmap.bodyPlaceholder')"
          rows="2"
          @blur="commitBody"
          @input="autosizeBody"
        />
      </div>
    </Transition>

    <!-- Body preview (collapsed) -->
    <div
      v-if="!bodyExpanded && bodyPreview"
      class="node-body-preview nodrag"
      @dblclick="toggleBody"
    >
      {{ bodyPreview }}
    </div>

    <!-- AI 展开加载反馈：底部扫描条 + 微光文字 -->
    <Transition name="v-fade">
      <div v-if="expanding" class="node-expanding-overlay">
        <span class="node-expanding-label anim-shimmer-text">{{ t('mindmap.aiGenerating') }}</span>
        <span class="anim-scan-bar node-expanding-scan" />
      </div>
    </Transition>

    <Handle type="target" :position="Position.Left" class="mind-handle" />
    <Handle type="source" :position="Position.Right" class="mind-handle" />
    <Handle id="top" type="source" :position="Position.Top" class="mind-handle hidden-handle" />
    <Handle
      id="bottom"
      type="source"
      :position="Position.Bottom"
      class="mind-handle hidden-handle"
    />

    <Teleport to="body">
      <div
        v-if="menuOpen"
        class="node-context-menu"
        :style="{ left: `${menuPos.x}px`, top: `${menuPos.y}px` }"
        @click.stop
        @contextmenu.prevent
      >
        <button @click="menuEdit"><span class="cm-ico">✎</span>{{ t('mindmap.editNode') }}</button>
        <button @click="menuAddChild">
          <span class="cm-ico">＋</span>{{ t('mindmap.childNode') }}
        </button>
        <button @click="menuAddSibling">
          <span class="cm-ico">⊕</span>{{ t('mindmap.addSibling') }}
        </button>
        <button @click="menuExpand">
          <span class="cm-ico">✦</span>{{ t('mindmap.aiExpand') }}
        </button>
        <div v-if="!data.isRoot" class="cm-sep" />
        <button v-if="!data.isRoot" class="cm-danger" @click="menuDelete">
          <span class="cm-ico">✕</span>{{ t('mindmap.deleteNode') }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { Handle, Position } from '@vue-flow/core'
import type { NodeProps } from '@vue-flow/core'
import { useMindMap } from '../../composables/useMindMap'
import UiSpinner from '../ui/UiSpinner.vue'

const props = defineProps<
  NodeProps<{
    text: string
    body: string
    depth: number
    isRoot: boolean
    hasChildren: boolean
  }>
>()

const {
  commitNodeText,
  updateNodeBody,
  selectedNodeId,
  analysisIssuesByNode,
  draftMindMap,
  addChild,
  addSibling,
  deleteNode,
  expandNode,
} = useMindMap()

const expandingNodeId = inject<Ref<string>>('expandingNodeId', ref(''))

const editing = ref(false)
const draftText = ref('')
const inputRef = ref<HTMLTextAreaElement>()

const bodyExpanded = ref(false)
const draftBody = ref('')
const bodyRef = ref<HTMLTextAreaElement>()

const menuOpen = ref(false)
const menuPos = ref({ x: 0, y: 0 })

const selected = computed(() => selectedNodeId.value === props.id)
const expanding = computed(() => !!expandingNodeId.value && expandingNodeId.value === props.id)
const issueCount = computed(() => analysisIssuesByNode.value[props.id] ?? 0)

const nodeBody = computed(() => draftMindMap.value.nodes[props.id]?.body ?? '')

const bodyPreview = computed(() => {
  const b = nodeBody.value
  if (!b) return ''
  const firstLine = b.split('\n')[0]
  return firstLine.length > 40 ? firstLine.slice(0, 40) + '...' : firstLine
})

const DEPTH_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
const DEPTH_ICONS = ['●', '◆', '■', '●', '◆', '■']
const barColor = computed(() => DEPTH_COLORS[Math.min(props.data.depth, DEPTH_COLORS.length - 1)])
const icon = computed(() => (props.data.isRoot ? '●' : DEPTH_ICONS[Math.min(props.data.depth, 5)]))

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

function cancel() {
  editing.value = false
}

function toggleBody() {
  bodyExpanded.value = !bodyExpanded.value
  if (bodyExpanded.value) {
    draftBody.value = nodeBody.value
    nextTick(() => {
      bodyRef.value?.focus()
      autosizeEl(bodyRef.value!)
    })
  }
}

function commitBody() {
  updateNodeBody(props.id, draftBody.value)
}

// ── Right-click context menu ──────────────────────────────
function onContextMenu(e: MouseEvent) {
  selectedNodeId.value = props.id
  menuPos.value = { x: e.clientX, y: e.clientY }
  menuOpen.value = true
  const close = () => {
    menuOpen.value = false
    document.removeEventListener('click', close)
    document.removeEventListener('contextmenu', close)
  }
  setTimeout(() => {
    document.addEventListener('click', close)
    document.addEventListener('contextmenu', close)
  }, 0)
}

function menuEdit() {
  menuOpen.value = false
  startEdit()
}

function menuAddChild() {
  menuOpen.value = false
  const newId = addChild(props.id)
  if (newId) {
    // Auto-start editing the new node's text
    nextTick(() => {
      selectedNodeId.value = newId
    })
  }
}

function menuAddSibling() {
  menuOpen.value = false
  addSibling(props.id)
}

async function menuExpand() {
  menuOpen.value = false
  await expandNode(props.id)
}

function menuDelete() {
  menuOpen.value = false
  deleteNode(props.id)
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
  border: 1px solid var(--c-border);
  border-radius: 11px;
  box-shadow: 0 4px 14px rgba(45, 39, 29, 0.09);
  overflow: hidden;
  position: relative;
  transition:
    transform 200ms var(--ease-spring),
    box-shadow 220ms var(--ease-out),
    border-color 200ms var(--ease-out),
    background 200ms var(--ease-out);
  cursor: grab;
}
.mind-node:active {
  cursor: grabbing;
}
.mind-node:hover {
  transform: translateY(-1px);
  box-shadow: 0 7px 20px rgba(45, 39, 29, 0.12);
  border-color: #d8d0c2;
}
.mind-node:active {
  transform: scale(0.985);
}
.mind-node:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus), var(--elevation-2);
  border-color: var(--c-accent);
}
.mind-node.selected {
  border-color: var(--c-accent);
  box-shadow:
    0 0 0 2px var(--c-accent-ring),
    0 7px 20px rgba(45, 39, 29, 0.11);
}
.mind-node.selected:hover {
  box-shadow:
    0 0 0 2px var(--c-accent-ring),
    var(--elevation-3);
}
.mind-node.editing {
  border-color: var(--c-accent);
  box-shadow:
    0 0 0 3px var(--c-accent-ring),
    var(--elevation-2);
}
.mind-node.expanding {
  border-color: var(--c-accent);
  animation: node-busy-pulse 1.4s var(--ease-smooth) infinite;
}
@keyframes node-busy-pulse {
  0%,
  100% {
    box-shadow:
      0 0 0 1px var(--c-accent-soft),
      var(--elevation-1);
  }
  50% {
    box-shadow:
      0 0 0 2px var(--c-accent-soft),
      var(--elevation-2);
  }
}
.mind-node.root {
  min-width: 260px;
  max-width: 320px;
  background: var(--c-accent);
  border-color: var(--c-accent);
  box-shadow: 0 5px 14px rgba(45, 39, 29, 0.12);
}
.mind-node.root.selected {
  box-shadow:
    0 0 0 2px var(--c-accent-ring),
    0 5px 14px rgba(45, 39, 29, 0.12);
}
.mind-node.root .color-bar {
  display: none;
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
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: var(--tracking-tight);
}
.mind-node.root .node-icon,
.mind-node.root .body-toggle {
  color: rgba(255, 255, 255, 0.82);
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
  transition:
    opacity 150ms var(--ease-out),
    color 150ms var(--ease-out);
}
.body-toggle:hover {
  opacity: 1;
  color: var(--c-accent);
}
.body-toggle.has-body {
  opacity: 0.8;
  color: var(--c-accent);
}

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
  transition:
    opacity 160ms var(--ease-out),
    transform 120ms var(--ease-spring);
  transform: scale(0.6);
}
.mind-node:hover .mind-handle,
.mind-node.selected .mind-handle {
  opacity: 1;
  transform: scale(1);
}
.mind-node:hover .mind-handle {
  transform: scale(1.12);
}
.mind-handle:hover {
  transform: scale(1.35) !important;
  box-shadow: 0 0 0 4px var(--c-accent-soft);
}
.hidden-handle {
  opacity: 0 !important;
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .mind-node,
  .mind-node.expanding {
    animation: none;
    transition: none;
  }
  .mind-node:hover {
    transform: none;
  }
  .mind-node:active {
    transform: none;
  }
  .node-badge {
    animation: none;
  }
}
</style>

<!-- Context menu (global — teleported to body) -->
<style>
.node-context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 168px;
  background: var(--c-surface-1, #fff);
  border: 1px solid var(--c-glass-border, #e0dccf);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(45, 39, 29, 0.16);
  padding: 5px;
  backdrop-filter: blur(20px) saturate(1.5);
  -webkit-backdrop-filter: blur(20px) saturate(1.5);
  display: flex;
  flex-direction: column;
  gap: 1px;
  animation: ncm-in 140ms var(--ease-spring, ease-out) both;
}
@keyframes ncm-in {
  from {
    opacity: 0;
    transform: scale(0.94) translateY(-4px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
.node-context-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: none;
  background: none;
  color: var(--c-text-1, #3a3328);
  font-size: 13px;
  text-align: left;
  border-radius: 6px;
  cursor: pointer;
  transition:
    background 100ms ease,
    color 100ms ease;
  font-family: inherit;
}
.node-context-menu button:hover {
  background: var(--c-accent-soft, rgba(200, 80, 58, 0.1));
  color: var(--c-accent-hover, #b0432f);
}
.node-context-menu button.cm-danger:hover {
  background: var(--c-danger-bg, rgba(220, 60, 60, 0.1));
  color: var(--c-danger, #dc3c3c);
}
.node-context-menu .cm-ico {
  font-size: 14px;
  width: 16px;
  text-align: center;
  opacity: 0.7;
  flex-shrink: 0;
}
.node-context-menu .cm-sep {
  height: 1px;
  background: var(--c-surface-3, #e8e4d8);
  margin: 3px 4px;
}
</style>

<!-- Context menu (global — teleported to body) -->
<style>
.node-context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 168px;
  background: var(--c-surface-1, #fff);
  border: 1px solid var(--c-glass-border, #e0dccf);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(45, 39, 29, 0.16);
  padding: 5px;
  backdrop-filter: blur(20px) saturate(1.5);
  -webkit-backdrop-filter: blur(20px) saturate(1.5);
  display: flex;
  flex-direction: column;
  gap: 1px;
  animation: ncm-in 140ms var(--ease-spring, ease-out) both;
}
@keyframes ncm-in {
  from {
    opacity: 0;
    transform: scale(0.94) translateY(-4px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
.node-context-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border: none;
  background: none;
  color: var(--c-text-1, #3a3328);
  font-size: 13px;
  text-align: left;
  border-radius: 6px;
  cursor: pointer;
  transition:
    background 100ms ease,
    color 100ms ease;
  font-family: inherit;
}
.node-context-menu button:hover {
  background: var(--c-accent-soft, rgba(200, 80, 58, 0.1));
  color: var(--c-accent-hover, #b0432f);
}
.node-context-menu button.cm-danger:hover {
  background: var(--c-danger-bg, rgba(220, 60, 60, 0.1));
  color: var(--c-danger, #dc3c3c);
}
.node-context-menu .cm-ico {
  font-size: 14px;
  width: 16px;
  text-align: center;
  opacity: 0.7;
  flex-shrink: 0;
}
.node-context-menu .cm-sep {
  height: 1px;
  background: var(--c-surface-3, #e8e4d8);
  margin: 3px 4px;
}
</style>
