<template>
  <UiPopover :width="width" :align="align" :offset="4">
    <template #trigger>
      <slot name="trigger" />
    </template>
    <template #default="{ close }">
      <div class="ui-dropdown" role="menu">
        <template v-for="(item, i) in items" :key="i">
          <div v-if="item.divider" class="dd-divider" />
          <div v-else-if="item.label" class="dd-section-label">{{ item.label }}</div>
          <button
            v-else
            type="button"
            class="dd-item"
            :class="{ disabled: item.disabled, danger: item.danger }"
            :disabled="item.disabled"
            @click="!item.disabled && (close(), nextTick(() => item.onClick?.()))"
            role="menuitem"
          >
            <component :is="item.icon" v-if="item.icon" :size="14" :stroke-width="1.6" class="dd-icon" />
            <span class="dd-label">{{ item.text }}</span>
            <span v-if="item.shortcut" class="dd-shortcut">{{ item.shortcut }}</span>
          </button>
        </template>
        <slot :close="close" />
      </div>
    </template>
  </UiPopover>
</template>

<script setup lang="ts">
import { nextTick } from 'vue'
import UiPopover from './UiPopover.vue'
import type { DropdownItem } from './UiDropdown.types'

export type { DropdownItem }

withDefaults(defineProps<{
  items?: DropdownItem[]
  width?: number
  align?: 'start' | 'end' | 'center'
}>(), {
  items: () => [],
  width: 200,
  align: 'start',
})
</script>

<style scoped>
.ui-dropdown {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: -4px;
  padding: 4px;
}
.dd-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-1);
  font: inherit;
  font-size: var(--text-sm);
  text-align: left;
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}
.dd-item:hover:not(.disabled) {
  background: var(--c-surface-2);
  color: var(--c-text-0);
  box-shadow: inset 2px 0 0 var(--c-accent);
}
.dd-item.disabled { opacity: 0.45; cursor: not-allowed; }
.dd-item.danger { color: var(--c-danger); }
.dd-item.danger:hover:not(.disabled) { background: var(--c-danger-bg); }
.dd-icon { flex-shrink: 0; opacity: 0.85; }
.dd-label { flex: 1; }
.dd-shortcut {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.dd-divider {
  height: 1px;
  background: var(--c-surface-3);
  margin: 4px 0;
}
.dd-section-label {
  padding: 6px 10px 4px;
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--c-text-3);
  font-weight: 600;
}
</style>
