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
        <button
          class="status-chip"
          data-status-btn
          :class="`chip-${point.status}`"
          @click="toggleStatusMenu"
        >
          {{ statusLabel }}
          <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor" class="chip-caret">
            <path d="M0 2.5 L4 6.5 L8 2.5Z" />
          </svg>
        </button>
        <div v-if="showMenu" class="status-menu">
          <button
            v-for="opt in statusOptions"
            :key="opt.value"
            class="menu-item"
            :class="{ active: opt.value === point.status }"
            @click="setStatus(opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Title -->
    <div class="card-title">{{ point.title }}</div>

    <!-- Detail -->
    <div class="card-detail" :class="{ collapsed: !detailExpanded && point.detail.length > 200 }">
      {{
        detailExpanded || point.detail.length <= 200
          ? point.detail
          : point.detail.slice(0, 200) + '…'
      }}
    </div>
    <button
      v-if="point.detail.length > 200"
      class="expand-btn"
      @click="detailExpanded = !detailExpanded"
    >
      {{ detailExpanded ? t('reviewerThread.collapse') : t('reviewerThread.expandFull') }}
    </button>

    <!-- Anchor -->
    <button
      v-if="point.anchor_id"
      class="anchor-btn"
      data-anchor-btn
      @click="$emit('focusAnchor', point.anchor_id!)"
    >
      <span class="anchor-label">{{ t('reviewerThread.anchorSource') }}</span>
      <span class="anchor-quote">“{{ anchorQuote || t('reviewerThread.locateText') }}”</span>
      <span class="anchor-jump">{{ t('reviewerThread.locate') }}</span>
    </button>

    <!-- Thread -->
    <div v-if="point.thread.length > 0" class="thread-list">
      <div
        v-for="turn in point.thread"
        :key="turn.id"
        class="thread-turn"
        :class="`turn-${turn.role}`"
      >
        <span class="turn-role">{{
          turn.role === 'author' ? t('reviewerThread.author') : t('reviewerThread.reviewer')
        }}</span>
        <span class="turn-text">{{
          isExpanded(turn.id) || turn.text.length <= 280 ? turn.text : turn.text.slice(0, 280) + '…'
        }}</span>
        <button v-if="turn.text.length > 280" class="turn-expand-btn" @click="toggleTurn(turn.id)">
          {{ isExpanded(turn.id) ? t('reviewerThread.collapse') : t('reviewerThread.expandFull') }}
        </button>
      </div>
    </div>

    <!-- Rebuttal input -->
    <div class="rebuttal-area">
      <div v-if="isSending" class="rebut-sending">
        <span class="dot-wave"><i></i><i></i><i></i></span>
        <span class="sending-text">{{ t('reviewerThread.thinking') }}</span>
      </div>
      <template v-else-if="canRebut">
        <button
          v-if="!chatExpanded"
          class="rebut-toggle"
          data-rebut-btn
          @click="chatExpanded = true"
        >
          {{ t('reviewerThread.rebut') }}
        </button>
        <div v-else class="rebut-input-wrap">
          <textarea
            v-model="rebuttalText"
            class="rebut-input"
            data-rebut-input
            :placeholder="t('reviewerThread.rebutPlaceholder')"
            rows="3"
          />
          <div class="rebut-actions">
            <button class="rebut-cancel" @click="chatExpanded = false">
              {{ t('reviewerThread.rebuteCancel') }}
            </button>
            <button
              class="rebut-send"
              data-rebut-send
              :disabled="!rebuttalText.trim()"
              @click="sendRebuttal"
            >
              {{ t('reviewerThread.rebutSend') }}
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import type { ReviewPoint, PointStatus } from '../../types'
import { useArgumentCompanion } from '../../composables/useArgumentCompanion'

const props = defineProps<{
  point: ReviewPoint
  rebuttalSending?: string
}>()
const companion = useArgumentCompanion()
const anchorQuote = computed(() => {
  if (!props.point.anchor_id) return ''
  const anchors = [
    ...(companion.state.review?.anchors ?? []),
    ...(companion.state.ledger?.anchors ?? []),
  ]
  return anchors.find((anchor) => anchor.id === props.point.anchor_id)?.quote || ''
})

const emit = defineEmits<{
  focusAnchor: [anchorId: string]
  updatePointStatus: [status: PointStatus]
  rebut: [pointId: string, message: string]
}>()

const chatExpanded = ref(false)
const rebuttalText = ref('')
const detailExpanded = ref(false)
const showMenu = ref(false)
const statusWrapRef = ref<HTMLElement>()
const expandedTurnIds = ref<Set<string>>(new Set())

function isExpanded(id: string) {
  return expandedTurnIds.value.has(id)
}
function toggleTurn(id: string) {
  const s = new Set(expandedTurnIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedTurnIds.value = s
}

const isSending = computed(() => props.rebuttalSending === props.point.id)

// Can rebut unless status is accepted or dismissed
const canRebut = computed(
  () => props.point.status !== 'accepted' && props.point.status !== 'dismissed',
)

const categoryLabel = computed(() =>
  t(`argument.reviewCategory.${props.point.category}`, props.point.category),
)
const statusLabel = computed(() => t(`argument.status.${props.point.status}`, props.point.status))
const sourceLabel = computed(() =>
  props.point.source === 'llm'
    ? 'AI'
    : t(`argument.checkType.${props.point.source}`, props.point.source),
)

const statusOptions = computed(() => {
  const all: { value: PointStatus; label: string }[] = [
    { value: 'open', label: t('argument.status.open') },
    { value: 'rebutted', label: t('argument.status.rebutted') },
    { value: 'accepted', label: t('argument.status.accepted') },
    { value: 'dismissed', label: t('argument.status.dismissed') },
  ]
  return all.filter((o) => o.value !== props.point.status)
})

function toggleStatusMenu() {
  showMenu.value = !showMenu.value
}

function setStatus(status: PointStatus) {
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
  border: 1px solid var(--c-border);
  border-left: 4px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-panel);
  margin-bottom: 14px;
  padding: 17px 18px 14px;
  animation: card-enter 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

@keyframes card-enter {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.sev-fatal {
  border-left-color: var(--c-danger);
}
.sev-major {
  border-left-color: var(--c-warn);
}
.sev-minor {
  border-left-color: color-mix(in srgb, var(--c-accent) 70%, transparent);
}
.sev-info {
  border-left-color: var(--c-border);
}

/* ── Header ── */
.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.sev-pip {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pip-fatal {
  background: var(--c-danger);
}
.pip-major {
  background: var(--c-warn);
}
.pip-minor {
  background: var(--c-accent);
  opacity: 0.7;
}
.pip-info {
  background: var(--c-text-3);
}

.card-category {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--c-text-2);
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--c-surface-2);
}

.card-source {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--c-surface-2);
  color: var(--c-text-3);
}
.src-ledger_check {
  color: color-mix(in srgb, var(--c-accent) 80%, #fff);
}
.src-scoped {
  color: var(--c-warn);
}

.header-spacer {
  flex: 1;
}

/* ── Status chip ── */
.status-wrap {
  position: relative;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  font-weight: 600;
  padding: 5px 9px;
  border-radius: 12px;
  border: 1px solid var(--c-border);
  background: var(--c-surface-2);
  color: var(--c-text-2);
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s;
}
.status-chip:hover {
  border-color: var(--c-accent);
  color: var(--c-accent);
}
.status-chip:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.chip-caret {
  opacity: 0.5;
  flex-shrink: 0;
}

.chip-rebutted {
  border-color: rgba(34, 197, 94, 0.27);
  color: var(--c-success);
  background: var(--c-success-bg);
}
.chip-accepted {
  border-color: rgba(59, 130, 246, 0.27);
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
.chip-dismissed {
  border-color: rgba(85, 85, 85, 0.27);
  color: var(--c-text-3);
}

.status-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: 6px;
  overflow: hidden;
  z-index: 50;
  min-width: 90px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  font-size: 11px;
  color: var(--c-text-2);
  background: none;
  border: none;
  cursor: pointer;
  transition: background 0.1s;
}
.menu-item:hover,
.menu-item.active {
  background: var(--c-surface-3);
  color: var(--c-text-0);
}

/* ── Content ── */
.card-title {
  font-size: 15px;
  font-weight: 650;
  color: var(--c-text-0);
  margin-bottom: 8px;
  line-height: 1.4;
}

.card-detail {
  font-size: 13px;
  color: var(--c-text-1);
  line-height: 1.7;
  margin-bottom: 12px;
}

.expand-btn {
  font-size: 11px;
  color: var(--c-accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-bottom: 6px;
}

.anchor-btn {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: var(--c-text-2);
  background: var(--c-surface-2);
  border: 1px solid var(--c-border);
  border-radius: 8px;
  cursor: pointer;
  padding: 9px 11px;
  margin-bottom: 8px;
  text-align: left;
  transition: color 0.15s;
}
.anchor-btn:hover {
  color: var(--c-accent);
}
.anchor-label {
  color: var(--c-text-3);
  font-weight: 650;
}
.anchor-quote {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.anchor-jump {
  color: var(--c-accent);
}

/* ── Thread ── */
.thread-list {
  border: 1px solid var(--c-border);
  border-radius: 8px;
  margin-top: 10px;
  padding: 10px 12px;
  background: var(--c-surface-2);
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
.turn-author .turn-role {
  color: var(--c-accent);
}
.turn-reviewer .turn-role {
  color: var(--c-warn);
}

.turn-text {
  color: var(--c-text-1);
  line-height: 1.5;
  flex: 1;
}

.turn-expand-btn {
  font-size: 10px;
  color: var(--c-accent);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-top: 2px;
  display: block;
}

/* ── Rebuttal area ── */
.rebuttal-area {
  margin-top: 8px;
}

.rebut-sending {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.sending-text {
  font-size: 11px;
  color: var(--c-text-2);
  font-style: italic;
}

.dot-wave {
  display: flex;
  gap: 4px;
  align-items: center;
}
.dot-wave i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-accent);
  display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) {
  animation-delay: 0.18s;
}
.dot-wave i:nth-child(3) {
  animation-delay: 0.36s;
}
@keyframes wave-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.25;
  }
  30% {
    transform: translateY(-5px);
    opacity: 1;
  }
}

.rebut-toggle {
  font-size: 11px;
  color: var(--c-text-2);
  background: none;
  border: 1px dashed var(--c-border);
  border-radius: 4px;
  padding: 3px 10px;
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s;
}
.rebut-toggle:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
}
.rebut-toggle:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
}

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
  border: 1px solid var(--c-border);
  border-radius: 6px;
  background: var(--c-surface-2);
  color: var(--c-text-0);
  resize: vertical;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  transition:
    border-color var(--motion-fast) var(--ease-out),
    box-shadow var(--motion-fast) var(--ease-out);
}
.rebut-input:focus-visible {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}

.rebut-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.rebut-cancel {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid var(--c-border);
  background: none;
  color: var(--c-text-3);
  cursor: pointer;
  transition:
    color var(--motion-fast) var(--ease-out),
    border-color var(--motion-fast) var(--ease-out);
}
.rebut-cancel:hover {
  color: var(--c-text-0);
  border-color: var(--c-text-3);
}
.rebut-cancel:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}

.rebut-send {
  font-size: 11px;
  padding: 3px 12px;
  border-radius: 4px;
  border: none;
  background: var(--c-accent);
  color: var(--c-on-accent);
  cursor: pointer;
  transition:
    filter var(--motion-fast) var(--ease-out),
    transform var(--motion-fast) var(--ease-out);
}
.rebut-send:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.rebut-send:not(:disabled):hover {
  filter: brightness(1.08);
}
.rebut-send:not(:disabled):active {
  transform: scale(0.97);
}
.rebut-send:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}

/* Consistent keyboard focus ring across all interactive elements in the card */
.anchor-btn:focus-visible,
.rebut-toggle:focus-visible,
.expand-btn:focus-visible,
.turn-expand-btn:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
</style>
