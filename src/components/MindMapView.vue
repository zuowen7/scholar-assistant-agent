<template>
  <div class="mindmap-view">
    <div class="mindmap-toolbar">
      <div>
        <div class="mindmap-kicker">Mind Map</div>
        <h2>思维导图</h2>
      </div>
      <div class="mindmap-actions">
        <button class="mindmap-btn" @click="resetMindMap()">新建导图</button>
        <button class="mindmap-btn" :disabled="!selectedNode" @click="addChild()">新增子节点</button>
        <button class="mindmap-btn" :disabled="!canDelete" @click="deleteNode()">删除节点</button>
        <button class="mindmap-btn primary" @click="saveAndStay">保存到当前工程</button>
        <button class="mindmap-btn primary" @click="saveAndEnterEditor">进入编辑器</button>
      </div>
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
          {{ node.text }}
        </button>
      </aside>

      <main
        class="mindmap-canvas"
        :class="{ panning: isPanning }"
        @pointerdown="startPan"
        @pointermove="movePan"
        @pointerup="endPan"
        @pointerleave="endPan"
      >
        <div class="mindmap-stage" :style="{ transform: `translate(${pan.x}px, ${pan.y}px)` }">
          <svg class="mindmap-lines" aria-hidden="true">
            <line
              v-for="line in connectorLines"
              :key="line.key"
              :x1="line.x1"
              :y1="line.y1"
              :x2="line.x2"
              :y2="line.y2"
            />
          </svg>
          <button
            v-for="node in positionedNodes"
            :key="node.id"
            class="map-node"
            :class="{ root: node.id === draftMindMap.rootId, active: node.id === selectedNodeId }"
            :style="{ left: `${node.x}px`, top: `${node.y}px` }"
            @click="selectNode(node.id)"
            @dblclick="startInlineEdit(node.id)"
          >
            <input
              v-if="editingNodeId === node.id"
              v-model="editingText"
              class="node-input"
              @blur="commitInlineEdit"
              @keydown.enter.prevent="commitInlineEdit"
              @keydown.escape.prevent="cancelInlineEdit"
              ref="nodeInputRef"
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
          <span>保存状态</span>
          <strong>{{ saveMessage || '未保存改动仅保存在当前界面' }}</strong>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useMindMap } from '../composables/useMindMap'

const emit = defineEmits<{
  (e: 'enter-editor'): void
}>()

const {
  draftMindMap,
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
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })

const canDelete = computed(() => !!selectedNode.value && selectedNodeId.value !== draftMindMap.value.rootId)

const orderedNodes = computed(() => {
  const output: Array<{ id: string; text: string; depth: number }> = []
  const visit = (id: string, depth: number) => {
    const node = draftMindMap.value.nodes[id]
    if (!node) return
    output.push({ id, text: node.text, depth })
    node.children.forEach(childId => visit(childId, depth + 1))
  }
  visit(draftMindMap.value.rootId, 0)
  return output
})

const positionedNodes = computed(() => {
  const depths = new Map<number, number>()
  return orderedNodes.value.map(node => {
    const index = depths.get(node.depth) ?? 0
    depths.set(node.depth, index + 1)
    return {
      ...node,
      x: 80 + node.depth * 220,
      y: 90 + index * 88,
    }
  })
})

const connectorLines = computed(() => {
  const positions = new Map(positionedNodes.value.map(node => [node.id, node]))
  return positionedNodes.value.flatMap(node => {
    const parentId = draftMindMap.value.nodes[node.id]?.parentId
    const parent = parentId ? positions.get(parentId) : null
    if (!parent) return []
    return [{
      key: `${parent.id}-${node.id}`,
      x1: parent.x + 160,
      y1: parent.y + 23,
      x2: node.x,
      y2: node.y + 23,
    }]
  })
})

watch(selectedNode, (node) => {
  selectedText.value = node?.text ?? ''
}, { immediate: true })

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
  if (target.closest('.map-node')) return
  isPanning.value = true
  panStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y,
  }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function movePan(event: PointerEvent) {
  if (!isPanning.value) return
  pan.value = {
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
.mindmap-toolbar {
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
.mindmap-toolbar h2 {
  margin: 2px 0 0;
  font-size: 18px;
}
.mindmap-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.mindmap-btn {
  height: 30px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--toolbar-bg);
  color: var(--text-primary);
  padding: 0 11px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.mindmap-btn:hover:not(:disabled) {
  background: var(--hover-bg);
  border-color: var(--accent);
}
.mindmap-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}
.mindmap-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
}
.outline-node:hover,
.outline-node.active {
  background: var(--hover-bg);
  color: var(--accent);
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
  width: 1800px;
  height: 1200px;
  transform-origin: 0 0;
}
.mindmap-lines {
  position: absolute;
  width: 1800px;
  height: 1200px;
  inset: 0;
  pointer-events: none;
}
.mindmap-lines line {
  stroke: var(--accent);
  stroke-width: 1.5;
  opacity: 0.55;
}
.map-node {
  position: absolute;
  width: 160px;
  min-height: 46px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--toolbar-bg);
  color: var(--text-primary);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  padding: 8px 10px;
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
  outline: 2px solid color-mix(in srgb, var(--accent) 60%, transparent);
  outline-offset: 2px;
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
  .mindmap-toolbar {
    align-items: flex-start;
    flex-direction: column;
    height: auto;
  }

  .mindmap-actions {
    justify-content: flex-start;
  }

  .mindmap-body {
    grid-template-columns: 1fr;
  }

  .mindmap-outline {
    display: none;
  }
}
</style>
