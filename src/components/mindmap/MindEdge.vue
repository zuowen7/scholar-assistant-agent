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
      <button @click="doDelete">删除连线</button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, inject, ref, type Ref } from 'vue'
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
    ? { stroke: 'var(--c-accent)', strokeDasharray: '6 4', strokeWidth: 1.5, opacity: 0.7 }
    : { stroke: 'var(--c-surface-4)', strokeWidth: 2 }

  if (selected.value) {
    return { ...base, stroke: 'var(--c-danger)', strokeWidth: 3, opacity: 1 }
  }
  if (hovered.value) {
    return { ...base, stroke: 'var(--c-warn)', strokeWidth: 3, opacity: 1 }
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
</style>
