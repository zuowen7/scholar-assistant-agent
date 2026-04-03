<template>
  <div
    class="app"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <!-- 全局拖拽遮罩 -->
    <div v-if="globalDragging" class="drag-overlay">
      <div class="drag-overlay-content">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 16V8m0 0l-3 3m3-3l3 3"/>
          <path d="M2 12c0-4.714 0-7.071 1.464-8.536C4.93 2 7.286 2 12 2c4.714 0 7.071 0 8.535 1.464C22 4.93 22 7.286 22 12c0 4.714 0 7.071-1.465 8.535C19.072 22 16.714 22 12 22s-7.071 0-8.536-1.465C2 19.072 2 16.714 2 12z"/>
        </svg>
        <p>松开以开始翻译</p>
      </div>
    </div>

    <!-- 顶栏 -->
    <header class="topbar">
      <div class="brand">
        <span class="logo">S</span>
        <div>
          <h1>Scholar Translate</h1>
          <p>学术文献智能翻译</p>
        </div>
      </div>
      <div class="topbar-right">
        <span class="pill" :class="healthOk ? 'ok' : 'off'">
          <span class="pill-dot"></span>后端
        </span>
        <button class="pill pill-btn" :class="ollamaOk ? 'ok' : 'off'" @click="toggleOllama" :disabled="ollamaLoading">
          <span class="pill-dot"></span>
          <template v-if="ollamaLoading">启动中...</template>
          <template v-else-if="ollamaOk">Ollama 在线</template>
          <template v-else>启动 Ollama</template>
        </button>
        <span v-if="ollamaError" class="pill error-text">{{ ollamaError }}</span>
      </div>
    </header>

    <main class="main">
      <!-- 上传态 -->
      <div v-if="state.status === 'idle' || state.status === 'error'" class="upload-view">
        <div class="drop-card" :class="{ hover: zoneHover }" @click="openFilePicker"
          @dragenter.prevent="zoneHover = true" @dragleave="zoneHover = false">
          <div class="drop-ring">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 16V8m0 0l-3 3m3-3l3 3"/>
              <path d="M2 12c0-4.714 0-7.071 1.464-8.536C4.93 2 7.286 2 12 2c4.714 0 7.071 0 8.535 1.464C22 4.93 22 7.286 22 12c0 4.714 0 7.071-1.465 8.535C19.072 22 16.714 22 12 22s-7.071 0-8.536-1.465C2 19.072 2 16.714 2 12z"/>
            </svg>
          </div>
          <p class="drop-title">点击选择 PDF 或拖拽文件到窗口任意位置</p>
          <p class="drop-hint">支持英文学术论文、双栏排版</p>
        </div>
        <div v-if="state.status === 'error' && state.errorMessage" class="error-banner">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ state.errorMessage }}
        </div>
      </div>

      <!-- 工作态：进度 -->
      <div v-else-if="state.status !== 'done'" class="work-view">
        <!-- 总进度条 -->
        <div class="progress-section">
          <div class="progress-header">
            <span class="progress-label">{{ state.stepMessage || '准备中...' }}</span>
            <span class="progress-pct">{{ progress }}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progress + '%' }"></div>
          </div>
        </div>

        <!-- 步骤指示 -->
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

        <!-- 解析信息 -->
        <div v-if="state.parsedInfo" class="info-tags">
          <span class="tag">{{ state.parsedInfo.pages }} 页</span>
          <span class="tag">{{ state.parsedInfo.chars.toLocaleString() }} 字符</span>
          <span v-if="state.parsedInfo.dual_column_pages" class="tag accent">{{ state.parsedInfo.dual_column_pages }} 页双栏</span>
        </div>

        <!-- 翻译子进度 -->
        <div v-if="state.currentStep === 4 && state.totalChunks > 0" class="sub-progress">
          <div class="sub-track">
            <div class="sub-fill" :style="{ width: `${(state.completedChunks / state.totalChunks) * 100}%` }"></div>
          </div>
          <span>{{ state.completedChunks }} / {{ state.totalChunks }} 块</span>
        </div>

        <!-- 实时翻译预览 -->
        <div v-if="state.translations.length > 0" class="live">
          <div class="live-label">实时预览</div>
          <div v-for="(t, i) in state.translations.slice(-3)" :key="i" class="live-item">
            <div class="live-orig">{{ t.original_preview }}</div>
            <div class="live-trans">{{ t.translated_preview }}</div>
          </div>
        </div>
      </div>

      <!-- 完成态 -->
      <div v-else class="result-view">
        <div class="result-bar">
          <div class="result-bar-left">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2.5">
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

        <!-- 逐句对照 -->
        <div v-if="viewMode === 'sentence' && allSentencePairs.length" class="sentence-view">
          <div v-for="(pair, i) in allSentencePairs" :key="i" class="sent-pair">
            <div class="sent-num">{{ i + 1 }}</div>
            <div class="sent-body">
              <p class="sent-orig">{{ pair.original }}</p>
              <p class="sent-trans">{{ pair.translated }}</p>
            </div>
          </div>
        </div>

        <!-- 段落对照 -->
        <div v-else-if="viewMode === 'parallel' && state.chunks.length" class="parallel">
          <div v-for="(chunk, i) in state.chunks" :key="i" class="par-card">
            <div class="par-header">
              <span class="par-badge">{{ i + 1 }} / {{ state.chunks.length }}</span>
            </div>
            <div class="par-body">
              <div class="par-col orig">
                <p>{{ chunk.original }}</p>
              </div>
              <div class="par-divider"></div>
              <div class="par-col trans">
                <p>{{ chunk.translated }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- 全文 Markdown -->
        <div v-else class="fulltext">
          <div class="md-body" v-html="renderedContent"></div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { useTranslate } from './composables/useTranslate'

const { state, translate, translateFromPath, reset, checkHealth, checkOllama, startOllama, downloadResult, overallProgress } = useTranslate()

const healthOk = ref(false)
const ollamaOk = ref(false)
const ollamaLoading = ref(false)
const ollamaError = ref<string | null>(null)
const globalDragging = ref(false)
const zoneHover = ref(false)
const viewMode = ref<'sentence' | 'parallel' | 'markdown'>('sentence')
const stepLabels = ['解析 PDF', '清洗文本', '智能分块', '翻译', '格式化输出']

const progress = computed(() => overallProgress())

// --- 句子拆分与配对 ---

interface SentencePair {
  original: string
  translated: string
}

function splitSentences(text: string, isChinese: boolean): string[] {
  if (!text.trim()) return []
  if (isChinese) {
    return text.split(/(?<=[。！？；…\n])/g).map(s => s.trim()).filter(s => s.length > 0)
  }
  return text.split(/(?<=[.!?])\s+|\n+/g).map(s => s.trim()).filter(s => s.length > 0)
}

function alignPairs(en: string[], zh: string[]): SentencePair[] {
  const pairs: SentencePair[] = []
  const maxLen = Math.max(en.length, zh.length)
  for (let i = 0; i < maxLen; i++) {
    pairs.push({
      original: en[i] ?? '',
      translated: zh[i] ?? '',
    })
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

// --- 简易 Markdown → HTML ---

function renderMarkdown(md: string): string {
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^\> (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/^---$/gm, '<hr/>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p>').replace(/$/, '</p>')
}

const renderedContent = computed(() => renderMarkdown(state.finalContent))

let dragCounter = 0
let timer: ReturnType<typeof setInterval> | null = null
let unlistenDragDrop: (() => void) | null = null

onMounted(async () => {
  healthOk.value = await checkHealth()
  ollamaOk.value = await checkOllama()
  timer = setInterval(async () => {
    if (state.status === 'idle') {
      healthOk.value = await checkHealth()
      ollamaOk.value = await checkOllama()
    }
  }, 8000)

  // Tauri v2 原生拖拽事件（WebView2 会拦截 HTML5 拖拽）
  try {
    unlistenDragDrop = await getCurrentWindow().onDragDropEvent((event) => {
      if (event.payload.type === 'enter') {
        globalDragging.value = true
      } else if (event.payload.type === 'drop') {
        globalDragging.value = false
        zoneHover.value = false
        const paths = event.payload.paths
        if (paths.length > 0 && paths[0].toLowerCase().endsWith('.pdf')) {
          translateFromPath(paths[0])
        }
      } else if (event.payload.type === 'leave') {
        globalDragging.value = false
      }
    })
  } catch {
    // 非 Tauri 环境，使用 HTML5 拖拽降级
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (unlistenDragDrop) unlistenDragDrop()
})

function onDragEnter(e: Event) {
  e.preventDefault()
  dragCounter++
  globalDragging.value = true
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter = 0
  globalDragging.value = false
  zoneHover.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.name.toLowerCase().endsWith('.pdf')) {
    translate(file)
  }
}

function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) translate(file)
  }
  input.click()
}

async function toggleOllama() {
  if (ollamaOk.value) return
  ollamaLoading.value = true
  ollamaError.value = null
  try {
    const err = await startOllama()
    if (err) {
      ollamaError.value = err
    } else {
      ollamaOk.value = true
    }
  } finally {
    ollamaLoading.value = false
  }
}
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

:root {
  --bg: #09090b;
  --surface: #131316;
  --surface2: #1c1c20;
  --border: #27272a;
  --text: #e4e4e7;
  --text2: #a1a1aa;
  --text3: #71717a;
  --accent: #6366f1;
  --accent2: #818cf8;
  --green: #4ade80;
  --red: #f87171;
  --radius: 10px;
}

html, body { height: 100%; overflow: hidden; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  -webkit-font-smoothing: antialiased;
}

.app { height: 100vh; display: flex; flex-direction: column; position: relative; }

/* ── 拖拽遮罩 ── */
.drag-overlay {
  position: fixed; inset: 0; z-index: 999;
  background: rgba(99, 102, 241, 0.08);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-overlay-content {
  text-align: center; color: var(--accent2);
}
.drag-overlay-content p { margin-top: 12px; font-size: 15px; font-weight: 500; }

/* ── 顶栏 ── */
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: var(--surface);
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.brand { display: flex; align-items: center; gap: 10px; }
.logo {
  width: 32px; height: 32px; border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), #a78bfa);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 15px; color: #fff;
}
.brand h1 { font-size: 14px; font-weight: 600; color: #fff; }
.brand p { font-size: 11px; color: var(--text3); margin-top: 1px; }

.topbar-right { display: flex; gap: 8px; align-items: center; }

.pill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; padding: 5px 10px; border-radius: 20px;
  background: var(--surface2); color: var(--text3);
  border: none; font-family: inherit;
}
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text3); flex-shrink: 0; }
.pill.ok .pill-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
.pill.ok { color: var(--green); }
.pill.off .pill-dot { background: var(--red); }

.pill-btn {
  cursor: pointer; transition: all 0.2s;
}
.pill-btn:hover { background: var(--border); }
.pill-btn:disabled { opacity: 0.5; cursor: wait; }
.pill-btn.ok { cursor: default; }
.pill-btn.ok:hover { background: var(--surface2); }

.error-text {
  color: var(--red); font-size: 11px;
  background: #f8717112; border: 1px solid #f8717130;
  max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── 主区域 ── */
.main { flex: 1; padding: 20px; overflow-y: auto; }

/* ── 上传态 ── */
.upload-view { display: flex; flex-direction: column; align-items: center; padding-top: 8vh; }

.drop-card {
  width: 440px; max-width: 100%; padding: 44px 28px;
  background: var(--surface); border: 2px dashed var(--border);
  border-radius: 16px; text-align: center; cursor: pointer;
  transition: all 0.25s;
}
.drop-card:hover, .drop-card.hover {
  border-color: var(--accent);
  background: #6366f108;
  box-shadow: 0 0 60px #6366f110;
}

.drop-ring {
  width: 60px; height: 60px; margin: 0 auto 14px;
  border-radius: 50%; border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); transition: all 0.25s;
}
.drop-card:hover .drop-ring { border-color: var(--accent); background: #6366f115; }

.drop-title { font-size: 14px; font-weight: 500; color: var(--text); }
.drop-hint { font-size: 12px; color: var(--text3); margin-top: 4px; }

.error-banner {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 10px 14px;
  background: #f8717112; border: 1px solid #f8717130;
  border-radius: var(--radius); color: var(--red); font-size: 13px;
}

/* ── 工作态 ── */
.work-view { max-width: 560px; margin: 0 auto; }

.progress-section { margin-bottom: 24px; }
.progress-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.progress-label { font-size: 14px; color: var(--text); font-weight: 500; }
.progress-pct { font-size: 14px; color: var(--accent2); font-weight: 600; }

.progress-track {
  height: 8px; background: var(--surface2);
  border-radius: 4px; overflow: hidden;
}
.progress-fill {
  height: 100%; border-radius: 4px;
  background: linear-gradient(90deg, var(--accent), var(--accent2));
  transition: width 0.4s ease;
}

/* 步骤指示 */
.steps { display: flex; gap: 6px; margin-bottom: 20px; }
.step-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 8px 4px; border-radius: 8px;
  background: var(--surface); border: 1px solid var(--border);
  transition: all 0.3s; font-size: 11px; color: var(--text3);
}
.step-item.active { border-color: var(--accent); background: #6366f112; color: var(--accent2); }
.step-item.done { border-color: #4ade8040; background: #4ade8008; color: var(--green); }

.step-dot {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
}

.info-tags { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.tag {
  padding: 4px 10px; background: var(--surface2); border-radius: 6px;
  font-size: 12px; color: var(--text2);
}
.tag.accent { background: #6366f118; color: var(--accent2); }

.sub-progress {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 16px; font-size: 12px; color: var(--text3);
}
.sub-track {
  flex: 1; height: 4px; background: var(--surface2);
  border-radius: 2px; overflow: hidden;
}
.sub-fill {
  height: 100%; background: var(--accent);
  border-radius: 2px; transition: width 0.3s;
}

/* 实时预览 */
.live { margin-top: 12px; }
.live-label { font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.live-item {
  padding: 10px 12px; margin-bottom: 4px;
  background: var(--surface); border-radius: 8px;
  border-left: 3px solid var(--accent);
}
.live-orig { font-size: 12px; color: var(--text3); margin-bottom: 4px; line-height: 1.5; }
.live-trans { font-size: 13px; color: var(--text); line-height: 1.6; }

/* ── 结果态 ── */
.result-view { display: flex; flex-direction: column; height: 100%; }

.result-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 0; border-bottom: 1px solid var(--border);
  margin-bottom: 16px; flex-shrink: 0;
}
.result-bar-left { display: flex; align-items: center; gap: 10px; }
.done-label { font-size: 16px; font-weight: 600; color: var(--green); }
.done-meta { font-size: 13px; color: var(--text3); }
.result-bar-right { display: flex; gap: 8px; }

.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 14px; border: none; border-radius: 7px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.btn.primary { background: var(--accent); color: #fff; }
.btn.primary:hover { background: #5558e6; }
.btn.outline { background: transparent; color: var(--text2); border: 1px solid var(--border); }
.btn.outline:hover { background: var(--surface2); }
.btn.ghost { background: transparent; color: var(--text3); }
.btn.ghost:hover { color: var(--text); }
.btn.ghost.on { color: var(--accent2); background: #6366f115; }

/* ── 逐句对照 ── */
.sentence-view { flex: 1; overflow-y: auto; max-width: 900px; margin: 0 auto; width: 100%; }

.sent-pair {
  display: flex; gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid #27272a40;
  transition: background 0.15s;
}
.sent-pair:hover { background: var(--surface); }
.sent-pair:last-child { border-bottom: none; }

.sent-num {
  flex-shrink: 0; width: 32px; text-align: right;
  font-size: 13px; color: var(--text3); padding-top: 3px;
  font-variant-numeric: tabular-nums;
}

.sent-body { flex: 1; min-width: 0; }
.sent-orig {
  font-size: 14px; color: var(--text2); line-height: 1.7;
  white-space: pre-wrap; word-break: break-word;
  margin-bottom: 8px;
}
.sent-trans {
  font-size: 16px; color: var(--text); line-height: 1.9;
  white-space: pre-wrap; word-break: break-word;
  font-weight: 400;
}

/* ── 段落对照 ── */
.parallel { flex: 1; overflow-y: auto; }

.par-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; margin-bottom: 14px; overflow: hidden;
}
.par-header {
  padding: 8px 18px; border-bottom: 1px solid var(--border);
  background: var(--surface2);
}
.par-badge {
  font-size: 12px; color: var(--text3); font-weight: 500;
}
.par-body { display: flex; min-height: 0; }
.par-col {
  flex: 1; padding: 18px; min-width: 0;
  font-size: 14px; line-height: 1.9;
  white-space: pre-wrap; word-break: break-word;
}
.par-col.orig p { color: var(--text2); }
.par-col.trans p { color: var(--text); }
.par-divider {
  width: 1px; background: var(--border); flex-shrink: 0;
}

/* ── 全文 Markdown ── */
.fulltext {
  flex: 1; overflow-y: auto; background: var(--surface);
  border-radius: var(--radius); padding: 24px 28px;
}
.md-body {
  font-size: 15px; line-height: 2.0; color: var(--text);
  max-width: 800px;
}
.md-body h1 { font-size: 22px; font-weight: 700; margin: 24px 0 14px; color: var(--accent2); }
.md-body h2 { font-size: 18px; font-weight: 600; margin: 20px 0 12px; color: var(--text); }
.md-body h3 { font-size: 16px; font-weight: 600; margin: 16px 0 10px; color: var(--text); }
.md-body p { margin-bottom: 14px; }
.md-body blockquote {
  border-left: 3px solid var(--accent); padding: 6px 14px;
  color: var(--text2); margin: 10px 0; background: #6366f108;
  border-radius: 0 6px 6px 0;
}
.md-body hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
.md-body strong { color: var(--accent2); font-weight: 600; }

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
