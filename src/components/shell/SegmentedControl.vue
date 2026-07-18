<template>
  <div class="segmented-control" role="tablist" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      class="segment-button"
      :class="{ active: modelValue === option.value }"
      role="tab"
      :aria-selected="modelValue === option.value"
      @click="$emit('update:modelValue', option.value)"
    >
      {{ option.label }}
      <span v-if="option.count !== undefined" class="segment-count">{{ option.count }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
  options: Array<{ value: string; label: string; count?: number }>
  label?: string
}>()
defineEmits<{ 'update:modelValue': [value: string] }>()
</script>

<style scoped>
.segmented-control {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-surface-1);
}
.segment-button {
  height: 30px;
  padding: 0 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--c-text-2);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.segment-button:hover { color: var(--c-text-0); background: var(--c-surface-2); }
.segment-button.active { color: #fff; background: var(--c-accent); }
.segment-count { margin-left: 5px; opacity: .72; }
</style>
