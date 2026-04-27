<template>
  <div class="mindmap-view">
    <div class="mindmap-header">
      <div>
        <div class="mindmap-kicker">Mind Map</div>
        <h2>思维导图</h2>
      </div>
      <div class="view-meta">{{ Math.round(viewport.zoom * 100) }}%</div>
    </div>

    <div class="mindmap-body">
      <aside class="mindmap-outline">
        <div class="panel-title">大纲</div>
        <button
          v-for="node in orderedNodes"
          :key="node.id"
          class="outline-node"
          :class="{ active: node.id === selectedNodeId }"
          :style="{ paddingLeft: `${12 + node.depth * 14}px` }"
          @click="selectNode(node.id)"
        >
          <span
            v-if="node.hasChildren"
            class="collapse-toggle"
            @click.stop="toggleCollapse(node.id)"
          >
            {{ node.collapsed ? '▸' : '▾' }}
          </span>
          <span v-else class="collapse-spacer" />
          <span class="outline-text">{{ node.text }}</span>
        </button>
      </aside>

      <main
        ref="canvasRef"
        class="mindmap-canvas"
        :class="{ panning: isPanning }"
        @pointerdown="startPan"
        @pointermove="movePan"
        @pointerup="endPan"
        @pointercancel="endPan"
        @pointerleave="endPan"
      >
        <MindMapFloatingToolbar
          :position="viewport.toolbar"
          :can-add="!!selectedNode"
          :can-delete="canDelete"
          @update:position="viewport.toolbar = $event"
          @reset-map="resetMap"
          @add-child="addChild"
          @delete-node="deleteNode"
          @zoom-in="zoomBy(1.12)"
          @zoom-out="zoomBy(0.88)"
          @reset-view="resetView"
          @fit-view="fitView"
          @save="saveAndStay"
          @enter-editor="saveAndEnterEditor"
        />

        <div class="mindmap-stage" :style="stageStyle">
          <svg class="mindmap-lines" aria-hidden="true">
            <path
              v-for="line in connectorLines"
              :key="line.key"
              :d="line.d"
            />
          </svg>
          <button
            v-for="node in positionedNodes"
            :key="node.id"
            class="map-node"
            :class="{ root: node.id === draftMindMap.rootId, active: node.id === selectedNodeId }"
            :style="{ left: `${node.x}px`, top: `${node.y}px` }"
            @pointerdown.stop
            @click="selectNode(node.id)"
            @dblclick="startInlineEdit(node.id)"
          >
            <input
              v-if="editingNodeId === node.id"
              ref="nodeInputRef"
              v-model="editingText"
              class="node-input"
              @blur="commitInlineEdit"
              @keydown.enter.prevent="commitInlineEdit"
              @keydown.escape.prevent="cancelInlineEdit"
            />
            <span v-else>{{ node.text }}</span>
          </button>
        </div>
      </main>

      <aside class="mindmap-inspector">
        <div class="panel-title">属性</div>
        <label class="inspector-label">
          节点文字
          <textarea
            v-model="selectedText"
            class="inspector-input"
            rows="4"
            :disabled="!selectedNode"
            @change="applyInspectorText"
          />
        </label>
        <div class="inspector-meta">
          <span>节点数</span>
          <strong>{{ orderedNodes.length }}</strong>
        </div>
        <div class="inspector-meta">
          <span>缩放</span>
          <strong>{{ Math.round(viewport.zoom * 100) }}%</strong>
        </div>
        <div class="inspector-meta">
          <span>保存状态</span>
          <strong>{{ saveMessage || '未保存改动仅保存在当前界面' }}</strong>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MindMapFloatingToolbar from './MindMapFloatingToolbar.vue'
import { useMindMap } from '../composables/useMindMap'

const emit = defineEmits<{
  (e: 'enter-editor'): void
}>()

const NODE_WIDTH = 168
const NODE_HEIGHT = 52
const X_GAP = 260
const Y_GAP = 88
const STAGE_WIDTH = 2600
const STAGE_HEIGHT = 1800
const MIN_ZOOM = 0.35
const MAX_ZOOM = 1.8

const {
  draftMindMap,
  viewport,
  selectedNodeId,
  selectedNode,
  resetMindMap,
  saveMindMap,
  selectNode,
  updateNodeText,
  addChild,
  deleteNode,
} = useMindMap()

const editingNodeId = ref('')
const editingText = ref('')
const selectedText = ref('')
const saveMessage = ref('')
const nodeInputRef = ref<HTMLInputElement[]>()
const canvasRef = ref<HTMLElement | null>(null)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const collapsedNodeIds = ref<Set<string>>(new Set())

const canDelete = computed(() => !!selectedNode.value && selectedNodeId.value !== draftMindMap.value.rootId)

const orderedNodes = computed(() => {
  const output: Array<{ id: string; text: string; depth: number; hasChildren: boolean; collapsed: boolean }> = []
  const visit = (id: string, depth: number) => {
    const node = draftMindMap.value.nodes[id]
    if (!node) return
    const hasChildren = node.children.length > 0
    const collapsed = collapsedNodeIds.value.has(id)
    output.push({ id, text: node.text, depth, hasChildren, collapsed })
    if (collapsed) return
    node.children.forEach(childId => visit(childId, depth + 1))
  }
  visit(draftMindMap.value.rootId, 0)
  return output
})

const positionedNodes = computed(() => {
  const positions = new Map<string, { id: string; text: string; depth: number; x: number; y: number }>()
  let cursorY = 120

  const place = (id: string, depth: number): number => {
    const node = draftMindMap.value.nodes[id]
    if (!node) return cursorY

    let y: number
    const visibleChildren = collapsedNodeIds.value.has(id) ? [] : node.children
    if (!visibleChildren.length) {
      y = cursorY
      cursorY += Y_GAP
    } else {
      const childYs = visibleChildren.map(childId => place(childId, depth + 1))
      y = (childYs[0] + childYs[childYs.length - 1]) / 2
    }

    positions.set(id, {
      id,
      text: node.text,
      depth,
      x: 120 + depth * X_GAP,
      y,
    })
    return y
  }

  place(draftMindMap.value.rootId, 0)
  return orderedNodes.value
    .map(node => positions.get(node.id))
    .filter((node): node is NonNullable<typeof node> => !!node)
})

const connectorLines = computed(() => {
  const positions = new Map(positionedNodes.value.map(node => [node.id, node]))
  return positionedNodes.value.flatMap(node => {
    const parentId = draftMindMap.value.nodes[node.id]?.parentId
    const parent = parentId ? positions.get(parentId) : null
    if (!parent) return []

    const startX = parent.x + NODE_WIDTH
    const startY = parent.y + NODE_HEIGHT / 2
    const endX = node.x
    const endY = node.y + NODE_HEIGHT / 2
    const mid = Math.max(70, (endX - startX) * 0.5)

    return [{
      key: `${parent.id}-${node.id}`,
      d: `M ${startX} ${startY} C ${startX + mid} ${startY}, ${endX - mid} ${endY}, ${endX} ${endY}`,
    }]
  })
})

const stageStyle = computed(() => ({
  width: `${STAGE_WIDTH}px`,
  height: `${STAGE_HEIGHT}px`,
  transform: `translate(${viewport.value.pan.x}px, ${viewport.value.pan.y}px) scale(${viewport.value.zoom})`,
}))

watch(selectedNode, (node) => {
  selectedText.value = node?.text ?? ''
}, { immediate: true })

onMounted(() => {
  canvasRef.value?.addEventListener('wheel', handleWheel, { passive: false })
})

onBeforeUnmount(() => {
  canvasRef.value?.removeEventListener('wheel', handleWheel)
})

function clampZoom(value: number) {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value))
}

function startInlineEdit(id: string) {
  const node = draftMindMap.value.nodes[id]
  if (!node) return
  selectNode(id)
  editingNodeId.value = id
  editingText.value = node.text
  nextTick(() => nodeInputRef.value?.[0]?.focus())
}

function commitInlineEdit() {
  if (editingNodeId.value) updateNodeText(editingNodeId.value, editingText.value)
  editingNodeId.value = ''
}

function cancelInlineEdit() {
  editingNodeId.value = ''
}

function applyInspectorText() {
  if (selectedNode.value) updateNodeText(selectedNode.value.id, selectedText.value)
}

function startPan(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.closest('.map-node') || target.closest('.floating-toolbar')) return
  isPanning.value = true
  panStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: viewport.value.pan.x,
    panY: viewport.value.pan.y,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function movePan(event: PointerEvent) {
  if (!isPanning.value) return
  viewport.value.pan = {
    x: panStart.value.panX + event.clientX - panStart.value.x,
    y: panStart.value.panY + event.clientY - panStart.value.y,
  }
}

function endPan(event: PointerEvent) {
  if (!isPanning.value) return
  isPanning.value = false
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
}

function setZoom(nextZoom: number, anchor?: { x: number; y: number }) {
  const zoom = clampZoom(nextZoom)
  const canvas = canvasRef.value
  if (!canvas) {
    viewport.value.zoom = zoom
    return
  }

  const rect = canvas.getBoundingClientRect()
  const point = anchor ?? { x: rect.width / 2, y: rect.height / 2 }
  const stageX = (point.x - viewport.value.pan.x) / viewport.value.zoom
  const stageY = (point.y - viewport.value.pan.y) / viewport.value.zoom

  viewport.value.zoom = zoom
  viewport.value.pan = {
    x: point.x - stageX * zoom,
    y: point.y - stageY * zoom,
  }
}

function handleWheel(event: WheelEvent) {
  event.preventDefault()
  const target = canvasRef.value
  if (!target) return
  const rect = target.getBoundingClientRect()
  const factor = event.deltaY > 0 ? 0.9 : 1.1
  setZoom(viewport.value.zoom * factor, {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  })
}

function zoomBy(factor: number) {
  setZoom(viewport.value.zoom * factor)
}

function resetView() {
  viewport.value.pan = { x: 80, y: 80 }
  viewport.value.zoom = 1
}

function fitView() {
  const canvas = canvasRef.value
  if (!canvas || !positionedNodes.value.length) return

  const rect = canvas.getBoundingClientRect()
  const xs = positionedNodes.value.map(node => [node.x, node.x + NODE_WIDTH]).flat()
  const ys = positionedNodes.value.map(node => [node.y, node.y + NODE_HEIGHT]).flat()
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const mapWidth = maxX - minX
  const mapHeight = maxY - minY
  const zoom = clampZoom(Math.min((rect.width - 160) / mapWidth, (rect.height - 140) / mapHeight, 1.25))

  viewport.value.zoom = zoom
  viewport.value.pan = {
    x: (rect.width - mapWidth * zoom) / 2 - minX * zoom,
    y: (rect.height - mapHeight * zoom) / 2 - minY * zoom,
  }
}

function resetMap() {
  collapsedNodeIds.value = new Set()
  resetMindMap()
  nextTick(fitView)
}

function toggleCollapse(id: string) {
  const next = new Set(collapsedNodeIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsedNodeIds.value = next
}

function markSaved() {
  saveMessage.value = '已保存'
  window.setTimeout(() => {
    if (saveMessage.value === '已保存') saveMessage.value = ''
  }, 1800)
}

function saveAndStay() {
  saveMindMap()
  markSaved()
}

function saveAndEnterEditor() {
  saveMindMap()
  emit('enter-editor')
}
</script>

<style scoped>
.mindmap-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  background: var(--editor-bg);
  color: var(--text-primary);
}
.mindmap-header {
  min-height: 64px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--toolbar-bg);
}
.mindmap-kicker {
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.mindmap-header h2 {
  margin: 2px 0 0;
  font-size: 18px;
}
.view-meta {
  color: var(--text-secondary);
  font-size: 12px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  padding: 4px 9px;
}
.mindmap-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: clamp(160px, 15vw, 220px) minmax(280px, 1fr) clamp(190px, 16vw, 240px);
}
.mindmap-outline,
.mindmap-inspector {
  min-width: 0;
  overflow: auto;
  border-right: 1px solid var(--border-color);
  background: var(--sidebar-bg);
}
.mindmap-inspector {
  border-right: 0;
  border-left: 1px solid var(--border-color);
  padding: 14px;
}
.panel-title {
  height: 36px;
  display: flex;
  align-items: center;
  padding: 0 14px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-color);
}
.outline-node {
  width: 100%;
  min-height: 32px;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 55%, transparent);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.outline-node:hover,
.outline-node.active {
  background: var(--hover-bg);
  color: var(--accent);
}
.collapse-toggle,
.collapse-spacer {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.collapse-toggle {
  border-radius: 4px;
  color: var(--text-secondary);
}
.collapse-toggle:hover {
  background: var(--active-bg);
  color: var(--accent);
}
.outline-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mindmap-canvas {
  position: relative;
  overflow: hidden;
  min-width: 0;
  cursor: grab;
  background:
    linear-gradient(var(--border-color) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
  background-size: 48px 48px;
  background-color: var(--editor-bg);
  touch-action: none;
}
.mindmap-canvas.panning {
  cursor: grabbing;
}
.mindmap-stage {
  position: absolute;
  inset: 0;
  transform-origin: 0 0;
}
.mindmap-lines {
  position: absolute;
  width: 100%;
  height: 100%;
  inset: 0;
  pointer-events: none;
  overflow: visible;
}
.mindmap-lines path {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2;
  opacity: 0.52;
}
.map-node {
  position: absolute;
  width: 168px;
  min-height: 52px;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  background: var(--toolbar-bg);
  color: var(--text-primary);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.18);
  padding: 9px 11px;
  font: inherit;
  font-size: 13px;
  text-align: center;
  cursor: pointer;
}
.map-node.root {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 700;
}
.map-node.active {
  border-color: var(--accent);
  outline: 3px solid color-mix(in srgb, var(--accent) 42%, transparent);
  outline-offset: 3px;
  box-shadow: 0 12px 34px color-mix(in srgb, var(--accent) 24%, transparent);
}
.node-input {
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: center;
}
.inspector-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.inspector-input {
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--editor-bg);
  color: var(--text-primary);
  padding: 9px 10px;
  font: inherit;
  resize: vertical;
  outline: none;
}
.inspector-input:focus {
  border-color: var(--accent);
}
.inspector-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  color: var(--text-secondary);
  font-size: 12px;
}
.inspector-meta strong {
  color: var(--text-primary);
  font-weight: 600;
  text-align: right;
  overflow-wrap: anywhere;
}

@media (max-width: 980px) {
  .mindmap-body {
    grid-template-columns: 160px minmax(260px, 1fr);
  }

  .mindmap-inspector {
    display: none;
  }
}

@media (max-width: 720px) {
  .mindmap-header {
    min-height: 54px;
  }

  .mindmap-body {
    grid-template-columns: 1fr;
  }

  .mindmap-outline {
    display: none;
  }
}
</style>
