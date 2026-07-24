<template>
  <div v-if="checkpoint" class="checkpoint-card" :class="checkpoint.checkpoint_type.toLowerCase()">
    <div class="checkpoint-header">
      <span class="checkpoint-icon">{{ isMandatory ? '🔒' : '📋' }}</span>
      <span class="checkpoint-title">{{ checkpoint.title }}</span>
      <span v-if="isMandatory" class="checkpoint-required">MANDATORY</span>
    </div>

    <div v-if="checkpoint.deliverables?.length" class="checkpoint-deliverables">
      <div v-for="d in checkpoint.deliverables" :key="d" class="deliverable-item">
        ✓ {{ d }}
      </div>
    </div>

    <div v-if="checkpoint.metrics && Object.keys(checkpoint.metrics).length" class="checkpoint-metrics">
      <span v-for="(val, key) in checkpoint.metrics" :key="key" class="metric">
        {{ key }}: {{ val }}
      </span>
    </div>

    <div class="checkpoint-actions">
      <button class="btn-continue" @click="$emit('decide', 'continue')">
        Continue
      </button>
      <button v-if="!isMandatory" class="btn-pause" @click="$emit('decide', 'pause')">
        Pause
      </button>
      <button class="btn-revise" @click="$emit('decide', 'revise')">
        Revise
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PendingCheckpoint } from '../composables/useAgentChat'

const props = defineProps<{
  checkpoint: PendingCheckpoint | null
}>()

defineEmits<{
  decide: [decision: string]
}>()

const isMandatory = computed(() =>
  props.checkpoint?.checkpoint_type === 'MANDATORY'
)
</script>
