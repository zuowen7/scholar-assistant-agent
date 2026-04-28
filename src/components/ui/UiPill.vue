<template>
  <component
    :is="clickable ? 'button' : 'span'"
    :type="clickable ? 'button' : undefined"
    :disabled="clickable && disabled"
    class="ui-pill"
    :class="[tone, { clickable, disabled }]"
    @click="clickable && !disabled && $emit('click', $event)"
  >
    <span class="pill-dot" />
    <slot />
  </component>
</template>

<script setup lang="ts">
defineProps<{
  /** Visual tone — neutral by default. `ok` = success/online, `off` = offline, `warn` = warning, `danger` = error, `info` = informational */
  tone?: 'neutral' | 'ok' | 'off' | 'warn' | 'danger' | 'info'
  clickable?: boolean
  disabled?: boolean
}>()

defineEmits<{
  (e: 'click', event: MouseEvent): void
}>()
</script>

<style scoped>
.ui-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font: inherit;
  font-size: var(--text-xs);
  font-weight: 500;
  white-space: nowrap;
  -webkit-app-region: no-drag;
}
.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
  opacity: 0.55;
}

/* Tones */
.ui-pill.ok { color: var(--c-success); background: rgba(74, 222, 128, 0.10); }
.ui-pill.ok .pill-dot { opacity: 1; box-shadow: 0 0 6px var(--c-success); }
.ui-pill.off { color: var(--c-text-3); background: var(--c-surface-2); }
.ui-pill.off .pill-dot { background: var(--c-danger); opacity: 0.6; }
.ui-pill.warn { color: var(--c-warn); background: rgba(245, 158, 11, 0.10); }
.ui-pill.danger { color: var(--c-danger); background: var(--c-danger-bg); border-color: var(--c-danger-border); }
.ui-pill.info { color: var(--c-accent-hover); background: var(--c-accent-bg); }

/* Clickable */
.ui-pill.clickable {
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}
.ui-pill.clickable:hover:not(.disabled) {
  background: var(--c-surface-3);
  color: var(--c-text-0);
}
.ui-pill.clickable.ok:hover { background: rgba(74, 222, 128, 0.18); }
.ui-pill.clickable.disabled { opacity: 0.55; cursor: wait; }
</style>
