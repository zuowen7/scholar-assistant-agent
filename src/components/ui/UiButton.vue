<template>
  <button
    :class="['ui-btn', variant ?? 'secondary', size ?? 'md', { 'icon-only': iconOnly, loading }]"
    :disabled="disabled || loading"
    :type="type ?? 'button'"
    @click="$emit('click', $event)"
  >
    <Loader2 v-if="loading" :size="iconSize" :stroke-width="2" class="btn-loader" />
    <slot v-else name="icon-left" />
    <slot />
    <slot name="icon-right" />
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loader2 } from './icons'

const props = defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'soft' | 'subtle' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
  iconOnly?: boolean
  type?: 'button' | 'submit' | 'reset'
}>()

defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()

const iconSize = computed(() => (props.size === 'sm' ? 12 : props.size === 'lg' ? 16 : 14))
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
  font-weight: 500;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out),
              border-color var(--motion-fast) var(--ease-out),
              box-shadow var(--motion-fast) var(--ease-out),
              transform var(--motion-fast) var(--ease-out);
  white-space: nowrap;
  user-select: none;
}
.ui-btn:disabled { opacity: 0.42; cursor: not-allowed; }
.ui-btn:not(:disabled):active { transform: translateY(1px); }
.ui-btn:focus-visible { outline: none; box-shadow: var(--ring-focus); }

/* Sizes */
.lg { height: 36px; padding: 0 18px; font-size: var(--text-base); }
.md { height: 30px; padding: 0 14px; font-size: var(--text-sm); }
.sm { height: 24px; padding: 0 10px; font-size: var(--text-xs); }

.ui-btn.icon-only.lg { width: 36px; padding: 0; }
.ui-btn.icon-only.md { width: 30px; padding: 0; }
.ui-btn.icon-only.sm { width: 24px; padding: 0; }

/* Variants */
.primary {
  background: var(--c-accent);
  border-color: var(--c-accent);
  color: #fff;
  font-weight: 600;
}
.primary:not(:disabled):hover { background: var(--c-accent-hover); border-color: var(--c-accent-hover); }
.primary:not(:disabled):active { background: var(--c-accent-strong); }

.secondary {
  background: var(--c-surface-2);
  border-color: var(--c-surface-3);
  color: var(--c-text-0);
}
.secondary:not(:disabled):hover { background: var(--c-surface-3); border-color: var(--c-surface-4); }

.soft {
  background: var(--c-accent-bg);
  color: var(--c-accent-hover);
  border-color: transparent;
}
.soft:not(:disabled):hover { background: var(--c-accent-soft); }

.subtle {
  background: transparent;
  color: var(--c-text-2);
  border-color: transparent;
}
.subtle:not(:disabled):hover { background: var(--c-surface-2); color: var(--c-text-0); }

.ghost {
  background: transparent;
  color: var(--c-text-0);
}
.ghost:not(:disabled):hover { background: var(--hover-bg); color: var(--c-accent-hover); }

.danger {
  background: var(--c-danger-bg);
  border-color: var(--c-danger-border);
  color: var(--c-danger);
}
.danger:not(:disabled):hover { background: var(--c-danger); color: #fff; border-color: var(--c-danger); }

/* Loading */
.ui-btn.loading { cursor: wait; }
.btn-loader { animation: btn-spin 700ms linear infinite; flex-shrink: 0; }
@keyframes btn-spin { to { transform: rotate(360deg); } }
</style>
