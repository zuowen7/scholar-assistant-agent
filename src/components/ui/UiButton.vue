<template>
  <button
    :class="['ui-btn', variant, size]"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  disabled?: boolean
}>()

defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()
</script>

<style scoped>
.ui-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font: inherit;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.ui-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

/* Sizes */
.md {
  height: 30px;
  padding: 0 14px;
  font-size: var(--text-sm);
}
.sm {
  height: 26px;
  padding: 0 9px;
  font-size: var(--text-xs);
}

/* Variants */
.primary {
  background: var(--c-accent);
  border-color: var(--c-accent);
  color: #fff;
  font-weight: 600;
}
.primary:not(:disabled):hover {
  opacity: 0.88;
}

.secondary {
  background: var(--c-surface-2);
  border-color: var(--c-surface-3);
  color: var(--c-text-0);
}
.secondary:not(:disabled):hover {
  background: var(--c-surface-3);
}

.ghost {
  background: transparent;
  color: var(--c-text-0);
}
.ghost:not(:disabled):hover {
  background: var(--hover-bg);
  color: var(--c-accent-hover);
}

.danger {
  background: var(--c-danger-bg);
  border-color: var(--c-danger-border);
  color: var(--c-danger);
}
.danger:not(:disabled):hover {
  background: var(--c-danger);
  color: #fff;
}
</style>
