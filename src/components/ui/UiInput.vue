<template>
  <div
    class="ui-input-wrap"
    :class="{ 'has-error': error, disabled }"
  >
    <span v-if="$slots.prefix" class="ui-input-prefix">
      <slot name="prefix" />
    </span>
    <input
      class="ui-input"
      :value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :aria-invalid="!!error"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="$slots.suffix" class="ui-input-suffix">
      <slot name="suffix" />
    </span>
    <button
      v-if="clearable && modelValue"
      class="ui-input-clear"
      tabindex="-1"
      @click="$emit('update:modelValue', '')"
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <line x1="2.5" y1="2.5" x2="7.5" y2="7.5" /><line x1="7.5" y1="2.5" x2="2.5" y2="7.5" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue?: string
  type?: string
  placeholder?: string
  disabled?: boolean
  error?: boolean
  clearable?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()
</script>

<style scoped>
.ui-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: var(--control-md);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-control);
  background: var(--c-surface-2);
  transition: box-shadow var(--motion-fast) var(--ease-out),
              border-color var(--motion-fast) var(--ease-out);
}

.ui-input-wrap:focus-within {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}

.ui-input-wrap.has-error {
  border-color: var(--c-danger);
  animation: input-shake 0.4s var(--ease-smooth);
}

.ui-input-wrap.disabled {
  opacity: 0.42;
  pointer-events: none;
}

.ui-input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0 10px;
  border: none;
  background: transparent;
  color: var(--c-text-0);
  font: inherit;
  font-size: var(--text-sm);
  outline: none;
}

.ui-input::placeholder { color: var(--c-text-3); }

.ui-input-prefix,
.ui-input-suffix {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  color: var(--c-text-3);
  padding: 0 2px;
}

.ui-input-prefix { padding-left: 10px; }
.ui-input-suffix { padding-right: 10px; }

.ui-input-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  background: var(--c-surface-3);
  color: var(--c-text-3);
  border-radius: 50%;
  cursor: pointer;
  margin-right: 6px;
  flex-shrink: 0;
  transition: background var(--motion-fast), color var(--motion-fast);
}
.ui-input-clear:hover { background: var(--c-surface-4); color: var(--c-text-0); }

@keyframes input-shake {
  0%, 100% { transform: translateX(0); }
  20%      { transform: translateX(-3px); }
  40%      { transform: translateX(3px); }
  60%      { transform: translateX(-2px); }
  80%      { transform: translateX(2px); }
}

/* Light mode */
:global([data-theme="light"]) .ui-input-wrap { background: var(--c-surface-2); border-color: var(--c-surface-3); }
</style>
