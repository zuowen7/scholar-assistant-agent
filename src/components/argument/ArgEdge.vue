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
  supports: '支持',
  warrants: '保证',
  backs: '支撑',
  qualifies: '限定',
  rebuts: '反驳',
  counters: '回应',
}
const relLabel = computed(() => REL_LABELS[props.data?.relation_type ?? 'supports'] ?? props.data?.relation_type)

const REL_COLORS: Record<RelationType, string> = {
  supports: '#10b981',
  warrants: '#3b82f6',
  backs: '#93c5fd',
  qualifies: '#f59e0b',
  rebuts: 'var(--c-danger)',
  counters: '#f97316',
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
  border-radius: 999px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  color: var(--c-text-1);
  white-space: nowrap;
  pointer-events: none;
}
.arg-edge-label.rel-supports { border-color: #10b981; color: #10b981; }
.arg-edge-label.rel-warrants { border-color: #3b82f6; color: #3b82f6; }
.arg-edge-label.rel-backs    { border-color: #93c5fd; color: #93c5fd; }
.arg-edge-label.rel-qualifies { border-color: #f59e0b; color: #f59e0b; }
.arg-edge-label.rel-rebuts   { border-color: var(--c-danger); color: var(--c-danger); }
.arg-edge-label.rel-counters { border-color: #f97316; color: #f97316; }

.arg-edge-menu {
  position: fixed;
  z-index: 9999;
  min-width: 120px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
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
