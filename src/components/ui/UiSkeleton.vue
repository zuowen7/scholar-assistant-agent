<template>
  <span
    class="ui-skeleton"
    :class="[shape, { 'ui-skeleton--text': shape === 'text' }]"
    :style="skeletonStyle"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  shape?: 'line' | 'card' | 'circle' | 'text'
  width?: string | number
  height?: string | number
  lines?: number
}>(), {
  shape: 'line',
  lines: 1,
})

const skeletonStyle = computed(() => {
  const w = typeof props.width === 'number' ? `${props.width}px` : props.width
  const h = typeof props.height === 'number' ? `${props.height}px` : props.height
  const base: Record<string, string> = {}
  if (w) base.width = w
  if (h) base.height = h
  return base
})
</script>

<style scoped>
.ui-skeleton {
  display: block;
  background: var(--c-surface-3);
  border-radius: var(--radius-xs);
  position: relative;
  overflow: hidden;
}

.ui-skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.04) 40%,
    rgba(255, 255, 255, 0.08) 50%,
    rgba(255, 255, 255, 0.04) 60%,
    transparent 100%
  );
  animation: skeleton-shimmer 1.6s ease-in-out infinite;
}

/* Shapes */
.ui-skeleton.line {
  width: 100%;
  height: 12px;
  border-radius: 6px;
}

.ui-skeleton.text {
  display: inline-block;
  width: 100%;
  height: 12px;
  border-radius: 6px;
}
.ui-skeleton.text + .ui-skeleton.text {
  margin-top: 8px;
}

.ui-skeleton.card {
  width: 100%;
  height: 80px;
  border-radius: var(--radius-md);
}

.ui-skeleton.circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
}

/* Light mode shimmer */
:global([data-theme="light"]) .ui-skeleton {
  background: var(--c-surface-3);
}
:global([data-theme="light"]) .ui-skeleton::after {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(0, 0, 0, 0.03) 40%,
    rgba(0, 0, 0, 0.06) 50%,
    rgba(0, 0, 0, 0.03) 60%,
    transparent 100%
  );
}

@keyframes skeleton-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@media (prefers-reduced-motion: reduce) {
  .ui-skeleton::after { animation: none; }
}
</style>
