<template>
  <div class="model-status" :title="model">
    <span class="model-dot" :class="{ online }" />
    <span class="model-provider">{{ provider }}</span>
    <span class="model-name">{{ model }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ provider: string; model: string; online?: boolean }>(), { online: false })
</script>

<style scoped>
.model-status { display: flex; align-items: center; gap: 7px; min-height: 38px; padding: 0 10px; border: 1px solid var(--c-border); border-radius: var(--radius-sm); background: color-mix(in srgb, var(--c-panel) 74%, transparent); color: var(--c-text-2); font-size: 11px; }
.model-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-text-3); flex: 0 0 auto; }
.model-dot.online { background: var(--c-success); }
.model-provider { color: var(--c-text-0); font-weight: 600; }
.model-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
