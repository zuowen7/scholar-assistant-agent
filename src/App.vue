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
    <div class="content-overlay">
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
          <!-- 引擎设置按钮 -->
          <div class="settings-wrapper">
            <button class="topbar-icon-btn settings-btn" :class="{ active: showEngineSettings }" @click.stop="showEngineSettings = !showEngineSettings; showSettings = false" title="翻译引擎设置">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
              </svg>
            </button>
            <!-- 引擎设置面板 -->
            <div v-if="showEngineSettings" class="settings-panel engine-panel" @click.stop>
              <div class="settings-title">翻译引擎</div>
              <div class="engine-switch">
                <button class="engine-tab" :class="{ active: engineType === 'ollama' }" @click="engineType = 'ollama'; saveEngineSettings()">
                  本地 Ollama
                </button>
                <button class="engine-tab" :class="{ active: engineType === 'cloud' }" @click="engineType = 'cloud'; saveEngineSettings()">
                  云端 API
                </button>
              </div>
              <div v-if="engineType === 'cloud'" class="cloud-settings">
                <div class="cloud-field">
                  <label>供应商</label>
                  <select v-model="cloudConfig.provider" @change="onProviderChange" class="cloud-select">
                    <option v-for="(preset, key) in providerPresets" :key="key" :value="key">{{ preset.name }}</option>
                  </select>
                </div>
                <div class="cloud-field">
                  <label>API Key</label>
                  <input type="password" v-model="cloudConfig.api_key" class="cloud-input" placeholder="输入 API Key" />
                </div>
                <div class="cloud-field">
                  <label>Base URL</label>
                  <input type="text" v-model="cloudConfig.base_url" class="cloud-input" placeholder="https://api.openai.com/v1" />
                </div>
                <div class="cloud-field">
                  <label>模型</label>
                  <div class="model-input-row">
                    <input type="text" v-model="cloudConfig.model" class="cloud-input" placeholder="gpt-4o" />
                    <select v-if="providerPresets[cloudConfig.provider]?.models?.length" class="cloud-select model-select" @change="cloudConfig.model = ($event.target as HTMLSelectElement).value">
                      <option value="" disabled selected>预设</option>
                      <option v-for="m in providerPresets[cloudConfig.provider]?.models || []" :key="m" :value="m">{{ m }}</option>
                    </select>
                  </div>
                </div>
                <div class="cloud-actions">
                  <button class="settings-action-btn" :disabled="cloudChecking || !cloudConfig.api_key" @click="testCloudConnection">
                    <template v-if="cloudChecking">测试中...</template>
                    <template v-else>测试连接</template>
                  </button>
                  <button class="settings-action-btn primary-btn" @click="saveEngineSettings">保存</button>
                </div>
                <div v-if="cloudConfig.api_key" class="cloud-status-hint" :class="cloudOk ? 'ok' : 'off'">
                  {{ cloudOk ? '已连接' : '未连接' }}
                </div>
              </div>
            </div>
          </div>

          <!-- 背景设置按钮 -->
          <div class="settings-wrapper">
            <button class="topbar-icon-btn settings-btn" :class="{ active: showSettings }" @click.stop="toggleSettings" title="背景设置">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="3"/>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
            </button>
            <div v-if="showSettings" class="settings-panel settings-panel-wide" @click.stop>
              <div class="settings-title">显示设置</div>
              <!-- 阅读设置 -->
              <div class="settings-section-label">阅读</div>
              <div class="settings-slider">
                <label>字号: {{ readSettings.fontSize }}px</label>
                <input type="range" min="12" max="28" :value="readSettings.fontSize" @input="onFontSizeChange" class="opacity-slider" />
              </div>
              <div class="settings-slider">
                <label>行高: {{ readSettings.lineHeight }}</label>
                <input type="range" min="14" max="32" :value="Math.round(readSettings.lineHeight * 10)" @input="onLineHeightChange" class="opacity-slider" />
              </div>
              <div class="cloud-field">
                <label>字体</label>
                <select v-model="readSettings.fontFamily" @change="saveReadSettings" class="cloud-select">
                  <option value="system-ui">系统默认</option>
                  <option value="'Noto Sans SC', sans-serif">思源黑体</option>
                  <option value="'Noto Serif SC', serif">思源宋体</option>
                  <option value="'LXGW WenKai', serif">霞鹜文楷</option>
                  <option value="'Microsoft YaHei', sans-serif">微软雅黑</option>
                  <option value="SimSun, serif">宋体</option>
                </select>
              </div>
              <div class="cloud-field">
                <label>译文颜色</label>
                <div class="color-row">
                  <input type="color" v-model="readSettings.transColor" @input="saveReadSettings" class="color-picker" />
                  <span class="color-hex">{{ readSettings.transColor }}</span>
                </div>
              </div>
              <!-- 背景设置 -->
              <div class="settings-section-label" style="margin-top: 10px;">背景</div>
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
          <!-- Ollama 状态（仅本地模式显示） -->
          <template v-if="engineType === 'ollama'">
            <button class="pill pill-btn" :class="ollamaOk ? 'ok' : 'off'" @click="toggleOllama" :disabled="ollamaLoading">
              <span class="pill-dot"></span>
              <template v-if="ollamaLoading">启动中...</template>
              <template v-else-if="ollamaOk">Ollama 在线</template>
              <template v-else>启动 Ollama</template>
            </button>
            <span v-if="ollamaError" class="pill error-text">{{ ollamaError }}</span>
          </template>
          <!-- 云端 API 状态（仅云端模式显示） -->
          <template v-if="engineType === 'cloud'">
            <span class="pill" :class="cloudOk ? 'ok' : 'off'">
              <span class="pill-dot"></span>
              <template v-if="cloudOk">云端已连接</template>
              <template v-else>云端未连接</template>
            </span>
          </template>

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
            <p class="drop-title">点击选择文件或拖拽文件到窗口任意位置</p>
            <p class="drop-hint">支持 PDF、Word、PPT、Excel、TXT、Markdown 等 16 种格式</p>
          </div>
          <div v-if="state.status === 'error' && state.errorMessage" class="error-banner">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            {{ state.errorMessage }}
            <button v-if="!healthOk" class="restart-btn" @click="handleRestartBackend">重启后端</button>
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
            <div v-for="t in state.translations.slice(-3)" :key="t.index" class="live-item">
              <div class="live-orig">{{ t.original_preview }}</div>
              <div class="live-trans">{{ t.translated_preview }}</div>
            </div>
          </div>
        </div>

        <!-- 完成态 -->
        <div v-else class="result-view" :style="readStyleVars">
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
                  <p v-for="(para, pi) in chunk.original.split(/\n\n+/)" :key="'o'+pi">{{ para }}</p>
                </div>
                <div class="par-divider"></div>
                <div class="par-col trans">
                  <p v-for="(para, pi) in chunk.translated.split(/\n\n+/)" :key="'t'+pi">{{ para }}</p>
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

const { state, translate, translateFromPath, reset, cleanup, checkHealth, checkOllama, startOllama, downloadResult, overallProgress, checkCloudApi, getConfig, updateConfig, getProviderPresets, restartBackend, listenBackendCrash, setStatus, setError, setStepMessage } = useTranslate()

const healthOk = ref(false)
const ollamaOk = ref(false)
const ollamaLoading = ref(false)
const ollamaError = ref<string | null>(null)
const cloudOk = ref(false)
const cloudChecking = ref(false)
const globalDragging = ref(false)
const zoneHover = ref(false)
const isDark = ref(true)
const viewMode = ref<'sentence' | 'parallel' | 'markdown'>('sentence')
const stepLabels = ['解析文档', '清洗文本', '智能分块', '翻译', '格式化输出']

// --- Translation engine settings ---
const engineType = ref<'ollama' | 'cloud'>('ollama')
const cloudConfig = ref({
  provider: 'openai',
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o',
  max_tokens: 16384,
})
const providerPresets = ref<Record<string, { name: string; base_url: string; models: string[] }>>({})
const showEngineSettings = ref(false)

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

// --- 阅读设置 ---

interface ReadSettings {
  fontSize: number
  lineHeight: number
  fontFamily: string
  transColor: string
}

const readSettings = ref<ReadSettings>({
  fontSize: 16,
  lineHeight: 1.9,
  fontFamily: 'system-ui',
  transColor: '#e4e4e7',
})

function loadReadSettings() {
  try {
    const raw = localStorage.getItem('read-settings')
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.fontSize === 'number') {
        readSettings.value = { ...readSettings.value, ...parsed }
      }
    }
  } catch { /* ignore */ }
}

function saveReadSettings() {
  try {
    localStorage.setItem('read-settings', JSON.stringify(readSettings.value))
  } catch { /* ignore */ }
}

function onFontSizeChange(e: Event) {
  readSettings.value.fontSize = parseInt((e.target as HTMLInputElement).value, 10)
  saveReadSettings()
}

function onLineHeightChange(e: Event) {
  readSettings.value.lineHeight = parseInt((e.target as HTMLInputElement).value, 10) / 10
  saveReadSettings()
}

const readStyleVars = computed(() => ({
  '--read-fs': `${readSettings.value.fontSize}px`,
  '--read-lh': readSettings.value.lineHeight,
  '--read-ff': readSettings.value.fontFamily,
  '--read-trans-color': readSettings.value.transColor,
}))

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
  if (showEngineSettings.value && !target.closest('.settings-wrapper')) {
    showEngineSettings.value = false
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

// --- 简易 Markdown -> HTML ---

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
  // 先将全文 HTML 转义，阻断 XSS 注入
  md = escapeHtml(md)

  const extracted: string[] = []

  function extract(re: RegExp, processor: (m: RegExpMatchArray) => string): void {
    md = md.replace(re, (...args) => {
      const ph = `\x00EX${extracted.length}\x00`
      extracted.push(processor(args as unknown as RegExpMatchArray))
      return ph
    })
  }

  // 引用块 (已被转义为 &gt;)
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

  return md
}

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

  // Load read settings
  loadReadSettings()

  // Close settings on outside click
  document.addEventListener('click', onDocumentClick)

  // Listen for backend crash events (Tauri only)
  listenBackendCrash()

  // Load engine settings from backend config
  await loadEngineSettings()

  // Health checks
  healthOk.value = await checkHealth()
  ollamaOk.value = await checkOllama()
  if (engineType.value === 'cloud') {
    cloudOk.value = await checkCloudApi()
  }
  timer = setInterval(async () => {
    if (state.status === 'idle') {
      const prev = healthOk.value
      healthOk.value = await checkHealth()
      // 后端从在线变为离线且非用户主动关闭 → 提示重启
      if (prev && !healthOk.value) {
        setError('Python 后端已离线，请点击「重启后端」')
      }
      if (engineType.value === 'ollama') {
        ollamaOk.value = await checkOllama()
      } else {
        cloudOk.value = await checkCloudApi()
      }
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
        const supportedExts = ['.pdf','.docx','.doc','.txt','.md','.html','.htm','.epub','.rtf','.tex','.csv','.pptx','.xlsx','.srt','.json','.xml','.log']
        if (paths.length > 0 && supportedExts.some(ext => paths[0].toLowerCase().endsWith(ext))) {
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
  cleanup()
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
  if (file) {
    translate(file)
  }
}

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

// --- Engine settings ---

async function loadEngineSettings() {
  const presets = await getProviderPresets()
  if (presets) providerPresets.value = presets

  const config = await getConfig()
  if (config?.translator) {
    const t = config.translator
    engineType.value = (t.engine as 'ollama' | 'cloud') || 'ollama'
    if (t.cloud) {
      cloudConfig.value = {
        provider: t.cloud.provider || 'openai',
        api_key: t.cloud.api_key || '',
        base_url: t.cloud.base_url || 'https://api.openai.com/v1',
        model: t.cloud.model || 'gpt-4o',
        max_tokens: t.cloud.max_tokens || 16384,
      }
    }
  }
}

async function saveEngineSettings() {
  await updateConfig({
    translator: { engine: engineType.value },
    cloud: { ...cloudConfig.value },
  })
  // If switched to cloud, check connectivity
  if (engineType.value === 'cloud') {
    cloudOk.value = false
    cloudOk.value = await checkCloudApi()
  }
}

function onProviderChange() {
  const preset = providerPresets.value[cloudConfig.value.provider]
  if (preset) {
    cloudConfig.value.base_url = preset.base_url
    if (preset.models.length > 0) {
      cloudConfig.value.model = preset.models[0]
    }
  }
}

async function testCloudConnection() {
  cloudChecking.value = true
  try {
    // Save first so the backend has the latest config
    await saveEngineSettings()
    cloudOk.value = await checkCloudApi()
  } finally {
    cloudChecking.value = false
  }
}

async function handleRestartBackend() {
  setStepMessage('正在重启后端...')
  setStatus('uploading')
  const ok = await restartBackend()
  if (ok) {
    healthOk.value = true
    setStatus('idle')
  } else {
    setError('后端重启失败，请手动检查 Python 环境')
  }
}
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap') /* offline fallback to system-ui */;

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

.settings-panel-wide {
  width: 280px;
}

.settings-section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.color-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.color-picker {
  width: 32px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
  background: none;
}

.color-hex {
  font-size: 11px;
  color: var(--text3);
  font-family: monospace;
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

/* ── Engine Settings Panel ── */
.engine-panel {
  width: 320px;
  right: 0;
}

.engine-switch {
  display: flex;
  gap: 4px;
  background: var(--surface2);
  border-radius: 8px;
  padding: 3px;
  margin-bottom: 14px;
}

.engine-tab {
  flex: 1;
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text3);
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}

.engine-tab.active {
  background: var(--accent);
  color: #fff;
}

.engine-tab:not(.active):hover {
  color: var(--text);
}

.cloud-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cloud-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cloud-field label {
  font-size: 11px;
  color: var(--text3);
  font-weight: 500;
}

.cloud-input, .cloud-select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--surface2);
  color: var(--text);
  font-size: 12px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.cloud-input:focus, .cloud-select:focus {
  border-color: var(--accent);
}

.cloud-select {
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 24px;
}

.model-input-row {
  display: flex;
  gap: 4px;
}

.model-input-row .cloud-input {
  flex: 1;
}

.model-select {
  width: auto;
  min-width: 70px;
  flex-shrink: 0;
}

.cloud-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.cloud-actions .settings-action-btn {
  flex: 1;
}

.primary-btn {
  background: var(--accent) !important;
  color: #fff !important;
  border-color: var(--accent) !important;
}

.primary-btn:hover {
  opacity: 0.9;
}

.cloud-status-hint {
  text-align: center;
  font-size: 12px;
  font-weight: 500;
  padding: 6px;
  border-radius: 6px;
}

.cloud-status-hint.ok {
  color: var(--green);
  background: rgba(74, 222, 128, 0.08);
}

.cloud-status-hint.off {
  color: var(--red);
  background: var(--red-bg);
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

.restart-btn {
  margin-left: auto;
  padding: 4px 12px;
  border: 1px solid var(--red-border);
  border-radius: 6px;
  background: rgba(248, 113, 113, 0.12);
  color: var(--red);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.restart-btn:hover {
  background: rgba(248, 113, 113, 0.22);
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
.btn.outline { background: transparent; color: var(--text); border: 1px solid var(--border); }
.btn.outline:hover { background: var(--surface2); }
.btn.ghost { background: transparent; color: var(--text); }
.btn.ghost:hover { color: var(--accent2); }
.btn.ghost.on { color: #fff; background: var(--accent); font-weight: 600; border-radius: 6px; padding: 5px 12px; }

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
  font-size: var(--read-fs, 16px); color: var(--read-trans-color, var(--text)); line-height: var(--read-lh, 1.9);
  white-space: pre-wrap; word-break: break-word;
  font-weight: 400;
  font-family: var(--read-ff, system-ui);
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
  font-size: var(--read-fs, 15px); line-height: var(--read-lh, 2.0); color: var(--read-trans-color, var(--text));
  max-width: 800px;
  margin: 0 auto;
  font-family: var(--read-ff, system-ui);
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
