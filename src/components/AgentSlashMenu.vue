<template>
  <div
    id="agent-slash-menu"
    class="slash-menu"
    role="listbox"
    :aria-label="menuLabel"
    :aria-busy="loading"
  >
    <div class="slash-menu-head">
      <span>{{ menuLabel }}</span>
      <kbd>↑↓</kbd>
      <kbd>Enter</kbd>
      <kbd>Esc</kbd>
    </div>

    <div v-if="loading && items.length === 0" class="slash-state">{{ loadingLabel }}</div>
    <div v-else-if="items.length === 0" class="slash-state">{{ emptyLabel }}</div>
    <template v-else>
      <section
        v-for="group in groups"
        :key="group.kind"
        class="slash-group"
        :aria-label="group.label"
      >
        <div class="slash-group-label">{{ group.label }}</div>
        <button
          v-for="entry in group.items"
          :id="`agent-slash-${entry.item.id}`"
          :key="entry.item.id"
          class="slash-option"
          :class="{ active: entry.index === activeIndex }"
          type="button"
          role="option"
          :aria-selected="entry.index === activeIndex"
          @mousemove="$emit('hover', entry.index)"
          @pointerdown.prevent="$emit('select', entry.item)"
        >
          <span class="slash-command">{{ entry.item.command }}</span>
          <span class="slash-copy">
            <span class="slash-label">
              {{ entry.item.label }}
              <span v-if="entry.item.selected" class="slash-selected">{{ selectedLabel }}</span>
            </span>
            <span class="slash-description">{{ entry.item.description }}</span>
          </span>
          <span class="slash-kind">{{ group.shortLabel }}</span>
        </button>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AgentSlashCommand, AgentSlashCommandKind } from '../composables/useAgentSlashCommands'

const props = defineProps<{
  items: AgentSlashCommand[]
  activeIndex: number
  loading?: boolean
  menuLabel: string
  loadingLabel: string
  emptyLabel: string
  presetLabel: string
  skillLabel: string
  selectedLabel: string
}>()

defineEmits<{
  (event: 'select', item: AgentSlashCommand): void
  (event: 'hover', index: number): void
}>()

const groups = computed(() => {
  const definitions: Array<{
    kind: AgentSlashCommandKind
    label: string
    shortLabel: string
  }> = [
    { kind: 'preset', label: props.presetLabel, shortLabel: props.presetLabel },
    { kind: 'skill', label: props.skillLabel, shortLabel: 'Skill' },
  ]

  return definitions
    .map((definition) => ({
      ...definition,
      items: props.items
        .map((item, index) => ({ item, index }))
        .filter((entry) => entry.item.kind === definition.kind),
    }))
    .filter((group) => group.items.length > 0)
})
</script>

<style scoped>
.slash-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  left: 0;
  z-index: 12;
  max-height: min(420px, 52vh);
  overflow: auto;
  padding: 6px;
  border: 1px solid var(--c-border);
  border-radius: 14px;
  background: color-mix(in srgb, var(--c-panel) 96%, transparent);
  box-shadow: var(--elevation-3);
  backdrop-filter: blur(24px);
}

.slash-menu-head {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 7px 7px;
  color: var(--c-text-3);
  font-size: 10px;
  letter-spacing: 0.03em;
}

.slash-menu-head span {
  margin-right: auto;
}

.slash-menu-head kbd {
  padding: 1px 4px;
  border: 1px solid var(--c-border);
  border-radius: 4px;
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font: inherit;
  letter-spacing: 0;
}

.slash-group + .slash-group {
  margin-top: 5px;
  padding-top: 5px;
  border-top: 1px solid var(--c-border);
}

.slash-group-label {
  padding: 3px 8px 4px;
  color: var(--c-text-3);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.slash-option {
  display: grid;
  grid-template-columns: minmax(84px, auto) minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  gap: 10px;
  padding: 8px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--c-text-1);
  text-align: left;
  cursor: pointer;
}

.slash-option.active {
  background: var(--c-accent-bg);
  color: var(--c-text-0);
  box-shadow: inset 2px 0 0 var(--c-accent);
}

.slash-command {
  color: var(--c-accent-hover);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  font-weight: 650;
}

.slash-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.slash-label {
  overflow: hidden;
  font-size: 12px;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slash-description {
  overflow: hidden;
  color: var(--c-text-3);
  font-size: 10px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slash-kind,
.slash-selected {
  border: 1px solid var(--c-border);
  border-radius: 999px;
  color: var(--c-text-3);
  font-size: 9px;
  line-height: 1;
}

.slash-kind {
  padding: 4px 6px;
}

.slash-selected {
  margin-left: 5px;
  padding: 2px 5px;
  color: var(--c-accent-hover);
}

.slash-state {
  padding: 22px 12px;
  color: var(--c-text-3);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 420px) {
  .slash-menu-head kbd,
  .slash-kind {
    display: none;
  }

  .slash-option {
    grid-template-columns: minmax(78px, auto) minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .slash-option {
    scroll-behavior: auto;
  }
}
</style>
