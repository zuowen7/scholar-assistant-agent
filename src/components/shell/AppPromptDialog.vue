<template>
  <AppDialog
    :model-value="modelValue"
    :title="title"
    :subtitle="description"
    :close-label="cancelLabel"
    :close-on-backdrop="!busy"
    @update:model-value="onOpenChange"
  >
    <form class="prompt-form" @submit.prevent="submit">
      <label :for="inputId">{{ label }}</label>
      <input
        :id="inputId"
        v-model="value"
        :placeholder="placeholder"
        :disabled="busy"
        autocomplete="off"
        @keydown.escape.stop="cancel"
      />
      <p v-if="error" class="prompt-error" role="alert">{{ error }}</p>
    </form>
    <template #footer>
      <UiButton variant="secondary" :disabled="busy" @click="cancel">{{ cancelLabel }}</UiButton>
      <UiButton variant="primary" :loading="busy" :disabled="!value.trim()" @click="submit">{{ confirmLabel }}</UiButton>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppDialog from './AppDialog.vue'
import UiButton from '../ui/UiButton.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  label: string
  placeholder?: string
  initialValue?: string
  confirmLabel: string
  cancelLabel: string
  error?: string
  busy?: boolean
}>(), {
  description: '',
  placeholder: '',
  initialValue: '',
  error: '',
  busy: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [value: string]
}>()

const value = ref(props.initialValue)
const inputId = `app-prompt-${Math.random().toString(36).slice(2)}`

watch(() => props.modelValue, (open) => {
  if (open) value.value = props.initialValue
})

function onOpenChange(open: boolean) {
  if (!props.busy) emit('update:modelValue', open)
}

function cancel() {
  if (!props.busy) emit('update:modelValue', false)
}

function submit() {
  const next = value.value.trim()
  if (next && !props.busy) emit('submit', next)
}
</script>

<style scoped>
.prompt-form { display: grid; gap: 8px; padding: 22px; }
label { color: var(--c-text-1); font-size: 12px; font-weight: 600; }
input {
  height: 38px;
  width: 100%;
  border: 1px solid var(--c-border-strong);
  border-radius: 8px;
  background: var(--c-surface-1);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
  outline: none;
  padding: 0 11px;
}
input:focus { border-color: var(--c-accent); box-shadow: var(--ring-focus); }
input:disabled { cursor: wait; opacity: .65; }
.prompt-error { margin: 0; color: var(--c-danger-fg); font-size: 12px; line-height: 1.5; }
</style>
