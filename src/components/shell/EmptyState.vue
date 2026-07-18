<template>
  <div class="empty-state">
    <div v-if="$slots.icon" class="empty-icon"><slot name="icon" /></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<style scoped>
.empty-state { display: grid; place-items: center; align-content: center; gap: 8px; min-height: 220px; padding: 32px; text-align: center; color: var(--c-text-2); }
.empty-icon { color: var(--c-accent); }
.empty-state h3 { margin: 0; color: var(--c-text-0); font: 600 16px/1.3 var(--font-sans), var(--font-zh); }
.empty-state p { max-width: 360px; margin: 0; font-size: 13px; line-height: 1.6; }
</style>
