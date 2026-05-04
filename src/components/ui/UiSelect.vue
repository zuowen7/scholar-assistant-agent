<template>
  <select
    class="ui-select"
    :value="modelValue"
    :disabled="disabled"
    @change="$emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <slot />
  </select>
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: string
  disabled?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()
</script>

<style scoped>
.ui-select {
  width: 100%;
  height: var(--control-md);
  padding: 0 28px 0 10px;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-control);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: var(--text-sm);
  outline: none;
  cursor: pointer;
  transition: box-shadow var(--motion-fast) var(--ease-out),
              border-color var(--motion-fast) var(--ease-out);
  box-sizing: border-box;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
}
.ui-select:focus {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}
.ui-select:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

:global([data-theme="light"]) .ui-select { background-color: var(--c-surface-2); }
</style>
