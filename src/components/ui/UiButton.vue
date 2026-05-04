<template>
  <button
    :class="['ui-btn', variant ?? 'secondary', size ?? 'md', { 'icon-only': iconOnly, loading }]"
    :disabled="disabled || loading"
    :type="type ?? 'button'"
    @click="$emit('click', $event)"
  >
    <!-- Loading: three-dot breathing -->
    <span v-if="loading" class="btn-loader-dots" aria-hidden="true">
      <span class="btn-dot" /><span class="btn-dot" /><span class="btn-dot" />
    </span>
    <template v-else>
      <span v-if="$slots['icon-left']" class="btn-icon"><slot name="icon-left" /></span>
      <slot />
      <slot name="icon-right" />
    </template>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'soft' | 'subtle' | 'danger' | 'bezel'
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
  border-radius: var(--radius-control);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  transition: background var(--motion-fast) var(--ease-brush),
              color var(--motion-fast) var(--ease-brush),
              border-color var(--motion-fast) var(--ease-brush),
              box-shadow var(--motion-fast) var(--ease-brush),
              transform var(--motion-fast) var(--ease-brush);
  white-space: nowrap;
  user-select: none;
  overflow: visible;
}

/* ── Ink bleed hover: 墨韵扩散 ── */
.ui-btn::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: inherit;
  background: radial-gradient(circle at center, var(--c-accent) 0%, transparent 70%);
  opacity: 0;
  transform: scale(0.75);
  transition: opacity 380ms var(--ease-brush), transform 420ms var(--ease-brush);
  pointer-events: none;
  z-index: -1;
  filter: blur(6px);
}
.ui-btn:not(:disabled):hover::after {
  opacity: 0.14;
  transform: scale(1.15);
}
.ui-btn:not(:disabled):active::after {
  opacity: 0.22;
  transform: scale(1.05);
  transition: opacity 120ms var(--ease-brush), transform 140ms var(--ease-brush);
}

.ui-btn:disabled { opacity: 0.42; cursor: not-allowed; }
.ui-btn:not(:disabled):hover { transform: translateY(-1px); }
.ui-btn:not(:disabled):active { transform: scale(0.97); }
.ui-btn:focus-visible { outline: none; box-shadow: var(--ring-focus); }

/* Sizes */
.lg { height: var(--control-lg); padding: 0 18px; font-size: var(--text-base); }
.md { height: var(--control-md); padding: 0 14px; font-size: var(--text-sm); }
.sm { height: var(--control-sm); padding: 0 10px; font-size: var(--text-xs); }

.ui-btn.icon-only.lg { width: var(--control-lg); padding: 0; }
.ui-btn.icon-only.md { width: var(--control-md); padding: 0; }
.ui-btn.icon-only.sm { width: var(--control-sm); padding: 0; }

/* Icon entrance */
.btn-icon {
  display: inline-flex;
  animation: btn-icon-in 0.3s var(--ease-out);
}
@keyframes btn-icon-in {
  from { transform: rotate(-30deg); opacity: 0; }
  to   { transform: rotate(0deg); opacity: 1; }
}

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

.bezel {
  background: var(--c-surface-2);
  border-color: var(--c-surface-3);
  color: var(--c-text-0);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 1px 0 rgba(0,0,0,0.2);
}
.bezel:not(:disabled):hover { background: var(--c-surface-3); border-color: var(--c-surface-4); }

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

/* Loading: three-dot breathing */
.ui-btn.loading { cursor: wait; }
.btn-loader-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.btn-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: currentColor;
  animation: btn-dot-breathe 1.2s ease-in-out infinite;
}
.btn-dot:nth-child(2) { animation-delay: 0.15s; }
.btn-dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes btn-dot-breathe {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1.1); }
}
</style>
