<template>
  <div class="status-cluster">
    <!-- Backend -->
    <UiPill :tone="healthOk ? 'ok' : 'off'">后端</UiPill>

    <!-- Ollama or Cloud (based on engine type) -->
    <template v-if="engineType === 'ollama'">
      <UiPill
        :tone="ollamaOk ? 'ok' : 'off'"
        :clickable="!ollamaOk"
        :disabled="ollamaLoading"
        @click="!ollamaOk && $emit('toggle-ollama')"
      >
        <template v-if="ollamaLoading">启动中…</template>
        <template v-else>Ollama</template>
      </UiPill>
    </template>
    <template v-else>
      <UiPill :tone="cloudOk ? 'ok' : 'off'">云端</UiPill>
    </template>

    <!-- LaTeX -->
    <UiPill
      :tone="tectonicOk ? 'ok' : 'off'"
      :clickable="!tectonicOk"
      :disabled="tectonicChecking"
      @click="!tectonicOk && $emit('handle-tectonic')"
    >
      <template v-if="tectonicChecking">检测…</template>
      <template v-else>LaTeX</template>
    </UiPill>
  </div>
</template>

<script setup lang="ts">
import UiPill from './ui/UiPill.vue'

defineProps<{
  healthOk: boolean
  engineType: 'ollama' | 'cloud'
  ollamaOk: boolean
  ollamaLoading: boolean
  cloudOk: boolean
  tectonicOk: boolean
  tectonicChecking: boolean
}>()

defineEmits<{
  (e: 'toggle-ollama'): void
  (e: 'handle-tectonic'): void
}>()
</script>

<style scoped>
.status-cluster {
  display: flex;
  align-items: center;
  gap: 4px;
  -webkit-app-region: no-drag;
}
</style>
