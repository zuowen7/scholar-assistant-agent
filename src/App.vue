<template>
  <div
    class="app"
    :class="{ light: !isDark }"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <!-- 自定义背景层 -->
    <div class="background-layer" :style="backgroundLayerStyle">
      <video
        v-if="bgSettings.type === 'video' && bgSettings.path"
        ref="bgVideo"
        class="bg-video"
        :src="bgAssetUrl"
        autoplay
        loop
        muted
        playsinline
      ></video>
    </div>

    <!-- 内容遮罩层（半透明，保证可读性） -->
    <div class="content-overlay" :style="{ opacity: bgSettings.path ? 1 : 1 }">
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
      <header class="topbar" data-tauri-drag-region>
        <div class="brand">
          <span class="logo">S</span>
          <div>
            <h1>Scholar Translate</h1>
            <p>学术文献智能翻译</p>
          </div>
        </div>
        <div class="topbar-right">
          <!-- 设置按钮 -->
          <div class="settings-wrapper">
            <button class="topbar-icon-btn settings-btn" :class="{ active: showSettings }" @click.stop="toggleSettings" title="背景设置">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
            <!-- 设置下拉面板 -->
            <div v-if="showSettings" class="settings-panel" @click.stop>
              <div class="settings-title">背景设置</div>
              <div class="settings-actions">
                <button class="settings-action-btn" @click="pickBackground">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                  选择背景
                </button>
                <button class="settings-action-btn danger" @click="clearBackground" :disabled="!bgSettings.path">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <polyline points="3 6 5 6 21 6"/>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  </svg>
                  清除背景
                </button>
              </div>
              <div class="settings-slider">
                <label>不透明度: {{ bgSettings.opacity }}%</label>
                <input type="range" min="5" max="100" :value="bgSettings.opacity" @input="onOpacityChange" class="opacity-slider" />
              </div>
            </div>
          </div>

          <!-- 主题切换按钮 -->
            <button class="topbar-icon-btn" @click="toggleTheme" :title="isDark ? '切换日间模式' : '切换夜间模式'">
              <svg v-if="isDark" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
            </button>

          <!-- 健康状态指示 -->
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

          <!-- 窗口控制按钮 -->
          <div class="window-controls">
            <button class="win-btn minimize" @click="handleMinimize" title="最小化">
              <svg width="12" height="12" viewBox="0 0 12 12">
                <line x1="2" y1="6" x2="10" y2="6" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </button>
            <button class="win-btn maximize" @click="handleToggleMaximize" title="最大化">
              <svg width="12" height="12" viewBox="0 0 12 12">
                <rect x="2" y="2" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1.2" rx="1"/>
              </svg>
            </button>
            <button class="win-btn close" @click="handleClose" title="关闭">
              <svg width="12" height="12" viewBox="0 0 12 12">
                <line x1="2" y1="2" x2="10" y2="10" stroke="currentColor" stroke-width="1.2"/>
                <line x1="10" y1="2" x2="2" y2="10" stroke="currentColor" stroke-width="1.2"/>
              </svg>
            </button>
          </div>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open } from '@tauri-apps/plugin-dialog'
import { convertFileSrc } from '@tauri-apps/api/core'
import { useTranslate } from './composables/useTranslate'

const { state, translate, translateFromPath, reset, checkHealth, checkOllama, startOllama, downloadResult, overallProgress } = useTranslate()

const healthOk = ref(false)
const ollamaOk = ref(false)
const ollamaLoading = ref(false)
const ollamaError = ref<string | null>(null)
const globalDragging = ref(false)
const zoneHover = ref(false)
const isDark = ref(true)
const viewMode = ref<'sentence' | 'parallel' | 'markdown'>('sentence')
const stepLabels = ['解析 PDF', '清洗文本', '智能分块', '翻译', '格式化输出']

const progress = computed(() => overallProgress())

// --- 窗口控制 ---

const appWindow = getCurrentWindow()

async function handleMinimize() {
  await appWindow.minimize()
}

async function handleToggleMaximize() {
  await appWindow.toggleMaximize()
}

async function handleClose() {
  await appWindow.close()
}

// --- 自定义背景 ---

interface BackgroundSettings {
  path: string
  type: 'image' | 'video'
  opacity: number
}

const bgSettings = ref<BackgroundSettings>({
  path: '',
  type: 'image',
  opacity: 30,
})

const showSettings = ref(false)

const bgAssetUrl = computed(() => {
  if (!bgSettings.value.path) return ''
  try {
    return convertFileSrc(bgSettings.value.path)
  } catch {
    return ''
  }
})

const backgroundLayerStyle = computed(() => {
  const s: Record<string, string> = {}
  const opacity = bgSettings.value.opacity / 100
  if (bgSettings.value.type === 'image' && bgSettings.value.path && bgAssetUrl.value) {
    s['background-image'] = `url("${bgAssetUrl.value}")`
    s['background-size'] = 'cover'
    s['background-position'] = 'center'
    s['background-repeat'] = 'no-repeat'
    s['opacity'] = String(opacity)
  } else if (bgSettings.value.type === 'video' && bgSettings.value.path && bgAssetUrl.value) {
    s['opacity'] = String(opacity)
  } else {
    s['display'] = 'none'
  }
  return s
})

function loadBgSettings() {
  try {
    const raw = localStorage.getItem('bg-settings')
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.path === 'string') {
        bgSettings.value = {
          path: parsed.path || '',
          type: parsed.type === 'video' ? 'video' : 'image',
          opacity: typeof parsed.opacity === 'number' ? parsed.opacity : 30,
        }
      }
    }
  } catch {
    // ignore
  }
}

function saveBgSettings() {
  try {
    localStorage.setItem('bg-settings', JSON.stringify(bgSettings.value))
  } catch {
    // ignore
  }
}

function toggleSettings() {
  showSettings.value = !showSettings.value
}

async function pickBackground() {
  try {
    const selected = await open({
      multiple: false,
      filters: [
        {
          name: '图片与视频',
          extensions: [
            'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg',
            'mp4', 'webm', 'mkv', 'avi', 'mov',
          ],
        },
        { name: '图片', extensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'] },
        { name: '视频', extensions: ['mp4', 'webm', 'mkv', 'avi', 'mov'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    })
    if (!selected) return

    const filePath = typeof selected === 'string' ? selected : (selected as string)
    if (!filePath) return

    const videoExts = ['mp4', 'webm', 'mkv', 'avi', 'mov']
    const ext = filePath.split('.').pop()?.toLowerCase() || ''
    const isVideo = videoExts.includes(ext)

    bgSettings.value = {
      path: filePath,
      type: isVideo ? 'video' : 'image',
      opacity: bgSettings.value.opacity,
    }
    saveBgSettings()
  } catch {
    // dialog not available in non-Tauri
  }
}

function clearBackground() {
  bgSettings.value = { path: '', type: 'image', opacity: 30 }
  saveBgSettings()
}

function onOpacityChange(e: Event) {
  const input = e.target as HTMLInputElement
  bgSettings.value.opacity = parseInt(input.value, 10)
  saveBgSettings()
}

// Close settings panel when clicking outside
function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (showSettings.value && !target.closest('.settings-wrapper')) {
    showSettings.value = false
  }
}

function toggleTheme() {
  isDark.value = !isDark.value
  try {
    localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  } catch { /* ignore */ }
}

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
  // Protect abbreviations from being split
  // 1. Single uppercase letter + period (e.g. "J." "A.")
  // 2. Common academic abbreviations
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

  // Protect single-letter abbreviations (A. B. C. etc.)
  protected_text = protected_text.replace(/\b([A-Z])\.\s/g, (m) => {
    const ph = `\x00PH${placeholders.length}\x00`
    placeholders.push(m)
    return ph
  })

  // Protect known multi-char abbreviations
  for (const abbr of abbrevs) {
    const re = new RegExp(`\\b${abbr}\\.\\s`, 'gi')
    protected_text = protected_text.replace(re, (m) => {
      const ph = `\x00PH${placeholders.length}\x00`
      placeholders.push(m)
      return ph
    })
  }

  // Split on sentence-ending punctuation followed by space or newline
  let sentences = protected_text
    .split(/(?<=[.!?])\s+|\n+/g)
    .map(s => s.trim())
    .filter(s => s.length > 0)

  // Restore placeholders
  sentences = sentences.map(s => {
    let restored = s
    for (let i = placeholders.length - 1; i >= 0; i--) {
      restored = restored.replace(`\x00PH${i}\x00`, placeholders[i])
    }
    return restored
  })

  // Filter out very short meaningless fragments (< 8 chars and no word content)
  sentences = sentences.filter(s => s.length >= 8 || /\b\w{3,}\b/.test(s))

  // Merge fragments that are clearly not complete sentences
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

  // 如果翻译句子明显少于原文（LLM 截断），尝试将剩余原文合并到最后一对
  if (zh.length === 0 && en.length > 0) {
    // 整个 chunk 都没翻译出来，合并为一条
    return [{ original: en.join(' '), translated: '' }]
  }

  if (en.length > zh.length * 2 && zh.length > 0) {
    // 翻译严重不足：前 N 条正常对齐，剩余原文合并到最后一条
    for (let i = 0; i < zh.length - 1; i++) {
      pairs.push({ original: en[i] ?? '', translated: zh[i] ?? '' })
    }
    // 最后一条翻译对应剩余所有原文
    const lastIdx = zh.length - 1
    const remainingOrig = en.slice(lastIdx).join(' ')
    pairs.push({ original: remainingOrig, translated: zh[lastIdx] ?? '' })
    return pairs
  }

  // 正常对齐
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

// --- 简易 Markdown -> HTML (BUG-11 fix: handle blockquotes before escaping) ---

function renderMarkdown(md: string): string {
  // Step 1: Extract blockquote lines before HTML escaping
  const blockquoteMap: string[] = []
  let text = md.replace(/^(>+\s*.+)$/gm, (match) => {
    const placeholder = `\x00BQ${blockquoteMap.length}\x00`
    blockquoteMap.push(match)
    return placeholder
  })

  // Step 2: Escape HTML entities in the remaining text
  text = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Step 3: Process markdown on escaped text (headings, bold, hr)
  text = text
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^---$/gm, '<hr/>')

  // Step 4: Restore blockquotes (with proper HTML conversion)
  text = text.replace(/\x00BQ(\d+)\x00/g, (_match, idx: string) => {
    const raw = blockquoteMap[parseInt(idx, 10)]
    // Convert the blockquote: strip the leading ">" markers and wrap
    const content = raw.replace(/^>+\s?/gm, '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    return `<blockquote>${content}</blockquote>`
  })

  // Step 5: Paragraphs and line breaks
  text = text
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p>').replace(/$/, '</p>')

  // Clean up empty paragraphs around block elements
  text = text.replace(/<p>\s*(<h[1-3]>)/g, '$1')
  text = text.replace(/(<\/h[1-3]>)\s*<\/p>/g, '$1')
  text = text.replace(/<p>\s*(<blockquote>)/g, '$1')
  text = text.replace(/(<\/blockquote>)\s*<\/p>/g, '$1')
  text = text.replace(/<p>\s*(<hr\/>)/g, '$1')
  text = text.replace(/(<hr\/>)\s*<\/p>/g, '$1')

  return text
}

const renderedContent = computed(() => renderMarkdown(state.finalContent))

// --- 拖拽处理 ---

let dragCounter = 0
let timer: ReturnType<typeof setInterval> | null = null
let unlistenDragDrop: (() => void) | null = null

onMounted(async () => {
  // Load theme preference
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light') isDark.value = false
  } catch { /* ignore */ }

  // Load background settings
  loadBgSettings()

  // Close settings on outside click
  document.addEventListener('click', onDocumentClick)

  // Health checks
  healthOk.value = await checkHealth()
  ollamaOk.value = await checkOllama()
  timer = setInterval(async () => {
    if (state.status === 'idle') {
      healthOk.value = await checkHealth()
      ollamaOk.value = await checkOllama()
    }
  }, 8000)

  // Tauri v2 native drag-drop events (WebView2 intercepts HTML5 drag)
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
    // Non-Tauri environment: HTML5 drag fallback
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (unlistenDragDrop) unlistenDragDrop()
  document.removeEventListener('click', onDocumentClick)
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
  --overlay-bg: rgba(9, 9, 11, 0.35);
  --shadow: rgba(0, 0, 0, 0.5);
  --accent-bg: rgba(99, 102, 241, 0.08);
  --accent-bg2: rgba(99, 102, 241, 0.05);
  --red-bg: rgba(248, 113, 113, 0.07);
  --red-border: rgba(248, 113, 113, 0.19);
  --sent-border: rgba(39, 39, 42, 0.25);
  --glass-blur: 24px;
  --glass: rgba(19, 19, 22, 0.55);
  --glass2: rgba(28, 28, 32, 0.45);
  --glass-border: rgba(39, 39, 42, 0.5);
  --topbar-bg: rgba(19, 19, 22, 0.6);
}

.light {
  --bg: #f5f5f7;
  --surface: #ffffff;
  --surface2: #f0f0f2;
  --border: #d8d8dc;
  --text: #1a1a2e;
  --text2: #555566;
  --text3: #888899;
  --overlay-bg: rgba(245, 245, 247, 0.35);
  --shadow: rgba(0, 0, 0, 0.1);
  --accent-bg: rgba(99, 102, 241, 0.07);
  --accent-bg2: rgba(99, 102, 241, 0.04);
  --red-bg: rgba(248, 113, 113, 0.08);
  --red-border: rgba(248, 113, 113, 0.25);
  --sent-border: rgba(0, 0, 0, 0.07);
  --glass: rgba(255, 255, 255, 0.55);
  --glass2: rgba(240, 240, 242, 0.45);
  --glass-border: rgba(216, 216, 220, 0.55);
  --topbar-bg: rgba(255, 255, 255, 0.55);
}

html, body { height: 100%; overflow: hidden; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  background: var(--bg); color: var(--text);
  -webkit-font-smoothing: antialiased;
}

.app { height: 100vh; display: flex; flex-direction: column; position: relative; }

/* ── Background Layer ── */
.background-layer {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

.bg-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ── Content Overlay ── */
.content-overlay {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--overlay-bg);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

/* ── Drag Overlay ── */
.drag-overlay {
  position: fixed; inset: 0; z-index: 999;
  background: var(--accent-bg);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;
}
.drag-overlay-content {
  text-align: center; color: var(--accent2);
}
.drag-overlay-content p { margin-top: 12px; font-size: 15px; font-weight: 500; }

/* ── Top Bar ── */
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 8px 12px 20px; background: var(--topbar-bg);
  border-bottom: 1px solid var(--border); flex-shrink: 0;
  -webkit-app-region: drag;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  position: relative; z-index: 100;
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

/* ── Settings Button & Panel ── */
.settings-wrapper {
  position: relative;
  -webkit-app-region: no-drag;
}

.topbar-icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 6px;
  background: transparent; border: none; color: var(--text3);
  cursor: pointer; transition: all 0.15s;
}
.topbar-icon-btn:hover {
  background: var(--surface2);
  color: var(--text);
}
.topbar-icon-btn.active {
  background: var(--surface2);
  color: var(--accent2);
}

.settings-panel {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 6px;
  width: 240px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  box-shadow: 0 8px 32px var(--shadow);
  z-index: 9999;
  -webkit-app-region: no-drag;
}

.settings-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
}

.settings-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
}

.settings-action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 7px 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface2);
  color: var(--text2);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}
.settings-action-btn:hover {
  background: var(--border);
  color: var(--text);
}
.settings-action-btn.danger:hover {
  background: var(--red-bg);
  border-color: var(--red-border);
  color: var(--red);
}
.settings-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.settings-slider {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.settings-slider label {
  font-size: 11px;
  color: var(--text3);
}

.opacity-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--surface2);
  outline: none;
  cursor: pointer;
}
.opacity-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  transition: transform 0.15s;
}
.opacity-slider::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

/* ── Window Controls ── */
.window-controls {
  display: flex;
  align-items: center;
  margin-left: 4px;
  -webkit-app-region: no-drag;
}

.win-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 30px;
  background: transparent; border: none;
  color: var(--text3);
  cursor: pointer;
  transition: all 0.12s;
  border-radius: 4px;
}
.win-btn:hover {
  background: var(--surface2);
  color: var(--text);
}
.win-btn.close:hover {
  background: var(--red);
  color: #fff;
}

/* ── Health Pills ── */
.pill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; padding: 5px 10px; border-radius: 20px;
  background: var(--surface2); color: var(--text3);
  border: none; font-family: inherit;
  -webkit-app-region: no-drag;
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
  background: var(--red-bg); border: 1px solid var(--red-border);
  max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ── Main Area ── */
.main { flex: 1; padding: 20px; overflow-y: auto; }

/* ── Upload View ── */
.upload-view { display: flex; flex-direction: column; align-items: center; padding-top: 8vh; }

.drop-card {
  width: 440px; max-width: 100%; padding: 44px 28px;
  background: var(--glass); border: 2px dashed var(--glass-border);
  border-radius: 16px; text-align: center; cursor: pointer;
  transition: all 0.25s;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.drop-card:hover, .drop-card.hover {
  border-color: var(--accent);
  background: var(--accent-bg);
  box-shadow: 0 0 60px var(--accent-bg);
}

.drop-ring {
  width: 60px; height: 60px; margin: 0 auto 14px;
  border-radius: 50%; border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  color: var(--accent2); transition: all 0.25s;
}
.drop-card:hover .drop-ring { border-color: var(--accent); background: var(--accent-bg); }

.drop-title { font-size: 14px; font-weight: 500; color: var(--text); }
.drop-hint { font-size: 12px; color: var(--text3); margin-top: 4px; }

.error-banner {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding: 10px 14px;
  background: var(--red-bg); border: 1px solid var(--red-border);
  border-radius: var(--radius); color: var(--red); font-size: 13px;
}

/* ── Working View ── */
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

/* Step indicators */
.steps { display: flex; gap: 6px; margin-bottom: 20px; }
.step-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px;
  padding: 8px 4px; border-radius: 8px;
  background: var(--glass); border: 1px solid var(--glass-border);
  transition: all 0.3s; font-size: 11px; color: var(--text3);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.step-item.active { border-color: var(--accent); background: var(--accent-bg); color: var(--accent2); }
.step-item.done { border-color: rgba(74, 222, 128, 0.25); background: rgba(74, 222, 128, 0.05); color: var(--green); }

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
.tag.accent { background: var(--accent-bg); color: var(--accent2); }

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

/* Live preview */
.live { margin-top: 12px; }
.live-label { font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.live-item {
  padding: 10px 12px; margin-bottom: 4px;
  background: var(--glass); border-radius: 8px;
  border-left: 3px solid var(--accent);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.live-orig { font-size: 12px; color: var(--text3); margin-bottom: 4px; line-height: 1.5; }
.live-trans { font-size: 13px; color: var(--text); line-height: 1.6; }

/* ── Result View ── */
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
.btn.ghost { background: transparent; color: var(--text2); }
.btn.ghost:hover { color: var(--text); }
.btn.ghost.on { color: var(--accent2); background: var(--accent-bg); font-weight: 600; }

/* ── Sentence View ── */
.sentence-view { flex: 1; overflow-y: auto; max-width: 900px; margin: 0 auto; width: 100%; }

.sent-pair {
  display: flex; gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--sent-border);
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

/* ── Parallel View ── */
.parallel { flex: 1; overflow-y: auto; }

.par-card {
  background: var(--glass); border: 1px solid var(--glass-border);
  border-radius: 12px; margin-bottom: 14px; overflow: hidden;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
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

/* ── Full Text Markdown ── */
.fulltext {
  flex: 1; overflow-y: auto; background: var(--glass);
  border-radius: var(--radius); padding: 24px 28px;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
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
  color: var(--text2); margin: 10px 0; background: var(--accent-bg2);
  border-radius: 0 6px 6px 0;
}
.md-body hr { border: none; border-top: 1px solid var(--border); margin: 20px 0; }
.md-body strong { color: var(--accent2); font-weight: 600; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Light mode overrides ── */
.light .brand h1 { color: var(--text); }
.light .logo {
  background: linear-gradient(135deg, var(--accent), #7c3aed);
  color: #fff;
}
.light .win-btn.close:hover { background: var(--red); color: #fff; }
.light .btn.primary { color: #fff; }
</style>
