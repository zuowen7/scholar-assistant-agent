<template>
  <div class="ledger-list">
    <div class="ledger-toolbar">
      <button
        class="analyze-btn u-interactive"
        data-analyze-btn
        :disabled="building"
        @click="$emit('analyze')"
      >
        <span v-if="building" class="analyze-loading">
          <span class="al-dots"><i /><i /><i /></span>
          <span class="anim-shimmer-text">分析中</span>
        </span>
        <span v-else>{{ ledger ? '重新分析' : '分析论证账本' }}</span>
      </button>
    </div>

    <!-- 重新分析时的顶部扫描条 -->
    <div v-if="building && ledger" class="anim-scan-bar ledger-scan" />

    <!-- 首次构建中：骨架屏，避免"以为没反应" -->
    <div v-if="building && !ledger" class="ledger-skeleton">
      <div class="sk-status">
        <UiSpinner size="sm" label="AI 正在通读全文，逐条提取承诺" />
      </div>
      <div v-for="i in 4" :key="i" class="sk-row" :style="{ '--stagger-i': i }">
        <UiSkeleton shape="line" width="46px" height="14px" />
        <div class="sk-body">
          <UiSkeleton shape="line" :width="i % 2 ? '92%' : '78%'" height="11px" />
          <UiSkeleton shape="line" width="60%" height="11px" />
        </div>
      </div>
    </div>

    <div v-else-if="!ledger" class="ledger-empty">
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
import UiSkeleton from '../ui/UiSkeleton.vue'
import UiSpinner from '../ui/UiSpinner.vue'

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
  overflow-y: auto;
}

.ledger-toolbar {
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--c-surface-4);
  position: sticky;
  top: 0;
  background: var(--c-surface-1);
  z-index: 1;
}

.analyze-btn {
  font-size: var(--text-sm);
  font-weight: 600;
  padding: var(--space-1) var(--space-4);
  border-radius: var(--radius-control);
  border: 1px solid transparent;
  background: var(--c-accent);
  color: #fff;
  cursor: pointer;
  transition: background .15s var(--ease, ease), opacity .15s ease, transform .1s ease;
}

.analyze-btn:disabled {
  opacity: 0.55;
  cursor: default;
  background: var(--c-surface-3);
  color: var(--c-text-2);
}

.analyze-btn:not(:disabled):hover {
  background: var(--c-accent-hover);
}
.analyze-btn:not(:disabled):active { transform: scale(0.97); }

.ledger-empty {
  padding: var(--space-5) var(--space-4);
  font-size: var(--text-sm);
  color: var(--c-text-2);
  line-height: 1.6;
}

/* 构建中 */
.ledger-scan { margin: 0; }

.ledger-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
}
.sk-status {
  padding: var(--space-1) 0 var(--space-2);
  border-bottom: 1px solid var(--c-surface-3);
}
.sk-row {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  animation: anim-fade-in-up var(--motion-slow) var(--ease-out) both;
  animation-delay: calc(var(--stagger-i, 0) * 90ms);
}
.sk-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* analyze 按钮加载态 */
.analyze-loading { display: inline-flex; align-items: center; gap: var(--space-2); }
.al-dots { display: inline-flex; gap: 3px; }
.al-dots i {
  width: 4px; height: 4px; border-radius: 50%;
  background: currentColor; opacity: 0.4;
  animation: al-breathe 1.2s ease-in-out infinite;
}
.al-dots i:nth-child(2) { animation-delay: 0.15s; }
.al-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes al-breathe {
  0%, 80%, 100% { opacity: 0.35; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1.15); }
}

.ledger-group {
  border-bottom: 1px solid var(--c-surface-3);
}

.group-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3) var(--space-1);
  font-size: var(--text-xs);
  position: sticky;
  top: 0;
}

.group-badge {
  padding: 1px var(--space-2);
  border-radius: var(--radius-xs);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .02em;
}

.badge-unpaid { background: rgba(248,113,113,.16); color: #f87171; }
.badge-mismatch { background: rgba(251,146,60,.16); color: #fb923c; }
.badge-partial { background: rgba(251,191,36,.16); color: #fbbf24; }
.badge-paid { background: rgba(74,222,128,.16); color: #4ade80; }
.badge-unknown { background: var(--c-surface-3); color: var(--c-text-2); }

.group-count {
  color: var(--c-text-3);
  font-size: 10px;
}

.promise-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--c-surface-3);
  transition: background .12s ease;
  animation: promise-in .22s var(--ease, ease) both;
}
.promise-row:hover { background: var(--c-surface-2); }

@keyframes promise-in {
  from { opacity: 0; transform: translateY(3px); }
  to { opacity: 1; transform: translateY(0); }
}

.promise-left {
  flex-shrink: 0;
  padding-top: 2px;
}

.kind-chip {
  font-size: 9px;
  padding: 1px var(--space-1);
  border-radius: var(--radius-xs);
  background: var(--c-surface-3);
  color: var(--c-text-2);
  white-space: nowrap;
}

.promise-body {
  flex: 1;
  min-width: 0;
}

.promise-text {
  display: block;
  font-size: var(--text-xs);
  color: var(--c-text-1);
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  text-align: left;
  width: 100%;
  line-height: 1.5;
  transition: color .12s ease;
}

.promise-text:hover {
  color: var(--c-accent);
  text-decoration: underline;
}

.promise-note {
  font-size: 10px;
  color: var(--c-text-2);
  margin-top: 2px;
  font-style: italic;
  line-height: 1.45;
}

.promise-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.jump-btn, .suggest-btn {
  font-size: 10px;
  padding: 2px var(--space-2);
  border-radius: var(--radius-xs);
  border: 1px solid var(--c-surface-4);
  background: none;
  color: var(--c-text-2);
  cursor: pointer;
  white-space: nowrap;
  transition: color .12s ease, border-color .12s ease, background .12s ease;
}

.jump-btn:hover, .suggest-btn:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}

.lost-badge {
  color: #fbbf24;
  font-size: var(--text-sm);
  cursor: help;
}
</style>
