<template>
  <div class="reviewer-workspace">
    <nav class="review-surface-nav" :aria-label="t('reviewerWorkspace.workspaceNav')">
      <button
        type="button"
        :class="{ active: surface === 'reviewer' }"
        :aria-pressed="surface === 'reviewer'"
        @click="surface = 'reviewer'"
      >
        <SquareCheckBig :size="16" />
        <span>{{ t('reviewerWorkspace.reviewerTab') }}</span>
        <small>{{ points.length }}</small>
      </button>
      <button
        type="button"
        :class="{ active: surface === 'ledger' }"
        :aria-pressed="surface === 'ledger'"
        @click="surface = 'ledger'"
      >
        <ListChecks :size="16" />
        <span>{{ t('reviewerWorkspace.ledgerTab') }}</span>
        <small>{{ companion.state.ledger?.promises.length ?? 0 }}</small>
      </button>
      <button
        type="button"
        :class="{ active: surface === 'map' }"
        :aria-pressed="surface === 'map'"
        @click="surface = 'map'"
      >
        <Network :size="16" />
        <span>{{ t('reviewerWorkspace.argumentMap') }}</span>
      </button>
    </nav>

    <template v-if="surface === 'reviewer'">
      <AppHeader
        :title="t('reviewerWorkspace.title')"
        :subtitle="reviewSubtitle"
        :icon="SquareCheckBig"
      >
        <StatusBadge tone="danger" dot>{{
          venue || t('reviewerWorkspace.generalReview')
        }}</StatusBadge>
        <button type="button" class="header-button" @click="showImport = !showImport">
          {{ t('reviewerWorkspace.importReview') }}
        </button>
        <button type="button" class="header-button" @click="surface = 'map'">
          {{ t('reviewerWorkspace.argumentMap') }}
        </button>
        <button
          type="button"
          class="header-button primary"
          :disabled="companion.state.reviewing || !content.trim()"
          @click="runReview"
        >
          {{
            companion.state.reviewing
              ? t('reviewerWorkspace.reviewing')
              : t('reviewerWorkspace.startReview')
          }}
        </button>
      </AppHeader>

      <div v-if="showImport" class="import-strip">
        <textarea
          v-model="importText"
          rows="2"
          :placeholder="t('reviewerWorkspace.importPlaceholder')"
        />
        <button
          type="button"
          :disabled="!importText.trim() || companion.state.reviewing"
          @click="importReviews"
        >
          {{ t('reviewerWorkspace.importAction') }}
        </button>
      </div>

      <div class="reviewer-body">
        <main class="critique-column">
          <div class="review-toolbar">
            <SegmentedControl
              v-model="filter"
              :options="filterOptions"
              :label="t('reviewerWorkspace.filterLabel')"
            />
            <div class="toolbar-spacer" />
            <select
              v-model="venue"
              class="quiet-select"
              :aria-label="t('reviewerWorkspace.targetVenue')"
            >
              <option value="">{{ t('reviewerWorkspace.generalReview') }}</option>
              <option>NeurIPS 2024</option>
              <option>ICML</option>
              <option>ICLR</option>
              <option>ACL</option>
              <option>CHI</option>
            </select>
            <select
              v-model="persona"
              class="quiet-select"
              :aria-label="t('reviewerWorkspace.persona')"
            >
              <option value="reviewer2">{{ t('argument.reviewModeReviewer2') }}</option>
              <option value="ac">{{ t('argument.reviewModeAC') }}</option>
              <option value="domain_expert">{{ t('argument.reviewModeDomainExpert') }}</option>
              <option value="friendly">{{ t('argument.reviewModeFriendly') }}</option>
            </select>
            <select
              v-model="reviewMode"
              class="quiet-select"
              :aria-label="t('reviewerWorkspace.reviewMode')"
            >
              <option value="parallel">{{ t('reviewerWorkspace.parallel') }}</option>
              <option value="serial">{{ t('reviewerWorkspace.serial') }}</option>
            </select>
          </div>

          <div v-if="filteredPoints.length" class="critique-list">
            <ReviewerThread
              v-for="point in filteredPoints"
              :key="point.id"
              :point="point"
              :rebuttal-sending="companion.state.rebuttalSending"
              @focus-anchor="companion.focusAnchor"
              @update-point-status="(status) => companion.updatePointStatus(point.id, status)"
              @rebut="(pointId, message) => companion.rebut(pointId, message, content)"
            />
          </div>

          <EmptyState
            v-else-if="!companion.state.reviewing"
            :title="t('reviewerWorkspace.emptyTitle')"
            :description="t('reviewerWorkspace.emptyDescription')"
          >
            <button
              type="button"
              class="empty-action"
              :disabled="!content.trim()"
              @click="runReview"
            >
              {{ t('reviewerWorkspace.reviewDocument') }}
            </button>
          </EmptyState>

          <div v-else class="review-loading">
            <span class="loading-line" /><span class="loading-line short" /><span
              class="loading-line"
            />
            <p>{{ t('reviewerWorkspace.loading') }}</p>
          </div>
        </main>

        <aside class="review-side">
          <Panel class="ledger-card">
            <div class="side-title-row">
              <h2>{{ t('reviewerWorkspace.ledgerTab') }}</h2>
              <button
                type="button"
                @click="companion.buildOrRebuildLedger(content)"
                :disabled="companion.state.building || !content.trim()"
              >
                {{
                  companion.state.ledger
                    ? t('reviewerWorkspace.rebuildLedger')
                    : t('reviewerWorkspace.buildLedger')
                }}
              </button>
            </div>
            <div v-if="ledgerItems.length" class="ledger-rows">
              <button
                v-for="promise in ledgerItems"
                :key="promise.id"
                type="button"
                class="ledger-row"
                @click="companion.focusAnchor(promise.source_anchor_id)"
              >
                <span class="ledger-dot" :class="`ledger-${promise.status}`" />
                <span class="ledger-text">{{ promise.text }}</span>
                <span class="ledger-status">{{ promiseStatus(promise.status) }}</span>
              </button>
            </div>
            <p v-else class="side-empty">{{ t('reviewerWorkspace.ledgerEmpty') }}</p>
          </Panel>

          <Panel class="overview-card" padded>
            <h2>{{ t('reviewerWorkspace.overview') }}</h2>
            <div class="overview-counts">
              <div>
                <strong>{{ points.length }}</strong
                ><span>{{ t('reviewerWorkspace.total') }}</span>
              </div>
              <div class="responded">
                <strong>{{ respondedCount }}</strong
                ><span>{{ t('reviewerWorkspace.responded') }}</span>
              </div>
              <div class="pending">
                <strong>{{ pendingCount }}</strong
                ><span>{{ t('reviewerWorkspace.pending') }}</span>
              </div>
            </div>
            <div class="progress-track"><span :style="{ width: `${responseRate}%` }" /></div>
            <p>{{ t('reviewerWorkspace.responseRate', { rate: responseRate }) }}</p>
          </Panel>

          <Panel class="note-card" padded>
            <div class="note-title"><Sparkles :size="16" /> {{ t('reviewerWorkspace.tip') }}</div>
            <p>{{ reviewTip }}</p>
          </Panel>
        </aside>
      </div>
    </template>

    <template v-else-if="surface === 'ledger'">
      <AppHeader
        :title="t('reviewerWorkspace.ledgerTitle')"
        :subtitle="t('reviewerWorkspace.ledgerSubtitle')"
        :icon="ListChecks"
      >
        <button
          type="button"
          class="header-button primary"
          :disabled="companion.state.building || !content.trim()"
          @click="companion.buildOrRebuildLedger(content)"
        >
          {{
            companion.state.ledger
              ? t('reviewerWorkspace.rebuildLedger')
              : t('reviewerWorkspace.buildLedger')
          }}
        </button>
      </AppHeader>
      <main class="ledger-workspace">
        <LedgerList
          :ledger="companion.state.ledger"
          :building="companion.state.building"
          :suggesting-id="suggestingId"
          @analyze="companion.buildOrRebuildLedger(content)"
          @focus-anchor="companion.focusAnchor"
          @suggest-experiment="suggestExperiment"
        />
        <Panel v-if="experimentSuggestion" class="experiment-suggestion" padded>
          <div class="side-title-row">
            <h2>{{ t('reviewerWorkspace.experimentSuggestion') }}</h2>
            <button type="button" @click="experimentSuggestion = ''">
              {{ t('general.close') }}
            </button>
          </div>
          <p>{{ experimentSuggestion }}</p>
        </Panel>
      </main>
    </template>

    <template v-else>
      <AppHeader
        :title="t('reviewerWorkspace.argumentMap')"
        :subtitle="t('reviewerWorkspace.mapSubtitle')"
        :icon="Network"
      >
        <button type="button" class="header-button" @click="surface = 'reviewer'">
          {{ t('reviewerWorkspace.backReviewer') }}
        </button>
      </AppHeader>
      <ArgumentMapView class="embedded-argument-map" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ListChecks, Network, Sparkles, SquareCheckBig } from 'lucide-vue-next'
import { useArgumentCompanion } from '../../composables/useArgumentCompanion'
import { useEditorState } from '../../composables/useEditorState'
import { API_BASE } from '../../utils/api'
import ReviewerThread from './ReviewerThread.vue'
import ArgumentMapView from './ArgumentMapView.vue'
import LedgerList from './LedgerList.vue'
import AppHeader from '../shell/AppHeader.vue'
import Panel from '../shell/Panel.vue'
import SegmentedControl from '../shell/SegmentedControl.vue'
import StatusBadge from '../shell/StatusBadge.vue'
import EmptyState from '../shell/EmptyState.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const companion = useArgumentCompanion()
const { content, activeFile, activeTab } = useEditorState()
const surface = ref<'reviewer' | 'ledger' | 'map'>('reviewer')
const filter = ref('all')
const venue = ref('NeurIPS 2024')
const persona = ref('reviewer2')
const reviewMode = ref<'serial' | 'parallel'>('parallel')
const showImport = ref(false)
const importText = ref('')
const suggestingId = ref('')
const experimentSuggestion = ref('')

watch(
  [activeFile, activeTab],
  () => {
    const id = activeFile.value || activeTab.value?.id || ''
    const title = activeTab.value?.name || t('reviewerWorkspace.currentDocument')
    if (id) companion.setDoc(id, title)
  },
  { immediate: true },
)

const points = computed(() => companion.state.review?.points ?? [])
const respondedCount = computed(
  () => points.value.filter((point) => point.status !== 'open').length,
)
const pendingCount = computed(() => points.value.filter((point) => point.status === 'open').length)
const responseRate = computed(() =>
  points.value.length ? Math.round((respondedCount.value / points.value.length) * 100) : 0,
)
const ledgerItems = computed(() => (companion.state.ledger?.promises ?? []).slice(0, 6))
const filteredPoints = computed(() => {
  if (filter.value === 'open') return points.value.filter((point) => point.status === 'open')
  if (filter.value === 'responded') return points.value.filter((point) => point.status !== 'open')
  return points.value
})
const filterOptions = computed(() => [
  { value: 'all', label: t('general.all'), count: points.value.length },
  { value: 'open', label: t('reviewerWorkspace.pending'), count: pendingCount.value },
  { value: 'responded', label: t('reviewerWorkspace.responded'), count: respondedCount.value },
])
const reviewSubtitle = computed(() => {
  const title = activeTab.value?.name || t('reviewerWorkspace.noDocument')
  return t('reviewerWorkspace.subtitle', { title, count: points.value.length })
})
const reviewTip = computed(() =>
  pendingCount.value ? t('reviewerWorkspace.pendingTip') : t('reviewerWorkspace.doneTip'),
)

async function runReview() {
  if (!content.value.trim()) return
  await companion.runReview(content.value, venue.value || null, persona.value, reviewMode.value)
}

async function importReviews() {
  const raw = importText.value.trim()
  if (!raw || !content.value.trim()) return
  await companion.importReviews(raw, content.value)
  importText.value = ''
  showImport.value = false
}

async function suggestExperiment(promiseId: string) {
  if (!companion.state.docId || suggestingId.value) return
  suggestingId.value = promiseId
  experimentSuggestion.value = ''
  try {
    const response = await fetch(
      `${API_BASE}/api/companion/ledger/promise/${promiseId}/suggest-experiment?doc_id=${encodeURIComponent(companion.state.docId)}`,
      { method: 'POST' },
    )
    if (!response.ok) return
    const data = (await response.json()) as { suggestion?: string }
    experimentSuggestion.value = data.suggestion ?? ''
  } finally {
    suggestingId.value = ''
  }
}

function promiseStatus(status: string) {
  return t(`reviewerWorkspace.promise.${status}`, status)
}
</script>

<style scoped>
.reviewer-workspace {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-app-bg);
  color: var(--c-text-0);
}
.review-surface-nav {
  flex: 0 0 44px;
  display: flex;
  align-items: stretch;
  gap: 4px;
  padding: 5px 18px 0;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-nav);
}
.review-surface-nav button {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 13px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--c-text-2);
  font:
    550 13px/1 var(--font-sans),
    var(--font-zh);
  cursor: pointer;
}
.review-surface-nav button:hover {
  color: var(--c-text-0);
  background: var(--c-surface-2);
}
.review-surface-nav button.active {
  border-bottom-color: var(--brand-red);
  color: var(--c-text-0);
  background: var(--c-panel);
}
.review-surface-nav small {
  min-width: 20px;
  padding: 2px 6px;
  border-radius: 8px;
  background: var(--c-surface-2);
  color: var(--c-text-3);
  font-size: 10px;
  text-align: center;
}
.header-button,
.empty-action {
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--c-panel);
  color: var(--c-text-1);
  font:
    500 13px/1 var(--font-sans),
    var(--font-zh);
  cursor: pointer;
}
.header-button:hover,
.empty-action:hover {
  border-color: #d4ccbd;
  background: var(--c-surface-2);
}
.header-button.primary,
.empty-action {
  border-color: var(--c-accent);
  background: var(--c-accent);
  color: #fff;
}
.header-button:disabled,
.empty-action:disabled {
  opacity: 0.5;
  cursor: default;
}
.import-strip {
  display: flex;
  gap: 10px;
  padding: 12px 22px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
}
.import-strip textarea {
  flex: 1;
  resize: none;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  padding: 10px 12px;
  color: var(--c-text-0);
  font:
    13px/1.5 var(--font-sans),
    var(--font-zh);
}
.import-strip button {
  border: 0;
  border-radius: 8px;
  padding: 0 16px;
  background: var(--c-accent);
  color: #fff;
}
.reviewer-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 350px;
  gap: 20px;
  padding: 20px 22px;
  overflow: hidden;
}
.critique-column {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.review-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 14px;
}
.toolbar-spacer {
  flex: 1;
}
.quiet-select {
  height: 36px;
  padding: 0 30px 0 10px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-panel);
  color: var(--c-text-1);
  font-size: 12px;
}
.critique-list {
  min-height: 0;
  overflow: auto;
  padding-right: 5px;
}
.review-side {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ledger-card {
  flex: 0 0 auto;
  padding: 14px;
}
.side-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.side-title-row h2,
.overview-card h2 {
  margin: 0;
  color: var(--c-text-0);
  font:
    650 15px/1.3 var(--font-sans),
    var(--font-zh);
}
.side-title-row button {
  border: 0;
  background: transparent;
  color: var(--c-accent);
  font-size: 12px;
  cursor: pointer;
}
.ledger-rows {
  display: grid;
  gap: 7px;
}
.ledger-row {
  width: 100%;
  min-height: 42px;
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: var(--c-surface-2);
  text-align: left;
  cursor: pointer;
}
.ledger-row:hover {
  background: var(--c-accent-soft);
}
.ledger-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c-text-3);
}
.ledger-paid {
  background: var(--c-success);
}
.ledger-partial {
  background: var(--c-warn);
}
.ledger-unpaid,
.ledger-mismatch {
  background: var(--c-danger);
}
.ledger-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-text-1);
  font-size: 12px;
}
.ledger-status {
  color: var(--c-text-3);
  font-size: 11px;
}
.side-empty {
  margin: 0;
  padding: 12px 2px 4px;
  color: var(--c-text-3);
  font-size: 12px;
  line-height: 1.6;
}
.overview-card h2 {
  margin-bottom: 18px;
}
.overview-counts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
}
.overview-counts div {
  display: grid;
  place-items: center;
  gap: 5px;
  border-right: 1px solid var(--c-border);
}
.overview-counts div:last-child {
  border-right: 0;
}
.overview-counts strong {
  color: var(--c-accent);
  font-size: 23px;
}
.overview-counts .responded strong {
  color: var(--c-success);
}
.overview-counts .pending strong {
  color: var(--c-warn);
}
.overview-counts span,
.overview-card p {
  color: var(--c-text-3);
  font-size: 11px;
}
.progress-track {
  height: 7px;
  margin-top: 18px;
  border-radius: 10px;
  background: var(--c-warn-bg);
  overflow: hidden;
}
.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-success);
}
.overview-card p {
  margin: 8px 0 0;
}
.note-card {
  border-color: var(--c-info-border);
  background: var(--c-info-bg);
}
.note-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--c-text-0);
  font-size: 13px;
  font-weight: 650;
}
.note-title svg {
  color: var(--c-accent);
}
.note-card p {
  margin: 10px 0 0;
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.7;
}
.review-loading {
  display: grid;
  gap: 12px;
  padding: 28px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-panel);
}
.loading-line {
  height: 12px;
  border-radius: 5px;
  background: var(--c-surface-2);
  animation: pulse 1.5s ease-in-out infinite;
}
.loading-line.short {
  width: 58%;
}
.review-loading p {
  margin: 8px 0 0;
  color: var(--c-text-3);
  font-size: 12px;
}
.embedded-argument-map {
  flex: 1;
  min-height: 0;
}
.ledger-workspace {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px 22px 24px;
}
.ledger-workspace :deep(.ledger-list) {
  max-width: 1040px;
  height: auto;
  min-height: 360px;
  margin: 0 auto;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-panel);
  overflow: hidden;
}
.experiment-suggestion {
  max-width: 1040px;
  margin: 14px auto 0;
}
.experiment-suggestion p {
  margin: 0;
  white-space: pre-wrap;
  color: var(--c-text-1);
  font-size: 13px;
  line-height: 1.75;
}
@keyframes pulse {
  50% {
    opacity: 0.45;
  }
}
@media (max-width: 1120px) {
  .reviewer-body {
    grid-template-columns: minmax(0, 1fr) 310px;
    gap: 14px;
    padding-inline: 16px;
  }
}
@media (max-width: 920px) {
  .reviewer-body {
    grid-template-columns: 1fr;
    overflow: auto;
  }
  .critique-list {
    overflow: visible;
  }
  .review-side {
    overflow: visible;
  }
}
</style>
