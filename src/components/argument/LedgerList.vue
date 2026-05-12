<template>
  <div class="ledger-list">
    <div class="ledger-toolbar">
      <button
        class="analyze-btn"
        data-analyze-btn
        :disabled="building"
        @click="$emit('analyze')"
      >
        {{ building ? '分析中…' : (ledger ? '重新分析' : '分析论证账本') }}
      </button>
    </div>

    <div v-if="!ledger" class="ledger-empty">
      还没分析。点上方「分析论证账本」让 AI 把你 abstract/intro 里立的承诺逐条对到正文。
    </div>

    <template v-else>
      <div
        v-for="group in groups"
        :key="group.status"
        class="ledger-group"
      >
        <div class="group-header">
          <span class="group-badge" :class="`badge-${group.status}`">{{ statusLabel(group.status) }}</span>
          <span class="group-count">{{ group.promises.length }}</span>
        </div>

        <div
          v-for="promise in group.promises"
          :key="promise.id"
          class="promise-row"
        >
          <div class="promise-left">
            <span class="kind-chip">{{ kindLabel(promise.kind) }}</span>
          </div>
          <div class="promise-body">
            <button
              class="promise-text"
              data-promise-focus
              @click="$emit('focusAnchor', promise.source_anchor_id)"
            >
              {{ promise.text }}
            </button>
            <div v-if="promise.note" class="promise-note">{{ promise.note }}</div>
          </div>
          <div class="promise-actions">
            <button
              v-if="promise.discharge_anchor_ids.length > 0"
              class="jump-btn"
              @click="$emit('focusAnchor', promise.discharge_anchor_ids[0])"
            >
              → 兑付处
            </button>
            <button
              v-if="promise.status === 'unpaid' || promise.status === 'partial'"
              class="suggest-btn"
              data-suggest-btn
              @click="$emit('suggestExperiment', promise.id)"
            >
              怎么补满
            </button>
            <span
              v-if="isLost(promise)"
              class="lost-badge"
              title="未在正文中定位"
            >⚠</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Ledger, Promise as ArgPromise, PromiseStatus, Anchor } from '../../types'

const props = defineProps<{
  ledger: Ledger | null
  building: boolean
}>()

defineEmits<{
  analyze: []
  focusAnchor: [anchorId: string]
  suggestExperiment: [promiseId: string]
}>()

const STATUS_ORDER: PromiseStatus[] = ['unpaid', 'mismatch', 'partial', 'paid', 'unknown']

interface Group { status: PromiseStatus; promises: ArgPromise[] }

const groups = computed<Group[]>(() => {
  if (!props.ledger) return []
  const map = new Map<PromiseStatus, ArgPromise[]>()
  for (const p of props.ledger.promises) {
    const list = map.get(p.status) ?? []
    list.push(p)
    map.set(p.status, list)
  }
  return STATUS_ORDER
    .filter(s => map.has(s))
    .map(s => ({ status: s, promises: map.get(s)! }))
})

function statusLabel(s: PromiseStatus): string {
  const labels: Record<PromiseStatus, string> = {
    unpaid: '未兑付',
    mismatch: '不一致',
    partial: '部分兑付',
    paid: '已兑付',
    unknown: '未知',
  }
  return labels[s] ?? s
}

function kindLabel(k: string): string {
  const labels: Record<string, string> = {
    contribution: 'Contribution',
    claim: 'Claim',
    hypothesis: 'Hypothesis',
    gap_statement: 'Gap',
    scope: 'Scope',
  }
  return labels[k] ?? k
}

function isLost(promise: ArgPromise): boolean {
  const anchor = props.ledger?.anchors.find((a: Anchor) => a.id === promise.source_anchor_id)
  return anchor?.status === 'lost'
}
</script>

<style scoped>
.ledger-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  height: 100%;
  overflow: hidden;
}

.ledger-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, #3a3a3a);
}

.analyze-btn {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border, #555);
  background: var(--bg-2, #2a2a2a);
  color: var(--text, #ccc);
  cursor: pointer;
}

.analyze-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.analyze-btn:not(:disabled):hover {
  background: var(--bg-3, #333);
}

.ledger-empty {
  padding: 24px 16px;
  font-size: 12px;
  color: var(--text-dim, #666);
  line-height: 1.6;
}

.ledger-group {
  border-bottom: 1px solid var(--border, #2a2a2a);
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 4px;
  font-size: 11px;
}

.group-badge {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}

.badge-unpaid { background: #4a1a1a; color: #f87171; }
.badge-mismatch { background: #4a2a1a; color: #fb923c; }
.badge-partial { background: #3a3a1a; color: #fbbf24; }
.badge-paid { background: #1a3a1a; color: #4ade80; }
.badge-unknown { background: #2a2a2a; color: #9ca3af; }

.group-count {
  color: var(--text-dim, #666);
  font-size: 10px;
}

.promise-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 12px;
  border-top: 1px solid var(--border, #1e1e1e);
}

.promise-left {
  flex-shrink: 0;
  padding-top: 2px;
}

.kind-chip {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 2px;
  background: var(--bg-3, #333);
  color: var(--text-dim, #888);
  white-space: nowrap;
}

.promise-body {
  flex: 1;
  min-width: 0;
}

.promise-text {
  display: block;
  font-size: 11px;
  color: var(--text, #ccc);
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  text-align: left;
  width: 100%;
  line-height: 1.4;
}

.promise-text:hover {
  color: var(--accent, #60a5fa);
  text-decoration: underline;
}

.promise-note {
  font-size: 10px;
  color: var(--text-dim, #888);
  margin-top: 2px;
  font-style: italic;
}

.promise-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.jump-btn, .suggest-btn {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid var(--border, #444);
  background: none;
  color: var(--text-dim, #888);
  cursor: pointer;
  white-space: nowrap;
}

.jump-btn:hover, .suggest-btn:hover {
  color: var(--accent, #60a5fa);
  border-color: var(--accent, #60a5fa);
}

.lost-badge {
  color: #fbbf24;
  font-size: 12px;
  cursor: help;
}
</style>
