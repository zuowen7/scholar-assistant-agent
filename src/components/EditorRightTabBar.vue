<template>
  <div class="rp-tab-bar">
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'preview' }"
      @click="emit('update:modelValue', 'preview')"
    >
      <Eye :size="13" :stroke-width="1.7" /> {{ t('editor.rightPreview') }}
    </button>
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'ai' }"
      @click="emit('update:modelValue', 'ai')"
    >
      <Bot :size="13" :stroke-width="1.7" /> {{ t('editor.rightAiEdit') }}
    </button>
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'argument' }"
      @click="emit('update:modelValue', 'argument')"
    >
      <GitBranch :size="13" :stroke-width="1.7" /> {{ t('editor.rightArgument') }}
    </button>
    <button class="rp-close" :title="t('editor.rightClosePanel')" @click="emit('update:modelValue', null)">
      <X :size="13" :stroke-width="2" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { Eye, Bot, GitBranch, X } from './ui/icons'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

type RightTab = 'preview' | 'ai' | 'argument'

defineProps<{ modelValue: RightTab | null }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: RightTab | null): void
}>()
</script>

<style scoped>
.rp-tab-bar {
  display: flex;
  align-items: center;
  background: transparent;
  padding: 8px 12px;
  gap: 4px;
  border-bottom: 1px solid var(--c-surface-2);
  flex-shrink: 0;
}
.rp-tab {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--c-text-3);
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out),
              background var(--motion-fast) var(--ease-out),
              border-color var(--motion-fast) var(--ease-out),
              transform var(--motion-fast) var(--ease-spring);
}
/* sliding underline indicator */
.rp-tab::after {
  content: '';
  position: absolute;
  left: 50%;
  right: 50%;
  bottom: 3px;
  height: 2px;
  border-radius: 2px;
  background: var(--c-accent);
  opacity: 0;
  transition: left var(--motion-base) var(--ease-spring),
              right var(--motion-base) var(--ease-spring),
              opacity var(--motion-fast);
}
.rp-tab:hover {
  color: var(--c-text-1);
  background: var(--c-surface-2);
}
.rp-tab:active { transform: scale(0.96); }
.rp-tab:focus-visible { outline: none; box-shadow: var(--ring-focus); }
.rp-tab.active {
  color: var(--c-text-0);
  background: var(--c-surface-3);
  border-color: var(--c-surface-4);
  box-shadow: var(--elevation-1);
}
.rp-tab.active::after { left: 12px; right: 12px; opacity: 0.8; }
.rp-tab.active :deep(svg) { color: var(--c-accent); }
.rp-close {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 4px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  transition: background var(--motion-fast), color var(--motion-fast), transform var(--motion-fast) var(--ease-spring);
}
.rp-close:hover {
  background: var(--c-danger-bg);
  color: var(--c-danger);
  transform: rotate(90deg);
}
.rp-close:active { transform: scale(0.85); }
.rp-close:focus-visible { outline: none; box-shadow: var(--ring-focus); }

@media (prefers-reduced-motion: reduce) {
  .rp-close:hover { transform: none; }
}
</style>
