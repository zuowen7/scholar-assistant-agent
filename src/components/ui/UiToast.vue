<template>
  <TransitionGroup name="v-slide-up" tag="div" class="toast-container">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="toast"
      :class="t.level"
      @click="dismiss(t.id)"
    >
      <span class="toast-dot" />
      <span class="toast-msg">{{ t.message }}</span>
      <button class="toast-close" @click.stop="dismiss(t.id)">
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <line x1="3" y1="3" x2="9" y2="9" /><line x1="9" y1="3" x2="3" y2="9" />
        </svg>
      </button>
    </div>
  </TransitionGroup>
</template>

<script setup lang="ts">
import { useToast } from '../../composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column-reverse;
  gap: 8px;
  z-index: 9999;
  pointer-events: none;
  max-width: 360px;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: color-mix(in srgb, var(--c-surface-1) 92%, transparent);
  backdrop-filter: blur(20px) saturate(1.4);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-3);
  pointer-events: auto;
  cursor: pointer;
  min-width: 200px;
}

.toast-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.toast.success .toast-dot { background: var(--c-success); box-shadow: 0 0 6px var(--c-success); }
.toast.warn    .toast-dot { background: var(--c-warn);    box-shadow: 0 0 6px var(--c-warn); }
.toast.danger  .toast-dot { background: var(--c-danger);  box-shadow: 0 0 6px var(--c-danger); }
.toast.info    .toast-dot { background: var(--c-info);    box-shadow: 0 0 6px var(--c-info); }

.toast.success { border-left: 3px solid var(--c-success); }
.toast.warn    { border-left: 3px solid var(--c-warn); }
.toast.danger  { border-left: 3px solid var(--c-danger); }
.toast.info    { border-left: 3px solid var(--c-info); }

.toast-msg {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--c-text-1);
  line-height: var(--leading-snug);
}

.toast-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  border-radius: var(--radius-xs);
  transition: background var(--motion-fast);
  flex-shrink: 0;
}
.toast-close:hover { background: var(--c-surface-3); color: var(--c-text-0); }
</style>
