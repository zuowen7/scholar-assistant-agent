<template>
  <Transition name="v-slide-up">
    <footer v-if="tasks.length" class="task-center" aria-live="polite">
      <span class="task-center-label"><Activity :size="14" />{{ t('tasks.title') }}</span>
      <button
        v-for="task in tasks"
        :key="task.id"
        type="button"
        class="task-chip"
        :class="task.status"
        @click="openTask(task.kind)"
      >
        <span class="task-dot" />
        <span>{{ task.label }}</span>
        <strong v-if="task.progress !== null">{{ task.progress }}%</strong>
        <strong v-else>{{ statusLabel(task.status) }}</strong>
      </button>
    </footer>
  </Transition>
</template>

<script setup lang="ts">
import { Activity } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useTaskCenter, type WorkspaceTask } from '../composables/useTaskCenter'
import { useWorkspaceNavigation } from '../composables/useWorkspaceNavigation'
import { currentProject } from '../composables/useProject'

const { t } = useI18n()
const { tasks } = useTaskCenter()
const workspace = useWorkspaceNavigation()

function statusLabel(status: WorkspaceTask['status']) {
  return t(`tasks.${status}`)
}

function openTask(kind: WorkspaceTask['kind']) {
  if (kind === 'translation' || kind === 'rag') {
    if (currentProject.value) workspace.navigate('sources')
    else workspace.openStandaloneTranslation()
  } else if (kind === 'review') workspace.navigate('review')
  else workspace.toggleAgentDock(true)
}
</script>

<style scoped>
.task-center {
  min-height: 34px;
  flex: 0 0 34px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 12px;
  border-top: 1px solid var(--c-border);
  background: var(--c-nav);
  overflow-x: auto;
  color: var(--c-text-2);
  font-size: 11px;
  scrollbar-width: none;
}
.task-center-label,
.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.task-center-label {
  color: var(--c-text-3);
  font-weight: 650;
}
.task-chip {
  height: 26px;
  padding: 0 9px;
  border: 1px solid var(--c-border);
  border-radius: 7px;
  background: var(--c-surface-1);
  color: var(--c-text-1);
  cursor: pointer;
}
.task-chip:hover {
  border-color: var(--c-accent-ring);
  background: var(--c-surface-2);
}
.task-chip strong {
  color: var(--c-text-3);
  font-size: 10px;
}
.task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-accent);
  animation: task-pulse 1.4s ease-in-out infinite;
}
.task-chip.queued .task-dot {
  background: var(--c-warn);
}
.task-chip.failed .task-dot {
  background: var(--c-danger);
  animation: none;
}
@keyframes task-pulse {
  50% {
    opacity: 0.35;
  }
}
@media (prefers-reduced-motion: reduce) {
  .task-dot {
    animation: none;
  }
}
</style>
