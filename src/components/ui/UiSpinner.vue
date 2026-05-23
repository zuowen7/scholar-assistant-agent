<template>
  <span class="ui-spinner" :class="size" role="status" :aria-label="label || '加载中'">
    <span class="sp-ring">
      <span class="sp-arc sp-arc-1" />
      <span class="sp-arc sp-arc-2" />
      <span class="sp-core" />
    </span>
    <span v-if="label" class="sp-label">{{ label }}<i class="sp-dots"><b>.</b><b>.</b><b>.</b></i></span>
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'sm' | 'md' | 'lg'
  label?: string
}>(), {
  size: 'md',
})
</script>

<style scoped>
.ui-spinner {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--c-text-2);
}

.sp-ring {
  position: relative;
  display: inline-block;
  flex-shrink: 0;
}
.sm .sp-ring { width: 16px; height: 16px; }
.md .sp-ring { width: 24px; height: 24px; }
.lg .sp-ring { width: 40px; height: 40px; }

/* 双弧反向旋转 — 活泼但克制 */
.sp-arc {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid transparent;
}
.lg .sp-arc { border-width: 3px; }

.sp-arc-1 {
  border-top-color: var(--c-accent);
  border-right-color: var(--c-accent);
  animation: sp-spin 0.9s var(--ease-smooth, cubic-bezier(0.4,0,0.2,1)) infinite;
}
.sp-arc-2 {
  inset: 22%;
  border-bottom-color: var(--c-accent-hover);
  border-left-color: var(--c-accent-hover);
  opacity: 0.7;
  animation: sp-spin-rev 0.7s linear infinite;
}

/* 中心微光呼吸 */
.sp-core {
  position: absolute;
  inset: 38%;
  border-radius: 50%;
  background: var(--c-accent);
  box-shadow: 0 0 8px 1px var(--c-accent-ring);
  animation: sp-pulse 1.2s ease-in-out infinite;
}

.sp-label {
  font-size: var(--text-sm);
  white-space: nowrap;
}
.sp-dots { font-style: normal; }
.sp-dots b {
  font-weight: 700;
  opacity: 0.25;
  animation: sp-dot 1.2s ease-in-out infinite;
}
.sp-dots b:nth-child(2) { animation-delay: 0.18s; }
.sp-dots b:nth-child(3) { animation-delay: 0.36s; }

@keyframes sp-spin { to { transform: rotate(360deg); } }
@keyframes sp-spin-rev { to { transform: rotate(-360deg); } }
@keyframes sp-pulse {
  0%, 100% { transform: scale(0.7); opacity: 0.6; }
  50%      { transform: scale(1); opacity: 1; }
}
@keyframes sp-dot {
  0%, 70%, 100% { opacity: 0.25; }
  35%           { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .sp-arc, .sp-arc-2, .sp-core, .sp-dots b { animation: none; }
  .sp-arc-1 { border-color: var(--c-accent) transparent transparent transparent; }
}
</style>
