<template>
  <div ref="rootRef" class="ui-popover-root">
    <span ref="triggerRef" class="ui-popover-trigger" @click.stop="toggle">
      <slot name="trigger" :open="open" />
    </span>
    <Teleport to="body">
      <Transition name="v-scale-in">
        <div
          v-if="open"
          ref="panelRef"
          class="ui-popover-panel"
          :class="[align, { glass }]"
          :style="{ ...panelStyle, transformOrigin }"
          @click.stop
        >
          <slot :close="close" />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'

const props = withDefaults(defineProps<{
  /** Width of the panel in pixels */
  width?: number
  /** Horizontal alignment relative to trigger */
  align?: 'start' | 'end' | 'center'
  /** Vertical placement: below or above the trigger */
  placement?: 'bottom' | 'top'
  /** Use frosted-glass background */
  glass?: boolean
  /** Pixel offset from trigger */
  offset?: number
}>(), {
  width: 280,
  align: 'end',
  placement: 'bottom',
  glass: false,
  offset: 6,
})

const emit = defineEmits<{
  (e: 'open'): void
  (e: 'close'): void
}>()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const panelPos = ref({ top: 0, left: 0 })

function toggle() {
  open.value ? close() : show()
}
function show() {
  open.value = true
  emit('open')
  nextTick(reposition)
}
function close() {
  if (!open.value) return
  open.value = false
  emit('close')
}

function reposition() {
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const panelWidth = props.width
  let left = rect.left
  if (props.align === 'end') left = rect.right - panelWidth
  else if (props.align === 'center') left = rect.left + rect.width / 2 - panelWidth / 2
  // Clamp horizontally to viewport
  left = Math.max(8, Math.min(left, window.innerWidth - panelWidth - 8))

  let top = rect.bottom + props.offset
  if (props.placement === 'top') {
    const panelHeight = panelRef.value?.offsetHeight ?? 0
    top = rect.top - props.offset - panelHeight
  }
  panelPos.value = { top, left }
}

const panelStyle = computed(() => ({
  top: panelPos.value.top + 'px',
  left: panelPos.value.left + 'px',
  width: props.width + 'px',
}))

const transformOrigin = computed(() => {
  switch (props.align) {
    case 'start': return 'top left'
    case 'end': return 'top right'
    default: return 'top center'
  }
})

function onDocClick(e: MouseEvent) {
  if (!open.value) return
  const t = e.target as Node
  if (rootRef.value?.contains(t)) return
  if (panelRef.value?.contains(t)) return
  close()
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) close()
}
function onResize() {
  if (open.value) reposition()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onKey)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onResize, true)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onResize, true)
})

defineExpose({ open, show, close, toggle })
</script>

<style scoped>
.ui-popover-root { display: inline-flex; }
.ui-popover-trigger { display: inline-flex; }
</style>

<style>
/* Global so the teleported panel inherits proper styles */
.ui-popover-panel {
  position: fixed;
  z-index: 1000;
  background: color-mix(in srgb, var(--c-surface-1) 88%, transparent);
  border: 1px solid var(--c-glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--elevation-3);
  padding: var(--space-3);
  -webkit-app-region: no-drag;
  backdrop-filter: blur(24px) saturate(1.5);
  -webkit-backdrop-filter: blur(24px) saturate(1.5);
  max-height: calc(100vh - 24px);
  overflow-y: auto;
  overflow-x: hidden;
}
.ui-popover-panel.glass {
  background: var(--c-glass);
  border-color: var(--c-glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
</style>
