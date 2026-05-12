<template>
  <div class="reviewer-thread" :class="`severity-${point.severity} status-${point.status}`">
    <!-- Header row: severity + category + source badges -->
    <div class="thread-header">
      <span class="badge badge-severity" :class="`badge-${point.severity}`">
        {{ SEVERITY_LABEL[point.severity] || point.severity }}
      </span>
      <span class="badge badge-category">{{ point.category }}</span>
      <span class="badge badge-source" :class="`badge-source-${point.source}`">
        {{ SOURCE_LABEL[point.source] || point.source }}
      </span>
      <span v-if="point.status !== 'open'" class="badge badge-status" :class="`badge-status-${point.status}`">
        {{ STATUS_LABEL[point.status] || point.status }}
      </span>
    </div>

    <!-- Title -->
    <div class="thread-title">{{ point.title }}</div>

    <!-- Detail -->
    <div class="thread-detail">{{ point.detail }}</div>

    <!-- Anchor link -->
    <button
      v-if="point.anchor_id"
      class="anchor-link"
      data-anchor-btn
      @click="$emit('focusAnchor', point.anchor_id!)"
    >
      跳转到原文位置
    </button>

    <!-- Status action button -->
    <button
      class="status-btn"
      data-status-btn
      @click="cycleStatus"
    >
      {{ point.status === 'open' ? '标记状态' : '重新打开' }}
    </button>

    <!-- Rebuttal section (Phase 4 full impl; Phase 3 placeholder) -->
    <div v-if="point.status === 'open' || point.thread.length > 0" class="rebuttal-section">
      <!-- Thread history -->
      <div
        v-for="turn in point.thread"
        :key="turn.id"
        class="thread-turn"
        :class="`turn-${turn.role}`"
      >
        <span class="turn-role">{{ turn.role === 'author' ? '作者' : 'Reviewer' }}</span>
        <span class="turn-text">{{ turn.text }}</span>
      </div>

      <!-- Rebuttal input placeholder -->
      <div v-if="point.status === 'open'" class="rebuttal-placeholder">
        <span class="rebuttal-hint">反驳 rebuttal（Phase 4 启用）</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ReviewPoint } from '../../types'

const props = defineProps<{ point: ReviewPoint }>()
const emit = defineEmits<{
  focusAnchor: [anchorId: string]
  updatePointStatus: [status: string]
}>()

const SEVERITY_LABEL: Record<string, string> = {
  minor: 'minor 轻微',
  major: 'major 严重',
  fatal: 'fatal 致命',
}

const STATUS_LABEL: Record<string, string> = {
  open: 'open',
  rebutted: 'rebutted 已反驳',
  accepted: 'accepted 认可',
  dismissed: 'dismissed 忽略',
}

const SOURCE_LABEL: Record<string, string> = {
  llm: 'llm',
  ledger_check: 'ledger 账本',
  coherence_check: 'coherence',
  rw_check: 'rw',
  scoped: 'scoped 质疑',
  imported: 'imported',
}

const STATUS_CYCLE: Record<string, string> = {
  open: 'rebutted',
  rebutted: 'accepted',
  accepted: 'dismissed',
  dismissed: 'open',
}

function cycleStatus() {
  const next = STATUS_CYCLE[props.point.status] ?? 'open'
  emit('updatePointStatus', next)
}
</script>

<style scoped>
.reviewer-thread {
  padding: var(--space-3, 10px);
  border-left: 3px solid var(--c-border, #ccc);
  margin-bottom: var(--space-2, 8px);
  border-radius: var(--radius-sm, 4px);
  background: var(--c-surface, #fafafa);
}

.reviewer-thread.severity-major { border-left-color: var(--c-warning, #f59e0b); }
.reviewer-thread.severity-fatal { border-left-color: var(--c-error, #ef4444); }
.reviewer-thread.status-rebutted { opacity: 0.6; }

.thread-header {
  display: flex;
  gap: var(--space-1, 4px);
  flex-wrap: wrap;
  margin-bottom: var(--space-2, 8px);
}

.badge {
  padding: 2px 6px;
  border-radius: var(--radius-xs, 2px);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge-minor { background: var(--c-info-bg, #dbeafe); color: var(--c-info, #1d4ed8); }
.badge-major { background: var(--c-warning-bg, #fef3c7); color: var(--c-warning, #92400e); }
.badge-fatal { background: var(--c-error-bg, #fee2e2); color: var(--c-error, #991b1b); }

.badge-source { background: var(--c-surface-2, #e5e7eb); color: var(--c-text-2, #6b7280); }
.badge-source-scoped { background: var(--c-accent-bg, #ede9fe); color: var(--c-accent, #7c3aed); }
.badge-source-ledger_check { background: var(--c-info-bg, #dbeafe); color: var(--c-info, #1d4ed8); }

.badge-category { background: var(--c-surface-3, #f3f4f6); color: var(--c-text, #374151); }
.badge-status-rebutted { background: var(--c-success-bg, #d1fae5); color: var(--c-success, #065f46); }
.badge-status-accepted { background: var(--c-info-bg, #dbeafe); color: var(--c-info, #1d4ed8); }

.thread-title {
  font-weight: 600;
  margin-bottom: var(--space-1, 4px);
  color: var(--c-text, #111);
}

.thread-detail {
  font-size: 13px;
  color: var(--c-text-2, #6b7280);
  margin-bottom: var(--space-2, 8px);
  line-height: 1.5;
}

.anchor-link, .status-btn {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: var(--radius-xs, 2px);
  border: 1px solid var(--c-border, #d1d5db);
  background: transparent;
  cursor: pointer;
  margin-right: var(--space-1, 4px);
  color: var(--c-accent, #6366f1);
}

.anchor-link:hover, .status-btn:hover {
  background: var(--c-surface-2, #f3f4f6);
}

.rebuttal-section { margin-top: var(--space-2, 8px); }

.thread-turn {
  display: flex;
  gap: var(--space-2, 8px);
  font-size: 12px;
  padding: var(--space-1, 4px) 0;
  border-top: 1px solid var(--c-border, #e5e7eb);
}

.turn-role {
  font-weight: 600;
  min-width: 60px;
  color: var(--c-text-2, #6b7280);
}

.rebuttal-placeholder {
  padding: var(--space-2, 8px);
  font-size: 12px;
  color: var(--c-text-3, #9ca3af);
  font-style: italic;
}
</style>
