<template>
  <div class="mindmap-view">
    <div class="mindmap-header">
      <div class="mindmap-title-row">
        <span class="mindmap-badge">&#24605;&#32500;&#23548;&#22270;</span>
        <span class="mindmap-node-count">
          <span v-if="connectionFromId">&#36873;&#25321;&#30446;&#26631;&#33410;&#28857;&#20197;&#23436;&#25104;&#36830;&#25509;</span>
          <span v-else>{{ nodeCount }} &#20010;&#33410;&#28857;</span>
        </span>
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
          v-if="outlineMode !== 'expanded'"
          class="outline-rail-button"
          :title="t('mindmap.expandOutline')"
          @click="outlineMode = 'expanded'"
        >
          &#22823;&#32434;
        </button>
        <div v-else class="panel-title outline-title">
          <span>&#22823;&#32434;</span>
          <button
            class="outline-collapse-button"
            :title="t('mindmap.collapseOutline')"
            @click="outlineMode = 'hidden'"
          >
            &lt;
          </button>
        </div>
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
            {{ node.collapsed ? '>' : 'v' }}
          </span>
          <span v-else class="collapse-spacer" />
          <span class="outline-text">{{ node.text }}</span>
        </button>
      </aside>

      <div
        v-if="outlineMode === 'expanded'"
        class="pane-splitter vertical"
        :title="t('mindmap.dragOutlineWidth')"
        @pointerdown="startPaneResize($event, 'outline')"
      />

      <section class="mindmap-workspace" :style="mindmapWorkspaceStyle">
      <main class="mindmap-canvas-vf">
        <MindMapFloatingToolbar
          :position="viewport.toolbar"
          :can-add="!!selectedNode"
          :can-delete="canDelete"
          :connecting="!!connectionFromId"
          :analyzing="analysisLoading"
          :expanding="expandingNode"
          :collapsed="toolbarCollapsed"
          @update:position="updateToolbarPosition"
          @update:collapsed="toolbarCollapsed = $event"
          @reset-map="resetMap"
          @add-child="addChildWithPosition"
          @ai-expand="aiExpandSelectedNode"
          @analyze="runMindMapAnalysis"
          @start-connect="startConnection"
          @delete-node="deleteSelectedNode"
          @zoom-in="sendViewCommand('zoom-in')"
          @zoom-out="sendViewCommand('zoom-out')"
          @reset-view="sendViewCommand('reset-view')"
          @fit-view="sendViewCommand('fit-view')"
          @save="saveAndStay"
          @enter-editor="saveAndEnterEditor"
          @auto-layout="autoLayout"
          @reset-layout="resetLayout"
        />

        <MindMapCanvas
          :connection-from-id="connectionFromId"
          :minimap="miniMap"
          :view-command="viewCommand"
          :expanding-node-id="expandingNode ? selectedNodeId : ''"
          @update:connection-from-id="connectionFromId = $event"
          @toggle-minimap="toggleMiniMap"
          @set-minimap-size="setMiniMapSize"
          @update-minimap-position="updateMiniMapPosition"
        />
      </main>

      <div
        v-if="!propertiesCollapsed"
        class="pane-splitter horizontal"
        title="Drag properties height"
        @pointerdown="startPaneResize($event, 'properties')"
      />

      <section class="mindmap-properties" :class="{ collapsed: propertiesCollapsed, detailed: propertyDetailsVisible }">
        <div class="properties-header">
          <div class="panel-title">&#23646;&#24615;</div>
          <div class="properties-actions">
            <button
              v-if="!propertiesCollapsed"
              class="properties-detail-button"
              @click="propertyDetailsOpen = !propertyDetailsOpen"
            >
              {{ propertyDetailsOpen ? '\u6536\u8d77\u7f16\u8f91' : '\u7f16\u8f91\u8282\u70b9\u6587\u5b57' }}
            </button>
            <button
              class="properties-collapse-button"
              :title="propertiesCollapsed ? 'Expand properties' : 'Collapse properties'"
              @click="propertiesCollapsed = !propertiesCollapsed"
            >
              {{ propertiesCollapsed ? '^' : 'v' }}
            </button>
          </div>
        </div>

        <div v-if="!propertiesCollapsed" class="property-summary">
          <span class="summary-main">{{ selectedNode?.text || '\u672a\u9009\u62e9\u8282\u70b9' }}</span>
          <span>{{ nodeCount }} &#33410;&#28857;</span>
          <span>{{ draftMindMap.links.length }} &#20851;&#32852;&#32447;</span>
          <span>{{ Math.round(viewport.zoom * 100) }}%</span>
          <span>{{ saveMessage || '\u672a\u4fdd\u5b58' }}</span>
        </div>

        <div v-if="propertyDetailsVisible" class="property-details">
          <label class="inspector-label">
            &#33410;&#28857;&#25991;&#23383;
            <textarea
              v-model="selectedText"
              class="inspector-input"
              rows="4"
              :disabled="!selectedNode"
              @change="applyInspectorText"
            />
          </label>
          <div class="inspector-meta-grid">
            <div class="inspector-meta">
              <span>&#33410;&#28857;&#25968;</span>
              <strong>{{ nodeCount }}</strong>
            </div>
            <div class="inspector-meta">
              <span>&#20851;&#32852;&#32447;</span>
              <strong>{{ draftMindMap.links.length }}</strong>
            </div>
            <div class="inspector-meta">
              <span>&#20445;&#23384;&#29366;&#24577;</span>
              <strong>{{ saveMessage || '\u672a\u4fdd\u5b58' }}</strong>
            </div>
          </div>
        </div>
      </section>
      </section>

      <div
        v-if="aiPanelOpen"
        class="pane-splitter vertical"
        :title="t('mindmap.dragAiPanelWidth')"
        @pointerdown="startPaneResize($event, 'ai')"
      />
      <aside class="mindmap-ai-panel" :class="{ open: aiPanelOpen }">
        <button
          v-if="!aiPanelOpen"
          class="ai-rail-button"
          :title="t('mindmap.expandAiHints')"
          @click="aiPanelOpen = true"
        >
          AI
        </button>
        <button
          v-else
          class="ai-collapse-button"
          :title="t('mindmap.collapseAiHints')"
          @click="aiPanelOpen = false"
        >
          ×
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
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import MindMapFloatingToolbar from './MindMapFloatingToolbar.vue'
import MindMapAiHints from './MindMapAiHints.vue'
import MindMapCanvas from './mindmap/MindMapCanvas.vue'
import { useMindMap, mindMapToMarkdown, setAnalysisIssues } from '../composables/useMindMap'
import { useMindMapAnalysis, type MindMapAnalysisIssue } from '../composables/useMindMapAnalysis'
import { useMindMapLayout } from '../composables/useMindMapLayout'
import { useMindMapKeyboard } from '../composables/useMindMapKeyboard'

const emit = defineEmits<{
  (e: 'enter-editor', outline: string): void
}>()

type PaneResizeTarget = 'outline' | 'ai' | 'properties'
type OutlineMode = 'expanded' | 'collapsed' | 'hidden'
type ViewCommandType = 'zoom-in' | 'zoom-out' | 'reset-view' | 'fit-view' | ''
type MiniMapSize = 'small' | 'medium' | 'large'
interface MindMapLayoutState {
  outlineMode: OutlineMode
  outlineWidth: number
  aiPanelOpen: boolean
  aiPanelWidth: number
  propertiesCollapsed: boolean
  propertiesHeight: number
  propertyDetailsOpen: boolean
  toolbarCollapsed: boolean
  miniMap: { collapsed: boolean; size: MiniMapSize; x: number; y: number; docked: boolean }
}

const LAYOUT_STORAGE_KEY = 'scholar.mindmap.layout.v2'

const defaultLayoutState = (): MindMapLayoutState => ({
  outlineMode: 'collapsed',
  outlineWidth: 178,
  aiPanelOpen: true,
  aiPanelWidth: 284,
  propertiesCollapsed: false,
  propertiesHeight: 132,
  propertyDetailsOpen: false,
  toolbarCollapsed: false,
  miniMap: { collapsed: false, size: 'medium', x: 0, y: 0, docked: true },
})

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
  addChild,
  addAssociationLink,
  expandNode,
  deleteNode,
} = useMindMap()
const { analyzeMindMap } = useMindMapAnalysis()
const { autoLayout } = useMindMapLayout()
const { onKeydown } = useMindMapKeyboard()

const selectedText = ref('')
const saveMessage = ref('')
const collapsedNodeIds = ref<Set<string>>(new Set())
const connectionFromId = ref('')
const analysisIssues = ref<MindMapAnalysisIssue[]>([])
const analysisLoading = ref(false)
const expandingNode = ref(false)
const activeIssueId = ref('')
const initialLayout = loadLayoutState()
const outlineMode = ref<OutlineMode>(initialLayout.outlineMode)
const outlineWidth = ref(initialLayout.outlineWidth)
const aiPanelOpen = ref(initialLayout.aiPanelOpen)
const aiPanelWidth = ref(initialLayout.aiPanelWidth)
const propertiesCollapsed = ref(initialLayout.propertiesCollapsed)
const propertiesHeight = ref(initialLayout.propertiesHeight)
const propertyDetailsOpen = ref(initialLayout.propertyDetailsOpen)
const toolbarCollapsed = ref(initialLayout.toolbarCollapsed)
const miniMap = ref({ ...initialLayout.miniMap })
const viewCommand = ref<{ seq: number; type: ViewCommandType }>({ seq: 0, type: '' })
let canvasResizeObserver: ResizeObserver | null = null

const canDelete = computed(() => !!selectedNode.value && selectedNodeId.value !== draftMindMap.value.rootId)
const nodeCount = computed(() => Object.keys(draftMindMap.value.nodes).length)
const propertyDetailsVisible = computed(() => !propertiesCollapsed.value && propertyDetailsOpen.value)

watch([
  outlineMode,
  outlineWidth,
  aiPanelOpen,
  aiPanelWidth,
  propertiesCollapsed,
  propertiesHeight,
  propertyDetailsOpen,
  toolbarCollapsed,
  miniMap,
], persistLayoutState, { deep: true })

watch([propertiesCollapsed, propertyDetailsOpen, propertiesHeight], () => {
  nextTick(() => clampMiniMapPosition())
})

watch([aiPanelOpen, aiPanelWidth, outlineMode, outlineWidth], () => {
  nextTick(() => {
    clampToolbarPosition()
    clampMiniMapPosition()
  })
})

watch(aiPanelOpen, () => {
  nextTick(() => recenterCanvasForSafeArea())
})

const mindmapBodyStyle = computed(() => {
  const outlineColumn = outlineMode.value === 'expanded' ? `${outlineWidth.value}px` : '36px'
  const aiColumn = aiPanelOpen.value ? `${aiPanelWidth.value}px` : '42px'
  return {
    gridTemplateColumns: `${outlineColumn} ${outlineMode.value === 'expanded' ? '4px ' : ''}minmax(320px, 1fr) ${aiPanelOpen.value ? '4px ' : ''}${aiColumn}`,
  }
})

const mindmapWorkspaceStyle = computed(() => ({
  gridTemplateRows: propertiesCollapsed.value
    ? 'minmax(0, 1fr) 42px'
    : propertyDetailsOpen.value
      ? `minmax(0, 1fr) 4px ${propertiesHeight.value}px`
      : 'minmax(0, 1fr) 4px 60px',
}))

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

watch(selectedNode, (node) => {
  selectedText.value = node?.text ?? ''
}, { immediate: true })

onMounted(async () => {
  canvasResizeObserver = new ResizeObserver(() => {
    clampPaneSizes()
    clampToolbarPosition()
  })
  canvasResizeObserver.observe(document.documentElement)
  window.addEventListener('resize', handleWindowResize)
  window.addEventListener('keydown', onKeydown)
  clampPaneSizes()
  await nextTick()
  placeMiniMapIfNeeded()
  await loadFromBackend()
  await nextTick()
  recenterCanvasForSafeArea()
})

onBeforeUnmount(() => {
  canvasResizeObserver?.disconnect()
  window.removeEventListener('resize', handleWindowResize)
  window.removeEventListener('keydown', onKeydown)
  _paneResizeCleanup?.()
  _paneResizeCleanup = null
})

function applyInspectorText() {
  if (selectedNode.value) updateNodeText(selectedNode.value.id, selectedText.value)
}

function handleWindowResize() {
  clampPaneSizes()
  clampToolbarPosition()
  clampMiniMapPosition()
}

function loadLayoutState(): MindMapLayoutState {
  if (typeof window === 'undefined') return defaultLayoutState()
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (!raw) return defaultLayoutState()
    const parsed = JSON.parse(raw) as Partial<MindMapLayoutState>
    const fallback = defaultLayoutState()
    const parsedMiniMap = parsed.miniMap as Partial<MindMapLayoutState['miniMap']> | undefined
    const hasDockedState = typeof parsedMiniMap?.docked === 'boolean'
    return {
      ...fallback,
      ...parsed,
      miniMap: {
        ...fallback.miniMap,
        ...(parsedMiniMap ?? {}),
        docked: hasDockedState ? parsedMiniMap.docked! : true,
      },
    }
  } catch {
    return defaultLayoutState()
  }
}

function persistLayoutState() {
  if (typeof window === 'undefined') return
  const state: MindMapLayoutState = {
    outlineMode: outlineMode.value,
    outlineWidth: outlineWidth.value,
    aiPanelOpen: aiPanelOpen.value,
    aiPanelWidth: aiPanelWidth.value,
    propertiesCollapsed: propertiesCollapsed.value,
    propertiesHeight: propertiesHeight.value,
    propertyDetailsOpen: propertyDetailsOpen.value,
    toolbarCollapsed: toolbarCollapsed.value,
    miniMap: { ...miniMap.value },
  }
  window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(state))
}

function resetLayout() {
  const state = defaultLayoutState()
  outlineMode.value = state.outlineMode
  outlineWidth.value = state.outlineWidth
  aiPanelOpen.value = state.aiPanelOpen
  aiPanelWidth.value = state.aiPanelWidth
  propertiesCollapsed.value = state.propertiesCollapsed
  propertiesHeight.value = state.propertiesHeight
  propertyDetailsOpen.value = state.propertyDetailsOpen
  toolbarCollapsed.value = state.toolbarCollapsed
  miniMap.value = { ...state.miniMap }
  nextTick(() => {
    placeMiniMapIfNeeded(true)
    clampPaneSizes()
    clampToolbarPosition()
  })
}

function clampPaneSizes() {
  const width = window.innerWidth
  const height = window.innerHeight

  outlineWidth.value = Math.min(Math.max(outlineWidth.value, 132), Math.max(132, width * 0.28))
  aiPanelWidth.value = Math.min(Math.max(aiPanelWidth.value, 220), Math.max(220, width * 0.36))
  propertiesHeight.value = Math.min(Math.max(propertiesHeight.value, 92), Math.max(92, height * 0.28))

  if (width < 760) {
    outlineMode.value = 'hidden'
    if (analysisIssues.value.length === 0) aiPanelOpen.value = false
  } else if (width < 1040 && outlineMode.value === 'expanded') {
    outlineMode.value = 'hidden'
  }

  if (height < 640) propertiesCollapsed.value = true
  clampMiniMapPosition()
}

let _paneResizeCleanup: (() => void) | null = null

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
      propertiesHeight.value = Math.max(92, Math.min(220, startProperties - (moveEvent.clientY - startY)))
    }
    clampToolbarPosition()
    clampMiniMapPosition()
  }

  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    window.removeEventListener('pointercancel', up)
    _paneResizeCleanup = null
  }

  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
  window.addEventListener('pointercancel', up)
  _paneResizeCleanup = up
}

function clampToolbarPosition() {
  const canvas = document.querySelector('.mindmap-canvas-vf')
  if (!canvas) return
  const maxX = Math.max(8, canvas.clientWidth - 190)
  const maxY = Math.max(8, canvas.clientHeight - 56)
  viewport.value.toolbar = {
    x: Math.min(Math.max(8, viewport.value.toolbar.x), maxX),
    y: Math.min(Math.max(8, viewport.value.toolbar.y), maxY),
  }
}

function getMiniMapSize() {
  if (miniMap.value.size === 'large') return { width: 176, height: 144 }
  if (miniMap.value.size === 'small') return { width: 104, height: 94 }
  return { width: 136, height: 116 }
}

function getMiniMapBounds() {
  const canvas = document.querySelector('.mindmap-canvas-vf')
  if (!canvas) return null
  const size = getMiniMapSize()
  const margin = 12
  const topSafe = 50
  return {
    minX: margin,
    minY: topSafe,
    maxX: Math.max(margin, canvas.clientWidth - size.width - margin),
    maxY: Math.max(topSafe, canvas.clientHeight - size.height - margin),
    size,
  }
}

function placeMiniMapIfNeeded(force = false) {
  const bounds = getMiniMapBounds()
  if (!bounds) return
  if (!force && !miniMap.value.docked) {
    clampMiniMapPosition()
    return
  }
  miniMap.value = {
    ...miniMap.value,
    x: bounds.maxX,
    y: bounds.maxY,
  }
}

function clampMiniMapPosition() {
  const bounds = getMiniMapBounds()
  if (!bounds) return
  if (miniMap.value.docked) {
    placeMiniMapIfNeeded(true)
    return
  }
  miniMap.value.x = Math.max(bounds.minX, Math.min(bounds.maxX, miniMap.value.x))
  miniMap.value.y = Math.max(bounds.minY, Math.min(bounds.maxY, miniMap.value.y))
}

function toggleMiniMap() {
  miniMap.value.collapsed = !miniMap.value.collapsed
  if (!miniMap.value.collapsed) nextTick(() => placeMiniMapIfNeeded())
}

function setMiniMapSize(size: MiniMapSize) {
  miniMap.value.size = size
  nextTick(() => {
    if (miniMap.value.docked) placeMiniMapIfNeeded(true)
    else clampMiniMapPosition()
  })
}

function updateMiniMapPosition(position: { x: number; y: number }) {
  miniMap.value = {
    ...miniMap.value,
    ...position,
    docked: false,
  }
  clampMiniMapPosition()
}

function updateToolbarPosition(position: { x: number; y: number }) {
  viewport.value.toolbar = position
  clampToolbarPosition()
}

function recenterCanvasForSafeArea() {
  if (!nodeCount.value) return
  sendViewCommand('fit-view')
}

function sendViewCommand(type: Exclude<ViewCommandType, ''>) {
  viewCommand.value = { seq: viewCommand.value.seq + 1, type }
  if (type === 'zoom-in') viewport.value.zoom = Math.min(2, Number((viewport.value.zoom + 0.1).toFixed(2)))
  if (type === 'zoom-out') viewport.value.zoom = Math.max(0.3, Number((viewport.value.zoom - 0.1).toFixed(2)))
  if (type === 'reset-view' || type === 'fit-view') viewport.value.zoom = 1
}

function addChildWithPosition() {
  const parent = selectedNode.value
  if (!parent) return
  addChild(parent.id)
}

function resetMap() {
  collapsedNodeIds.value = new Set()
  connectionFromId.value = ''
  clearAnalysisHighlights()
  resetMindMap()
}

function toggleCollapse(id: string) {
  const next = new Set(collapsedNodeIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  collapsedNodeIds.value = next
}

function markSaved() {
  saveMessage.value = '\u5df2\u4fdd\u5b58'
  window.setTimeout(() => {
    if (saveMessage.value === '\u5df2\u4fdd\u5b58') saveMessage.value = ''
  }, 1800)
}

async function runMindMapAnalysis() {
  analysisLoading.value = true
  activeIssueId.value = ''
  aiPanelOpen.value = true
  try {
    analysisIssues.value = await analyzeMindMap(draftMindMap.value)
    setAnalysisIssues(analysisIssues.value)
  } finally {
    analysisLoading.value = false
  }
}

function focusIssue(issue: MindMapAnalysisIssue) {
  activeIssueId.value = issue.id
  const targetId = issue.nodeIds.find(id => draftMindMap.value.nodes[id])
  if (!targetId) return
  expandAncestors(targetId)
  selectNode(targetId)
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

function clearAnalysisHighlights() {
  activeIssueId.value = ''
  analysisIssues.value = []
  setAnalysisIssues([])
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

function startConnection() {
  if (!selectedNode.value) return
  connectionFromId.value = connectionFromId.value === selectedNodeId.value ? '' : selectedNodeId.value
}

function deleteSelectedNode() {
  if (selectedNodeId.value && selectedNodeId.value !== draftMindMap.value.rootId) {
    deleteNode(selectedNodeId.value)
  }
}

async function aiExpandSelectedNode() {
  if (!selectedNode.value || expandingNode.value) return
  expandingNode.value = true
  try {
    await expandNode(selectedNodeId.value)
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
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--toolbar-bg);
}
.mindmap-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.mindmap-badge {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--c-accent);
  letter-spacing: 0.01em;
}
.mindmap-node-count {
  font-size: var(--text-sm);
  color: var(--c-text-3);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-pill);
  padding: 2px 8px;
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
  background: color-mix(in srgb, var(--sidebar-bg) 86%, transparent);
}
.mindmap-outline {
  position: relative;
  border-right: 1px solid color-mix(in srgb, var(--border-color) 58%, transparent);
}
.mindmap-body.outline-collapsed .mindmap-outline,
.mindmap-body.outline-hidden .mindmap-outline {
  overflow: hidden;
}
.mindmap-body.outline-collapsed .mindmap-outline .panel-title,
.mindmap-body.outline-collapsed .mindmap-outline .outline-node,
.mindmap-body.outline-hidden .mindmap-outline .panel-title,
.mindmap-body.outline-hidden .mindmap-outline .outline-node {
  display: none;
}
.mindmap-ai-panel {
  position: relative;
  border-left: 1px solid color-mix(in srgb, var(--border-color) 54%, transparent);
  padding: 12px;
}
.mindmap-ai-panel.open {
  padding-top: 38px;
}
.mindmap-ai-panel:not(.open) {
  overflow: hidden;
  padding: 0;
}
.outline-rail-button,
.ai-rail-button,
.ai-collapse-button,
.outline-collapse-button,
.properties-collapse-button {
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: color-mix(in srgb, var(--toolbar-bg) 72%, transparent);
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
}
.outline-rail-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: sticky;
  top: 10px;
  z-index: 8;
  width: 30px;
  height: 72px;
  margin: 10px auto;
  padding: 8px 6px;
  border-radius: 9px 0 0 9px;
  background: color-mix(in srgb, var(--toolbar-bg) 54%, transparent);
  border-color: color-mix(in srgb, var(--border-color) 46%, transparent);
  white-space: normal;
  line-height: 1.25;
  color: color-mix(in srgb, var(--text-secondary) 84%, transparent);
}
.outline-title {
  position: sticky;
  top: 0;
  z-index: 9;
  background: color-mix(in srgb, var(--sidebar-bg) 92%, transparent);
  justify-content: space-between;
  gap: 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 42%, transparent);
}
.outline-collapse-button {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  z-index: 10;
}
.ai-rail-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  min-height: 96px;
  margin: 10px 5px;
  writing-mode: horizontal-tb;
  border-radius: 0 9px 9px 0;
  background: color-mix(in srgb, var(--toolbar-bg) 54%, transparent);
  border-color: color-mix(in srgb, var(--border-color) 46%, transparent);
  font-weight: 700;
}
.ai-collapse-button {
  position: absolute;
  z-index: 4;
  width: 24px;
  height: 24px;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  font-size: 18px;
  background: color-mix(in srgb, var(--toolbar-bg) 84%, transparent);
  border-color: color-mix(in srgb, var(--border-color) 52%, transparent);
}
.properties-collapse-button {
  width: 24px;
  height: 24px;
}
.outline-rail-button:hover,
.ai-rail-button:hover,
.ai-collapse-button:hover,
.outline-collapse-button:hover,
.properties-collapse-button:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
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
  background: color-mix(in srgb, var(--c-accent) 55%, transparent);
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
.mindmap-canvas-vf {
  position: relative;
  overflow: visible;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 260px;
  /* 淡墨点阵 — 书法九宫格意境 */
  background-image: radial-gradient(circle, var(--c-surface-3) 1px, transparent 1px);
  background-size: 24px 24px;
}
.mindmap-properties {
  position: relative;
  min-width: 0;
  height: 100%;
  overflow: auto;
  border-top: 1px solid color-mix(in srgb, var(--border-color) 52%, transparent);
  background: color-mix(in srgb, var(--toolbar-bg) 64%, transparent);
  padding: 0 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.mindmap-properties.collapsed {
  overflow: hidden;
  padding-bottom: 0;
}
.mindmap-properties.collapsed .property-summary,
.mindmap-properties.collapsed .property-details {
  display: none;
}
.properties-header {
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 -12px;
  padding: 0 10px 0 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 48%, transparent);
}
.panel-title {
  display: flex;
  align-items: center;
  color: color-mix(in srgb, var(--text-secondary) 78%, transparent);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.properties-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.property-summary {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  padding: 2px 0 0;
}
.property-summary span {
  flex-shrink: 0;
}
.property-summary .summary-main {
  min-width: 0;
  max-width: min(360px, 42vw);
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
  font-weight: 650;
}
.properties-detail-button {
  height: 24px;
  border: 1px solid color-mix(in srgb, var(--border-color) 58%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--panel-bg) 76%, transparent);
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.properties-detail-button:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
}
.property-details {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(240px, 0.9fr);
  gap: 10px;
  align-items: stretch;
  padding-bottom: 4px;
}
.outline-node {
  width: 100%;
  min-height: 32px;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 36%, transparent);
  background: transparent;
  color: color-mix(in srgb, var(--text-primary) 86%, transparent);
  text-align: left;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
.mindmap-body.outline-collapsed .outline-node {
  min-height: 28px;
  font-size: 11px;
  padding-right: 8px;
}
.mindmap-body.outline-collapsed .collapse-toggle,
.mindmap-body.outline-collapsed .collapse-spacer {
  width: 10px;
}
.mindmap-body.outline-collapsed .panel-title {
  height: 24px;
  padding: 0 8px;
  font-size: 10px;
}
.outline-node:hover,
.outline-node.active {
  background: color-mix(in srgb, var(--hover-bg) 72%, transparent);
  color: var(--c-accent);
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
  color: var(--c-accent);
}
.outline-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inspector-label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.inspector-input {
  min-height: 74px;
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
  border-color: var(--c-accent);
}
.inspector-meta-grid {
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.inspector-meta {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 12px;
  min-height: 74px;
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
  .property-details {
    grid-template-columns: minmax(0, 1fr);
  }

  .inspector-meta-grid {
    grid-template-columns: repeat(3, minmax(100px, 1fr));
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
    padding-left: 10px;
    padding-right: 10px;
  }

  .properties-header {
    margin-left: -10px;
    margin-right: -10px;
  }

  .inspector-meta-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
