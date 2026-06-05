<template>
  <div class="workflow-list">
    <div class="workflow-list-header">
      <h3>{{ t('agent.sessions') }}</h3>
      <button class="btn-new-chat" @click="$emit('newChat')">
        + {{ t('agent.newChat') }}
      </button>
    </div>

    <div v-if="loading" class="workflow-loading">
      {{ t('common.loading') }}
    </div>

    <div v-else-if="workflows.length === 0" class="workflow-empty">
      {{ t('agent.noSessions') }}
    </div>

    <div v-else class="workflow-cards">
      <div
        v-for="wf in workflows"
        :key="wf.id"
        class="workflow-card"
        :class="{ active: wf.id === activeId }"
        @click="$emit('select', wf.id)"
      >
        <div class="wf-header">
          <span class="wf-title">{{ wf.title || wf.id.slice(0, 8) }}</span>
          <span class="wf-badge" :class="`state-${wf.state}`">{{ wf.state }}</span>
        </div>

        <div v-if="wf.current_stage" class="wf-pipeline">
          <div class="pipeline-bar">
            <div
              v-for="stage in pipelineStages"
              :key="stage"
              class="pipeline-dot"
              :class="{
                done: pipelineIndex(stage) < pipelineIndex(wf.current_stage),
                active: stage === wf.current_stage,
              }"
            />
          </div>
        </div>

        <div class="wf-meta">
          <span class="wf-count">{{ wf.message_count || 0 }} msgs</span>
          <span class="wf-time">{{ formatTime(wf.updated_at || wf.created_at) }}</span>
        </div>

        <button
          class="btn-delete-wf"
          @click.stop="$emit('delete', wf.id)"
        >
          ×
        </button>
      </div>
    </div>

    <div v-if="workflows.length > 0" class="workflow-cleanup">
      <button class="btn-cleanup" @click="$emit('cleanup')">
        {{ t('agent.cleanupOld') }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps<{
  workflows: any[]
  activeId: string | null
  loading?: boolean
}>()

defineEmits<{
  select: [id: string]
  delete: [id: string]
  newChat: []
  cleanup: []
}>()

const pipelineStages = ['research', 'outline', 'draft', 'review', 'revise', 'finalize']

function pipelineIndex(stage: string): number {
  return pipelineStages.indexOf(stage)
}

function formatTime(iso: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString()
  } catch {
    return iso.slice(0, 10)
  }
}
</script>
