<template>
  <span class="ui-tooltip-wrap">
    <slot />
    <span class="ui-tooltip" role="tooltip">{{ text }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  text: string
}>()
</script>

<style scoped>
.ui-tooltip-wrap {
  position: relative;
  display: inline-flex;
}
.ui-tooltip {
  position: fixed;
  z-index: 99999;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--c-surface-0);
  color: var(--c-text-0);
  font-size: var(--text-xs);
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.12s;
  box-shadow: var(--shadow-sm);
}
.ui-tooltip-wrap:hover .ui-tooltip {
  opacity: 1;
}
</style>
