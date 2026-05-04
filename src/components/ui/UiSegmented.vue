<template>
  <div
    ref="containerRef"
    class="ui-segmented"
    :class="[size, { full, 'use-vermilion': vermilionIndicator }]"
    role="tablist"
  >
    <span
      v-if="indicatorReady"
      class="seg-indicator"
      :style="indicatorStyle"
    />
    <button
      v-for="opt in options"
      :key="String(opt.value)"
      type="button"
      role="tab"
      class="seg-item"
      :class="{ active: opt.value === modelValue, disabled: opt.disabled }"
      :disabled="opt.disabled"
      :aria-selected="opt.value === modelValue"
      :ref="el => { if (opt.value === modelValue) activeRef = el as HTMLElement }"
      @click="!opt.disabled && $emit('update:modelValue', opt.value)"
    >
      <component :is="opt.icon" v-if="opt.icon" :size="iconSize" :stroke-width="1.6" class="seg-icon" />
      <span v-if="opt.label" class="seg-label">{{ opt.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends string | number">
import { ref, computed, watch, onMounted, nextTick } from 'vue'

interface SegmentedOption<V> {
  value: V
  label?: string
  icon?: any
  disabled?: boolean
}

const props = defineProps<{
  modelValue: T
  options: SegmentedOption<T>[]
  size?: 'sm' | 'md'
  full?: boolean
  vermilionIndicator?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: T): void
}>()

const iconSize = computed(() => (props.size === 'sm' ? 13 : 14))

const containerRef = ref<HTMLElement | null>(null)
const activeRef = ref<HTMLElement | null>(null)
const indicatorReady = ref(false)

const indicatorStyle = computed(() => {
  if (!containerRef.value || !activeRef.value) return {}
  const containerRect = containerRef.value.getBoundingClientRect()
  const activeRect = activeRef.value.getBoundingClientRect()
  return {
    left: `${activeRect.left - containerRect.left}px`,
    width: `${activeRect.width}px`,
  }
})

function recalc() {
  nextTick(() => {
    if (containerRef.value && activeRef.value) indicatorReady.value = true
  })
}

onMounted(recalc)
watch(() => props.modelValue, recalc)
</script>

<style scoped>
.ui-segmented {
  position: relative;
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
}
.ui-segmented.full { display: flex; width: 100%; }

/* Sliding indicator */
.seg-indicator {
  position: absolute;
  top: 3px;
  height: calc(100% - 6px);
  background: var(--c-surface-1);
  border-radius: var(--radius-sm);
  box-shadow: var(--elevation-1);
  transition: left var(--motion-base) var(--ease-emphasis),
              width var(--motion-base) var(--ease-emphasis);
  pointer-events: none;
  z-index: 0;
}
.ui-segmented.use-vermilion .seg-indicator {
  background: var(--vermilion-0);
  box-shadow: 0 0 8px rgba(200, 80, 58, 0.3);
}

.seg-item {
  position: relative;
  z-index: 1;
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: transparent;
  color: var(--c-text-3);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color var(--motion-fast) var(--ease-out);
}
.ui-segmented.md .seg-item { height: 28px; padding: 0 12px; font-size: var(--text-sm); }
.ui-segmented.sm .seg-item { height: 22px; padding: 0 10px; font-size: var(--text-xs); }

.seg-item:hover:not(.active):not(.disabled) {
  color: var(--c-text-2);
}
.seg-item.active {
  color: var(--c-text-0);
}
.ui-segmented.use-vermilion .seg-item.active {
  color: #fff;
}
.seg-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.seg-icon { flex-shrink: 0; }
.seg-label { white-space: nowrap; }
</style>
