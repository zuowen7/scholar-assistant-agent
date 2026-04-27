<template>
  <span class="ui-icon-btn-wrap">
    <button
      class="ui-icon-btn"
      :disabled="disabled"
      @click="$emit('click', $event)"
    >
      <slot />
    </button>
    <span v-if="tooltip" class="ui-icon-tooltip">{{ tooltip }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  tooltip?: string
  disabled?: boolean
}>()

defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()
</script>

<style scoped>
.ui-icon-btn-wrap {
  position: relative;
  display: inline-flex;
}
.ui-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  transition: all 0.15s;
}
.ui-icon-btn:not(:disabled):hover {
  background: var(--c-surface-2);
  color: var(--c-text-0);
}
.ui-icon-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}
.ui-icon-tooltip {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--c-surface-0);
  color: var(--c-text-0);
  font-size: var(--text-xs);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  box-shadow: var(--shadow-sm);
  z-index: 9999;
}
.ui-icon-btn-wrap:hover .ui-icon-tooltip {
  opacity: 1;
}
</style>
