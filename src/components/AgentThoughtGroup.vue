<template>
  <details v-if="phases.length" class="agent-thought-group">
    <summary>
      <span class="thought-dot" :class="{ active: streaming }"></span>
      <span class="thought-title">{{ t('agent.thoughtProcess') }}</span>
      <span class="thought-meta">
        {{
          streaming
            ? t('agent.thinkingCompact')
            : t('agent.thoughtPhases', { count: phases.length })
        }}
      </span>
      <span class="thought-chevron" aria-hidden="true">›</span>
    </summary>
    <div class="thought-details">
      <p v-for="(phase, index) in phases" :key="index">{{ phase }}</p>
    </div>
  </details>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AgentEvent } from '../types'
import { collapseThoughtEvents } from '../utils/agentThoughts'

const props = defineProps<{
  events: AgentEvent[]
  streaming?: boolean
}>()

const { t } = useI18n()
const phases = computed(() => collapseThoughtEvents(props.events))
</script>

<style scoped>
.agent-thought-group {
  margin: 0 0 7px;
  border: 1px solid var(--c-surface-3);
  border-radius: 8px;
  background: color-mix(in srgb, var(--c-accent) 3%, var(--c-surface-1));
  color: var(--c-text-2);
}

summary {
  display: flex;
  min-height: 32px;
  align-items: center;
  gap: 7px;
  padding: 5px 9px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

summary::-webkit-details-marker {
  display: none;
}

.thought-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--c-text-3);
}

.thought-dot.active {
  background: var(--c-accent);
  animation: thought-pulse 1.5s ease-in-out infinite;
}

.thought-title {
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 600;
}

.thought-meta {
  overflow: hidden;
  flex: 1;
  color: var(--c-text-3);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thought-chevron {
  color: var(--c-text-3);
  font-size: 16px;
  line-height: 1;
  transition: transform var(--motion-fast) var(--ease-out);
}

details[open] .thought-chevron {
  transform: rotate(90deg);
}

.thought-details {
  max-height: 220px;
  overflow: auto;
  padding: 0 10px 8px 22px;
  border-top: 1px solid var(--c-surface-3);
}

.thought-details p {
  margin: 8px 0 0;
  color: var(--c-text-2);
  font-size: 11.5px;
  line-height: 1.55;
  white-space: pre-wrap;
}

@keyframes thought-pulse {
  0%,
  100% {
    opacity: 0.35;
  }
  50% {
    opacity: 1;
  }
}
</style>
