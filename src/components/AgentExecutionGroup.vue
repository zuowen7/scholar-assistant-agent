<template>
  <details
    v-if="steps.length"
    class="execution-group"
    :class="{ attention: hasAttention }"
    :open="expanded"
    @toggle="handleToggle"
  >
    <summary>
      <span class="execution-dot" :class="{ active: summary.running > 0 || streaming }"></span>
      <span class="execution-title">{{ t('agent.execution.title') }}</span>
      <span class="execution-meta">{{ summaryText }}</span>
      <span class="execution-chevron" aria-hidden="true">›</span>
    </summary>

    <div class="execution-list">
      <details v-for="step in steps" :key="step.id" class="execution-step">
        <summary>
          <span class="step-status" :class="step.status" aria-hidden="true">
            {{
              step.status === 'success'
                ? '✓'
                : step.status === 'error'
                  ? '!'
                  : step.status === 'denied'
                    ? '×'
                    : step.status === 'skipped'
                      ? '↷'
                      : step.status === 'no_change'
                        ? '–'
                        : '•'
            }}
          </span>
          <span class="step-label">{{ actionLabel(step) }}</span>
          <span class="step-tool">{{ step.toolName }}</span>
          <span class="step-chevron" aria-hidden="true">›</span>
        </summary>
        <div class="step-details">
          <div v-if="Object.keys(step.args).length" class="detail-section">
            <span>{{ t('agent.execution.params') }}</span>
            <pre>{{ formatPayload(step.args) }}</pre>
          </div>
          <div v-if="step.result" class="detail-section">
            <span>{{ t('agent.execution.result') }}</span>
            <pre :class="{ error: step.status === 'error' }">{{
              truncate(step.resultDetail || step.result)
            }}</pre>
          </div>
        </div>
      </details>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AgentEvent } from '../types'
import {
  buildExecutionSteps,
  executionSummary,
  hasPendingApproval,
  type AgentExecutionStep,
} from '../utils/agentExecution'

const props = defineProps<{
  events: AgentEvent[]
  streaming?: boolean
}>()

const { t } = useI18n()
const expanded = ref(false)
const steps = computed(() => buildExecutionSteps(props.events))
const summary = computed(() => executionSummary(steps.value))
const hasAttention = computed(
  () => summary.value.failed > 0 || summary.value.denied > 0 || hasPendingApproval(props.events),
)

watch(
  hasAttention,
  (needsAttention) => {
    if (needsAttention) expanded.value = true
  },
  { immediate: true },
)

const summaryText = computed(() => {
  if (summary.value.running > 0 || props.streaming) {
    return t('agent.execution.running', { count: summary.value.total })
  }
  if (summary.value.failed > 0) {
    return t('agent.execution.failed', {
      count: summary.value.total,
      failed: summary.value.failed,
    })
  }
  return t('agent.execution.completed', { count: summary.value.completed })
})

function fileName(value: unknown): string {
  const path = String(value || '').replaceAll('\\', '/')
  return path.split('/').filter(Boolean).pop() || t('agent.execution.currentFile')
}

function actionLabel(step: AgentExecutionStep): string {
  const target = fileName(step.args.file_path || step.args.path)
  if (step.toolName === 'read_file') return t('agent.execution.readFile', { target })
  if (step.toolName === 'str_replace' || step.toolName === 'write_file')
    return t('agent.execution.editFile', { target })
  if (step.toolName === 'grep_files' || step.toolName === 'glob_files')
    return t('agent.execution.searchFiles')
  if (step.toolName === 'rag_search') return t('agent.execution.searchLibrary')
  if (step.toolName === 'web_search' || step.toolName === 'arxiv_search')
    return t('agent.execution.searchWeb')
  if (step.toolName === 'run_command') return t('agent.execution.runCommand')
  return t('agent.execution.useTool', { tool: step.toolName })
}

function formatPayload(payload: Record<string, unknown>): string {
  return truncate(JSON.stringify(payload, null, 2))
}

function truncate(value: string): string {
  const limit = 1600
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}

function handleToggle(event: Event) {
  expanded.value = (event.currentTarget as HTMLDetailsElement).open
}
</script>

<style scoped>
.execution-group {
  margin: 0 0 7px;
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  background: color-mix(in srgb, var(--c-accent) 3%, var(--c-surface-1));
  color: var(--c-text-2);
}

.execution-group.attention {
  border-color: color-mix(in srgb, var(--c-warn) 45%, var(--c-surface-3));
}

summary {
  list-style: none;
  cursor: pointer;
  user-select: none;
}

summary::-webkit-details-marker {
  display: none;
}

.execution-group > summary {
  display: flex;
  min-height: 32px;
  align-items: center;
  gap: 7px;
  padding: 5px 9px;
}

.execution-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--c-success);
}

.execution-dot.active {
  background: var(--c-accent);
  animation: execution-pulse 1.5s ease-in-out infinite;
}

.execution-title {
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 600;
}

.execution-meta {
  overflow: hidden;
  flex: 1;
  color: var(--c-text-3);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.execution-chevron,
.step-chevron {
  color: var(--c-text-3);
  transition: transform var(--motion-fast) var(--ease-out);
}

.execution-group[open] > summary .execution-chevron,
.execution-step[open] > summary .step-chevron {
  transform: rotate(90deg);
}

.execution-list {
  max-height: 300px;
  overflow: auto;
  padding: 4px 7px 7px;
  border-top: 1px solid var(--c-surface-3);
}

.execution-step {
  border-radius: 6px;
}

.execution-step > summary {
  display: flex;
  min-height: 30px;
  align-items: center;
  gap: 7px;
  padding: 4px 6px;
}

.execution-step > summary:hover {
  background: var(--c-surface-2);
}

.step-status {
  display: inline-grid;
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  color: var(--c-text-3);
  font-size: 10px;
  font-weight: 700;
}

.step-status.success {
  color: var(--c-success);
  background: color-mix(in srgb, var(--c-success) 12%, transparent);
}

.step-status.error {
  color: var(--c-danger);
  background: color-mix(in srgb, var(--c-danger) 12%, transparent);
}

.step-status.denied {
  color: var(--c-warn);
}

.step-status.skipped,
.step-status.no_change {
  color: var(--c-text-2);
}

.step-label {
  overflow: hidden;
  flex: 1;
  color: var(--c-text-1);
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-tool {
  color: var(--c-text-3);
  font-family: var(--font-mono);
  font-size: 9.5px;
}

.step-details {
  padding: 0 6px 7px 23px;
}

.detail-section + .detail-section {
  margin-top: 6px;
}

.detail-section > span {
  color: var(--c-text-3);
  font-size: 10px;
}

.detail-section pre {
  max-height: 140px;
  overflow: auto;
  margin: 3px 0 0;
  padding: 6px 7px;
  border: 1px solid var(--c-surface-3);
  border-radius: 5px;
  background: var(--c-surface-0);
  color: var(--c-text-2);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-section pre.error {
  color: var(--c-danger);
}

@keyframes execution-pulse {
  0%,
  100% {
    opacity: 0.35;
  }
  50% {
    opacity: 1;
  }
}
</style>
