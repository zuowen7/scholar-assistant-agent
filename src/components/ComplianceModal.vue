<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="modal-header">
        <span class="modal-title">论文合规检查</span>
        <button class="modal-close" @click="$emit('close')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="modal-loading">
        <div class="loading-spinner"></div>
        <span>AI 正在分析论文...</span>
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="modal-error">
        <span>{{ error }}</span>
        <button @click="$emit('retry')">重试</button>
      </div>

      <!-- 报告内容 -->
      <div v-else-if="report" class="modal-content">
        <!-- 总分卡片 -->
        <div class="score-card" :class="scoreClass">
          <div class="score-circle">
            <svg viewBox="0 0 36 36" class="score-svg">
              <path class="score-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
              <path class="score-fill" :stroke-dasharray="`${report.summary?.compliance_score || 0}, 100`" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"/>
            </svg>
            <div class="score-value">{{ report.summary?.compliance_score || 0 }}</div>
          </div>
          <div class="score-info">
            <div class="score-label">合规评分</div>
            <div class="score-status" :class="scoreClass">{{ statusText }}</div>
            <div class="score-meta">
              {{ report.summary?.total_words || 0 }} 字 · {{ report.summary?.total_sections || 0 }} 节
            </div>
          </div>
        </div>

        <!-- 章节结构 -->
        <div class="report-section">
          <div class="section-title">
            <span class="section-icon">📋</span>
            章节结构
          </div>
          <div class="section-body">
            <div
              v-for="(info, key) in report.structure?.required_sections || {}"
              :key="key"
              class="section-row"
              :class="{ missing: !info.found, empty: info.found && (info.word_count ?? 0) < 10 }"
            >
              <span class="section-name">{{ sectionNames[key] || key }}</span>
              <span v-if="!info.found" class="badge error">缺失</span>
              <span v-else-if="(info.word_count ?? 0) < 10" class="badge warning">过短</span>
              <span v-else class="badge pass">{{ info.word_count ?? 0 }} 字</span>
            </div>
            <div v-if="report.structure?.issues?.length" class="section-issues">
              <div v-for="(issue, i) in report.structure.issues" :key="i" class="issue-item" :class="issue.severity">
                {{ issue.detail }}
              </div>
            </div>
          </div>
        </div>

        <!-- 术语一致性 -->
        <div class="report-section" v-if="report.terminology">
          <div class="section-title">
            <span class="section-icon">🔤</span>
            术语一致性
          </div>
          <div class="section-body">
            <div v-if="report.terminology.consistent_terms?.length" class="tag-list">
              <span v-for="t in report.terminology.consistent_terms" :key="t" class="tag pass">{{ t }}</span>
            </div>
            <div v-if="report.terminology.inconsistent_terms?.length" class="section-issues">
              <div v-for="(item, i) in report.terminology.inconsistent_terms" :key="i" class="issue-item warning">
                <strong>{{ item.term }}</strong>：{{ item.variants?.join(', ') }} → 推荐统一为 "{{ item.recommendation }}"
              </div>
            </div>
            <div v-if="!report.terminology.consistent_terms?.length && !report.terminology.inconsistent_terms?.length" class="empty-note">
              未检测到术语使用
            </div>
          </div>
        </div>

        <!-- 引用格式 -->
        <div class="report-section" v-if="report.citation">
          <div class="section-title">
            <span class="section-icon">📚</span>
            引用格式 <span class="section-meta">{{ report.citation.total_citations || 0 }} 处引用</span>
          </div>
          <div class="section-body">
            <div v-if="report.citation.format_issues?.length" class="section-issues">
              <div v-for="(issue, i) in report.citation.format_issues" :key="i" class="issue-item warning">
                "{{ issue.text?.slice(0, 60) }}..." — {{ issue.issue }}
              </div>
            </div>
            <div v-else class="empty-note">引用格式检查通过</div>
          </div>
        </div>

        <!-- 幻觉风险 -->
        <div class="report-section" v-if="report.hallucination_risk">
          <div class="section-title">
            <span class="section-icon">⚠️</span>
            幻觉风险 <span class="section-meta risk-badge" :class="report.hallucination_risk.risk_level">{{ report.hallucination_risk.risk_level }}</span>
          </div>
          <div class="section-body">
            <div v-if="report.hallucination_risk.flags?.length" class="section-issues">
              <div v-for="(flag, i) in report.hallucination_risk.flags" :key="i" class="issue-item" :class="flag.severity">
                "{{ flag.text?.slice(0, 80) }}..." — {{ flag.risk }}
              </div>
            </div>
            <div v-else class="empty-note pass">未检测到明显幻觉风险</div>
          </div>
        </div>

        <!-- 可读性 -->
        <div class="report-section" v-if="report.readability">
          <div class="section-title">
            <span class="section-icon">📖</span>
            可读性
          </div>
          <div class="section-body">
            <div class="readability-stat">
              平均句子长度：<strong>{{ report.readability.avg_sentence_length || 0 }}</strong> 词
            </div>
            <div v-if="report.readability.long_sentences?.length" class="section-issues">
              <div v-for="(item, i) in report.readability.long_sentences.slice(0, 3)" :key="i" class="issue-item warning">
                {{ item.text?.slice(0, 80) }}... ({{ item.length }} 词)
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  loading: boolean
  error: string
  report: ComplianceReport | null
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'retry'): void
}>()

interface ComplianceReport {
  summary?: {
    compliance_score?: number
    overall_status?: string
    total_words?: number
    total_sections?: number
  }
  structure?: {
    required_sections?: Record<string, { found?: boolean; word_count?: number; issues?: string[] }>
    issues?: { type?: string; detail?: string; severity?: string }[]
  }
  terminology?: {
    consistent_terms?: string[]
    inconsistent_terms?: { term?: string; variants?: string[]; recommendation?: string }[]
    issues?: unknown[]
  }
  citation?: {
    total_citations?: number
    format_issues?: { text?: string; issue?: string; severity?: string }[]
    issues?: unknown[]
  }
  hallucination_risk?: {
    risk_level?: string
    flags?: { text?: string; risk?: string; severity?: string }[]
    issues?: unknown[]
  }
  readability?: {
    avg_sentence_length?: number
    long_sentences?: { text?: string; length?: number; suggestion?: string }[]
    issues?: unknown[]
  }
  error?: string
}

const sectionNames: Record<string, string> = {
  introduction: '引言',
  related_work: '相关工作',
  method: '方法',
  experiment: '实验',
  conclusion: '结论',
}

const scoreClass = computed(() => {
  const score = props.report?.summary?.compliance_score || 0
  if (score >= 80) return 'pass'
  if (score >= 50) return 'warning'
  return 'fail'
})

const statusText = computed(() => {
  const s = props.report?.summary?.overall_status
  if (s === 'pass') return '通过'
  if (s === 'warning') return '需改进'
  if (s === 'fail') return '不合格'
  return '未知'
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modal-panel {
  background: var(--surface2, #1f1f1f);
  border: 1px solid var(--border, #333);
  border-radius: 12px;
  width: 560px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 16px 64px rgba(0,0,0,0.6);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border, #333);
}
.modal-title { font-weight: 600; font-size: 15px; }
.modal-close {
  background: none; border: none; color: #888; cursor: pointer; padding: 4px;
  border-radius: 4px; display: flex; align-items: center;
}
.modal-close:hover { background: #333; color: #ddd; }

.modal-loading {
  display: flex; align-items: center; gap: 12px;
  padding: 32px 18px; color: #888; font-size: 14px;
}
.loading-spinner {
  width: 20px; height: 20px; border: 2px solid #444;
  border-top-color: var(--accent, #007acc); border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.modal-error {
  display: flex; align-items: center; gap: 10px;
  padding: 20px 18px; color: #f44336; font-size: 13px;
}
.modal-error button {
  background: #f44336; border: none; color: #fff;
  padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;
}

.modal-content { padding: 16px 18px; }

.score-card {
  display: flex; align-items: center; gap: 16px;
  padding: 14px; border-radius: 10px; margin-bottom: 16px;
  background: #181818;
}
.score-circle { position: relative; width: 64px; height: 64px; flex-shrink: 0; }
.score-svg { width: 64px; height: 64px; transform: rotate(-90deg); }
.score-bg { fill: none; stroke: #333; stroke-width: 3; }
.score-fill { fill: none; stroke: #888; stroke-width: 3; stroke-linecap: round; transition: stroke-dasharray 0.6s; }
.score-card.pass .score-fill { stroke: #4caf50; }
.score-card.warning .score-fill { stroke: #ff9800; }
.score-card.fail .score-fill { stroke: #f44336; }
.score-value { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; }
.score-label { font-size: 13px; color: #888; margin-bottom: 2px; }
.score-status { font-size: 16px; font-weight: 600; }
.score-status.pass { color: #4caf50; }
.score-status.warning { color: #ff9800; }
.score-status.fail { color: #f44336; }
.score-meta { font-size: 12px; color: #666; margin-top: 2px; }

.report-section { margin-bottom: 14px; }
.section-title {
  font-size: 13px; font-weight: 600; color: #ccc; margin-bottom: 8px;
  display: flex; align-items: center; gap: 6px;
}
.section-icon { font-size: 12px; }
.section-meta { font-size: 11px; color: #666; font-weight: 400; margin-left: auto; }
.risk-badge { padding: 1px 8px; border-radius: 10px; font-size: 10px; }
.risk-badge.low { background: rgba(76,175,80,0.2); color: #4caf50; }
.risk-badge.medium { background: rgba(255,152,0,0.2); color: #ff9800; }
.risk-badge.high { background: rgba(244,67,54,0.2); color: #f44336; }

.section-body { background: #181818; border-radius: 8px; padding: 10px 12px; }
.section-row {
  display: flex; align-items: center; gap: 8px; padding: 4px 0;
  font-size: 12px; color: #ccc;
}
.section-row.missing { color: #f44336; }
.section-row.empty { color: #ff9800; }
.section-name { flex: 1; }
.badge { padding: 1px 8px; border-radius: 10px; font-size: 10px; }
.badge.pass { background: rgba(76,175,80,0.2); color: #4caf50; }
.badge.warning { background: rgba(255,152,0,0.2); color: #ff9800; }
.badge.error { background: rgba(244,67,54,0.2); color: #f44336; }

.section-issues { margin-top: 6px; border-top: 1px solid #2a2a2a; padding-top: 6px; }
.issue-item {
  font-size: 11px; color: #888; padding: 3px 0;
  border-left: 2px solid transparent; padding-left: 6px;
}
.issue-item.warning { border-color: #ff9800; color: #cc7000; }
.issue-item.error { border-color: #f44336; color: #d32f2f; }
.issue-item.pass { border-color: #4caf50; color: #4caf50; }

.tag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.tag.pass { background: rgba(76,175,80,0.15); color: #4caf50; }

.empty-note { font-size: 12px; color: #555; font-style: italic; }
.empty-note.pass { color: #4caf50; }

.readability-stat { font-size: 12px; color: #ccc; margin-bottom: 6px; }
</style>
