<template>
  <ComplianceModal
    :visible="visible"
    :loading="loading"
    :error="error"
    :report="report"
    @close="$emit('close')"
    @retry="$emit('retry')"
  />
</template>

<script setup lang="ts">
import ComplianceModal from './ComplianceModal.vue'

defineProps<{
  visible: boolean
  loading: boolean
  error: string
  report: Record<string, unknown> | null
}>()

defineEmits<{
  close: []
  retry: []
}>()
</script>
