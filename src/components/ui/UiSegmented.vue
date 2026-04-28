<template>
  <div class="ui-segmented" :class="[size, { full }]" role="tablist">
    <button
      v-for="opt in options"
      :key="String(opt.value)"
      type="button"
      role="tab"
      class="seg-item"
      :class="{ active: opt.value === modelValue, disabled: opt.disabled }"
      :disabled="opt.disabled"
      :aria-selected="opt.value === modelValue"
      @click="!opt.disabled && $emit('update:modelValue', opt.value)"
    >
      <component :is="opt.icon" v-if="opt.icon" :size="iconSize" :stroke-width="1.6" class="seg-icon" />
      <span v-if="opt.label" class="seg-label">{{ opt.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends string | number">
import { computed } from 'vue'

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
}>()

defineEmits<{
  (e: 'update:modelValue', value: T): void
}>()

const iconSize = computed(() => (props.size === 'sm' ? 13 : 14))
</script>

<style scoped>
.ui-segmented {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
}
.ui-segmented.full { display: flex; width: 100%; }

.seg-item {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: transparent;
  color: var(--c-text-2);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color var(--motion-fast) var(--ease-out),
              background var(--motion-fast) var(--ease-out);
}
.ui-segmented.md .seg-item { height: 26px; padding: 0 12px; font-size: var(--text-sm); }
.ui-segmented.sm .seg-item { height: 22px; padding: 0 10px; font-size: var(--text-xs); }

.seg-item:hover:not(.active):not(.disabled) {
  color: var(--c-text-0);
}
.seg-item.active {
  background: var(--c-surface-1);
  color: var(--c-text-0);
  box-shadow: var(--elevation-1);
}
.seg-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.seg-icon { flex-shrink: 0; }
.seg-label { white-space: nowrap; }
</style>
