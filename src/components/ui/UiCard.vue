<template>
  <div class="ui-card" :class="[surface, { glass, interactive, padded }]">
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** Background surface — defaults to surface-1 */
  surface?: 'flat' | 'raised' | 'sunken'
  /** Frosted-glass background */
  glass?: boolean
  /** Hover/active feedback */
  interactive?: boolean
  /** Add default padding */
  padded?: boolean
}>()
</script>

<style scoped>
.ui-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-lg);
  background: var(--c-surface-1);
  transition: border-color var(--motion-fast) var(--ease-out),
              box-shadow var(--motion-base) var(--ease-out),
              transform var(--motion-base) var(--ease-out);
}
.ui-card.padded { padding: var(--space-4); }
.ui-card.flat { background: var(--c-surface-1); }
.ui-card.raised { background: var(--c-surface-1); box-shadow: var(--elevation-2); }
.ui-card.sunken { background: var(--c-surface-2); border-color: transparent; }
.ui-card.glass {
  background: var(--c-glass);
  border-color: var(--c-glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.ui-card.interactive { cursor: pointer; }
.ui-card.interactive:hover {
  border-color: var(--c-accent-soft);
  box-shadow: var(--elevation-2);
}
</style>
