<template>
  <section class="ai-hints">
    <div class="ai-hints-header">
      <div>
        <div class="ai-hints-kicker">AI 提醒</div>
        <strong>思维链检查</strong>
      </div>
      <span class="issue-count">{{ issues.length }}</span>
    </div>

    <div v-if="loading" class="empty-state busy">正在检查思维链...</div>
    <div v-else-if="!issues.length" class="empty-state compact">
      <span class="empty-badge">OK</span>
      <span>暂无提醒，当前结构看起来比较清晰。</span>
    </div>
    <button
      v-for="issue in issues"
      v-else
      :key="issue.id"
      class="issue-card"
      :class="[issue.severity, { active: issue.id === activeIssueId }]"
      @click="$emit('select-issue', issue)"
    >
      <span class="issue-dot" />
      <span class="issue-content">
        <strong>{{ issue.title }}</strong>
        <span>{{ issue.message }}</span>
      </span>
    </button>
  </section>
</template>

<script setup lang="ts">
import type { MindMapAnalysisIssue } from '../composables/useMindMapAnalysis'

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
.empty-state.busy {
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 28%, transparent);
  padding: 8px;
}
.empty-badge {
  min-width: 26px;
  height: 18px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, #22c55e 14%, transparent);
  color: #22c55e;
  font-size: 10px;
  font-weight: 800;
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
