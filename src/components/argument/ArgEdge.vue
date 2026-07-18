<template>
  <g class="arg-edge" @contextmenu.prevent="onContextMenu">
    <BaseEdge :id="id" :path="path[0]" :style="edgeStyle" />
    <!-- hit-area for easier selection -->
    <path :d="path[0]" fill="none" stroke="transparent" stroke-width="14" class="arg-edge-hit" />
    <!-- relation label chip at midpoint -->
    <EdgeLabelRenderer>
      <div
        class="arg-edge-label"
        :class="`rel-${data?.relation_type}`"
        :style="{
          transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          pointerEvents: 'all',
        }"
      >
        {{ relLabel }}
      </div>
    </EdgeLabelRenderer>
  </g>

  <Teleport to="body">
    <div
      v-if="menuOpen"
      class="arg-edge-menu"
      :style="{ left: `${menuPos.x}px`, top: `${menuPos.y}px` }"
    >
      <button @click="doDelete">{{ t('argument.deleteRelation') }}</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@vue-flow/core'
import type { EdgeProps } from '@vue-flow/core'
import type { RelationType } from '../../composables/useArgumentMap'
import { useArgumentMap } from '../../composables/useArgumentMap'

const props = defineProps<EdgeProps<{
  relation_type: RelationType
  label: string | null
  created_by: 'user' | 'ai'
}>>()

const { deleteEdge } = useArgumentMap()

const REL_LABELS: Record<RelationType, string> = {
  supports: t('argument.supports'),
  warrants: t('argument.warrants'),
  backs: t('argument.backs'),
  qualifies: t('argument.qualifies'),
  rebuts: t('argument.rebuts'),
  counters: t('argument.counters'),
}
const relLabel = computed(() => REL_LABELS[props.data?.relation_type ?? 'supports'] ?? props.data?.relation_type)

const REL_COLORS: Record<RelationType, string> = {
  supports: '#6f9276',
  warrants: '#7182a6',
  backs: '#94a3a5',
  qualifies: '#aa8757',
  rebuts: '#a76f62',
  counters: '#a77b5c',
}
const edgeColor = computed(() => REL_COLORS[props.data?.relation_type ?? 'supports'] ?? 'var(--c-surface-4)')

const path = computed(() => getBezierPath({
  sourceX: props.sourceX, sourceY: props.sourceY,
  targetX: props.targetX, targetY: props.targetY,
  sourcePosition: props.sourcePosition, targetPosition: props.targetPosition,
}))

const [, labelX, labelY] = path.value

const edgeStyle = computed(() => ({
  stroke: edgeColor.value,
  strokeWidth: props.selected ? 2.5 : 1.8,
  opacity: props.selected ? 1 : 0.75,
}))

const menuOpen = ref(false)
const menuPos = ref({ x: 0, y: 0 })

function onContextMenu(e: MouseEvent) {
  menuPos.value = { x: e.clientX, y: e.clientY }
  menuOpen.value = true
  const close = () => { menuOpen.value = false; document.removeEventListener('click', close) }
  setTimeout(() => document.addEventListener('click', close), 0)
}

async function doDelete() {
  menuOpen.value = false
  await deleteEdge(props.id)
}
</script>

<style>
.arg-edge-hit { cursor: pointer; }

.arg-edge-label {
  position: absolute;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 5px;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  color: var(--c-text-1);
  white-space: nowrap;
  pointer-events: none;
}
.arg-edge-label.rel-supports { color: #5f7f66; }
.arg-edge-label.rel-warrants { color: #647595; }
.arg-edge-label.rel-backs    { color: #758486; }
.arg-edge-label.rel-qualifies { color: #8d704a; }
.arg-edge-label.rel-rebuts   { color: #8d5d53; }
.arg-edge-label.rel-counters { color: #8d684f; }

.arg-edge-menu {
  position: fixed;
  z-index: 9999;
  min-width: 120px;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  box-shadow: var(--elevation-3);
  padding: 4px;
}
.arg-edge-menu button {
  display: block;
  width: 100%;
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-danger);
  font: inherit;
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
}
.arg-edge-menu button:hover { background: var(--c-danger-bg); }
</style>
