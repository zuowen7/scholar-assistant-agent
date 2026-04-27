<template>
  <div
    class="mindmap-canvas-wrapper"
    :class="{ connecting: !!connectionFromId }"
    @click="onClickWrapper"
    tabindex="0"
    ref="wrapperRef"
    @keydown="onCanvasKeydown"
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
      <MiniMap node-color="var(--c-accent)" mask-color="rgba(0,0,0,0.4)" />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, provide, ref } from 'vue'
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

defineProps<{
  connectionFromId: string
}>()

const emit = defineEmits<{
  (e: 'update:connectionFromId', value: string): void
}>()

const {
  draftMindMap, selectNode, commitNodePosition,
  addAssociationLink, removeAssociationLink, detachChild,
} = useMindMap()

const { getSelectedEdges } = useVueFlow()

const nodeTypes = { mindNode: markRaw(MindNodeCard) }
const edgeTypes = { mindEdge: markRaw(MindEdge) }

const nodes = computed(() => toFlowNodes(draftMindMap.value))
const edges = computed(() => toFlowEdges(draftMindMap.value))

const hoveredEdgeId = ref('')
provide('hoveredEdgeId', hoveredEdgeId)

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

function onClickWrapper() {
  wrapperRef.value?.focus()
}
</script>

<style scoped>
.mindmap-canvas-wrapper {
  width: 100%;
  height: 100%;
  outline: none;
}
.mindmap-canvas-wrapper :deep(.vue-flow__background) {
  background: var(--editor-bg);
}
.mindmap-canvas-wrapper.connecting {
  cursor: crosshair;
}
.mindmap-canvas-wrapper.connecting :deep(.vue-flow__node) {
  cursor: crosshair;
}
</style>
