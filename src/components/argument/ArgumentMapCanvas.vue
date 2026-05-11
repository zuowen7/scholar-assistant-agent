<template>
  <div class="arg-canvas-wrapper" @click="onClickWrapper" tabindex="0">
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :default-edge-options="{ type: 'argEdge' }"
      :connection-line-style="{ stroke: 'var(--c-accent)', strokeWidth: 2, strokeDasharray: '4 4' }"
      :elements-selectable="!readonly"
      :nodes-draggable="!readonly"
      :nodes-connectable="!readonly"
      fit-view-on-init
      @connect="onConnect"
      @node-click="onNodeClick"
      @edge-click="onEdgeClick"
      @nodes-change="onNodesChange"
    >
      <Background pattern-color="var(--c-surface-3)" :gap="20" />
      <Controls v-if="!readonly" />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue'
import { VueFlow } from '@vue-flow/core'
import type { Connection, NodeChange, NodeMouseEvent, EdgeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useArgumentMap, inferRelationType, toFlowNodes, toFlowEdges } from '../../composables/useArgumentMap'
import type { RelationType } from '../../composables/useArgumentMap'
import { useToast } from '../../composables/useToast'
import ArgNodeCard from './ArgNodeCard.vue'
import ArgEdge from './ArgEdge.vue'

const props = withDefaults(defineProps<{ readonly?: boolean }>(), { readonly: false })

const { state, upsertEdge } = useArgumentMap()
const { danger } = useToast()

const nodeTypes = { argNode: markRaw(ArgNodeCard) }
const edgeTypes = { argEdge: markRaw(ArgEdge) }

const flowNodes = computed(() => state.graph ? toFlowNodes(state.graph) : [])
const flowEdges = computed(() => state.graph ? toFlowEdges(state.graph) : [])

function onClickWrapper(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('arg-canvas-wrapper')) {
    state.selectedNodeId = ''
    state.selectedEdgeId = ''
  }
}

function onNodeClick(e: NodeMouseEvent) {
  state.selectedNodeId = e.node.id
  state.selectedEdgeId = ''
}

function onEdgeClick(e: EdgeMouseEvent) {
  state.selectedEdgeId = e.edge.id
  state.selectedNodeId = ''
}

async function onConnect(conn: Connection) {
  if (!conn.source || !conn.target || !state.graph) return

  const srcNode = state.graph.nodes.find(n => n.id === conn.source)
  const tgtNode = state.graph.nodes.find(n => n.id === conn.target)
  if (!srcNode || !tgtNode) return

  const relType = inferRelationType(srcNode.node_type, tgtNode.node_type)
  if (!relType) {
    danger(`无效关系：${srcNode.node_type} → ${tgtNode.node_type}`)
    return
  }

  try {
    await upsertEdge({
      source_id: conn.source,
      target_id: conn.target,
      relation_type: relType as RelationType,
    })
  } catch {
    danger('创建关系失败')
  }
}

function onNodesChange(changes: NodeChange[]) {
  // Sync position changes to local state (no API call for position drag)
  for (const change of changes) {
    if (change.type === 'position' && change.position && state.graph) {
      const node = state.graph.nodes.find(n => n.id === change.id)
      if (node) node.position = change.position
    }
  }
}
</script>

<style scoped>
.arg-canvas-wrapper {
  width: 100%;
  height: 100%;
  outline: none;
}
</style>
