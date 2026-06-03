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
    <div v-if="state.extracting" class="canvas-extracting-overlay">
      <div class="canvas-extracting-pill">
        <span class="dot-wave"><i></i><i></i><i></i></span>
        <span class="canvas-extracting-label">{{ t('argument.buildingMap') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { VueFlow } from '@vue-flow/core'
import type { Connection, NodeChange, NodeMouseEvent, EdgeMouseEvent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { useArgumentMap, inferRelationType, toFlowNodes, toFlowEdges, focusNode } from '../../composables/useArgumentMap'
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
  focusNode(e.node.id)
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
    danger(t('argument.invalidRelation', { src: srcNode.node_type, tgt: tgtNode.node_type }))
    return
  }

  try {
    await upsertEdge({
      source_id: conn.source,
      target_id: conn.target,
      relation_type: relType as RelationType,
    })
  } catch {
    danger(t('argument.deleteRelation'))
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
  position: relative;
  width: 100%;
  height: 100%;
  outline: none;
}

.canvas-extracting-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 28px;
  pointer-events: none;
  z-index: 10;
}

.canvas-extracting-pill {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 18px;
  background: color-mix(in srgb, var(--c-accent) 12%, var(--c-surface-1));
  border: 1px solid color-mix(in srgb, var(--c-accent) 35%, transparent);
  border-radius: 20px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: var(--elevation-3);
  animation: pill-appear 0.25s var(--ease-out, cubic-bezier(0.4, 0, 0.2, 1));
}
@keyframes pill-appear {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.canvas-extracting-label {
  font-size: 12px;
  color: var(--c-text-1);
  white-space: nowrap;
}

.dot-wave { display: flex; gap: 4px; align-items: center; }
.dot-wave i {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-accent); display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes wave-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.25; }
  30%            { transform: translateY(-5px); opacity: 1; }
}
</style>
