<template>
  <g class="mind-edge" @contextmenu.prevent="onContextMenu">
    <BaseEdge
      :id="id"
      :path="path[0]"
      :style="edgeStyle"
    />
    <path
      :d="path[0]"
      fill="none"
      stroke="transparent"
      stroke-width="14"
      class="edge-hit-area"
    />
  </g>
  <Teleport to="body">
    <div
      v-if="menuOpen"
      class="edge-context-menu"
      :style="{ left: `${menuPos.x}px`, top: `${menuPos.y}px` }"
    >
      <button @click="doDelete">{{ t('mindmap.deleteEdge') }}</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, inject, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { BaseEdge, getBezierPath } from '@vue-flow/core'
import type { EdgeProps } from '@vue-flow/core'
import { useMindMap } from '../../composables/useMindMap'

const props = defineProps<EdgeProps<{ kind: 'parent' | 'association'; childId?: string }>>()

const hoveredEdgeId = inject<Ref<string>>('hoveredEdgeId', ref(''))

const path = computed(() => getBezierPath({
  sourceX: props.sourceX, sourceY: props.sourceY,
  targetX: props.targetX, targetY: props.targetY,
  sourcePosition: props.sourcePosition, targetPosition: props.targetPosition,
}))

const isAssociation = computed(() => props.data?.kind === 'association')
const hovered = computed(() => hoveredEdgeId.value === props.id)
const selected = computed(() => props.selected)

const edgeStyle = computed(() => {
  const base = isAssociation.value
    ? { stroke: 'var(--c-accent)', strokeDasharray: '6 5', strokeWidth: 1.6, opacity: 0.5 }
    : { stroke: 'color-mix(in srgb, var(--c-surface-4) 60%, transparent)', strokeWidth: 1.6, opacity: 0.85 }

  if (selected.value) {
    return { ...base, stroke: 'var(--c-accent)', strokeWidth: 2.6, opacity: 1, strokeDasharray: isAssociation.value ? '8 4' : 'none' }
  }
  if (hovered.value) {
    return { ...base, stroke: 'var(--c-accent-hover)', strokeWidth: 2.6, opacity: 0.9, strokeDasharray: isAssociation.value ? '8 4' : 'none' }
  }
  return base
})

const menuOpen = ref(false)
const menuPos = ref({ x: 0, y: 0 })

function onContextMenu(e: MouseEvent) {
  menuPos.value = { x: e.clientX, y: e.clientY }
  menuOpen.value = true
  const close = () => {
    menuOpen.value = false
    document.removeEventListener('click', close)
    document.removeEventListener('contextmenu', close)
  }
  setTimeout(() => {
    document.addEventListener('click', close)
    document.addEventListener('contextmenu', close)
  }, 0)
}

function doDelete() {
  menuOpen.value = false
  const { removeAssociationLink, detachChild } = useMindMap()
  if (isAssociation.value) {
    removeAssociationLink(props.id)
  } else if (props.data?.childId) {
    detachChild(props.data.childId)
  }
}
</script>

<style>
/* 连线落笔：首次渲染时如笔锋自源头划向目标 */
.mind-edge .vue-flow__edge-path {
  stroke-dasharray: 600;
  stroke-dashoffset: 600;
  animation: edge-draw 620ms var(--ease-brush) forwards;
  transition: stroke 180ms var(--ease-out), stroke-width 180ms var(--ease-out), opacity 180ms var(--ease-out);
}
@keyframes edge-draw {
  to { stroke-dashoffset: 0; }
}
.edge-hit-area {
  cursor: pointer;
}
.edge-context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 120px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: 4px;
}
.edge-context-menu button {
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
.edge-context-menu button:hover {
  background: var(--c-danger-bg);
}
.edge-context-menu {
  animation: anim-pop-in 200ms var(--ease-spring) both;
}

@media (prefers-reduced-motion: reduce) {
  .mind-edge .vue-flow__edge-path {
    animation: none;
    stroke-dasharray: none;
    stroke-dashoffset: 0;
  }
  .edge-context-menu { animation: none; }
}
</style>
