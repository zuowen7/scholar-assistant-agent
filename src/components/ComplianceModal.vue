<template>
  <AppDialog
    :model-value="visible"
    :title="t('editor.complianceTitle')"
    :subtitle="t('editor.complianceSubtitle')"
    :close-label="t('general.close')"
    @update:model-value="!$event && $emit('close')"
  >
    <div class="modal-body">
      <!-- Loading -->
      <div v-if="loading" class="compliance-loading">
        <div class="spinner" />
        <p>{{ t('editor.complianceAnalyzing') }}</p>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="compliance-error">
        <p class="state-mark">!</p>
        <p>{{ error }}</p>
        <button class="btn primary-btn" @click="$emit('retry')">
          {{ t('editor.complianceRecheck') }}
        </button>
      </div>

      <!-- Report -->
      <div v-else-if="report" class="compliance-report">
        <!-- Summary Score -->
        <div class="report-summary" :class="scoreClass">
          <div class="score-circle">
            <svg viewBox="0 0 36 36">
              <path
                class="score-bg"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                class="score-bar"
                :stroke-dasharray="`${report.summary?.compliance_score || 0}, 100`"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <span class="score-text">{{ report.summary?.compliance_score || 0 }}</span>
          </div>
          <div class="summary-text">
            <strong>{{ statusLabel }}</strong>
            <p>
              {{ report.summary?.total_words || 0 }} {{ t('editor.complianceWords') }} /
              {{ report.summary?.total_characters || 0 }} {{ t('editor.characters') }}
            </p>
          </div>
        </div>

        <!-- Sections -->
        <div class="report-sections">
          <!-- Structure -->
          <div class="report-section" v-if="report.structure">
            <h4>{{ t('editor.complianceStructure') }}</h4>
            <div class="section-content">
              <div class="section-item">
                <span class="label">{{ t('editor.complianceSectionRequired') }}</span>
                <span>{{ formatSections(report.structure.required_sections) }}</span>
              </div>
              <div v-if="report.structure.issues?.length" class="issues">
                <span
                  class="issue-tag warning"
                  v-for="(issue, i) in report.structure.issues"
                  :key="i"
                  >{{ typeof issue === 'object' ? issue.detail : issue }}</span
                >
              </div>
            </div>
          </div>

          <!-- Terminology -->
          <div class="report-section" v-if="report.terminology">
            <h4>{{ t('editor.complianceTerminology') }}</h4>
            <div class="section-content">
              <div class="section-item">
                <span class="label">{{ t('editor.complianceTermConsistent') }}</span>
                <span class="ok">{{
                  Array.isArray(report.terminology.consistent_terms)
                    ? report.terminology.consistent_terms.join(', ')
                    : t('editor.complianceNone')
                }}</span>
              </div>
              <div v-if="report.terminology.inconsistent_terms?.length" class="section-item">
                <span class="label">{{ t('editor.complianceTermInconsistent') }}</span>
                <span class="warn">{{
                  formatTermList(report.terminology.inconsistent_terms)
                }}</span>
              </div>
              <div v-if="report.terminology.issues?.length" class="issues">
                <span
                  class="issue-tag warning"
                  v-for="(issue, i) in report.terminology.issues"
                  :key="i"
                  >{{ fmt(issue) }}</span
                >
              </div>
            </div>
          </div>

          <!-- Citation -->
          <div class="report-section" v-if="report.citation">
            <h4>{{ t('editor.complianceCitations') }}</h4>
            <div class="section-content">
              <div class="section-item">
                <span class="label">{{ t('editor.complianceCiteTotal') }}</span>
                <span>{{ report.citation.total_citations || 0 }}</span>
              </div>
              <div v-if="report.citation.format_issues?.length" class="issues">
                <span
                  class="issue-tag warning"
                  v-for="(issue, i) in report.citation.format_issues"
                  :key="i"
                  >{{ fmt(issue) }}</span
                >
              </div>
              <div v-if="report.citation.issues?.length" class="issues">
                <span
                  class="issue-tag error"
                  v-for="(issue, i) in report.citation.issues"
                  :key="i"
                  >{{ fmt(issue) }}</span
                >
              </div>
            </div>
          </div>

          <!-- Hallucination Risk -->
          <div class="report-section" v-if="report.hallucination_risk">
            <h4>{{ t('editor.complianceHallucination') }}</h4>
            <div class="section-content">
              <div class="section-item">
                <span class="label">{{ t('editor.complianceRiskLevel') }}</span>
                <span :class="'risk-' + (report.hallucination_risk.risk_level || 'unknown')">
                  {{ riskLevelLabel }}
                </span>
              </div>
              <div v-if="report.hallucination_risk.flags?.length" class="issues">
                <span
                  class="issue-tag error"
                  v-for="(flag, i) in report.hallucination_risk.flags"
                  :key="i"
                  >{{ fmt(flag) }}</span
                >
              </div>
              <div v-if="report.hallucination_risk.issues?.length" class="issues">
                <span
                  class="issue-tag warning"
                  v-for="(issue, i) in report.hallucination_risk.issues"
                  :key="i"
                  >{{ fmt(issue) }}</span
                >
              </div>
            </div>
          </div>

          <!-- Readability -->
          <div class="report-section" v-if="report.readability">
            <h4>{{ t('editor.complianceReadability') }}</h4>
            <div class="section-content">
              <div class="section-item">
                <span class="label">{{ t('editor.complianceAvgSentence') }}</span>
                <span
                  >{{ report.readability.avg_sentence_length?.toFixed(1) || '?' }}
                  {{ t('editor.complianceWords2') }}</span
                >
              </div>
              <div v-if="report.readability.long_sentences?.length" class="issues">
                <span
                  class="issue-tag info"
                  v-for="(s, i) in report.readability.long_sentences.slice(0, 3)"
                  :key="i"
                >
                  {{ (typeof s === 'string' ? s : s?.text || JSON.stringify(s)).slice(0, 60)
                  }}{{ (typeof s === 'string' ? s : s?.text || '').length > 60 ? '...' : '' }}
                </span>
              </div>
              <div v-if="report.readability.issues?.length" class="issues">
                <span
                  class="issue-tag warning"
                  v-for="(issue, i) in report.readability.issues"
                  :key="i"
                  >{{ fmt(issue) }}</span
                >
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty -->
      <div v-else class="compliance-empty">
        <p>{{ t('editor.complianceStart') }}</p>
      </div>
    </div>
    <template #footer>
      <button class="btn secondary-btn" @click="$emit('close')">{{ t('general.close') }}</button>
      <button class="btn primary-btn" @click="$emit('retry')" :disabled="loading">
        {{ t('editor.complianceRecheck') }}
      </button>
    </template>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppDialog from './shell/AppDialog.vue'
import type { ComplianceIssue, ComplianceReport } from '../types'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
  loading: boolean
  error: string
  report: ComplianceReport | null
}>()

defineEmits<{
  close: []
  retry: []
}>()

const scoreClass = computed(() => {
  const score = props.report?.summary?.compliance_score || 0
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
})

const statusLabel = computed(() => {
  const status = props.report?.summary?.overall_status || 'unknown'
  const labels: Record<string, string> = {
    pass: t('editor.compliancePass'),
    warning: t('editor.complianceWarn'),
    fail: t('editor.complianceFail'),
    unknown: t('editor.complianceUnknown'),
  }
  return labels[status] || status
})

const riskLevelLabel = computed(() => {
  const level = props.report?.hallucination_risk?.risk_level || 'unknown'
  const labels: Record<string, string> = {
    low: t('editor.complianceLowRisk'),
    medium: t('editor.complianceMediumRisk'),
    high: t('editor.complianceHighRisk'),
    unknown: t('editor.complianceUnknown'),
  }
  return labels[level] || level
})

function formatSections(sections: Record<string, ComplianceIssue> | null | undefined): string {
  if (!sections) return t('editor.complianceNone')
  const names = Object.keys(sections)
  return names.length ? names.join(' · ') : t('editor.complianceNone')
}

function formatTermList(items: (string | { term?: string })[] | null | undefined): string {
  if (!items?.length) return ''
  return items
    .map((item) => (typeof item === 'string' ? item : item?.term || JSON.stringify(item)))
    .join(', ')
}

function fmt(v: ComplianceIssue): string {
  if (typeof v === 'string') return v
  return v.detail || v.text || JSON.stringify(v)
}
</script>

<style scoped>
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.compliance-loading,
.compliance-error,
.compliance-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: var(--c-text-3);
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--c-surface-3);
  border-top-color: var(--c-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.state-mark {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  margin: 0;
  border-radius: 9px;
  background: var(--c-danger-bg);
  color: var(--c-danger);
  font-weight: 700;
}

.report-summary {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  margin-bottom: 20px;
}
.score-high {
  border-left: 3px solid var(--c-success);
}
.score-mid {
  border-left: 3px solid var(--c-warn);
}
.score-low {
  border-left: 3px solid var(--c-danger);
}

.score-circle {
  position: relative;
  width: 80px;
  height: 80px;
}
.score-circle svg {
  width: 80px;
  height: 80px;
  transform: rotate(-90deg);
}
.score-bg {
  fill: none;
  stroke: var(--c-surface-3);
  stroke-width: 3;
}
.score-bar {
  fill: none;
  stroke: var(--c-success);
  stroke-width: 3;
  stroke-linecap: round;
}
.score-mid .score-bar {
  stroke: var(--c-warn);
}
.score-low .score-bar {
  stroke: var(--c-danger);
}
.score-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 700;
  color: var(--c-text-0);
}
.summary-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--c-text-1);
}
.summary-text strong {
  font-size: 16px;
}

.report-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.report-section {
  border-top: 1px solid var(--c-border);
  padding-top: 12px;
}
.report-section h4 {
  margin: 0;
  padding: 0 2px 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text-1);
}

.section-content {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.section-item {
  display: flex;
  gap: 8px;
  font-size: 13px;
}
.label {
  color: var(--c-text-3);
  white-space: nowrap;
  min-width: 72px;
}
.ok {
  color: var(--c-success);
}
.warn {
  color: var(--c-warn);
}

.issues {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.issue-tag {
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.45;
}
.issue-tag.warning {
  background: var(--c-warn-bg);
  color: var(--c-warn);
}
.issue-tag.error {
  background: var(--c-danger-bg);
  color: var(--c-danger);
}
.issue-tag.info {
  background: var(--c-info-bg);
  color: var(--c-info);
}

.risk-low {
  color: var(--c-success);
}
.risk-medium {
  color: var(--c-warn);
}
.risk-high {
  color: var(--c-danger);
}
.risk-unknown {
  color: var(--c-text-3);
}

.btn {
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.primary-btn {
  background: var(--c-accent);
  color: #fff;
}
.primary-btn:hover:not(:disabled) {
  background: var(--c-accent-hover);
}
.secondary-btn {
  background: var(--c-surface-2);
  color: var(--c-text-1);
  border: 1px solid var(--c-surface-3);
}
</style>
