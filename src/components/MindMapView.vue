<template>
  <div class="mindmap-view">
    <div class="mindmap-header">
      <div>
        <div class="mindmap-kicker">Mind Map</div>
        <h2>思维导图</h2>
      </div>
      <div class="view-meta">
        <span v-if="connectionFromId">选择目标节点以完成连接</span>
        <span v-else>{{ Math.round(viewport.zoom * 100) }}%</span>
      </div>
    </div>

    <div
      class="mindmap-body"
      :class="{
        'outline-collapsed': outlineMode === 'collapsed',
        'outline-hidden': outlineMode === 'hidden',
        'ai-closed': !aiPanelOpen,
      }"
      :style="mindmapBodyStyle"
    >
      <aside class="mindmap-outline">
        <button
          class="outline-mode-button"
          :title="outlineMode === 'expanded' ? '折叠大纲' : '展开大纲'"
          @click="outlineMode = outlineMode === 'expanded' ? 'collapsed' : 'expanded'"
        >
          {{ outlineMode === 'expanded' ? '‹' : '大纲' }}
        </button>
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

      <div
        v-if="outlineMode === 'expanded'"
        class="pane-splitter vertical"
        title="拖动调整大纲宽度"
        @pointerdown="startPaneResize($event, 'outline')"
      />

      <section class="mindmap-workspace" :style="mindmapWorkspaceStyle">
      <main
        ref="canvasRef"
        class="mindmap-canvas"
        :class="{ panning: isPanning, connecting: !!connectionFromId }"
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
          :connecting="!!connectionFromId"
          :analyzing="analysisLoading"
          :expanding="expandingNode"
          @update:position="updateToolbarPosition"
          @reset-map="resetMap"
          @add-child="addChildWithPosition"
          @ai-expand="aiExpandSelectedNode"
          @analyze="runMindMapAnalysis"
          @start-connect="startConnection"
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
              v-for="line in treeLines"
              :key="line.key"
              class="tree-line"
              :d="line.d"
            />
            <path
              v-for="line in associationLines"
              :key="line.key"
              class="association-line"
              :d="line.d"
            />
          </svg>
          <button
            v-for="node in positionedNodes"
            :key="node.id"
            class="map-node"
            :class="{
              root: node.id === draftMindMap.rootId,
              active: node.id === selectedNodeId,
              source: node.id === connectionFromId,
              hinted: highlightedNodeIds.has(node.id),
            }"
            :style="{ left: `${node.x}px`, top: `${node.y}px` }"
            @pointerdown.stop="startNodeDrag($event, node.id)"
            @click.stop="handleNodeClick(node.id)"
            @dblclick.stop="startInlineEdit(node.id)"
          >
            <input
              v-if="editingNodeId === node.id"
              ref="nodeInputRef"
              v-model="editingText"
              class="node-input"
              @pointerdown.stop
              @click.stop
              @blur="commitInlineEdit"
              @keydown.enter.prevent="commitInlineEdit"
              @keydown.escape.prevent="cancelInlineEdit"
            />
            <span v-else>{{ node.text }}</span>
            <span v-if="issueCountByNode[node.id]" class="issue-badge">{{ issueCountByNode[node.id] }}</span>
          </button>
        </div>
      </main>

      <div
        v-if="!propertiesCollapsed"
        class="pane-splitter horizontal"
        title="拖动调整属性区高度"
        @pointerdown="startPaneResize($event, 'properties')"
      />

      <section class="mindmap-properties" :class="{ collapsed: propertiesCollapsed }">
        <div class="panel-title">属性</div>
        <button
          class="properties-collapse-button"
          :title="propertiesCollapsed ? '展开属性区' : '折叠属性区'"
          @click="propertiesCollapsed = !propertiesCollapsed"
        >
          {{ propertiesCollapsed ? '⌃' : '⌄' }}
        </button>
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
          <span>关联线</span>
          <strong>{{ draftMindMap.links.length }}</strong>
        </div>
        <div class="inspector-meta">
          <span>缩放</span>
          <strong>{{ Math.round(viewport.zoom * 100) }}%</strong>
        </div>
        <div class="inspector-meta">
          <span>保存状态</span>
          <strong>{{ saveMessage || '未保存' }}</strong>
        </div>
      </section>
      </section>

      <div
        v-if="aiPanelOpen"
        class="pane-splitter vertical"
        title="拖动调整 AI 面板宽度"
        @pointerdown="startPaneResize($event, 'ai')"
      />
      <aside class="mindmap-ai-panel" :class="{ open: aiPanelOpen }">
        <button
          v-if="!aiPanelOpen"
          class="ai-rail-button"
          title="展开 AI 提醒"
          @click="aiPanelOpen = true"
        >
          AI
        </button>
        <button
          v-else
          class="ai-collapse-button"
          title="收起 AI 提醒"
          @click="aiPanelOpen = false"
        >
          ›
        </button>
        <MindMapAiHints
          v-show="aiPanelOpen"
          :issues="analysisIssues"
          :active-issue-id="activeIssueId"
          :loading="analysisLoading"
          @select-issue="focusIssue"
        />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MindMapFloatingToolbar from './MindMapFloatingToolbar.vue'
import MindMapAiHints from './MindMapAiHints.vue'
import { useMindMap, mindMapToMarkdown } from '../composables/useMindMap'
import { useMindMapAnalysis, type MindMapAnalysisIssue } from '../composables/useMindMapAnalysis'

const emit = defineEmits<{
  (e: 'enter-editor', outline: string): void
}>()

const NODE_WIDTH = 168
const NODE_HEIGHT = 52
const X_GAP = 260
const Y_GAP = 88
const STAGE_WIDTH = 2600
const STAGE_HEIGHT = 1800
const MIN_ZOOM = 0.35
const MAX_ZOOM = 1.8

type PositionedNode = { id: string; text: string; depth: number; x: number; y: number }
type PaneResizeTarget = 'outline' | 'ai' | 'properties'
type OutlineMode = 'expanded' | 'collapsed' | 'hidden'

const {
  draftMindMap,
  viewport,
  selectedNodeId,
  selectedNode,
  resetMindMap,
  saveMindMap,
  loadFromBackend,
  selectNode,
  updateNodeText,
  setNodePosition,
  addChild,
  addAssociationLink,
  expandNode,
  deleteNode,
} = useMindMap()
const { analyzeMindMap } = useMindMapAnalysis()

const editingNodeId = ref('')
const editingText = ref('')
const selectedText = ref('')
const saveMessage = ref('')
const nodeInputRef = ref<HTMLInputElement[]>()
const canvasRef = ref<HTMLElement | null>(null)
const isPanning = ref(false)
const panStart = ref({ x: 0, y: 0, panX: 0, panY: 0 })
const collapsedNodeIds = ref<Set<string>>(new Set())
const connectionFromId = ref('')
const analysisIssues = ref<MindMapAnalysisIssue[]>([])
const analysisLoading = ref(false)
const expandingNode = ref(false)
const activeIssueId = ref('')
const highlightedNodeIds = ref<Set<string>>(new Set())
const outlineMode = ref<OutlineMode>('collapsed')
const outlineWidth = ref(178)
const aiPanelOpen = ref(true)
const aiPanelWidth = ref(284)
const propertiesCollapsed = ref(false)
const propertiesHeight = ref(148)
const nodeDrag = ref<{
  id: string
  pointerX: number
  pointerY: number
  startX: number
  startY: number
  moved: boolean
} | null>(null)
const suppressNextNodeClick = ref(false)
let canvasResizeObserver: ResizeObserver | null = null

const canDelete = computed(() => !!selectedNode.value && selectedNodeId.value !== draftMindMap.value.rootId)

const mindmapBodyStyle = computed(() => {
  const outlineColumn = outlineMode.value === 'hidden'
    ? '0px'
    : outlineMode.value === 'collapsed'
      ? '42px'
      : `${outlineWidth.value}px`
  const aiColumn = aiPanelOpen.value ? `${aiPanelWidth.value}px` : '42px'
  return {
    gridTemplateColumns: `${outlineColumn} ${outlineMode.value === 'expanded' ? '4px ' : ''}minmax(320px, 1fr) ${aiPanelOpen.value ? '4px ' : ''}${aiColumn}`,
  }
})

const mindmapWorkspaceStyle = computed(() => ({
  gridTemplateRows: propertiesCollapsed.value
    ? 'minmax(0, 1fr) 36px'
    : `minmax(0, 1fr) 4px ${propertiesHeight.value}px`,
}))

const issueCountByNode = computed(() => {
  const counts: Record<string, number> = {}
  analysisIssues.value.forEach((issue) => {
    issue.nodeIds.forEach((id) => {
      counts[id] = (counts[id] ?? 0) + 1
    })
  })
  return counts
})

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

const autoPositionedNodes = computed(() => {
  const positions = new Map<string, PositionedNode>()
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
  return positions
})

const positionedNodes = computed(() => {
  return orderedNodes.value
    .map((node) => {
      const autoPosition = autoPositionedNodes.value.get(node.id)
      if (!autoPosition) return null
      const savedPosition = draftMindMap.value.positions?.[node.id]
      return {
        ...autoPosition,
        x: savedPosition?.x ?? autoPosition.x,
        y: savedPosition?.y ?? autoPosition.y,
      }
    })
    .filter((node): node is PositionedNode => !!node)
})

const positionMap = computed(() => new Map(positionedNodes.value.map(node => [node.id, node])))

const treeLines = computed(() => {
  return positionedNodes.value.flatMap(node => {
    const parentId = draftMindMap.value.nodes[node.id]?.parentId
    const parent = parentId ? positionMap.value.get(parentId) : null
    if (!parent) return []
    return [{
      key: `tree-${parent.id}-${node.id}`,
      d: makeRightBranchPath(parent, node),
    }]
  })
})

const associationLines = computed(() => {
  return draftMindMap.value.links.flatMap(link => {
    const from = positionMap.value.get(link.from)
    const to = positionMap.value.get(link.to)
    if (!from || !to) return []
    return [{
      key: link.id,
      d: makeAssociationPath(from, to),
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

onMounted(async () => {
  canvasRef.value?.addEventListener('wheel', handleWheel, { passive: false })
  canvasResizeObserver = new ResizeObserver(() => {
    clampPaneSizes()
    clampToolbarPosition()
  })
  if (canvasRef.value) canvasResizeObserver.observe(canvasRef.value)
  window.addEventListener('resize', handleWindowResize)
  clampPaneSizes()
  await loadFromBackend()
})

onBeforeUnmount(() => {
  canvasRef.value?.removeEventListener('wheel', handleWheel)
  canvasResizeObserver?.disconnect()
  window.removeEventListener('resize', handleWindowResize)
})

function makeRightBranchPath(from: PositionedNode, to: PositionedNode) {
  const startX = from.x + NODE_WIDTH
  const startY = from.y + NODE_HEIGHT / 2
  const endX = to.x
  const endY = to.y + NODE_HEIGHT / 2
  const mid = Math.max(70, Math.abs(endX - startX) * 0.5)
  return `M ${startX} ${startY} C ${startX + mid} ${startY}, ${endX - mid} ${endY}, ${endX} ${endY}`
}

function makeAssociationPath(from: PositionedNode, to: PositionedNode) {
  const startX = from.x + NODE_WIDTH / 2
  const startY = from.y + NODE_HEIGHT / 2
  const endX = to.x + NODE_WIDTH / 2
  const endY = to.y + NODE_HEIGHT / 2
  const curve = Math.max(50, Math.abs(endX - startX) * 0.2)
  return `M ${startX} ${startY} C ${startX + curve} ${startY - 56}, ${endX - curve} ${endY - 56}, ${endX} ${endY}`
}

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

function startNodeDrag(event: PointerEvent, id: string) {
  if (editingNodeId.value === id || connectionFromId.value) return
  const node = positionMap.value.get(id)
  if (!node) return
  selectNode(id)
  nodeDrag.value = {
    id,
    pointerX: event.clientX,
    pointerY: event.clientY,
    startX: node.x,
    startY: node.y,
    moved: false,
  }
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)

  const move = (moveEvent: PointerEvent) => {
    const drag = nodeDrag.value
    if (!drag) return
    const dx = (moveEvent.clientX - drag.pointerX) / viewport.value.zoom
    const dy = (moveEvent.clientY - drag.pointerY) / viewport.value.zoom
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) drag.moved = true
    setNodePosition(id, {
      x: drag.startX + dx,
      y: drag.startY + dy,
    })
  }

  const up = (upEvent: PointerEvent) => {
    const moved = !!nodeDrag.value?.moved
    suppressNextNodeClick.value = moved
    nodeDrag.value = null
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', up)
    target.removeEventListener('pointercancel', up)
    if (target.hasPointerCapture(upEvent.pointerId)) target.releasePointerCapture(upEvent.pointerId)
    window.setTimeout(() => {
      suppressNextNodeClick.value = false
    }, 0)
  }

  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', up)
  target.addEventListener('pointercancel', up)
}

function handleNodeClick(id: string) {
  if (suppressNextNodeClick.value) return
  if (connectionFromId.value) {
    if (connectionFromId.value !== id) addAssociationLink(connectionFromId.value, id)
    selectNode(id)
    connectionFromId.value = ''
    return
  }
  selectNode(id)
}

function startConnection() {
  if (!selectedNode.value) return
  connectionFromId.value = connectionFromId.value === selectedNodeId.value ? '' : selectedNodeId.value
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

function handleWindowResize() {
  clampPaneSizes()
  clampToolbarPosition()
}

function clampPaneSizes() {
  const width = window.innerWidth
  const height = window.innerHeight

  outlineWidth.value = Math.min(Math.max(outlineWidth.value, 132), Math.max(132, width * 0.28))
  aiPanelWidth.value = Math.min(Math.max(aiPanelWidth.value, 220), Math.max(220, width * 0.36))
  propertiesHeight.value = Math.min(Math.max(propertiesHeight.value, 92), Math.max(92, height * 0.32))

  if (width < 760) {
    outlineMode.value = 'hidden'
    aiPanelOpen.value = false
  } else if (width < 1040 && outlineMode.value === 'expanded') {
    outlineMode.value = 'collapsed'
  }

  if (height < 640) propertiesCollapsed.value = true
}

function startPaneResize(event: PointerEvent, target: PaneResizeTarget) {
  event.preventDefault()
  const startX = event.clientX
  const startY = event.clientY
  const startOutline = outlineWidth.value
  const startAi = aiPanelWidth.value
  const startProperties = propertiesHeight.value

  const move = (moveEvent: PointerEvent) => {
    if (target === 'outline') {
      outlineWidth.value = Math.max(132, Math.min(300, startOutline + moveEvent.clientX - startX))
    } else if (target === 'ai') {
      aiPanelWidth.value = Math.max(220, Math.min(420, startAi - (moveEvent.clientX - startX)))
    } else {
      propertiesHeight.value = Math.max(92, Math.min(260, startProperties - (moveEvent.clientY - startY)))
    }
    clampToolbarPosition()
  }

  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    window.removeEventListener('pointercancel', up)
  }

  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  window.addEventListener('pointercancel', up)
}

function clampToolbarPosition() {
  const canvas = canvasRef.value
  if (!canvas) return
  const maxX = Math.max(8, canvas.clientWidth - 190)
  const maxY = Math.max(8, canvas.clientHeight - 56)
  viewport.value.toolbar = {
    x: Math.min(Math.max(8, viewport.value.toolbar.x), maxX),
    y: Math.min(Math.max(8, viewport.value.toolbar.y), maxY),
  }
}

function updateToolbarPosition(position: { x: number; y: number }) {
  viewport.value.toolbar = position
  clampToolbarPosition()
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

function addChildWithPosition() {
  const parent = selectedNode.value
  if (!parent) return
  const parentPosition = positionMap.value.get(parent.id)
  const childIndex = parent.children.length
  addChild(parent.id, parentPosition
    ? { x: parentPosition.x + X_GAP, y: parentPosition.y + (childIndex - 0.5) * Y_GAP }
    : undefined,
  )
}

function resetMap() {
  collapsedNodeIds.value = new Set()
  connectionFromId.value = ''
  clearAnalysisHighlights()
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

async function runMindMapAnalysis() {
  analysisLoading.value = true
  activeIssueId.value = ''
  highlightedNodeIds.value = new Set()
  try {
    analysisIssues.value = await analyzeMindMap(draftMindMap.value)
  } finally {
    analysisLoading.value = false
  }
}

function focusIssue(issue: MindMapAnalysisIssue) {
  activeIssueId.value = issue.id
  highlightedNodeIds.value = new Set(issue.nodeIds)
  const targetId = issue.nodeIds.find(id => draftMindMap.value.nodes[id])
  if (!targetId) return
  expandAncestors(targetId)
  selectNode(targetId)
  nextTick(() => centerNode(targetId))
}

function expandAncestors(id: string) {
  const next = new Set(collapsedNodeIds.value)
  let parentId = draftMindMap.value.nodes[id]?.parentId
  while (parentId) {
    next.delete(parentId)
    parentId = draftMindMap.value.nodes[parentId]?.parentId ?? null
  }
  collapsedNodeIds.value = next
}

function centerNode(id: string) {
  const canvas = canvasRef.value
  const node = positionMap.value.get(id)
  if (!canvas || !node) return
  const rect = canvas.getBoundingClientRect()
  viewport.value.pan = {
    x: rect.width / 2 - (node.x + NODE_WIDTH / 2) * viewport.value.zoom,
    y: rect.height / 2 - (node.y + NODE_HEIGHT / 2) * viewport.value.zoom,
  }
}

function clearAnalysisHighlights() {
  activeIssueId.value = ''
  highlightedNodeIds.value = new Set()
  analysisIssues.value = []
}

function saveAndStay() {
  saveMindMap()
  markSaved()
}

function saveAndEnterEditor() {
  saveMindMap()
  const outline = mindMapToMarkdown(draftMindMap.value)
  emit('enter-editor', outline)
}

async function aiExpandSelectedNode() {
  if (!selectedNode.value || expandingNode.value) return
  expandingNode.value = true
  try {
    await expandNode(selectedNodeId.value)
    nextTick(fitView)
  } finally {
    expandingNode.value = false
  }
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
  position: relative;
  display: grid;
  overflow: hidden;
}
.mindmap-outline,
.mindmap-ai-panel {
  min-width: 0;
  overflow: auto;
  background: var(--sidebar-bg);
}
.mindmap-outline {
  border-right: 1px solid var(--border-color);
}
.mindmap-body.outline-collapsed .mindmap-outline {
  overflow: hidden;
}
.mindmap-body.outline-collapsed .mindmap-outline .panel-title,
.mindmap-body.outline-collapsed .mindmap-outline .outline-node {
  display: none;
}
.mindmap-body.outline-hidden .mindmap-outline {
  display: none;
}
.mindmap-ai-panel {
  position: relative;
  border-left: 1px solid var(--border-color);
  padding: 14px;
}
.mindmap-ai-panel:not(.open) {
  overflow: hidden;
  padding: 0;
}
.outline-mode-button,
.ai-rail-button,
.ai-collapse-button,
.properties-collapse-button {
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--toolbar-bg);
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
}
.outline-mode-button {
  position: sticky;
  top: 8px;
  z-index: 2;
  margin: 8px;
  min-width: 26px;
  min-height: 26px;
}
.mindmap-body.outline-collapsed .outline-mode-button {
  writing-mode: vertical-rl;
  width: 26px;
  height: auto;
  min-height: 64px;
  margin: 10px auto;
}
.ai-rail-button {
  width: 28px;
  min-height: 72px;
  margin: 10px 6px;
  writing-mode: vertical-rl;
}
.ai-collapse-button,
.properties-collapse-button {
  position: absolute;
  z-index: 2;
  width: 24px;
  height: 24px;
}
.ai-collapse-button {
  top: 8px;
  right: 8px;
}
.properties-collapse-button {
  top: 6px;
  right: 10px;
}
.outline-mode-button:hover,
.ai-rail-button:hover,
.ai-collapse-button:hover,
.properties-collapse-button:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.pane-splitter {
  position: relative;
  z-index: 6;
  background: transparent;
  flex-shrink: 0;
}
.pane-splitter::after {
  content: '';
  position: absolute;
  inset: 0;
  background: transparent;
  transition: background 0.15s;
}
.pane-splitter:hover::after {
  background: color-mix(in srgb, var(--accent) 55%, transparent);
}
.pane-splitter.vertical {
  width: 4px;
  cursor: col-resize;
}
.pane-splitter.horizontal {
  height: 4px;
  cursor: row-resize;
}
.mindmap-workspace {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: grid;
}
.mindmap-properties {
  position: relative;
  min-width: 0;
  height: 100%;
  overflow: auto;
  border-top: 1px solid var(--border-color);
  background: var(--toolbar-bg);
  padding: 0 14px 12px;
  display: grid;
  grid-template-columns: minmax(220px, 1.2fr) repeat(4, minmax(110px, 0.45fr));
  gap: 10px 14px;
  align-items: start;
}
.mindmap-properties.collapsed {
  overflow: hidden;
  padding-bottom: 0;
}
.mindmap-properties.collapsed .inspector-label,
.mindmap-properties.collapsed .inspector-meta {
  display: none;
}
.mindmap-properties .panel-title {
  grid-column: 1 / -1;
  margin: 0 -14px;
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
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 260px;
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
.mindmap-canvas.connecting {
  cursor: crosshair;
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
}
.tree-line {
  stroke: var(--accent);
  stroke-width: 2;
  opacity: 0.52;
}
.association-line {
  stroke: color-mix(in srgb, var(--accent) 50%, var(--text-secondary));
  stroke-width: 1.8;
  stroke-dasharray: 8 7;
  opacity: 0.68;
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
  cursor: move;
  touch-action: none;
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
.map-node.source {
  outline: 3px dashed color-mix(in srgb, var(--accent) 72%, transparent);
  outline-offset: 5px;
}
.map-node.hinted {
  border-color: #f59e0b;
  box-shadow: 0 0 0 3px color-mix(in srgb, #f59e0b 28%, transparent), 0 12px 34px rgba(0, 0, 0, 0.22);
}
.issue-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  min-width: 18px;
  height: 18px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f59e0b;
  color: #111827;
  font-size: 11px;
  font-weight: 800;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28);
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
  min-height: 54px;
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
  min-height: 54px;
  margin-top: 20px;
  padding: 9px 10px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--editor-bg);
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
  .mindmap-properties {
    grid-template-columns: minmax(180px, 1fr) repeat(2, minmax(100px, 0.5fr));
  }
}

@media (max-width: 720px) {
  .mindmap-header {
    min-height: 54px;
  }

  .mindmap-body {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  .mindmap-outline,
  .pane-splitter.vertical {
    display: none;
  }

  .mindmap-ai-panel.open {
    display: block;
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 20;
    width: min(320px, 86vw);
    box-shadow: -18px 0 44px rgba(0, 0, 0, 0.28);
  }

  .mindmap-ai-panel:not(.open) {
    display: none;
  }

  .mindmap-properties {
    grid-template-columns: minmax(160px, 1fr);
  }
}
</style>
