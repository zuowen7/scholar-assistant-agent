<template>
  <span class="status-badge" :class="`tone-${tone}`">
    <span v-if="dot" class="status-dot" aria-hidden="true" />
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger'
    dot?: boolean
  }>(),
  {
    tone: 'neutral',
    dot: false,
  },
)
</script>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 3px 9px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}
.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}
.tone-accent {
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
.tone-success {
  color: var(--c-success);
  background: var(--c-success-bg);
}
.tone-warning {
  color: var(--c-warn);
  background: var(--c-warn-bg);
}
.tone-danger {
  color: var(--c-danger);
  background: var(--c-danger-bg);
}
</style>
