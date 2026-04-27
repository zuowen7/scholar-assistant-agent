<template>
  <div class="ui-panel" :class="{ collapsed }">
    <div class="ui-panel-header">
      <span class="ui-panel-title">{{ title }}</span>
      <button
        v-if="collapsible"
        class="ui-panel-toggle"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? '▸' : '▾' }}
      </button>
    </div>
    <div v-show="!collapsed" class="ui-panel-body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  title: string
  collapsible?: boolean
}>()

const collapsed = ref(false)
</script>

<style scoped>
.ui-panel {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--toolbar-bg);
  overflow: hidden;
}
.ui-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--border-color);
  background: var(--c-surface-2);
}
.ui-panel-title {
  font-size: var(--text-xs);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}
.ui-panel-toggle {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  padding: 2px 4px;
  border-radius: 3px;
}
.ui-panel-toggle:hover {
  color: var(--c-accent);
}
.ui-panel-body {
  padding: var(--space-3);
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.collapsed .ui-panel-header {
  border-bottom: none;
}
</style>
