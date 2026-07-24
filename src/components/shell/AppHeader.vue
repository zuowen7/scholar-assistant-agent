<template>
  <header class="app-header" :class="{ 'no-center': !$slots.center }" data-tauri-drag-region>
    <div class="header-leading">
      <component :is="icon" v-if="icon" :size="21" aria-hidden="true" />
      <div class="header-copy">
        <div class="header-title-row">
          <h1>{{ title }}</h1>
          <slot name="title-after" />
        </div>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
    </div>
    <div v-if="$slots.center" class="header-center"><slot name="center" /></div>
    <div class="header-actions"><slot /></div>
  </header>
</template>

<script setup lang="ts">
import type { Component } from 'vue'
defineProps<{ title: string; subtitle?: string; icon?: Component }>()
</script>

<style scoped>
.app-header { min-height: 76px; flex: 0 0 76px; display: grid; grid-template-columns: minmax(260px, 1fr) minmax(180px, .7fr) minmax(260px, 1fr); align-items: center; gap: 18px; padding: 0 108px 0 22px; border-bottom: 1px solid var(--c-border); background: var(--c-panel); }
.app-header.no-center { grid-template-columns: minmax(260px, 1fr) auto; }
.header-leading { min-width: 0; display: flex; align-items: center; gap: 13px; color: var(--c-text-1); }
.header-copy { min-width: 0; }
.header-title-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.header-title-row h1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 0; color: var(--c-text-0); font: 650 20px/1.25 var(--font-sans), var(--font-zh); letter-spacing: -.01em; }
.header-copy p { margin: 4px 0 0; color: var(--c-text-3); font-size: 12px; }
.header-center { min-width: 0; }
.header-actions { min-width: 0; display: flex; justify-content: flex-end; align-items: center; gap: 8px; white-space: nowrap; }
.header-actions > :deep(*) { flex-shrink: 0; }
@media (max-width: 1100px) {
  .app-header { grid-template-columns: minmax(210px, 1fr) minmax(0, auto); padding: 0 104px 0 16px; }
  .header-center { display: none; }
}
@media (max-width: 760px) {
  .app-header { min-height: 96px; flex-basis: 96px; grid-template-columns: minmax(0, 1fr); align-content: center; gap: 8px; padding: 13px 104px 9px 14px; }
  .header-leading { gap: 9px; }
  .header-title-row h1 { font-size: 17px; }
  .header-copy p { display: none; }
  .header-actions { justify-content: flex-start; overflow-x: auto; overscroll-behavior-inline: contain; padding: 2px 3px 5px; scrollbar-width: none; }
  .header-actions::-webkit-scrollbar { display: none; }
}
</style>
