<template>
  <main class="main">
    <!-- Upload state -->
    <div v-if="state.status === 'idle' || state.status === 'error'" class="upload-view">
      <div class="drop-card" :class="{ hover: zoneHover }" @click="openFilePicker"
        @dragenter.prevent="zoneHover = true" @dragleave="zoneHover = false">
        <div class="drop-ring">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 16V8m0 0l-3 3m3-3l3 3"/>
            <path d="M2 12c0-4.714 0-7.071 1.464-8.536C4.93 2 7.286 2 12 2c4.714 0 7.071 0 8.535 1.464C22 4.93 22 7.286 22 12c0 4.714 0 7.071-1.465 8.535C19.072 22 16.714 22 12 22s-7.071 0-8.536-1.465C2 19.072 2 16.714 2 12z"/>
          </svg>
        </div>
        <p class="drop-title">点击选择文件或拖拽文件到窗口任意位置</p>
        <p class="drop-hint">支持 PDF、Word、PPT、Excel、TXT、Markdown 等 16 种格式</p>
      </div>
      <div v-if="state.status === 'error' && state.errorMessage" class="error-banner">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        {{ state.errorMessage }}
        <button v-if="!healthOk" class="restart-btn" @click="$emit('restart-backend')">重启后端</button>
      </div>
    </div>

    <!-- Working state -->
    <div v-else-if="state.status !== 'done'" class="work-view">
      <div class="progress-section">
        <div class="progress-header">
          <span class="progress-label">{{ state.stepMessage || '准备中...' }}</span>
          <span class="progress-pct">{{ progress }}%</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        </div>
      </div>

      <div class="steps">
        <div v-for="(label, idx) in stepLabels" :key="idx" class="step-item"
          :class="{ active: idx + 1 === state.currentStep, done: idx + 1 < state.currentStep }">
          <div class="step-dot">
            <svg v-if="idx + 1 < state.currentStep" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <span>{{ label }}</span>
        </div>
      </div>

      <div v-if="state.parsedInfo" class="info-tags">
        <span class="tag">{{ state.parsedInfo.pages }} 页</span>
        <span class="tag">{{ state.parsedInfo.chars.toLocaleString() }} 字符</span>
        <span v-if="state.parsedInfo.dual_column_pages" class="tag accent">{{ state.parsedInfo.dual_column_pages }} 页双栏</span>
      </div>

      <div v-if="state.currentStep === 4 && state.totalChunks > 0" class="sub-progress">
        <div class="sub-track">
          <div class="sub-fill" :style="{ width: `${(state.completedChunks / state.totalChunks) * 100}%` }"></div>
        </div>
        <span>{{ state.completedChunks }} / {{ state.totalChunks }} 块</span>
      </div>

      <div v-if="state.translations.length > 0" class="live">
        <div class="live-label">实时预览</div>
        <div v-for="t in state.translations.slice(-3)" :key="t.index" class="live-item">
          <div class="live-orig">{{ t.original_preview }}</div>
          <div class="live-trans">{{ t.translated_preview }}</div>
        </div>
      </div>
    </div>

    <!-- Done state -->
    <div v-else class="result-view" :style="readStyleVars">
      <div class="result-bar">
        <div class="result-bar-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--c-success)" stroke-width="2.5">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <span class="done-label">翻译完成</span>
          <span v-if="state.chunks.length" class="done-meta">{{ state.chunks.length }} 段 · {{ allSentencePairs.length }} 句</span>
        </div>
        <div class="result-bar-right">
          <button class="btn ghost" :class="{ on: viewMode === 'sentence' }" @click="viewMode = 'sentence'">逐句对照</button>
          <button class="btn ghost" :class="{ on: viewMode === 'parallel' }" @click="viewMode = 'parallel'">段落对照</button>
          <button class="btn ghost" :class="{ on: viewMode === 'markdown' }" @click="viewMode = 'markdown'">全文</button>
          <button class="btn primary" @click="downloadResult">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            下载
          </button>
          <button class="btn outline" @click="reset">新翻译</button>
        </div>
      </div>

      <!-- Sentence view -->
      <div v-if="viewMode === 'sentence' && allSentencePairs.length" class="sentence-view">
        <div v-for="(pair, i) in allSentencePairs" :key="i" class="sent-pair">
          <div class="sent-num">{{ i + 1 }}</div>
          <div class="sent-body">
            <p class="sent-orig">{{ pair.original }}</p>
            <p class="sent-trans">{{ pair.translated }}</p>
          </div>
        </div>
      </div>

      <!-- Parallel view -->
      <div v-else-if="viewMode === 'parallel' && state.chunks.length" class="parallel">
        <div v-for="(chunk, i) in state.chunks" :key="i" class="par-card">
          <div class="par-header">
            <span class="par-badge">{{ i + 1 }} / {{ state.chunks.length }}</span>
          </div>
          <div class="par-body">
            <div class="par-col orig">
              <p v-for="(para, pi) in chunk.original.split(/\n\n+/)" :key="'o'+pi">{{ para }}</p>
            </div>
            <div class="par-divider"></div>
            <div class="par-col trans">
              <p v-for="(para, pi) in chunk.translated.split(/\n\n+/)" :key="'t'+pi">{{ para }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Full text Markdown -->
      <div v-else class="fulltext">
        <div class="md-body" v-html="renderedContent"></div>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTranslate } from '../composables/useTranslate'
import DOMPurify from 'dompurify'

const props = defineProps<{
  healthOk: boolean
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
}>()

defineEmits<{
  (e: 'restart-backend'): void
}>()

const { state, translate, reset, downloadResult, overallProgress } = useTranslate()

const viewMode = ref<'sentence' | 'parallel' | 'markdown'>('sentence')
const zoneHover = ref(false)
const stepLabels = ['解析文档', '清洗文本', '智能分块', '翻译', '格式化输出']

const progress = computed(() => overallProgress())

const readStyleVars = computed(() => ({
  '--read-fs': `${props.readSettings.fontSize}px`,
  '--read-lh': props.readSettings.lineHeight,
  '--read-ff': props.readSettings.fontFamily,
  '--read-trans-color': props.readSettings.transColor,
}))

// ── Sentence splitting & alignment ──

interface SentencePair {
  original: string
  translated: string
}

function splitSentences(text: string, isChinese: boolean): string[] {
  if (!text.trim()) return []
  if (isChinese) {
    return text.split(/(?<=[。！？；…\n])/g).map(s => s.trim()).filter(s => s.length > 0)
  }
  const abbrevs = [
    'et al', 'etc', 'fig', 'eq', 'ref', 'vol', 'no', 'pp', 'cf',
    'e.g', 'i.e', 'vs', 'al', 'ed', 'eds', 'rev', 'proc', 'inst',
    'dept', 'univ', 'sci', 'tech', 'phys', 'chem', 'biol', 'med',
    'hum', 'evol', 'anthrop', 'soc', 'pol', 'econ', 'psych',
    'nat', 'int', 'inc', 'ltd', 'co', 'st', 'dr', 'mr', 'mrs',
    'prof', 'sr', 'jr', 'ph', 'd.c', 'b.a', 'm.a',
  ]
  const placeholders: string[] = []
  let protected_text = text

  protected_text = protected_text.replace(/\b([A-Z])\.\s/g, (m) => {
    const ph = `\x00PH${placeholders.length}\x00`
    placeholders.push(m)
    return ph
  })

  for (const abbr of abbrevs) {
    const re = new RegExp(`\\b${abbr}\\.\\s`, 'gi')
    protected_text = protected_text.replace(re, (m) => {
      const ph = `\x00PH${placeholders.length}\x00`
      placeholders.push(m)
      return ph
    })
  }

  let sentences = protected_text
    .split(/(?<=[.!?])\s+|\n+/g)
    .map(s => s.trim())
    .filter(s => s.length > 0)

  sentences = sentences.map(s => {
    let restored = s
    for (let i = placeholders.length - 1; i >= 0; i--) {
      restored = restored.replace(`\x00PH${i}\x00`, placeholders[i])
    }
    return restored
  })

  sentences = sentences.filter(s => s.length >= 8 || /\b\w{3,}\b/.test(s))

  const merged: string[] = []
  for (const s of sentences) {
    if (merged.length > 0 && s.length < 15 && !/^[A-Z]/.test(s)) {
      merged[merged.length - 1] += ' ' + s
    } else {
      merged.push(s)
    }
  }

  return merged.filter(s => s.trim().length > 0)
}

function alignPairs(en: string[], zh: string[]): SentencePair[] {
  const pairs: SentencePair[] = []

  if (zh.length === 0 && en.length > 0) {
    return [{ original: en.join(' '), translated: '' }]
  }

  if (en.length === 0 && zh.length > 0) {
    return zh.map(z => ({ original: '', translated: z }))
  }

  if (en.length === zh.length) {
    return en.map((e, i) => ({ original: e, translated: zh[i] }))
  }

  if (en.length > zh.length * 2 && zh.length > 0) {
    for (let i = 0; i < zh.length - 1; i++) {
      pairs.push({ original: en[i] ?? '', translated: zh[i] ?? '' })
    }
    const lastIdx = zh.length - 1
    const remainingOrig = en.slice(lastIdx).join(' ')
    pairs.push({ original: remainingOrig, translated: zh[lastIdx] ?? '' })
    return pairs
  }

  if (zh.length > en.length * 2 && en.length > 0) {
    for (let i = 0; i < en.length - 1; i++) {
      pairs.push({ original: en[i] ?? '', translated: zh[i] ?? '' })
    }
    const lastIdx = en.length - 1
    const remainingTrans = zh.slice(lastIdx).join('')
    pairs.push({ original: en[lastIdx] ?? '', translated: remainingTrans })
    return pairs
  }

  const maxLen = Math.max(en.length, zh.length)
  if (maxLen <= 0) return []

  const ratio = zh.length / en.length
  let zhIdx = 0
  for (let enI = 0; enI < en.length; enI++) {
    const targetZh = Math.round((enI + 1) * ratio)
    const targetZhClamped = Math.min(targetZh, zh.length)
    const zhEnd = Math.max(targetZhClamped, zhIdx + 1)
    const translated = zh.slice(zhIdx, zhEnd).join('')
    pairs.push({ original: en[enI], translated })
    zhIdx = zhEnd
  }
  while (zhIdx < zh.length) {
    const lastPair = pairs[pairs.length - 1]
    if (lastPair) {
      lastPair.translated += zh[zhIdx]
    } else {
      pairs.push({ original: '', translated: zh[zhIdx] })
    }
    zhIdx++
  }

  return pairs
}

const allSentencePairs = computed<SentencePair[]>(() => {
  const result: SentencePair[] = []
  for (const chunk of state.chunks) {
    const en = splitSentences(chunk.original, false)
    const zh = splitSentences(chunk.translated, true)
    if (en.length > 0 || zh.length > 0) {
      result.push(...alignPairs(en, zh))
    }
  }
  return result
})

// ── Markdown rendering ──

const renderedContent = computed(() => renderMarkdown(state.finalContent))

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderMarkdown(md: string): string {
  md = escapeHtml(md)

  const extracted: string[] = []

  function extract(re: RegExp, processor: (m: RegExpMatchArray) => string): void {
    md = md.replace(re, (...args) => {
      const ph = `\x00EX${extracted.length}\x00`
      extracted.push(processor(args as unknown as RegExpMatchArray))
      return ph
    })
  }

  extract(/^(?:&gt;)+\s*(.+(?:(?:\n|^)(?:&gt;)+\s*.+)*)/gm, (m) => {
    const lines = m[1].replace(/^(?:&gt;)+\s?/gm, '').split('\n')
    const content = lines
      .map(l => l.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'))
      .join('<br/>')
    return `<blockquote>${content}</blockquote>`
  })

  md = md.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  md = md.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  md = md.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  md = md.replace(/^---$/gm, '<hr/>')

  md = md.replace(/\x00EX(\d+)\x00/g, (_: string, idx: string) => extracted[parseInt(idx)])

  md = md.replace(/\n{2,}/g, '</p><p>')
  md = md.replace(/\n/g, '<br/>')
  md = `<p>${md}</p>`

  md = md.replace(/<p>\s*(<h[1-3]>)/g, '$1')
  md = md.replace(/(<\/h[1-3]>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*(<blockquote>)/g, '$1')
  md = md.replace(/(<\/blockquote>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*(<hr\/>)/g, '$1')
  md = md.replace(/(<hr\/>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*<\/p>/g, '')

  return DOMPurify.sanitize(md)
}

// ── File picker ──

function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.docx,.doc,.txt,.md,.log,.html,.htm,.epub,.rtf,.tex,.csv,.pptx,.xlsx,.srt,.json,.xml'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) translate(file)
  }
  input.click()
}
</script>

<style scoped>
.main { flex: 1; padding: 20px; overflow-y: auto; }

/* Upload */
.upload-view { display: flex; flex-direction: column; align-items: center; padding-top: 8vh; }

.drop-card {
  width: 440px; max-width: 100%; padding: 44px 28px;
  background: var(--c-glass); border: 2px dashed var(--c-glass-border);
  border-radius: 16px; text-align: center; cursor: pointer;
  transition: all 0.25s;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.drop-card:hover, .drop-card.hover {
  border-color: var(--c-accent);
  background: var(--c-accent-bg);
  box-shadow: 0 0 60px var(--c-accent-bg);
}

.drop-ring {
  width: 60px; height: 60px; margin: 0 auto 14px;
  border-radius: 50%; border: 2px solid var(--c-surface-3);
  display: flex; align-items: center; justify-content: center;
  color: var(--c-accent-hover); transition: all 0.25s;
}
.drop-card:hover .drop-ring { border-color: var(--c-accent); background: var(--c-accent-bg); }

.drop-title { font-size: 14px; font-weight: 500; color: var(--c-text-0); }
.drop-hint { font-size: 12px; color: var(--c-text-3); margin-top: 4px; }

.error-banner {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 10px 14px;
  background: var(--c-danger-bg); border: 1px solid var(--c-danger-border);
  border-radius: var(--radius-lg); color: var(--c-danger); font-size: 13px;
}

.restart-btn {
  margin-left: auto; padding: 4px 12px;
  border: 1px solid var(--c-danger-border); border-radius: 6px;
  background: var(--c-danger-bg); color: var(--c-danger);
  font-size: 12px; font-family: inherit; cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.restart-btn:hover { background: rgba(248, 113, 113, 0.22); }

/* Working */
.work-view { max-width: 560px; margin: 0 auto; }
.progress-section { margin-bottom: 24px; }
.progress-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.progress-label { font-size: 14px; color: var(--c-text-0); font-weight: 500; }
.progress-pct { font-size: 14px; color: var(--c-accent-hover); font-weight: 600; }

.progress-track { height: 8px; background: var(--c-surface-2); border-radius: 4px; overflow: hidden; }
.progress-fill {
  height: 100%; border-radius: 4px;
  background: linear-gradient(90deg, var(--c-accent), var(--c-accent-hover));
  transition: width 0.4s ease;
}

.steps { display: flex; gap: 6px; margin-bottom: 20px; }
.step-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 8px 4px; border-radius: 8px;
  background: var(--c-glass); border: 1px solid var(--c-glass-border);
  transition: all 0.3s; font-size: 11px; color: var(--c-text-3);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.step-item.active { border-color: var(--c-accent); background: var(--c-accent-bg); color: var(--c-accent-hover); }
.step-item.done { border-color: rgba(74, 222, 128, 0.25); background: rgba(74, 222, 128, 0.05); color: var(--c-success); }

.step-dot {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
}

.info-tags { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.tag { padding: 4px 10px; background: var(--c-surface-2); border-radius: 6px; font-size: 12px; color: var(--c-text-2); }
.tag.accent { background: var(--c-accent-bg); color: var(--c-accent-hover); }

.sub-progress { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; font-size: 12px; color: var(--c-text-3); }
.sub-track { flex: 1; height: 4px; background: var(--c-surface-2); border-radius: 2px; overflow: hidden; }
.sub-fill { height: 100%; background: var(--c-accent); border-radius: 2px; transition: width 0.3s; }

.live { margin-top: 12px; }
.live-label { font-size: 10px; color: var(--c-text-3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.live-item {
  padding: 10px 12px; margin-bottom: 4px;
  background: var(--c-glass); border-radius: 8px;
  border-left: 3px solid var(--c-accent);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.live-orig { font-size: 12px; color: var(--c-text-3); margin-bottom: 4px; line-height: 1.5; }
.live-trans { font-size: 13px; color: var(--c-text-0); line-height: 1.6; }

/* Result */
.result-view { display: flex; flex-direction: column; height: 100%; }
.result-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0; border-bottom: 1px solid var(--c-surface-3);
  margin-bottom: 16px; flex-shrink: 0;
}
.result-bar-left { display: flex; align-items: center; gap: 10px; }
.done-label { font-size: 16px; font-weight: 600; color: var(--c-success); }
.done-meta { font-size: 13px; color: var(--c-text-3); }
.result-bar-right { display: flex; gap: 8px; }

.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border: none; border-radius: 7px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.btn.primary { background: var(--c-accent); color: #fff; }
.btn.primary:hover { opacity: 0.88; }
.btn.outline { background: transparent; color: var(--c-text-0); border: 1px solid var(--c-surface-3); }
.btn.outline:hover { background: var(--c-surface-2); }
.btn.ghost { background: transparent; color: var(--c-text-0); }
.btn.ghost:hover { color: var(--c-accent-hover); }
.btn.ghost.on { color: #fff; background: var(--c-accent); font-weight: 600; border-radius: 6px; padding: 5px 12px; }

/* Sentence view */
.sentence-view { flex: 1; overflow-y: auto; max-width: 900px; margin: 0 auto; width: 100%; }

.sent-pair { display: flex; gap: 16px; padding: 14px 20px; border-bottom: 1px solid var(--sent-border); transition: background 0.15s; }
.sent-pair:hover { background: var(--c-surface-1); }
.sent-pair:last-child { border-bottom: none; }

.sent-num { flex-shrink: 0; width: 32px; text-align: right; font-size: 13px; color: var(--c-text-3); padding-top: 3px; font-variant-numeric: tabular-nums; }
.sent-body { flex: 1; min-width: 0; }
.sent-orig { font-size: 14px; color: var(--c-text-2); line-height: 1.7; white-space: pre-wrap; word-break: break-word; margin-bottom: 8px; }
.sent-trans {
  font-size: var(--read-fs, 16px); color: var(--read-trans-color, var(--c-text-0)); line-height: var(--read-lh, 1.9);
  white-space: pre-wrap; word-break: break-word; font-weight: 400; font-family: var(--read-ff, system-ui);
}

/* Parallel view */
.parallel { flex: 1; overflow-y: auto; }
.par-card {
  background: var(--c-glass); border: 1px solid var(--c-glass-border);
  border-radius: 12px; margin-bottom: 14px; overflow: hidden;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.par-header { padding: 8px 18px; border-bottom: 1px solid var(--c-surface-3); background: var(--c-surface-2); }
.par-badge { font-size: 12px; color: var(--c-text-3); font-weight: 500; }
.par-body { display: flex; min-height: 0; }
.par-col { flex: 1; padding: 18px; min-width: 0; font-size: 14px; line-height: 1.9; white-space: pre-wrap; word-break: break-word; }
.par-col.orig p { color: var(--c-text-2); }
.par-col.trans p { color: var(--c-text-0); }
.par-divider { width: 1px; background: var(--c-surface-3); flex-shrink: 0; }

/* Full text */
.fulltext {
  flex: 1; overflow-y: auto; background: var(--c-glass);
  border-radius: var(--radius-lg); padding: 24px 28px;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.md-body {
  font-size: var(--read-fs, 15px); line-height: var(--read-lh, 2.0); color: var(--read-trans-color, var(--c-text-0));
  max-width: 800px; margin: 0 auto; font-family: var(--read-ff, system-ui);
}
.md-body h1 { font-size: 22px; font-weight: 700; margin: 24px 0 14px; color: var(--c-accent-hover); }
.md-body h2 { font-size: 18px; font-weight: 600; margin: 20px 0 12px; color: var(--c-text-0); }
.md-body h3 { font-size: 16px; font-weight: 600; margin: 16px 0 10px; color: var(--c-text-0); }
.md-body p { margin-bottom: 14px; }
.md-body blockquote {
  border-left: 3px solid var(--c-accent); padding: 6px 14px;
  color: var(--c-text-2); margin: 10px 0; background: var(--c-accent-bg2);
  border-radius: 0 6px 6px 0;
}
.md-body hr { border: none; border-top: 1px solid var(--c-surface-3); margin: 20px 0; }
.md-body strong { color: var(--c-accent-hover); font-weight: 600; }
</style>
