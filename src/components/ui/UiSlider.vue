<template>
  <div class="ui-slider">
    <div v-if="label" class="ui-slider-header">
      <span class="ui-slider-label">{{ label }}</span>
      <span class="ui-slider-value">{{ displayValue }}</span>
    </div>
    <input
      type="range"
      class="ui-slider-track"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      :disabled="disabled"
      @input="$emit('update:modelValue', Number(($event.target as HTMLInputElement).value))"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  label?: string
  suffix?: string
  disabled?: boolean
}>(), {
  min: 0,
  max: 100,
  step: 1,
  suffix: '',
})

defineEmits<{
  (e: 'update:modelValue', value: number): void
}>()

const displayValue = computed(() => `${props.modelValue}${props.suffix}`)
</script>

<style scoped>
.ui-slider {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ui-slider-header {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--c-text-2);
}

.ui-slider-label { font-weight: 500; }
.ui-slider-value { font-family: var(--font-mono); font-feature-settings: "tnum"; color: var(--c-text-1); }

.ui-slider-track {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 3px;
  border-radius: 2px;
  background: var(--c-surface-3);
  outline: none;
  cursor: pointer;
}

.ui-slider-track::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--c-accent);
  cursor: pointer;
  transition: transform var(--motion-fast) var(--ease-spring),
              box-shadow var(--motion-fast) var(--ease-out);
}
.ui-slider-track::-webkit-slider-thumb:hover {
  transform: scale(1.25);
  box-shadow: 0 0 0 4px var(--c-accent-soft);
}

.ui-slider-track:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}
</style>
