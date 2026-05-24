<template>
  <div class="companion-panel">
    <!-- Sub-tab bar -->
    <div class="sub-tab-bar">
      <button
        class="sub-tab"
        :class="{ active: activeSubTab === 'ledger' }"
        @click="activeSubTab = 'ledger'"
      >
        论证账本
      </button>
      <button
        class="sub-tab"
        :class="{ active: activeSubTab === 'reviewer' }"
        @click="activeSubTab = 'reviewer'"
      >
        Reviewer 2
      </button>
      <button
        class="sub-tab"
        :class="{ active: activeSubTab === 'graph' }"
        @click="activeSubTab = 'graph'"
      >
        论证图
      </button>
    </div>

    <!-- Agent link status -->
    <div v-if="agentLinked" class="agent-link-bar">
      <span class="agent-link-dot"></span>
      <span>论证图已关联文档，Agent 可读取</span>
    </div>

    <!-- Staleness banner -->
    <div v-if="companion.state.ledgerStale" class="stale-banner">
      草稿已改，可能过期
      <button class="reanalyze-btn" @click="handleAnalyze">重新分析</button>
    </div>

    <!-- Ledger sub-page -->
    <div v-if="activeSubTab === 'ledger'" class="sub-page">
      <LedgerList
        :ledger="companion.state.ledger"
        :building="companion.state.building"
        :suggesting-id="suggestingId"
        @analyze="handleAnalyze"
        @focus-anchor="companion.focusAnchor"
        @suggest-experiment="handleSuggestExperiment"
      />
      <!-- Experiment suggestion popup -->
      <div v-if="experimentSuggestion" class="suggestion-popup">
        <div class="suggestion-header">
          实验设计建议
          <button class="suggestion-close" @click="experimentSuggestion = ''">✕</button>
        </div>
        <pre class="suggestion-body">{{ experimentSuggestion }}</pre>
      </div>
    </div>

    <!-- Toulmin graph sub-page -->
    <div v-else-if="activeSubTab === 'graph'" class="sub-page">
      <ArgumentMapMini :content="content" />
    </div>

    <!-- Reviewer 2 sub-page (Phase 3) -->
    <div v-else class="sub-page reviewer-page">
      <!-- Venue + persona controls -->
      <div class="reviewer-controls">
        <select v-model="venue" class="ctrl-select">
          <option value="">通用 (Generic)</option>
          <option value="NeurIPS">NeurIPS</option>
          <option value="ICML">ICML</option>
          <option value="ICLR">ICLR</option>
          <option value="ACL">ACL</option>
          <option value="CVPR">CVPR</option>
          <option value="KDD">KDD</option>
          <option value="CHI">CHI</option>
        </select>
        <select v-model="persona" class="ctrl-select">
          <option value="reviewer2">Reviewer 2 (苛刻)</option>
          <option value="ac">AC (均衡)</option>
          <option value="domain_expert">领域专家</option>
          <option value="friendly">友好评审</option>
        </select>
        <select v-model="reviewMode" class="ctrl-select">
          <option value="serial">单角度</option>
          <option value="parallel">三角度并行</option>
        </select>
        <button
          class="run-review-btn u-interactive"
          :disabled="companion.state.reviewing"
          @click="handleRunReview"
        >
          <span v-if="companion.state.reviewing" class="rv-loading">
            <span class="rv-dots"><i /><i /><i /></span>
            <span class="anim-shimmer-text">评审中</span>
          </span>
          <span v-else>红队这篇</span>
        </button>
      </div>

      <!-- Review point list -->
      <div v-if="companion.state.review && companion.state.review.points.length > 0" class="point-list">
        <div v-if="companion.state.reviewing" class="anim-scan-bar point-list-scan" />
        <div class="point-list-toolbar">
          <button
            v-if="companion.state.review?.id"
            class="download-btn"
            @click="handleDownload"
          >
            ↓ 导出 rebuttal
          </button>
        </div>
        <ReviewerThread
          v-for="point in companion.state.review.points"
          :key="point.id"
          :point="point"
          :rebuttal-sending="companion.state.rebuttalSending"
          :content="props.content"
          @focus-anchor="companion.focusAnchor"
          @update-point-status="(s) => updatePointStatus(point.id, s)"
          @rebut="(pid, msg) => handleRebut(pid, msg)"
        />
      </div>

      <!-- 评审中且尚无意见：骨架卡片 + 状态提示 -->
      <div v-else-if="companion.state.reviewing" class="reviewing-block">
        <div class="anim-scan-bar" />
        <div class="reviewing-status">
          <UiSpinner size="sm" :label="reviewMode === 'parallel' ? '三位审稿人正在并行通读' : 'Reviewer 2 正在逐段审阅'" />
        </div>
        <div v-for="i in 3" :key="i" class="rv-sk-card" :style="{ '--stagger-i': i }">
          <UiSkeleton shape="line" width="30%" height="11px" />
          <UiSkeleton shape="line" width="94%" height="11px" />
          <UiSkeleton shape="line" width="70%" height="11px" />
        </div>
      </div>

      <!-- Empty state -->
      <div v-else class="reviewer-empty">
        <p class="empty-hint">点击「红队这篇」开始模拟同行评审。</p>
      </div>

      <!-- Import real reviews section -->
      <div class="import-section">
        <div class="import-label">导入真实审稿意见</div>
        <textarea
          v-model="importText"
          class="import-textarea"
          data-import-textarea
          placeholder="粘贴真实审稿意见…"
          rows="4"
        />
        <button
          class="import-btn"
          data-import-btn
          :disabled="!importText.trim() || companion.state.reviewing"
          @click="handleImportReviews"
        >
          {{ companion.state.reviewing ? '导入中…' : '导入审稿意见' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useArgumentCompanion } from '../../composables/useArgumentCompanion'
import { useArgumentMap } from '../../composables/useArgumentMap'
import LedgerList from './LedgerList.vue'
import ReviewerThread from './ReviewerThread.vue'
import ArgumentMapMini from './ArgumentMapMini.vue'
import UiSpinner from '../ui/UiSpinner.vue'
import UiSkeleton from '../ui/UiSkeleton.vue'

const companion = useArgumentCompanion()
const { state: argState } = useArgumentMap()

const agentLinked = computed(() => !!argState.graph?.source_doc)
const activeSubTab = ref<'ledger' | 'reviewer' | 'graph'>('ledger')
const venue = ref<string>('')
const persona = ref<string>('reviewer2')
const reviewMode = ref<'serial' | 'parallel'>('serial')
const importText = ref<string>('')
const experimentSuggestion = ref<string>('')
const suggestingId = ref<string>('')

const props = defineProps<{
  content: string
}>()

async function handleAnalyze() {
  console.log('[companion] handleAnalyze called, content length:', props.content?.length ?? 0)
  await companion.buildOrRebuildLedger(props.content)
}

async function handleRunReview() {
  await companion.runReview(props.content, venue.value || null, persona.value, reviewMode.value)
}

async function handleImportReviews() {
  const raw = importText.value.trim()
  if (!raw) return
  await companion.importReviews(raw, props.content)
  importText.value = ''
}

async function handleRebut(pointId: string, message: string) {
  await companion.rebut(pointId, message, props.content)
}

async function handleSuggestExperiment(promiseId: string) {
  const ledger = companion.state.ledger
  if (!ledger) return
  const promise = ledger.promises.find(p => p.id === promiseId)
  if (!promise) return
  suggestingId.value = promiseId
  try {
    const { API_BASE } = await import('../../utils/api')
    const resp = await fetch(
      `${API_BASE}/api/companion/ledger/promise/${promiseId}/suggest-experiment?doc_id=${encodeURIComponent(companion.state.docId)}`,
      { method: 'POST' },
    )
    if (!resp.ok) return
    const data = await resp.json()
    experimentSuggestion.value = data.suggestion ?? ''
  } catch { /* ignore */ } finally {
    suggestingId.value = ''
  }
}

async function handleDownload() {
  const sid = companion.state.review?.id
  if (!sid) return
  try {
    const { API_BASE } = await import('../../utils/api')
    const url = `${API_BASE}/api/companion/download/review/${sid}`
    const resp = await fetch(url)
    if (!resp.ok) {
      const { useToast } = await import('../../composables/useToast')
      useToast().pushError(`导出 rebuttal 失败（${resp.status}）`)
      return
    }
    const blob = await resp.blob()
    const { saveBlob } = await import('../../composables/useEditorIO')
    await saveBlob(blob, `rebuttal_${sid.slice(0, 8)}.md`)
  } catch (e) {
    console.error('[companion] download failed:', e)
    const { useToast } = await import('../../composables/useToast')
    useToast().pushError('导出 rebuttal 失败，请重试')
  }
}

async function updatePointStatus(pointId: string, status: string) {
  if (!companion.state.review) return
  const sid = companion.state.review.id
  if (!sid) return
  try {
    const { API_BASE } = await import('../../utils/api')
    await fetch(`${API_BASE}/api/companion/review/${sid}/point/${pointId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    const point = companion.state.review.points.find(p => p.id === pointId)
    if (point) point.status = status as typeof point.status
  } catch { /* ignore network errors */ }
}
</script>

<style scoped>
.companion-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  font-size: 12px;
}

.sub-tab-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
}

.agent-link-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 10px;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.07);
  border-bottom: 1px solid rgba(74, 222, 128, 0.14);
  flex-shrink: 0;
}

.agent-link-dot {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  flex-shrink: 0;
}
.agent-link-dot::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1.5px solid #4ade80;
  animation: sonar-ring 1.8s ease-out infinite;
}
@keyframes sonar-ring {
  0%   { transform: scale(1);   opacity: 0.7; }
  100% { transform: scale(2.6); opacity: 0; }
}

.sub-tab {
  flex: 1;
  padding: 6px 8px;
  font-size: 11px;
  border: none;
  background: none;
  color: var(--c-text-2);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color var(--motion-fast) var(--ease-out), border-color var(--motion-base) var(--ease-out), background var(--motion-fast) ease;
}

.sub-tab.active {
  color: var(--c-accent);
  border-bottom-color: var(--c-accent);
}

.sub-tab:hover:not(.active) {
  color: var(--c-text-1);
  background: var(--c-surface-2);
}

.stale-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: var(--c-warn-bg);
  color: var(--c-warn);
  font-size: 11px;
  flex-shrink: 0;
}

.reanalyze-btn {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #fbbf24;
  background: none;
  color: #fbbf24;
  cursor: pointer;
}

.sub-page {
  flex: 1;
  overflow-y: auto;
  position: relative;
}

.reviewer-page {
  display: flex;
  flex-direction: column;
  padding: 8px;
}

.reviewer-controls {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.ctrl-select {
  flex: 1;
  min-width: 80px;
  padding: 3px 6px;
  font-size: 11px;
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-1);
  border-radius: 3px;
}

.run-review-btn {
  padding: 3px 10px;
  font-size: 11px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--c-accent);
  background: transparent;
  color: var(--c-accent);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out), color var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-brush);
}

.run-review-btn:hover:not(:disabled) {
  background: var(--c-accent);
  color: #fff;
}
.run-review-btn:active:not(:disabled) { transform: scale(0.96); }

.run-review-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.point-list {
  flex: 1;
  overflow-y: auto;
}

.reviewer-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
}

.empty-hint {
  color: var(--c-text-3);
  font-size: 12px;
  text-align: center;
}

/* 评审加载态 */
.rv-loading { display: inline-flex; align-items: center; gap: var(--space-2); }
.rv-dots { display: inline-flex; gap: 3px; }
.rv-dots i {
  width: 4px; height: 4px; border-radius: 50%;
  background: currentColor; opacity: 0.4;
  animation: al-breathe 1.2s ease-in-out infinite;
}
.rv-dots i:nth-child(2) { animation-delay: 0.15s; }
.rv-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes al-breathe {
  0%, 80%, 100% { opacity: 0.35; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1.15); }
}

.reviewing-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  overflow-y: auto;
}
.reviewing-status { padding: var(--space-1) 0; }
.rv-sk-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  background: var(--c-surface-1);
  animation: anim-fade-in-up var(--motion-slow) var(--ease-out) both;
  animation-delay: calc(var(--stagger-i, 0) * 110ms);
}
.point-list-scan { flex-shrink: 0; }

.import-section {
  flex-shrink: 0;
  padding: 8px;
  border-top: 1px solid var(--c-surface-3);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.import-label {
  font-size: 10px;
  color: var(--c-text-3);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.import-textarea {
  font-size: 11px;
  padding: 4px 6px;
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-1);
  border-radius: 3px;
  resize: vertical;
  font-family: inherit;
}

.import-btn {
  align-self: flex-end;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--c-surface-4);
  background: none;
  color: var(--c-text-2);
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out), border-color var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-brush);
}
.import-btn:active:not(:disabled) { transform: scale(0.96); }

.import-btn:hover:not(:disabled) {
  color: var(--c-accent);
  border-color: var(--c-accent);
}

.import-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.point-list-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
}

.download-btn {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--c-surface-4);
  background: none;
  color: var(--c-text-2);
  cursor: pointer;
  transition: color var(--motion-fast) var(--ease-out), border-color var(--motion-fast) var(--ease-out), background var(--motion-fast) ease, transform var(--motion-fast) var(--ease-brush);
}

.download-btn:hover {
  color: var(--c-accent);
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}
.download-btn:active { transform: scale(0.95); }

.suggestion-popup {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-4);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-3, 0 8px 24px rgba(0,0,0,0.3));
  z-index: 10;
  animation: anim-fade-in-up var(--motion-base) var(--ease-spring) both;
  max-height: 200px;
  display: flex;
  flex-direction: column;
}

.suggestion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-1);
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
}

.suggestion-close {
  background: none;
  border: none;
  color: var(--c-text-2);
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
}

.suggestion-body {
  font-size: 11px;
  color: var(--c-text-1);
  padding: 6px 8px;
  margin: 0;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}
</style>
