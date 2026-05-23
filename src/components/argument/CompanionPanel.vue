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
          class="run-review-btn"
          :disabled="companion.state.reviewing"
          @click="handleRunReview"
        >
          {{ companion.state.reviewing ? '评审中…' : '红队这篇' }}
        </button>
      </div>

      <!-- Review point list -->
      <div v-if="companion.state.review && companion.state.review.points.length > 0" class="point-list">
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

      <!-- Empty state -->
      <div v-else-if="!companion.state.reviewing" class="reviewer-empty">
        <p class="empty-hint">点击「红队这篇」开始模拟同行评审。</p>
      </div>

      <!-- Loading state -->
      <div v-if="companion.state.reviewing" class="reviewing-hint">
        评审中，每条意见实时出现…
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

const companion = useArgumentCompanion()
const { state: argState } = useArgumentMap()

const agentLinked = computed(() => !!argState.graph?.source_doc)
const activeSubTab = ref<'ledger' | 'reviewer' | 'graph'>('ledger')
const venue = ref<string>('')
const persona = ref<string>('reviewer2')
const reviewMode = ref<'serial' | 'parallel'>('serial')
const importText = ref<string>('')
const experimentSuggestion = ref<string>('')

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
  try {
    const { API_BASE } = await import('../../utils/api')
    const resp = await fetch(
      `${API_BASE}/api/companion/ledger/${encodeURIComponent(companion.state.docId)}/promise/${promiseId}/suggest-experiment`,
      { method: 'POST' },
    )
    if (!resp.ok) return
    const data = await resp.json()
    experimentSuggestion.value = data.suggestion ?? ''
  } catch { /* ignore */ }
}

async function handleDownload() {
  const sid = companion.state.review?.id
  if (!sid) return
  try {
    const { API_BASE } = await import('../../utils/api')
    const url = `${API_BASE}/api/companion/download/review/${sid}`
    const a = document.createElement('a')
    a.href = url
    a.download = 'rebuttal.md'
    a.click()
  } catch { /* ignore */ }
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
  border-bottom: 1px solid var(--border, #2a2a2a);
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
  color: var(--text-dim, #888);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.sub-tab.active {
  color: var(--accent, #60a5fa);
  border-bottom-color: var(--accent, #60a5fa);
}

.sub-tab:hover:not(.active) {
  color: var(--text, #ccc);
}

.stale-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 12px;
  background: #3a2f00;
  color: #fbbf24;
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
  border: 1px solid var(--border, #2a2a2a);
  background: var(--bg-2, #1a1a1a);
  color: var(--text, #ccc);
  border-radius: 3px;
}

.run-review-btn {
  padding: 3px 10px;
  font-size: 11px;
  border-radius: 3px;
  border: 1px solid var(--accent, #60a5fa);
  background: transparent;
  color: var(--accent, #60a5fa);
  cursor: pointer;
  white-space: nowrap;
}

.run-review-btn:hover:not(:disabled) {
  background: var(--accent, #60a5fa);
  color: #000;
}

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
  color: var(--text-dim, #666);
  font-size: 12px;
  text-align: center;
}

.reviewing-hint {
  font-size: 11px;
  color: var(--accent, #60a5fa);
  text-align: center;
  padding: 8px 0;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.import-section {
  flex-shrink: 0;
  padding: 8px;
  border-top: 1px solid var(--border, #2a2a2a);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.import-label {
  font-size: 10px;
  color: var(--text-dim, #666);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.import-textarea {
  font-size: 11px;
  padding: 4px 6px;
  border: 1px solid var(--border, #2a2a2a);
  background: var(--bg-2, #1a1a1a);
  color: var(--text, #ccc);
  border-radius: 3px;
  resize: vertical;
  font-family: inherit;
}

.import-btn {
  align-self: flex-end;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 3px;
  border: 1px solid var(--border, #444);
  background: none;
  color: var(--text-dim, #888);
  cursor: pointer;
}

.import-btn:hover:not(:disabled) {
  color: var(--accent, #60a5fa);
  border-color: var(--accent, #60a5fa);
}

.import-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.point-list-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 4px 8px;
  border-bottom: 1px solid var(--border, #2a2a2a);
  flex-shrink: 0;
}

.download-btn {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid var(--border, #444);
  background: none;
  color: var(--text-dim, #888);
  cursor: pointer;
}

.download-btn:hover {
  color: var(--accent, #60a5fa);
  border-color: var(--accent, #60a5fa);
}

.suggestion-popup {
  position: absolute;
  bottom: 8px;
  left: 8px;
  right: 8px;
  background: var(--bg-2, #1e1e1e);
  border: 1px solid var(--border, #3a3a3a);
  border-radius: 4px;
  z-index: 10;
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
  color: var(--text, #ccc);
  border-bottom: 1px solid var(--border, #333);
  flex-shrink: 0;
}

.suggestion-close {
  background: none;
  border: none;
  color: var(--text-dim, #888);
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
}

.suggestion-body {
  font-size: 11px;
  color: var(--text, #ccc);
  padding: 6px 8px;
  margin: 0;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.5;
}
</style>
