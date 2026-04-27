<template>
  <div class="mindmap-view">
    <div class="mindmap-header">
      <div>
        <div class="mindmap-kicker">Mind Map</div>
        <h2>思维导图</h2>
      </div>
      <div class="view-meta">
        <span v-if="connectionFromId">选择目标节点以完成连接</span>
        <span v-else>{{ nodeCount }} 个节点</span>
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
      <main class="mindmap-canvas-vf">
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
          @delete-node="deleteSelectedNode"
          @reset-view="() => {}"
          @fit-view="() => {}"
          @save="saveAndStay"
          @enter-editor="saveAndEnterEditor"
          @auto-layout="autoLayout"
        />

        <MindMapCanvas
          :connection-from-id="connectionFromId"
          @update:connection-from-id="connectionFromId = $event"
        />
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
          <strong>{{ nodeCount }}</strong>
        </div>
        <div class="inspector-meta">
          <span>关联线</span>
          <strong>{{ draftMindMap.links.length }}</strong>
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
import MindMapCanvas from './mindmap/MindMapCanvas.vue'
import { useMindMap, mindMapToMarkdown, setAnalysisIssues } from '../composables/useMindMap'
import { useMindMapAnalysis, type MindMapAnalysisIssue } from '../composables/useMindMapAnalysis'
import { useMindMapLayout } from '../composables/useMindMapLayout'

const emit = defineEmits<{
  (e: 'enter-editor', outline: string): void
}>()

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
  addChild,
  addAssociationLink,
  expandNode,
  deleteNode,
} = useMindMap()
const { analyzeMindMap } = useMindMapAnalysis()
const { autoLayout } = useMindMapLayout()

const selectedText = ref('')
const saveMessage = ref('')
const collapsedNodeIds = ref<Set<string>>(new Set())
const connectionFromId = ref('')
const analysisIssues = ref<MindMapAnalysisIssue[]>([])
const analysisLoading = ref(false)
const expandingNode = ref(false)
const activeIssueId = ref('')
const outlineMode = ref<OutlineMode>('collapsed')
const outlineWidth = ref(178)
const aiPanelOpen = ref(true)
const aiPanelWidth = ref(284)
const propertiesCollapsed = ref(false)
const propertiesHeight = ref(148)
let canvasResizeObserver: ResizeObserver | null = null

const canDelete = computed(() => !!selectedNode.value && selectedNodeId.value !== draftMindMap.value.rootId)
const nodeCount = computed(() => Object.keys(draftMindMap.value.nodes).length)

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
  clampPaneSizes()
  await loadFromBackend()
})

onBeforeUnmount(() => {
  canvasResizeObserver?.disconnect()
  window.removeEventListener('resize', handleWindowResize)
})

function applyInspectorText() {
  if (selectedNode.value) updateNodeText(selectedNode.value.id, selectedText.value)
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
  const canvas = document.querySelector('.mindmap-canvas-vf')
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
  saveMessage.value = '已保存'
  window.setTimeout(() => {
    if (saveMessage.value === '已保存') saveMessage.value = ''
  }, 1800)
}

async function runMindMapAnalysis() {
  analysisLoading.value = true
  activeIssueId.value = ''
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
.mindmap-canvas-vf {
  position: relative;
  overflow: hidden;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 260px;
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
