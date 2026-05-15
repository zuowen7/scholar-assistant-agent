<template>
  <div class="rp-tab-bar">
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'preview' }"
      @click="emit('update:modelValue', 'preview')"
    >
      <Eye :size="13" :stroke-width="1.7" /> 预览
    </button>
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'ai' }"
      @click="emit('update:modelValue', 'ai')"
    >
      <Bot :size="13" :stroke-width="1.7" /> AI 编辑
    </button>
    <button
      class="rp-tab"
      :class="{ active: modelValue === 'argument' }"
      @click="emit('update:modelValue', 'argument')"
    >
      <GitBranch :size="13" :stroke-width="1.7" /> 论证陪练
    </button>
    <button class="rp-close" title="关闭面板" @click="emit('update:modelValue', null)">
      <X :size="13" :stroke-width="2" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { Eye, Bot, GitBranch, X } from './ui/icons'

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
  border-bottom: 1px solid rgba(255, 255, 255, 0.02);
  flex-shrink: 0;
}
.rp-tab {
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
  transition: all var(--motion-fast) var(--ease-out);
}
.rp-tab:hover {
  color: var(--c-text-1);
  background: rgba(255, 255, 255, 0.03);
}
.rp-tab.active {
  color: var(--c-text-0);
  background: var(--c-surface-3);
  border-color: rgba(255, 255, 255, 0.06);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2), inset 0 1px 1px rgba(255, 255, 255, 0.05);
}
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
}
.rp-close:hover {
  background: var(--hover-bg);
  color: var(--c-danger);
}
</style>
