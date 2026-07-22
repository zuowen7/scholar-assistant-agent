<template>
  <AppDialog
    :model-value="modelValue"
    :title="title"
    :subtitle="description"
    :close-label="cancelLabel"
    :close-on-backdrop="!busy"
    @update:model-value="!busy && $emit('update:modelValue', $event)"
  >
    <div class="confirm-body" :class="`confirm-body--${tone}`">
      <div class="confirm-symbol" aria-hidden="true"><AlertTriangle v-if="tone === 'danger'" :size="20" /><Info v-else :size="20" /></div>
      <p><slot>{{ detail }}</slot></p>
    </div>
    <template #footer>
      <UiButton variant="secondary" :disabled="busy" @click="$emit('update:modelValue', false)">{{ cancelLabel }}</UiButton>
      <UiButton :variant="tone === 'danger' ? 'danger' : 'primary'" :loading="busy" @click="$emit('confirm')">{{ confirmLabel }}</UiButton>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { AlertTriangle, Info } from 'lucide-vue-next'
import AppDialog from './AppDialog.vue'
import UiButton from '../ui/UiButton.vue'

withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description?: string
  detail?: string
  confirmLabel: string
  cancelLabel: string
  tone?: 'default' | 'danger'
  busy?: boolean
}>(), { description: '', detail: '', tone: 'default', busy: false })

defineEmits<{ 'update:modelValue': [value: boolean]; confirm: [] }>()
</script>

<style scoped>
.confirm-body { display: flex; align-items: flex-start; gap: 13px; padding: 24px; }
.confirm-symbol { display: grid; width: 38px; height: 38px; flex: 0 0 auto; place-items: center; border-radius: 9px; background: var(--c-info-bg); color: var(--c-info-fg); }
.confirm-body--danger .confirm-symbol { background: var(--c-danger-bg); color: var(--c-danger-fg); }
p { margin: 4px 0 0; color: var(--c-text-1); font-size: 13px; line-height: 1.65; }
</style>
