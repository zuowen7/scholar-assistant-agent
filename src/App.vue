<template>
  <div
    class="app"
    @dragenter.prevent="onDragEnter"
    @dragleave.prevent="onDragLeave"
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
      <Transition name="drag-fade">
        <div v-if="globalDragging" class="drag-overlay">
          <div class="drag-card">
            <div class="drag-ring">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 16V8m0 0l-3 3m3-3l3 3"/>
              </svg>
            </div>
            <p class="drag-label">松开以开始翻译</p>
            <p class="drag-hint">支持 PDF、Word、TXT、Markdown 等格式</p>
          </div>
        </div>
      </Transition>

      <!-- 顶栏 -->
      <AppTopBar
        :app-mode="appMode"
        :is-dark="isDark"
        :show-agent-chat="showAgentChat"
        :engine-type="engineType"
        :cloud-config="cloudConfig"
        :provider-presets="providerPresets"
        :cloud-checking="cloudChecking"
        :cloud-ok="cloudOk"
        :cloud-error="cloudError"
        :health-ok="healthOk"
        :ollama-ok="ollamaOk"
        :ollama-loading="ollamaLoading"
        :ollama-error="ollamaError"
        :tectonic-ok="tectonicOk"
        :tectonic-checking="tectonicChecking"
        :bg-settings="bgSettings"
        :read-settings="readSettings"
        :proxy-url="proxyUrl"
        @update:app-mode="appMode = $event"
        @update:show-agent-chat="showAgentChat = $event"
        @update:engine-type="engineType = $event"
        @update:cloud-config="cloudConfig = $event"
        @update:proxy-url="proxyUrl = $event"
        @toggle-theme="toggleTheme($event)"
        @toggle-ollama="toggleOllama"
        @handle-tectonic="handleTectonic"
        @save-engine-settings="saveEngineSettings"
        @test-cloud="testCloudConnection"
        @provider-change="onProviderChange"
        @save-proxy="saveProxy"
        @pick-background="pickBackground"
        @clear-background="clearBackground"
        @opacity-change="onOpacityChange"
        @font-size-change="onFontSizeChange"
        @line-height-change="onLineHeightChange"
        @save-read-settings="saveReadSettings"
        @font-family-change="onFontFamilyChange"
        @color-change="onColorChange"
        @window-minimize="handleMinimize"
        @window-maximize="handleToggleMaximize"
        @window-close="handleClose"
      />

      <!-- Translation recovery banner -->
      <Transition name="v-slide-up">
        <div v-if="showRecoveryBanner" class="recovery-banner">
          <span class="recovery-text">检测到上次未关闭的翻译结果</span>
          <div class="recovery-actions">
            <UiButton variant="primary" size="sm" @click="showRecoveryBanner = false; appMode = 'translate'">恢复查看</UiButton>
            <UiButton variant="ghost" size="sm" @click="showRecoveryBanner = false; discardPersisted()">丢弃</UiButton>
          </div>
        </div>
      </Transition>

      <!-- 主内容区：KeepAlive 保留各模式状态，Transition 提供切换动画 -->
      <div class="mode-container">
        <Transition name="v-page-cross" mode="out-in">
          <KeepAlive>
            <TranslateView
              v-if="appMode === 'translate'"
              :health-ok="healthOk"
              :read-settings="readSettings"
              @restart-backend="handleRestartBackend"
              @open-agent-docs="openAgentDocs"
            />
            <EditorLayout
              v-else-if="appMode === 'editor'"
              :isDark="isDark"
              class="editor-mode"
            />
          </KeepAlive>
        </Transition>
      </div>

      <!-- Agent 聊天面板 -->
      <AgentPanel :open="showAgentChat" @update:open="showAgentChat = $event" @switch-to-editor="appMode = 'editor'" />

      <!-- Global toast notifications -->
      <UiToast />
    </div>

    <Transition name="app-loading-fade">
      <InkBrushLoader
        v-if="appBootLoading"
        overlay
        size="large"
        text="正在整理思路..."
      />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open } from '@tauri-apps/plugin-dialog'
import { convertFileSrc } from '@tauri-apps/api/core'
import { useTranslate } from './composables/useTranslate'
import { useEditor } from './composables/useEditor'
import EditorLayout from './components/EditorLayout.vue'
import AgentPanel from './components/AgentPanel.vue'
import TranslateView from './components/TranslateView.vue'
import AppTopBar from './components/AppTopBar.vue'
import InkBrushLoader from './components/InkBrushLoader.vue'
import UiButton from './components/ui/UiButton.vue'
import UiToast from './components/ui/UiToast.vue'
import type { AppMode } from './types'
import { API_BASE } from './utils/api'

const { state, translate, translateFromPath, cleanup, checkHealth, checkOllama, startOllama, checkCloudApi, getConfig, updateConfig, getProviderPresets, restartBackend, listenBackendCrash, setStatus, setError, setStepMessage, recoverTranslation, discardPersisted } = useTranslate()

// ── 应用模式 ──────────────────────────────────────────────────
const appMode = ref<AppMode>('editor')

// ── Agent 聊天 ──────────────────────────────────────────────
const showAgentChat = ref(false)

function openAgentDocs() {
  showAgentChat.value = true
}
const { cleanup: editorCleanup } = useEditor()

const healthOk = ref(false)
const ollamaOk = ref(false)
const ollamaLoading = ref(false)
const ollamaError = ref<string | null>(null)
const cloudOk = ref(false)
const cloudError = ref<string | null>(null)
const cloudChecking = ref(false)
const tectonicOk = ref(false)
const tectonicChecking = ref(false)
const globalDragging = ref(false)
const isDark = ref(true)
function applyTheme(dark: boolean) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}
watch(() => isDark.value, applyTheme, { immediate: true })
const appBootLoading = ref(true)
const bootLoadingStartedAt = Date.now()
const minBootLoadingMs = 1400
let bootSafetyTimer: ReturnType<typeof setTimeout> | null = null
const showRecoveryBanner = ref(false)

function finishBootLoading() {
  if (bootSafetyTimer) { clearTimeout(bootSafetyTimer); bootSafetyTimer = null }
  const elapsed = Date.now() - bootLoadingStartedAt
  const delay = Math.max(0, minBootLoadingMs - elapsed)
  window.setTimeout(async () => {
    appBootLoading.value = false
    // Check for recoverable translation
    const recovered = await recoverTranslation()
    if (recovered) {
      showRecoveryBanner.value = true
    }
  }, delay)
}

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
const proxyUrl = ref('')

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
  transColor: '',
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
  } catch (e) { console.warn('loadReadSettings failed:', e) }
}

function saveReadSettings() {
  try {
    localStorage.setItem('read-settings', JSON.stringify(readSettings.value))
  } catch (e) { console.warn('saveReadSettings failed:', e) }
}

function onFontSizeChange(value: number) {
  readSettings.value.fontSize = value
  saveReadSettings()
}

function onLineHeightChange(value: number) {
  readSettings.value.lineHeight = value / 10
  saveReadSettings()
}

function onFontFamilyChange(value: string) {
  readSettings.value.fontFamily = value
  saveReadSettings()
}

function onColorChange(value: string) {
  readSettings.value.transColor = value
  saveReadSettings()
}

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

function onOpacityChange(value: number) {
  bgSettings.value.opacity = value
  saveBgSettings()
}


function toggleTheme(_e?: MouseEvent) {
  isDark.value = !isDark.value
  try {
    localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
  } catch (err) { console.warn('saveTheme failed:', err) }
}

// --- 拖拽处理 ---

let dragCounter = 0
let timer: ReturnType<typeof setInterval> | null = null
let unlistenDragDrop: (() => void) | null = null

onMounted(async () => {
  // 安全兜底：最多 5 秒后强制隐藏加载画面
  bootSafetyTimer = setTimeout(() => {
    if (appBootLoading.value) {
      appBootLoading.value = false
    }
  }, 5000)
  try {
  // Load theme preference
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light') isDark.value = false
  } catch (e) { console.warn('loadTheme failed:', e) }

  // Load background settings
  loadBgSettings()

  // Load read settings
  loadReadSettings()

  // Listen for backend crash events (Tauri only)
  listenBackendCrash()

  // Load engine settings from backend config
  await loadEngineSettings()

  // Health checks
  healthOk.value = await checkHealth()
  ollamaOk.value = await checkOllama()
  checkTectonic()
  if (engineType.value === 'cloud') {
    const r = await checkCloudApi()
    cloudOk.value = r.ok
    cloudError.value = r.error ?? null
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
        const r = await checkCloudApi()
        cloudOk.value = r.ok
        cloudError.value = r.error ?? null
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
  } finally {
    finishBootLoading()
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (unlistenDragDrop) unlistenDragDrop()
  cleanup()
  editorCleanup()
})

function onDragEnter(e: Event) {
  e.preventDefault()
  dragCounter++
  globalDragging.value = true
}

function onDragLeave(e: Event) {
  e.preventDefault()
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    globalDragging.value = false
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter = 0
  globalDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    translate(file)
  }
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

// --- Tectonic (LaTeX) ---

async function checkTectonic() {
  tectonicChecking.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/tectonic/status`)
    if (resp.ok) {
      const data = await resp.json()
      tectonicOk.value = data.available === true
    }
  } catch (e) { console.warn('tectonic check failed:', e) }
  finally { tectonicChecking.value = false }
}

function handleTectonic() {
  if (tectonicOk.value) return
  tectonicChecking.value = true
  fetch(`${API_BASE}/api/tectonic/install`, { method: 'POST' })
    .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(d.detail || '安装失败')))
    .then(data => {
      tectonicOk.value = data.success !== false
      if (data.version) {
        // show brief success
      }
    })
    .catch(e => {
      console.error('Tectonic install failed:', e)
      // Fallback: open download page
      window.open('https://github.com/typst/tectonic/releases/latest', '_blank')
    })
    .finally(() => { tectonicChecking.value = false })
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
  // 加载代理配置
  if (config?.network?.proxy) {
    proxyUrl.value = config.network.proxy
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
    const r = await checkCloudApi()
    cloudOk.value = r.ok
    cloudError.value = r.error ?? null
  }
}

async function saveProxy() {
  await updateConfig({
    network: { proxy: proxyUrl.value },
  })
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
  cloudError.value = null
  try {
    // Save first so the backend has the latest config
    await saveEngineSettings()
    const r = await checkCloudApi()
    cloudOk.value = r.ok
    cloudError.value = r.error ?? null
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
/* Design tokens are in src/styles/tokens.css — imported by main.ts */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

html, body { height: 100%; overflow: hidden; }
html { background: var(--c-surface-0); opacity: 1 !important; }

body {
  font-family: var(--font-sans), var(--font-zh);
  background: var(--c-surface-0); color: var(--c-text-0);
  -webkit-font-smoothing: antialiased;
}

/* Paper noise texture — adds depth to the flat dark background */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.045;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 180px 180px;
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  background: var(--c-surface-0);
  color: var(--c-text-0);
}

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
  background: var(--c-surface-0);
}

/* ── Drag Overlay ── */
.drag-overlay {
  position: fixed;
  inset: 8px;
  z-index: 999;
  border-radius: var(--radius-xl);
  border: 2px dashed var(--c-accent);
  background: rgba(99, 102, 241, 0.06);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.drag-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}
.drag-ring {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2px solid var(--c-accent);
  background: var(--c-accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-accent-hover);
  animation: drag-pulse 1.4s ease-in-out infinite;
}
.drag-label {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--c-accent-hover);
}
.drag-hint {
  font-size: var(--text-sm);
  color: var(--c-text-2);
}
@keyframes drag-pulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 var(--c-accent-soft); }
  50% { transform: scale(1.06); box-shadow: 0 0 0 10px transparent; }
}
/* Drag overlay transition */
.drag-fade-enter-active,
.drag-fade-leave-active { transition: opacity var(--motion-base) var(--ease-out); }
.drag-fade-enter-from,
.drag-fade-leave-to { opacity: 0; }

.app-loading-fade-enter-active { transition: opacity 320ms var(--ease-out); }
.app-loading-fade-leave-active { transition: opacity 320ms var(--ease-out), transform 320ms var(--ease-out); }
.app-loading-fade-enter-from { opacity: 0; }
.app-loading-fade-leave-to { opacity: 0; transform: scale(0.96); }

/* ── Agent icon active state (kept here because it's part of topbar) ── */
.editor-mode { flex: 1; min-height: 0; }

/* ── Mode container: KeepAlive + Transition ── */
.mode-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.mode-container > * {
  flex: 1;
  min-height: 0;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--c-surface-3); border-radius: 3px; }

/* ── Light mode overrides ── */

/* Light mode global tweaks */
[data-theme="light"] ::-webkit-scrollbar-thumb { background: var(--c-surface-5); }
[data-theme="light"] ::-webkit-scrollbar-thumb:hover { background: var(--c-surface-3); }
[data-theme="light"] body::after { opacity: 0.028; }
/* ── View Transition (theme switch) ── */
::view-transition-old(root), ::view-transition-new(root) { mix-blend-mode: normal; }
::view-transition-new(root) { animation: vt-clip-in 320ms var(--ease-emphasis, cubic-bezier(0.2, 0, 0, 1)); }
@keyframes vt-clip-in {
  from { clip-path: circle(0 at var(--vt-x, 50%) var(--vt-y, 50%)); }
  to   { clip-path: circle(150vmax at var(--vt-x, 50%) var(--vt-y, 50%)); }
}

/* ── Recovery Banner ── */
.recovery-banner {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 300;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 8px 16px;
  background: color-mix(in srgb, var(--c-surface-1) 92%, transparent);
  backdrop-filter: blur(20px);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-pill);
  box-shadow: var(--elevation-2);
}
.recovery-text { font-size: var(--text-sm); color: var(--c-text-1); }
.recovery-actions { display: flex; gap: 4px; }
</style>
