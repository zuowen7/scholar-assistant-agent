<template>
  <input
    class="ui-input"
    :value="modelValue"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
  />
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: string
  type?: string
  placeholder?: string
  disabled?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()
</script>

<style scoped>
.ui-input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--input-bg);
  color: var(--text-primary);
  font: inherit;
  font-size: var(--text-sm);
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}
.ui-input:focus {
  border-color: var(--c-accent);
}
.ui-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ui-input::placeholder {
  color: var(--c-text-3);
}
</style>
