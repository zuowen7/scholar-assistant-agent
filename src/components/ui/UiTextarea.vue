<template>
  <textarea
    class="ui-textarea"
    :value="modelValue"
    :placeholder="placeholder"
    :rows="rows"
    :disabled="disabled"
    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
  />
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: string
  placeholder?: string
  rows?: number
  disabled?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()
</script>

<style scoped>
.ui-textarea {
  width: 100%;
  min-height: 54px;
  padding: 9px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--input-bg);
  color: var(--text-primary);
  font: inherit;
  font-size: var(--text-sm);
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.ui-textarea:focus {
  border-color: var(--c-accent);
}
.ui-textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ui-textarea::placeholder {
  color: var(--c-text-3);
}
</style>
