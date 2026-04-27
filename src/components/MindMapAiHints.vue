<template>
  <section class="ai-hints">
    <div class="ai-hints-header">
      <div>
        <div class="ai-hints-kicker">AI Hints</div>
        <strong>思维链提醒</strong>
      </div>
      <span class="issue-count">{{ issues.length }}</span>
    </div>

    <div v-if="loading" class="empty-state">正在检查思维链...</div>
    <div v-else-if="!issues.length" class="empty-state">暂无提醒，结构看起来比较清晰。</div>
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.ai-hints-kicker {
  color: var(--accent);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.issue-count {
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--active-bg);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}
.empty-state {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  padding: 10px 0;
}
.issue-card {
  width: 100%;
  display: flex;
  gap: 9px;
  align-items: flex-start;
  margin-bottom: 8px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 86%, transparent);
  color: var(--text-primary);
  padding: 9px;
  text-align: left;
  font: inherit;
  cursor: pointer;
  flex-shrink: 0;
}
.issue-card:hover,
.issue-card.active {
  border-color: var(--accent);
  background: var(--hover-bg);
}
.issue-dot {
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 999px;
  background: var(--accent);
  flex-shrink: 0;
}
.issue-card.warning .issue-dot {
  background: #f59e0b;
}
.issue-card.critical .issue-dot {
  background: #ef4444;
}
.issue-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.issue-content strong {
  font-size: 12px;
}
.issue-content span {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}
</style>
