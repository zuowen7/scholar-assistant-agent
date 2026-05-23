<template>
  <div class="review-card" :class="`sev-${point.severity}`">
    <!-- Header -->
    <div class="card-header">
      <span class="sev-pip" :class="`pip-${point.severity}`"></span>
      <span class="card-category">{{ categoryLabel }}</span>
      <span class="card-source" :class="`src-${point.source}`">{{ sourceLabel }}</span>
      <div class="header-spacer"></div>
      <!-- Status selector -->
      <div class="status-wrap" ref="statusWrapRef">
        <button class="status-chip" data-status-btn :class="`chip-${point.status}`" @click="toggleStatusMenu">
          {{ STATUS_LABEL[point.status] }}
          <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" class="chip-caret">
            <path d="M0 2.5 L4 6.5 L8 2.5Z"/>
          </svg>
        </button>
        <div v-if="showMenu" class="status-menu">
          <button
            v-for="opt in statusOptions"
            :key="opt.value"
            class="menu-item"
            :class="{ active: opt.value === point.status }"
            @click="setStatus(opt.value)"
          >{{ opt.label }}</button>
        </div>
      </div>
    </div>

    <!-- Title -->
    <div class="card-title">{{ point.title }}</div>

    <!-- Detail -->
    <div class="card-detail" :class="{ collapsed: !detailExpanded && point.detail.length > 200 }">
      {{ detailExpanded || point.detail.length <= 200 ? point.detail : point.detail.slice(0, 200) + '…' }}
    </div>
    <button
      v-if="point.detail.length > 200"
      class="expand-btn"
      @click="detailExpanded = !detailExpanded"
    >{{ detailExpanded ? '收起' : '展开全文' }}</button>

    <!-- Anchor -->
    <button
      v-if="point.anchor_id"
      class="anchor-btn"
      data-anchor-btn
      @click="$emit('focusAnchor', point.anchor_id!)"
    >
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M4 8h8M10 5l3 3-3 3"/>
      </svg>
      定位原文
    </button>

    <!-- Thread -->
    <div v-if="point.thread.length > 0" class="thread-list">
      <div
        v-for="turn in point.thread"
        :key="turn.id"
        class="thread-turn"
        :class="`turn-${turn.role}`"
      >
        <span class="turn-role">{{ turn.role === 'author' ? '作者' : 'Reviewer' }}</span>
        <span class="turn-text">{{ turn.text }}</span>
      </div>
    </div>

    <!-- Rebuttal input -->
    <div class="rebuttal-area">
      <div v-if="isSending" class="rebut-sending">
        <span class="dot-wave"><i></i><i></i><i></i></span>
        <span class="sending-text">Reviewer 思考中…</span>
      </div>
      <template v-else-if="canRebut">
        <button
          v-if="!chatExpanded"
          class="rebut-toggle"
          @click="chatExpanded = true"
        >+ 反驳</button>
        <div v-else class="rebut-input-wrap">
          <textarea
            v-model="rebuttalText"
            class="rebut-input"
            placeholder="写下你的反驳理由…"
            rows="3"
          />
          <div class="rebut-actions">
            <button class="rebut-cancel" @click="chatExpanded = false">取消</button>
            <button
              class="rebut-send"
              :disabled="!rebuttalText.trim()"
              @click="sendRebuttal"
            >发送</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { ReviewPoint } from '../../types'

const props = defineProps<{
  point: ReviewPoint
  rebuttalSending?: string
}>()

const emit = defineEmits<{
  focusAnchor: [anchorId: string]
  updatePointStatus: [status: string]
  rebut: [pointId: string, message: string]
}>()

const chatExpanded = ref(false)
const rebuttalText = ref('')
const detailExpanded = ref(false)
const showMenu = ref(false)
const statusWrapRef = ref<HTMLElement>()

const isSending = computed(() => props.rebuttalSending === props.point.id)

// Can rebut unless status is accepted or dismissed
const canRebut = computed(() =>
  props.point.status !== 'accepted' && props.point.status !== 'dismissed'
)

const CATEGORY_LABEL: Record<string, string> = {
  motivation: '动机',
  novelty: '创新性',
  baseline: '基线',
  ablation: '消融实验',
  soundness: '可靠性',
  claim_overreach: '声称过度',
  missing_related_work: '相关工作',
  reproducibility: '可复现',
  experiment_design: '实验设计',
  writing_clarity: '写作清晰度',
  inconsistency: '内部矛盾',
  gap_mismatch: '差距不符',
  weak_positioning: '定位偏弱',
  term_drift: '术语漂移',
  other: '其他',
}

const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  rebutted: '已反驳',
  accepted: '已认可',
  dismissed: '已忽略',
}

const SOURCE_LABEL: Record<string, string> = {
  llm: 'AI',
  ledger_check: '账本核查',
  coherence_check: '一致性',
  rw_check: '相关工作',
  scoped: '局部质疑',
  imported: '导入',
}

const categoryLabel = computed(() => CATEGORY_LABEL[props.point.category] ?? props.point.category)
const sourceLabel = computed(() => SOURCE_LABEL[props.point.source] ?? props.point.source)

const statusOptions = computed(() => {
  const all = [
    { value: 'open', label: '待处理' },
    { value: 'rebutted', label: '已反驳' },
    { value: 'accepted', label: '已认可' },
    { value: 'dismissed', label: '已忽略' },
  ]
  return all.filter(o => o.value !== props.point.status)
})

function toggleStatusMenu() {
  showMenu.value = !showMenu.value
}

function setStatus(status: string) {
  showMenu.value = false
  emit('updatePointStatus', status)
}

function sendRebuttal() {
  const msg = rebuttalText.value.trim()
  if (!msg) return
  emit('rebut', props.point.id, msg)
  rebuttalText.value = ''
  chatExpanded.value = false
}

function onClickOutside(e: MouseEvent) {
  if (statusWrapRef.value && !statusWrapRef.value.contains(e.target as Node)) {
    showMenu.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onUnmounted(() => document.removeEventListener('mousedown', onClickOutside))
</script>

<style scoped>
.review-card {
  position: relative;
  border-left: 3px solid var(--c-border, #333);
  border-radius: 0 8px 8px 0;
  background: var(--c-surface-1, #181818);
  margin-bottom: 8px;
  padding: 10px 12px 8px;
  animation: card-enter 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes card-enter {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.sev-fatal { border-left-color: var(--c-error, #ef4444); }
.sev-major { border-left-color: var(--c-warning, #f59e0b); }
.sev-minor { border-left-color: color-mix(in srgb, var(--c-accent) 70%, transparent); }
.sev-info  { border-left-color: var(--c-border, #333); }

/* ── Header ── */
.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.sev-pip {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pip-fatal { background: var(--c-error, #ef4444); }
.pip-major { background: var(--c-warning, #f59e0b); }
.pip-minor { background: var(--c-accent, #6366f1); opacity: 0.7; }
.pip-info  { background: var(--c-text-3, #555); }

.card-category {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--c-text-2, #888);
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--c-surface-2, #232323);
}

.card-source {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--c-surface-2, #232323);
  color: var(--c-text-3, #666);
}
.src-ledger_check { color: color-mix(in srgb, var(--c-accent) 80%, #fff); }
.src-scoped       { color: var(--c-warning, #f59e0b); }

.header-spacer { flex: 1; }

/* ── Status chip ── */
.status-wrap { position: relative; }

.status-chip {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 12px;
  border: 1px solid var(--c-border, #333);
  background: var(--c-surface-2, #232323);
  color: var(--c-text-2, #999);
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s;
}
.status-chip:hover { border-color: var(--c-accent, #6366f1); color: var(--c-accent, #6366f1); }
.chip-caret { opacity: 0.5; flex-shrink: 0; }

.chip-rebutted  { border-color: #22c55e44; color: #4ade80; background: #0f2a1a; }
.chip-accepted  { border-color: #3b82f644; color: #60a5fa; background: #0f1e2e; }
.chip-dismissed { border-color: #55555544; color: #888; }

.status-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: var(--c-surface-2, #1e1e1e);
  border: 1px solid var(--c-border, #333);
  border-radius: 6px;
  overflow: hidden;
  z-index: 50;
  min-width: 90px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}

.menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--c-text-2, #bbb);
  background: none;
  border: none;
  cursor: pointer;
  transition: background 0.1s;
}
.menu-item:hover, .menu-item.active { background: var(--c-surface-3, #2a2a2a); color: var(--c-text, #e5e7eb); }

/* ── Content ── */
.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text, #e5e7eb);
  margin-bottom: 5px;
  line-height: 1.4;
}

.card-detail {
  font-size: 12px;
  color: var(--c-text-2, #9ca3af);
  line-height: 1.6;
  margin-bottom: 6px;
}

.expand-btn {
  font-size: 11px;
  color: var(--c-accent, #6366f1);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 6px;
}

.anchor-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--c-text-3, #666);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 4px;
  transition: color 0.15s;
}
.anchor-btn:hover { color: var(--c-accent, #6366f1); }

/* ── Thread ── */
.thread-list {
  border-top: 1px solid var(--c-border, #2a2a2a);
  margin-top: 8px;
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.thread-turn {
  display: flex;
  gap: 8px;
  font-size: 12px;
  align-items: flex-start;
}

.turn-role {
  font-weight: 600;
  font-size: 10px;
  min-width: 46px;
  padding-top: 2px;
  flex-shrink: 0;
}
.turn-author .turn-role { color: var(--c-accent, #6366f1); }
.turn-reviewer .turn-role { color: var(--c-warning, #f59e0b); }

.turn-text {
  color: var(--c-text-2, #ccc);
  line-height: 1.5;
  flex: 1;
}

/* ── Rebuttal area ── */
.rebuttal-area { margin-top: 8px; }

.rebut-sending {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.sending-text { font-size: 11px; color: var(--c-text-3, #777); font-style: italic; }

.dot-wave { display: flex; gap: 4px; align-items: center; }
.dot-wave i {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--c-accent, #6366f1); display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes wave-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.25; }
  30%            { transform: translateY(-5px); opacity: 1; }
}

.rebut-toggle {
  font-size: 11px;
  color: var(--c-text-3, #666);
  background: none;
  border: 1px dashed var(--c-border, #333);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.rebut-toggle:hover { color: var(--c-accent, #6366f1); border-color: var(--c-accent, #6366f1); }

.rebut-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.rebut-input {
  width: 100%;
  box-sizing: border-box;
  font-size: 12px;
  padding: 8px 10px;
  border: 1px solid var(--c-border, #333);
  border-radius: 6px;
  background: var(--c-surface-2, #222);
  color: var(--c-text, #e5e7eb);
  resize: vertical;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.15s;
}
.rebut-input:focus { border-color: var(--c-accent, #6366f1); }

.rebut-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.rebut-cancel {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid var(--c-border, #333);
  background: none;
  color: var(--c-text-3, #777);
  cursor: pointer;
}
.rebut-cancel:hover { color: var(--c-text, #ccc); }

.rebut-send {
  font-size: 11px;
  padding: 3px 12px;
  border-radius: 4px;
  border: none;
  background: var(--c-accent, #6366f1);
  color: #fff;
  cursor: pointer;
  transition: opacity 0.15s;
}
.rebut-send:disabled { opacity: 0.35; cursor: not-allowed; }
.rebut-send:not(:disabled):hover { opacity: 0.85; }
</style>
