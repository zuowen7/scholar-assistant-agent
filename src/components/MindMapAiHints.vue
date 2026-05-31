<template>
  <section class="ai-hints">
    <div class="ai-hints-header">
      <div>
        <div class="ai-hints-kicker">{{ t('mindmap.aiReminder') }}</div>
        <strong>{{ t('mindmap.chainCheck') }}</strong>
      </div>
      <span class="issue-count">{{ issues.length }}</span>
    </div>

    <div v-if="loading" class="hints-loading">
      <div class="hints-loading-head">
        <UiSpinner size="sm" />
        <span class="anim-shimmer-text">{{ t('mindmap.checkingChain') }}</span>
      </div>
      <div class="hints-skeletons">
        <div v-for="n in 3" :key="n" class="skeleton-card" :style="{ '--stagger-i': n - 1 }">
          <UiSkeleton shape="circle" width="7" height="7" />
          <div class="skeleton-lines">
            <UiSkeleton shape="line" width="58%" height="9" />
            <UiSkeleton shape="line" width="88%" height="8" />
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="!issues.length" class="empty-state compact anim-fade-in-up">
      <span class="empty-badge">OK</span>
      <span>{{ t('mindmap.noReminders') }}</span>
    </div>
    <TransitionGroup v-else name="v-list-stagger" tag="div" class="issue-list" appear>
      <button
        v-for="(issue, i) in issues"
        :key="issue.id"
        class="issue-card u-interactive"
        :class="[issue.severity, { active: issue.id === activeIssueId }]"
        :style="{ '--stagger-i': i }"
        @click="$emit('select-issue', issue)"
      >
        <span class="issue-dot" />
        <span class="issue-content">
          <strong>{{ issue.title }}</strong>
          <span>{{ issue.message }}</span>
        </span>
      </button>
    </TransitionGroup>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import type { MindMapAnalysisIssue } from '../composables/useMindMapAnalysis'
import UiSpinner from './ui/UiSpinner.vue'
import UiSkeleton from './ui/UiSkeleton.vue'

defineProps<{
  issues: MindMapAnalysisIssue[]
  activeIssueId: string
  loading: boolean
}>()

defineEmits<{
  (e: 'select-issue', issue: MindMapAnalysisIssue): void
}>()
</script>

<style scoped>
.ai-hints {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ai-hints-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.ai-hints-kicker {
  color: var(--c-accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.ai-hints-header strong {
  display: block;
  margin-top: 2px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.25;
}
.issue-count {
  min-width: 20px;
  height: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--active-bg) 70%, transparent);
  color: var(--c-accent);
  font-size: 11px;
  font-weight: 700;
}
.empty-state {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}
.empty-state.compact {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 9px;
  border: 1px solid color-mix(in srgb, var(--border-color) 48%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 28%, transparent);
}
.empty-badge {
  min-width: 26px;
  height: 18px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--c-success-bg);
  color: var(--c-success-fg);
  font-size: 10px;
  font-weight: 800;
}

/* ── 加载状态：spinner + 骨架卡片 ───────────────────── */
.hints-loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hints-loading-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
}
.hints-skeletons {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.skeleton-card {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 9px;
  border: 1px solid color-mix(in srgb, var(--border-color) 42%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 24%, transparent);
  animation: anim-fade-in-up var(--motion-slow) var(--ease-out) both;
  animation-delay: calc(var(--stagger-i, 0) * var(--motion-stagger));
}
.skeleton-card :deep(.ui-skeleton.circle) { margin-top: 4px; }
.skeleton-lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.issue-card {
  width: 100%;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 6px;
  border: 1px solid color-mix(in srgb, var(--border-color) 52%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 38%, transparent);
  color: var(--text-primary);
  padding: 8px 9px;
  text-align: left;
  font: inherit;
  cursor: pointer;
  flex-shrink: 0;
}
.issue-card:hover,
.issue-card.active {
  border-color: var(--c-accent);
  background: var(--hover-bg);
}
.issue-dot {
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 999px;
  background: var(--c-accent);
  flex-shrink: 0;
}
.issue-card.warning .issue-dot {
  background: var(--c-warn);
}
.issue-card.critical .issue-dot {
  background: var(--c-danger);
}
.issue-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.issue-content strong {
  font-size: 12px;
}
.issue-content span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.42;
}
</style>
