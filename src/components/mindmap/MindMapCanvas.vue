<template>
  <div
    class="mindmap-canvas-wrapper"
    :class="{ connecting: !!connectionFromId }"
    @click="onClickWrapper"
    tabindex="0"
    ref="wrapperRef"
    @keydown="onCanvasKeydown"
    @keydown.esc="cancelConnection"
  >
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :default-edge-options="{ type: 'mindEdge' }"
      :connection-line-style="{ stroke: 'var(--c-accent)', strokeWidth: 2, strokeDasharray: '4 4' }"
      :edges-updatable="true"
      :elements-selectable="true"
      :select-nodes-on-drag="false"
      delete-key-code="''"
      fit-view-on-init
      @connect="onConnect"
      @nodes-change="onNodesChange"
      @node-click="onNodeClick"
      @edge-mouse-enter="onEdgeEnter"
      @edge-mouse-leave="onEdgeLeave"
    >
      <Background pattern-color="var(--c-surface-3)" :gap="20" />
      <Controls />
      <div
        class="minimap-panel"
        :class="[{ collapsed: minimap.collapsed }, `size-${minimap.size}`]"
        :style="{ left: `${minimap.x}px`, top: `${minimap.y}px` }"
        @pointerdown.stop="startMinimapDrag"
      >
        <div class="minimap-bar">
          <span class="minimap-title">{{ minimap.collapsed ? '小地图' : '地图' }}</span>
          <button type="button" @click.stop="$emit('toggle-minimap')">
            {{ minimap.collapsed ? '展开' : '收起' }}
          </button>
          <template v-if="!minimap.collapsed">
            <button type="button" :class="{ active: minimap.size === 'small' }" @click.stop="$emit('set-minimap-size', 'small')">S</button>
            <button type="button" :class="{ active: minimap.size === 'medium' }" @click.stop="$emit('set-minimap-size', 'medium')">M</button>
            <button type="button" :class="{ active: minimap.size === 'large' }" @click.stop="$emit('set-minimap-size', 'large')">L</button>
          </template>
        </div>
        <MiniMap
          v-if="!minimap.collapsed"
          class="mindmap-minimap"
          :width="miniMapSize.width"
          :height="miniMapSize.height"
          node-color="var(--c-accent)"
          node-stroke-color="transparent"
          :node-stroke-width="0"
          :node-border-radius="6"
          mask-color="rgba(99, 102, 241, 0.14)"
          mask-stroke-color="rgba(99, 102, 241, 0.62)"
          :mask-stroke-width="1"
          :mask-border-radius="8"
        />
      </div>
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, provide, ref, watch } from 'vue'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import type { Connection, NodeChange, GraphEdge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import MindNodeCard from './MindNodeCard.vue'
import MindEdge from './MindEdge.vue'
import {
  useMindMap, toFlowNodes, toFlowEdges,
} from '../../composables/useMindMap'
import { useMindMapKeyboard } from '../../composables/useMindMapKeyboard'

const props = defineProps<{
  connectionFromId: string
  minimap: { collapsed: boolean; size: 'small' | 'medium' | 'large'; x: number; y: number }
  viewCommand: { seq: number; type: 'zoom-in' | 'zoom-out' | 'reset-view' | 'fit-view' | '' }
}>()

const emit = defineEmits<{
  (e: 'update:connectionFromId', value: string): void
  (e: 'toggle-minimap'): void
  (e: 'set-minimap-size', value: 'small' | 'medium' | 'large'): void
  (e: 'update-minimap-position', value: { x: number; y: number }): void
}>()

const {
  draftMindMap, selectNode, commitNodePosition,
  addAssociationLink, removeAssociationLink, detachChild,
} = useMindMap()

const { getSelectedEdges, zoomIn, zoomOut, fitView, setViewport } = useVueFlow()

const nodeTypes = { mindNode: markRaw(MindNodeCard) }
const edgeTypes = { mindEdge: markRaw(MindEdge) }

const nodes = computed(() => toFlowNodes(draftMindMap.value))
const edges = computed(() => toFlowEdges(draftMindMap.value))
const miniMapSize = computed(() => {
  if (props.minimap.size === 'large') return { width: 176, height: 116 }
  if (props.minimap.size === 'small') return { width: 104, height: 66 }
  return { width: 136, height: 88 }
})

const hoveredEdgeId = ref('')
provide('hoveredEdgeId', hoveredEdgeId)

watch(() => props.viewCommand.seq, () => {
  if (props.viewCommand.type === 'zoom-in') zoomIn()
  else if (props.viewCommand.type === 'zoom-out') zoomOut()
  else if (props.viewCommand.type === 'fit-view') fitView({ padding: 0.18 })
  else if (props.viewCommand.type === 'reset-view') setViewport({ x: 0, y: 0, zoom: 1 })
})

function onConnect(conn: Connection) {
  if (conn.source && conn.target && conn.source !== conn.target) {
    addAssociationLink(conn.source, conn.target)
  }
}

function onNodesChange(changes: NodeChange[]) {
  for (const c of changes) {
    if (c.type === 'position' && c.position && !c.dragging) {
      commitNodePosition(c.id, c.position)
    }
  }
}

function onNodeClick({ node }: { node: { id: string } }) {
  if (props.connectionFromId) {
    if (props.connectionFromId !== node.id) addAssociationLink(props.connectionFromId, node.id)
    emit('update:connectionFromId', '')
  }
  selectNode(node.id)
}

function onEdgeEnter({ edge }: { edge: GraphEdge }) {
  hoveredEdgeId.value = edge.id
}

function onEdgeLeave() {
  hoveredEdgeId.value = ''
}

function deleteEdgeById(edgeId: string) {
  if (!edgeId) return
  if (edgeId.startsWith('tree-')) {
    const edge = edges.value.find(e => e.id === edgeId)
    const childId = (edge?.data as any)?.childId
    if (childId) detachChild(childId)
  } else {
    removeAssociationLink(edgeId)
  }
}

function onCanvasKeydown(e: KeyboardEvent) {
  const t = e.target as HTMLElement
  if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) return

  if (e.key === 'Delete' || e.key === 'Backspace') {
    e.preventDefault()
    const target = hoveredEdgeId.value || getSelectedEdges.value[0]?.id
    if (target) deleteEdgeById(target)
    return
  }

  const { onKeydown } = useMindMapKeyboard()
  onKeydown(e)
}

const wrapperRef = ref<HTMLElement>()

function onClickWrapper(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (target.closest('.vue-flow__node')) return
  wrapperRef.value?.focus()
  if (props.connectionFromId) emit('update:connectionFromId', '')
}

function cancelConnection() {
  if (props.connectionFromId) emit('update:connectionFromId', '')
}

function startMinimapDrag(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.tagName === 'BUTTON') return

  const wrapper = wrapperRef.value
  if (!wrapper) return
  const rect = wrapper.getBoundingClientRect()
  const origin = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    x: props.minimap.x,
    y: props.minimap.y,
  }
  const handle = event.currentTarget as HTMLElement
  handle.setPointerCapture(event.pointerId)

  const move = (moveEvent: PointerEvent) => {
    const width = props.minimap.size === 'large' ? 176 : props.minimap.size === 'medium' ? 136 : 104
    const height = (props.minimap.size === 'large' ? 116 : props.minimap.size === 'medium' ? 88 : 66) + 30
    const margin = 12
    const topSafe = 50
    emit('update-minimap-position', {
      x: Math.max(margin, Math.min(rect.width - width - margin, origin.x + moveEvent.clientX - origin.pointerX)),
      y: Math.max(topSafe, Math.min(rect.height - height - margin, origin.y + moveEvent.clientY - origin.pointerY)),
    })
  }

  const up = (upEvent: PointerEvent) => {
    handle.removeEventListener('pointermove', move)
    handle.removeEventListener('pointerup', up)
    handle.removeEventListener('pointercancel', up)
    if (handle.hasPointerCapture(upEvent.pointerId)) handle.releasePointerCapture(upEvent.pointerId)
  }

  handle.addEventListener('pointermove', move)
  handle.addEventListener('pointerup', up)
  handle.addEventListener('pointercancel', up)
}
</script>

<style scoped>
.mindmap-canvas-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  outline: none;
  overflow: hidden;
}
.mindmap-canvas-wrapper :deep(.vue-flow__background) {
  background: var(--editor-bg);
}
.mindmap-canvas-wrapper :deep(.vue-flow__controls) {
  left: 12px;
  bottom: 12px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border-color) 42%, transparent);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
}
.mindmap-canvas-wrapper.connecting {
  cursor: crosshair;
}
.mindmap-canvas-wrapper.connecting :deep(.vue-flow__node) {
  cursor: crosshair;
}
.minimap-panel {
  position: absolute;
  z-index: 8;
  display: flex;
  flex-direction: column;
  border-radius: 11px;
  border: 1px solid color-mix(in srgb, var(--border-color) 42%, transparent);
  background: color-mix(in srgb, var(--panel-bg) 76%, transparent);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.14);
  overflow: hidden;
  opacity: 0.54;
  cursor: grab;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  transition: opacity 0.16s, width 0.16s, height 0.16s, transform 0.16s;
}
.minimap-panel:hover {
  opacity: 0.94;
}
.minimap-panel:active {
  cursor: grabbing;
}
.minimap-panel.collapsed {
  min-width: 94px;
}
.minimap-bar {
  height: 28px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 3px 4px 3px 8px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-color) 34%, transparent);
  background: color-mix(in srgb, var(--toolbar-bg) 46%, transparent);
}
.minimap-title {
  flex: 1;
  min-width: 0;
  color: color-mix(in srgb, var(--text-secondary) 86%, transparent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.minimap-bar button {
  height: 20px;
  min-width: 21px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 10px;
  cursor: pointer;
}
.minimap-bar button:hover,
.minimap-bar button.active {
  background: var(--hover-bg);
  color: var(--accent);
}
.mindmap-canvas-wrapper :deep(.mindmap-minimap) {
  position: relative !important;
  inset: auto !important;
  right: auto !important;
  bottom: auto !important;
  left: auto !important;
  top: auto !important;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  overflow: hidden;
  opacity: 1;
}
.mindmap-canvas-wrapper :deep(.mindmap-minimap svg) {
  background: transparent;
}
.mindmap-canvas-wrapper :deep(.vue-flow__minimap-node) {
  opacity: 0.72;
}
.mindmap-canvas-wrapper :deep(.vue-flow__minimap-mask) {
  fill: rgba(99, 102, 241, 0.14);
  stroke: rgba(99, 102, 241, 0.62);
}
</style>
