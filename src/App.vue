<template>
  <!-- Agent 独立窗口：极简模式，无背景/粒子/拖拽 -->
  <div v-if="isAgentOnly" class="app agent-only-mode">
    <AgentPanel
      :open="true"
      :standalone="true"
      @update:open="onAgentWindowClose"
      @switch-to-editor="onAgentWindowClose"
    />
  </div>

  <!-- 主窗口：完整布局 -->
  <div
    v-else
    class="app"
    :class="{ 'has-wallpaper': bgSettings.path }"
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

    <!-- 自选背景时的宣纸纹理叠加层 — 统一质感 -->
    <div v-if="bgSettings.path" class="bg-paper-overlay" aria-hidden="true" />

    <!-- 环境光晕 — 缓慢漂移的墨色柔光，鼠标微视差 -->
    <div class="ambient-orb" :style="orbParallaxStyle" aria-hidden="true" />

    <!-- 墨粒子 — 漂浮的墨滴，如墨入水 -->
    <div class="ink-particles" :style="particleParallaxStyle" aria-hidden="true">
      <span class="ink-particle" v-for="i in 15" :key="i" :style="{ '--i': i }" />
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
            <ArgumentMapView v-else-if="appMode === 'argument'" class="arg-mode" />
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
import { checkArgumentMapV2Flag, _openFullArgMapTick } from './composables/useArgumentMap'
import ArgumentMapView from './components/argument/ArgumentMapView.vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { open } from '@tauri-apps/plugin-dialog'
import { useToast } from './composables/useToast'
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
const { pushError } = useToast()

// ── 应用模式 ──────────────────────────────────────────────────
const appMode = ref<AppMode>('editor')

// ── Agent 聊天 ──────────────────────────────────────────────
const showAgentChat = ref(false)

// ── Agent 独立窗口模式 ──────────────────────────────────────
const isAgentOnly = ref(false)
// Detect agent-only mode via URL param — set by AgentPanel's openAgentWindow().
// URL params survive cross-window navigation in Tauri (unlike sessionStorage which is window-isolated).
{
  const _params = new URLSearchParams(window.location.search)
  if (_params.get('agent-only') === '1') {
    isAgentOnly.value = true
    // Clean the URL so refreshing doesn't re-enter agent-only mode accidentally
    const cleanUrl = window.location.pathname
    window.history.replaceState({}, '', cleanUrl)
  }
}

async function onAgentWindowClose() {
  if (isAgentOnly.value) {
    await getCurrentWindow().close()
  }
}

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
const mouseX = ref(0)
const mouseY = ref(0)
const isDark = ref(true)
function applyTheme(dark: boolean) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}
watch(() => isDark.value, applyTheme, { immediate: true })
watch(_openFullArgMapTick, () => { appMode.value = 'argument' })
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

// ── 鼠标微视差：光晕/粒子跟随鼠标 ──
function onMouseMove(e: MouseEvent) {
  mouseX.value = e.clientX
  mouseY.value = e.clientY
}
const orbParallaxStyle = computed(() => {
  const x = (mouseX.value / window.innerWidth - 0.5) * 22
  const y = (mouseY.value / window.innerHeight - 0.5) * 22
  return { transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)` }
})
const particleParallaxStyle = computed(() => {
  const x = (mouseX.value / window.innerWidth - 0.5) * 14
  const y = (mouseY.value / window.innerHeight - 0.5) * 14
  return { transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)` }
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
  } catch (err) {
    // Show error to user - might be browser mode or permission issue
    pushError('背景选择失败，请确保在 Tauri 桌面版中使用')
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


function toggleTheme(e?: MouseEvent) {
  const doc = document.documentElement
  // Capture click position as circle-clip origin
  if (e) {
    doc.style.setProperty('--vt-x', `${e.clientX}px`)
    doc.style.setProperty('--vt-y', `${e.clientY}px`)
  } else {
    doc.style.setProperty('--vt-x', '50%')
    doc.style.setProperty('--vt-y', '50%')
  }
  // View Transition API: cinematic circle-clip dissolve
  if ('startViewTransition' in document) {
    ;document.startViewTransition(() => {
      isDark.value = !isDark.value
      try {
        localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
      } catch (err) { console.warn('saveTheme failed:', err) }
    })
  } else {
    isDark.value = !isDark.value
    try {
      localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
    } catch (err) { console.warn('saveTheme failed:', err) }
  }
}

// --- 拖拽处理 ---

let dragCounter = 0
let timer: ReturnType<typeof setInterval> | null = null
let unlistenDragDrop: (() => void) | null = null

onMounted(async () => {
  checkArgumentMapV2Flag().catch(() => {})
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

  // Mouse parallax for ambient orbs / particles
  window.addEventListener('mousemove', onMouseMove, { passive: true })

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
  window.removeEventListener('mousemove', onMouseMove)
  if (timer) clearInterval(timer)
  if (unlistenDragDrop) unlistenDragDrop()
  if (bootSafetyTimer) { clearTimeout(bootSafetyTimer); bootSafetyTimer = null }
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
      const provider = t.cloud.provider || 'openai'
      const preset = providerPresets.value[provider]
      cloudConfig.value = {
        provider,
        api_key: t.cloud.api_key || '',
        base_url: t.cloud.base_url || preset?.base_url || 'https://api.openai.com/v1',
        model: t.cloud.model || preset?.models?.[0] || 'gpt-4o',
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

function onProviderChange(provider = cloudConfig.value.provider) {
  const preset = providerPresets.value[provider]
  if (preset) {
    cloudConfig.value = {
      ...cloudConfig.value,
      provider,
      base_url: preset.base_url,
      model: preset.models.length > 0 ? preset.models[0] : cloudConfig.value.model,
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

/* ── Focus indicator — 键盘可访问 ── */
:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
  border-radius: var(--radius-xs);
}

/* ── Typography scale: 标题衬线 / 正文无衬线 ── */
h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-weight: 600;
  color: var(--c-text-0);
  line-height: var(--leading-tight);
}
h1 { font-size: var(--text-display-lg); letter-spacing: var(--tracking-display); }
h2 { font-size: var(--text-display); letter-spacing: var(--tracking-tight); }
h3 { font-size: var(--text-2xl); }
h4 { font-size: var(--text-xl); }
h5 { font-size: var(--text-lg); }
h6 { font-size: var(--text-base); }

/* ── 版心容器：限制内容最大宽度，模拟古籍版面呼吸感 ── */
.page-core {
  max-width: var(--page-width);
  margin-left: auto;
  margin-right: auto;
  padding-left: var(--page-gutter);
  padding-right: var(--page-gutter);
  width: 100%;
}
.page-core--wide {
  max-width: var(--page-width-wide);
}

/* ── Rice paper texture (宣纸纤维纹理) ──
   Three layers:
   1. Fine grain — 砚石微粒 (fractalNoise, high freq)
   2. Fiber streaks — 纸纤维 (anisotropic noise, low freq in X, higher in Y)
   3. Speckles — 纸面杂质斑点 (turbulence with discrete alpha)
   Combined opacity creates realistic handmade paper feel.
   SVG layers are shared between body::after (default bg) and .bg-paper-overlay (custom bg). */
body::after,
.bg-paper-overlay {
  background-image:
    /* Layer 3: Speckles — occasional dark specks like paper impurities */
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='s'%3E%3CfeTurbulence type='turbulence' baseFrequency='0.95' numOctaves='2' seed='7' stitchTiles='stitch'/%3E%3CfeColorMatrix type='matrix' values='1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.04 0'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='discrete' tableValues='0 0 0 0 0 0 0 0 0 0 0 0 0 0 1'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23s)'/%3E%3C/svg%3E"),
    /* Layer 2: Fiber streaks — directional cellulose fibers */
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='400'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.008 0.22' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='matrix' values='1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.06 0'/%3E%3C/filter%3E%3Crect width='400' height='400' filter='url(%23f)'/%3E%3C/svg%3E"),
    /* Layer 1: Fine grain — 砚石微粒基底 */
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.55' numOctaves='5' stitchTiles='stitch'/%3E%3CfeColorMatrix type='matrix' values='1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.07 0'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23g)'/%3E%3C/svg%3E");
  background-size: 300px 300px, 400px 400px, 300px 300px;
  background-repeat: repeat;
}

body::after {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.055;
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  background: var(--c-surface-0);
  color: var(--c-text-0);
}

/* Agent 独立窗口：无背景/粒子/装饰 */
.agent-only-mode {
  background: var(--c-surface-1);
  overflow: hidden;
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

/* ── 自选背景宣纸纹理叠加 — 统一质感 ── */
/* background-image/size/repeat shared with body::after via the combined selector above */
.bg-paper-overlay {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.09;
}

/* Light mode: reduce paper texture against lighter backgrounds */
[data-theme="light"] .bg-paper-overlay { opacity: 0.055; }

/* ── Ambient light orb — 砚池流光，缓慢漂移 ── */
.ambient-orb {
  position: fixed;
  z-index: 0;
  pointer-events: none;
  width: 900px;
  height: 900px;
  border-radius: 50%;
  background: radial-gradient(circle at center,
    rgba(91, 108, 255, 0.10) 0%,
    rgba(91, 108, 255, 0.05) 30%,
    transparent 70%
  );
  filter: blur(70px);
  animation: orb-drift 28s ease-in-out infinite;
  opacity: 0.85;
  transition: transform 1.2s var(--ease-out);
}
@keyframes orb-drift {
  0%   { top: -300px; left: -200px; transform: scale(1); }
  25%  { top: 20%; left: 70%; transform: scale(1.2); }
  50%  { top: 60%; left: 40%; transform: scale(0.85); }
  75%  { top: 10%; left: 10%; transform: scale(1.1); }
  100% { top: -300px; left: -200px; transform: scale(1); }
}

/* Second orb — 朱砂微光 */
.ambient-orb::after {
  content: '';
  position: fixed;
  width: 700px;
  height: 700px;
  border-radius: 50%;
  background: radial-gradient(circle at center,
    rgba(200, 80, 58, 0.06) 0%,
    rgba(200, 80, 58, 0.02) 40%,
    transparent 70%
  );
  filter: blur(80px);
  animation: orb-drift-2 34s ease-in-out infinite;
}
@keyframes orb-drift-2 {
  0%   { top: 70%; left: 80%; transform: scale(1.1); }
  33%  { top: 10%; left: 30%; transform: scale(0.8); }
  66%  { top: 50%; left: -100px; transform: scale(1.15); }
  100% { top: 70%; left: 80%; transform: scale(1.1); }
}

/* ── Ink particles — 墨粒子漂浮，如墨入水 ── */
.ink-particles {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  transition: transform 1.5s var(--ease-out);
}
.ink-particle {
  position: absolute;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 40%,
    rgba(91, 108, 255, 0.15) 0%,
    rgba(91, 108, 255, 0.06) 40%,
    transparent 70%
  );
  filter: blur(3px);
  width: calc(30px + var(--i, 1) * 14px);
  height: calc(30px + var(--i, 1) * 14px);
  top: calc(var(--i, 1) * 11.1%);
  left: calc((var(--i, 1) * 17px + 7px) * 3.7 % 100);
  animation: particle-float calc(18s + var(--i, 1) * 3s) ease-in-out infinite;
  animation-delay: calc(var(--i, 1) * -2.2s);
  opacity: 0;
}
@keyframes particle-float {
  0%   { transform: translate(0, 0) scale(0.6); opacity: 0; }
  10%  { opacity: 0.85; }
  25%  { transform: translate(40px, -30px) scale(1.1); opacity: 0.6; }
  50%  { transform: translate(-25px, -60px) scale(0.85); opacity: 0.35; }
  75%  { transform: translate(-50px, -15px) scale(1.05); opacity: 0.6; }
  90%  { opacity: 0; }
  100% { transform: translate(10px, 10px) scale(0.6); opacity: 0; }
}

/* Light mode adjustments */
[data-theme="light"] .ambient-orb {
  background: radial-gradient(circle at center,
    rgba(91, 108, 255, 0.06) 0%,
    rgba(91, 108, 255, 0.02) 30%,
    transparent 70%
  );
  opacity: 0.65;
}
[data-theme="light"] .ambient-orb::after {
  background: radial-gradient(circle at center,
    rgba(200, 80, 58, 0.035) 0%,
    rgba(200, 80, 58, 0.012) 40%,
    transparent 70%
  );
}
[data-theme="light"] .ink-particle {
  background: radial-gradient(circle at 40% 40%,
    rgba(91, 108, 255, 0.10) 0%,
    rgba(91, 108, 255, 0.03) 40%,
    transparent 70%
  );
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

/* ── Scrollbar — 研墨定制 ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: var(--c-surface-5);
  border-radius: 3px;
  transition: background var(--motion-fast) var(--ease-out);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--c-accent);
}
::-webkit-scrollbar-corner { background: transparent; }

/* ── Light mode overrides ── */

/* Light mode global tweaks */
[data-theme="light"] ::-webkit-scrollbar-thumb { background: var(--c-surface-4); }
[data-theme="light"] ::-webkit-scrollbar-thumb:hover { background: var(--c-accent); }
[data-theme="light"] body::after { opacity: 0.032; }
/* ── View Transition (theme switch) — 影视级墨染过渡 ── */
::view-transition-old(root) {
  animation: vt-old-out 480ms var(--ease-emphasis, cubic-bezier(0.22, 0, 0, 1));
  mix-blend-mode: normal;
}
::view-transition-new(root) {
  animation: vt-new-in 480ms var(--ease-emphasis, cubic-bezier(0.22, 0, 0, 1));
  mix-blend-mode: normal;
}
/* Old theme: brief brightness surge then clip shrink */
@keyframes vt-old-out {
  0%   { filter: brightness(1); clip-path: circle(150vmax at var(--vt-x, 50%) var(--vt-y, 50%)); }
  25%  { filter: brightness(1.35); }
  60%  { filter: brightness(0.55); }
  100% { filter: brightness(0); clip-path: circle(0 at var(--vt-x, 50%) var(--vt-y, 50%)); }
}
/* New theme: clip expand with glow surge → settle */
@keyframes vt-new-in {
  0%   { clip-path: circle(0 at var(--vt-x, 50%) var(--vt-y, 50%)); filter: brightness(1.5) saturate(0.7); }
  30%  { filter: brightness(1.15) saturate(0.85); }
  70%  { filter: brightness(0.92) saturate(0.95); }
  100% { clip-path: circle(150vmax at var(--vt-x, 50%) var(--vt-y, 50%)); filter: brightness(1) saturate(1); }
}
/* Ink-bloom pseudo-element: radial glow ring at transition center */
::view-transition-new(root)::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(circle 120px at var(--vt-x, 50%) var(--vt-y, 50%),
    rgba(91, 108, 255, 0.18) 0%,
    rgba(91, 108, 255, 0.06) 40%,
    transparent 70%
  );
  animation: vt-glow-pulse 480ms ease-out forwards;
}
@keyframes vt-glow-pulse {
  0%   { opacity: 0; }
  25%  { opacity: 1; }
  100% { opacity: 0; }
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

/* ── Wallpaper-aware semi-transparent backgrounds ── */
.app.has-wallpaper {
  --editor-bg: rgba(19, 19, 21, 0.82);
  --sidebar-bg: rgba(19, 19, 21, 0.75);
  --toolbar-bg: rgba(19, 19, 21, 0.78);
  --panel-bg: rgba(19, 19, 21, 0.80);
  --border-color: rgba(46, 46, 52, 0.60);
  --hover-bg: rgba(46, 46, 52, 0.70);
  --active-bg: rgba(66, 66, 74, 0.70);
  --code-bg: rgba(35, 35, 40, 0.75);
  --input-bg: rgba(35, 35, 40, 0.75);
}
[data-theme="light"].has-wallpaper {
  --editor-bg: rgba(250, 250, 250, 0.88);
  --sidebar-bg: rgba(244, 244, 247, 0.85);
  --toolbar-bg: rgba(244, 244, 247, 0.88);
  --panel-bg: rgba(250, 250, 250, 0.88);
  --border-color: rgba(204, 204, 210, 0.60);
  --hover-bg: rgba(226, 226, 230, 0.80);
  --active-bg: rgba(212, 212, 218, 0.80);
  --code-bg: rgba(240, 240, 243, 0.85);
  --input-bg: rgba(244, 244, 247, 0.85);
}
</style>
