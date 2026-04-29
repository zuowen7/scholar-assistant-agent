<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-panel" :class="{ dark: isDarkMode }">
        <div class="modal-header">
          <h3>📋 论文合规检查报告</h3>
          <button class="close-btn" @click="$emit('close')">✕</button>
        </div>

        <div class="modal-body">
          <!-- Loading -->
          <div v-if="loading" class="compliance-loading">
            <div class="spinner"></div>
            <p>正在分析论文合规性...</p>
          </div>

          <!-- Error -->
          <div v-else-if="error" class="compliance-error">
            <p class="error-icon">⚠️</p>
            <p>{{ error }}</p>
            <button class="btn retry-btn" @click="$emit('retry')">重新检查</button>
          </div>

          <!-- Report -->
          <div v-else-if="report" class="compliance-report">
            <!-- Summary Score -->
            <div class="report-summary" :class="scoreClass">
              <div class="score-circle">
                <svg viewBox="0 0 36 36">
                  <path class="score-bg"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                  <path class="score-bar"
                    :stroke-dasharray="`${report.summary?.compliance_score || 0}, 100`"
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                  />
                </svg>
                <span class="score-text">{{ report.summary?.compliance_score || 0 }}</span>
              </div>
              <div class="summary-text">
                <strong>{{ statusLabel }}</strong>
                <p>{{ report.summary?.total_words || 0 }} 字 / {{ report.summary?.total_characters || 0 }} 字符</p>
              </div>
            </div>

            <!-- Sections -->
            <div class="report-sections">
              <!-- Structure -->
              <div class="report-section" v-if="report.structure">
                <h4>📑 论文结构</h4>
                <div class="section-content">
                  <div class="section-item">
                    <span class="label">必要章节:</span>
                    <span>{{ formatSections(report.structure.required_sections) }}</span>
                  </div>
                  <div v-if="report.structure.issues?.length" class="issues">
                    <span class="issue-tag warning" v-for="(issue, i) in report.structure.issues" :key="i">{{ typeof issue === 'object' ? issue.detail : issue }}</span>
                  </div>
                </div>
              </div>

              <!-- Terminology -->
              <div class="report-section" v-if="report.terminology">
                <h4>🔤 术语一致性</h4>
                <div class="section-content">
                  <div class="section-item">
                    <span class="label">一致术语:</span>
                    <span class="ok">{{ Array.isArray(report.terminology.consistent_terms) ? report.terminology.consistent_terms.join(', ') : '无' }}</span>
                  </div>
                  <div v-if="report.terminology.inconsistent_terms?.length" class="section-item">
                    <span class="label">不一致:</span>
                    <span class="warn">{{ formatTermList(report.terminology.inconsistent_terms) }}</span>
                  </div>
                  <div v-if="report.terminology.issues?.length" class="issues">
                    <span class="issue-tag warning" v-for="(issue, i) in report.terminology.issues" :key="i">{{ fmt(issue) }}</span>
                  </div>
                </div>
              </div>

              <!-- Citation -->
              <div class="report-section" v-if="report.citation">
                <h4>📚 引用格式</h4>
                <div class="section-content">
                  <div class="section-item">
                    <span class="label">引用总数:</span>
                    <span>{{ report.citation.total_citations || 0 }}</span>
                  </div>
                  <div v-if="report.citation.format_issues?.length" class="issues">
                    <span class="issue-tag warning" v-for="(issue, i) in report.citation.format_issues" :key="i">{{ fmt(issue) }}</span>
                  </div>
                  <div v-if="report.citation.issues?.length" class="issues">
                    <span class="issue-tag error" v-for="(issue, i) in report.citation.issues" :key="i">{{ fmt(issue) }}</span>
                  </div>
                </div>
              </div>

              <!-- Hallucination Risk -->
              <div class="report-section" v-if="report.hallucination_risk">
                <h4>⚡ 幻觉风险</h4>
                <div class="section-content">
                  <div class="section-item">
                    <span class="label">风险等级:</span>
                    <span :class="'risk-' + (report.hallucination_risk.risk_level || 'unknown')">
                      {{ riskLevelLabel }}
                    </span>
                  </div>
                  <div v-if="report.hallucination_risk.flags?.length" class="issues">
                    <span class="issue-tag error" v-for="(flag, i) in report.hallucination_risk.flags" :key="i">{{ fmt(flag) }}</span>
                  </div>
                  <div v-if="report.hallucination_risk.issues?.length" class="issues">
                    <span class="issue-tag warning" v-for="(issue, i) in report.hallucination_risk.issues" :key="i">{{ fmt(issue) }}</span>
                  </div>
                </div>
              </div>

              <!-- Readability -->
              <div class="report-section" v-if="report.readability">
                <h4>📖 可读性</h4>
                <div class="section-content">
                  <div class="section-item">
                    <span class="label">平均句长:</span>
                    <span>{{ report.readability.avg_sentence_length?.toFixed(1) || '?' }} 词</span>
                  </div>
                  <div v-if="report.readability.long_sentences?.length" class="issues">
                    <span class="issue-tag info" v-for="(s, i) in report.readability.long_sentences.slice(0,3)" :key="i">
                      {{ (typeof s === 'string' ? s : s?.text || JSON.stringify(s)).slice(0, 60) }}{{ (typeof s === 'string' ? s : s?.text || '').length > 60 ? '...' : '' }}
                    </span>
                  </div>
                  <div v-if="report.readability.issues?.length" class="issues">
                    <span class="issue-tag warning" v-for="(issue, i) in report.readability.issues" :key="i">{{ fmt(issue) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Empty -->
          <div v-else class="compliance-empty">
            <p>点击"重新检查"开始分析</p>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn secondary-btn" @click="$emit('close')">关闭</button>
          <button class="btn primary-btn" @click="$emit('retry')" :disabled="loading">重新检查</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  loading: boolean
  error: string
  report: any | null
}>()

defineEmits<{
  close: []
  retry: []
}>()

const isDarkMode = document.documentElement.classList.contains('dark')

const scoreClass = computed(() => {
  const score = (props.report?.summary as any)?.compliance_score || 0
  if (score >= 80) return 'score-high'
  if (score >= 60) return 'score-mid'
  return 'score-low'
})

const statusLabel = computed(() => {
  const status = (props.report?.summary as any)?.overall_status || 'unknown'
  const labels: Record<string, string> = {
    pass: '✅ 合格', warning: '⚠️ 需改进', fail: '❌ 不合格', unknown: '❓ 未知'
  }
  return labels[status] || status
})

const riskLevelLabel = computed(() => {
  const level = (props.report?.hallucination_risk as any)?.risk_level || 'unknown'
  const labels: Record<string, string> = {
    low: '🟢 低风险', medium: '🟡 中风险', high: '🔴 高风险', unknown: '❓ 未知'
  }
  return labels[level] || level
})

function formatSections(sections: Record<string, any> | null | undefined): string {
  if (!sections) return '无'
  const names = Object.keys(sections)
  return names.length ? names.join(' · ') : '无'
}

function formatTermList(items: any[] | null | undefined): string {
  if (!items?.length) return ''
  return items.map(item => typeof item === 'string' ? item : item?.term || JSON.stringify(item)).join(', ')
}

function fmt(v: unknown): string {
  if (typeof v === 'string') return v
  if (typeof v === 'object' && v !== null) return (v as any).detail || (v as any).text || JSON.stringify(v)
  return String(v ?? '')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center;
}
.modal-panel {
  background: #fff; border-radius: 12px; width: 560px; max-width: 95vw;
  max-height: 85vh; display: flex; flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  overflow: hidden;
}
.modal-panel.dark { background: #1e1e1e; color: #e0e0e0; }
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #eee;
  font-size: 15px; font-weight: 600;
}
.dark .modal-header { border-color: #333; }
.close-btn { background: none; border: none; font-size: 18px; cursor: pointer; color: #888; }
.close-btn:hover { color: #333; }
.dark .close-btn { color: #888; }

.modal-body { flex: 1; overflow-y: auto; padding: 20px; }

.compliance-loading, .compliance-error, .compliance-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 200px; gap: 12px; color: #666;
}
.dark .compliance-loading, .dark .compliance-error, .dark .compliance-empty { color: #aaa; }
.spinner {
  width: 36px; height: 36px; border: 3px solid #eee;
  border-top-color: #4a9eff; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error-icon { font-size: 48px; }

.report-summary {
  display: flex; align-items: center; gap: 20px;
  padding: 16px; border-radius: 10px; margin-bottom: 20px;
}
.score-high { background: #e8f5e9; }
.score-mid { background: #fff8e1; }
.score-low { background: #ffebee; }
.dark .score-high { background: #1b3a1b; }
.dark .score-mid { background: #2a2510; }
.dark .score-low { background: #3a1b1b; }

.score-circle {
  position: relative; width: 80px; height: 80px;
}
.score-circle svg { width: 80px; height: 80px; transform: rotate(-90deg); }
.score-bg { fill: none; stroke: #ddd; stroke-width: 3; }
.score-bar { fill: none; stroke: #4caf50; stroke-width: 3; stroke-linecap: round; }
.score-mid .score-bar { stroke: #ff9800; }
.score-low .score-bar { stroke: #f44336; }
.score-text {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 700; color: #333;
}
.dark .score-text { color: #e0e0e0; }
.summary-text { font-size: 14px; line-height: 1.6; }
.summary-text strong { font-size: 16px; }

.report-sections { display: flex; flex-direction: column; gap: 16px; }
.report-section {
  border: 1px solid #eee; border-radius: 8px; overflow: hidden;
}
.dark .report-section { border-color: #333; }
.report-section h4 {
  margin: 0; padding: 10px 14px; background: #f8f8f8;
  font-size: 13px; font-weight: 600;
}
.dark .report-section h4 { background: #252525; }

.section-content { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.section-item { display: flex; gap: 8px; font-size: 13px; }
.label { color: #888; white-space: nowrap; min-width: 72px; }
.dark .label { color: #777; }
.ok { color: #4caf50; }
.warn { color: #ff9800; }

.issues { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.issue-tag {
  padding: 3px 10px; border-radius: 20px; font-size: 12px;
}
.issue-tag.warning { background: #fff3e0; color: #e65100; }
.issue-tag.error { background: #ffebee; color: #c62828; }
.issue-tag.info { background: #e3f2fd; color: #1565c0; }
.dark .issue-tag.warning { background: #3a2a10; color: #ffb74d; }
.dark .issue-tag.error { background: #3a1a1a; color: #ef9a9a; }
.dark .issue-tag.info { background: #1a2a3a; color: #90caf9; }

.risk-low { color: #4caf50; }
.risk-medium { color: #ff9800; }
.risk-high { color: #f44336; }
.risk-unknown { color: #888; }

.modal-footer {
  display: flex; justify-content: flex-end; gap: 10px;
  padding: 14px 20px; border-top: 1px solid #eee;
}
.dark .modal-footer { border-color: #333; }
.btn {
  padding: 8px 20px; border-radius: 6px; border: none; cursor: pointer;
  font-size: 14px; transition: all 0.2s;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.primary-btn { background: #4a9eff; color: #fff; }
.primary-btn:hover:not(:disabled) { background: #3a8eef; }
.secondary-btn { background: #f0f0f0; color: #333; }
.dark .secondary-btn { background: #333; color: #e0e0e0; }
.retry-btn { margin-top: 8px; background: #4a9eff; color: #fff; padding: 8px 24px; border: none; border-radius: 6px; cursor: pointer; }
</style>
