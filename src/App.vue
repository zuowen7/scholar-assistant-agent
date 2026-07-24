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

  <!-- 主窗口：共享产品外壳 -->
  <div
    v-else
    class="app reference-ui"
    :class="{ 'has-wallpaper': Boolean(bgAssetUrl) }"
    @dragenter.prevent="onDragEnter"
    @dragleave.prevent="onDragLeave"
    @dragover.prevent
    @drop.prevent="onDrop"
  >
    <div class="background-layer" :style="backgroundLayerStyle" aria-hidden="true">
      <video
        v-if="bgSettings.type === 'video' && bgAssetUrl"
        class="bg-video"
        :src="bgAssetUrl"
        autoplay
        loop
        muted
        playsinline
      />
    </div>
    <div class="content-overlay">
      <!-- 全局拖拽遮罩 -->
      <Transition name="drag-fade">
        <div v-if="globalDragging" class="drag-overlay">
          <div class="drag-card">
            <div class="drag-ring">
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <path d="M12 16V8m0 0l-3 3m3-3l3 3" />
              </svg>
            </div>
            <p class="drag-label">{{ t('app.dragToTranslate') }}</p>
            <p class="drag-hint">{{ t('app.dragFormats') }}</p>
          </div>
        </div>
      </Transition>

      <!-- Translation recovery banner -->
      <Transition name="v-slide-up">
        <div v-if="showRecoveryBanner" class="recovery-banner">
          <span class="recovery-text">{{ t('app.recoveryBanner') }}</span>
          <div class="recovery-actions">
            <UiButton variant="primary" size="sm" @click="handleRecoveryView">{{
              t('app.recoveryView')
            }}</UiButton>
            <UiButton variant="ghost" size="sm" @click="handleRecoveryDiscard">{{
              t('app.recoveryDiscard')
            }}</UiButton>
          </div>
        </div>
      </Transition>

      <AppShell
        :active-module="shellSection"
        :recent-files="shellRecentFiles"
        :provider="shellProvider"
        :model="shellModel"
        :model-online="shellModelOnline"
        @navigate="handleShellNavigate"
        @open-recent="handleShellRecent"
        @settings="openLegacySettings"
        @agent="toggleAgentChat(true)"
      >
        <!-- 主内容区：KeepAlive 保留各模式状态 -->
        <div class="mode-container" :class="{ 'mode-enter': modeTransition }">
          <KeepAlive>
            <TranslateView
              v-if="appMode === 'translate'"
              key="translate"
              :health-ok="healthOk"
              :backend-restarting="backendRestarting"
              :read-settings="readSettings"
              @restart-backend="handleRestartBackend"
              @open-agent-docs="openAgentDocs"
            />
            <EditorLayout
              v-else-if="appMode === 'editor'"
              key="editor"
              :isDark="isDark"
              class="editor-mode"
            />
            <ReviewerWorkspace v-else-if="appMode === 'argument'" key="argument" class="arg-mode" />
          </KeepAlive>
        </div>
      </AppShell>

      <SettingsCenter
        v-model="showSettings"
        :is-dark="isDark"
        :engine-type="engineType"
        :cloud-config="cloudConfig"
        :ollama-model="ollamaModel"
        :ollama-models="ollamaModels"
        :ollama-models-loading="ollamaModelsLoading"
        :provider-presets="providerPresets"
        :cloud-checking="cloudChecking"
        :cloud-ok="cloudOk"
        :cloud-error="cloudError"
        :health-ok="healthOk"
        :backend-restarting="backendRestarting"
        :ollama-ok="ollamaOk"
        :ollama-loading="ollamaLoading"
        :ollama-error="ollamaError"
        :tectonic-ok="tectonicOk"
        :tectonic-checking="tectonicChecking"
        :bg-settings="bgSettings"
        :read-settings="readSettings"
        :ui-zoom="uiZoom"
        :proxy-url="proxyUrl"
        :update-checking="updateChecking"
        :update-result="updateResult"
        @update:engine-type="engineType = $event"
        @update:cloud-config="cloudConfig = $event"
        @update:ollama-model="ollamaModel = $event"
        @update:proxy-url="proxyUrl = $event"
        @toggle-theme="toggleTheme"
        @toggle-ollama="toggleOllama"
        @refresh-ollama-models="refreshOllamaModels"
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
        @font-family-change="onFontFamilyChange"
        @color-change="onColorChange"
        @ui-zoom-change="applyUiZoom"
        @voice-settings-change="applyVoiceSettings"
        @restart-backend="handleRestartBackend"
        @check-update="handleCheckUpdate"
        @open-release="openReleasePage"
      />

      <!-- Agent 聊天面板 -->
      <AgentPanel
        :open="showAgentChat"
        @update:open="toggleAgentChat($event)"
        @switch-to-editor="navigateTo('write')"
      />

      <!-- 语音助手 Siri 风格浮层 -->
      <VoiceAssistantView />

      <!-- Global toast notifications -->
      <UiToast />
    </div>

    <Transition name="app-loading-fade">
      <InkBrushLoader v-if="appBootLoading" overlay size="large" :text="t('app.thinking')" />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { useAppMode } from './composables/useAppMode'
import { useVoiceRouter } from './composables/useVoiceRouter'
import { registerAllVoiceCommands } from './composables/voiceCommands'
import { checkArgumentMapV2Flag, _openFullArgMapTick } from './composables/useArgumentMap'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { useToast } from './composables/useToast'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import { useTranslate } from './composables/useTranslate'
import { checkForUpdate } from './composables/useUpdateChecker'
import type { UpdateCheckResult } from './composables/useUpdateChecker'
import { useEditor } from './composables/useEditor'
import EditorLayout from './components/EditorLayout.vue'
import AgentPanel from './components/AgentPanel.vue'
import AppShell from './components/shell/AppShell.vue'
import SettingsCenter from './components/settings/SettingsCenter.vue'
import InkBrushLoader from './components/InkBrushLoader.vue'
import UiButton from './components/ui/UiButton.vue'
import UiToast from './components/ui/UiToast.vue'
import { API_BASE } from './utils/api'
import { useVoiceCommand } from './composables/useVoiceCommand'
import { useGlobalHotkey } from './composables/useGlobalHotkey'
import { useWakeWord } from './composables/useWakeWord'
import { useAgentChat } from './composables/useAgentChat'
import { useFileTree } from './composables/useFileTree'
import VoiceAssistantView from './components/VoiceAssistantView.vue'
import { logger } from './utils/logger'
import { useProject } from './composables/useProject'
import { useUiZoom } from './composables/useUiZoom'
import { useReadSettings } from './composables/useReadSettings'
import { useBackground } from './composables/useBackground'
import { useAppTheme } from './composables/useAppTheme'
import { useAppWindow } from './composables/useAppWindow'

const TranslateView = defineAsyncComponent(() => import('./components/TranslateView.vue'))
const ReviewerWorkspace = defineAsyncComponent(
  () => import('./components/argument/ReviewerWorkspace.vue'),
)

const {
  state,
  translate,
  translateFromPath,
  cleanup,
  checkHealth,
  checkOllama,
  startOllama,
  checkCloudApi,
  getConfig,
  updateConfig,
  getProviderPresets,
  fetchOllamaModels,
  restartBackend,
  listenBackendCrash,
  setBackendError,
  clearBackendError,
  recoverTranslation,
  discardPersisted,
} = useTranslate()
const { pushError, info, success } = useToast()

// ── 应用模式 ──────────────────────────────────────────────────
const { appMode, showAgentChat, modeTransition, setMode, toggleAgentChat } = useAppMode()
const shellSection = ref<'translate' | 'write' | 'mindmap' | 'review'>('write')
const { recentProjects, loadRecentProjects, openProject } = useProject()
const shellRecentFiles = computed(() =>
  recentProjects.value.map((project) => ({
    name: project.name || project.path.split(/[\\/]/).filter(Boolean).pop() || project.path,
    path: project.path,
  })),
)

const shellProvider = computed(() =>
  engineType.value === 'cloud'
    ? providerPresets.value[cloudConfig.value.provider]?.name || cloudConfig.value.provider
    : 'Ollama',
)
const shellModel = computed(() =>
  engineType.value === 'cloud' ? cloudConfig.value.model : ollamaModel.value,
)
const shellModelOnline = computed(() =>
  engineType.value === 'cloud' ? cloudOk.value : ollamaOk.value,
)

type ShellSection = 'translate' | 'write' | 'mindmap' | 'review'

function navigateTo(section: ShellSection) {
  shellSection.value = section
  if (section === 'translate') setMode('translate')
  else if (section === 'review') setMode('argument')
  else {
    setMode('editor')
    window.dispatchEvent(
      new CustomEvent('shell-workspace-mode', {
        detail: section === 'mindmap' ? 'mindmap' : 'editor',
      }),
    )
  }
}

function handleShellNavigate(section: ShellSection) {
  navigateTo(section)
}

// Keep the shell highlight aligned when a non-shell action changes the app
// mode (recovery banner, Agent navigation, argument-map shortcut, etc.).
watch(appMode, (mode) => {
  if (mode === 'translate') shellSection.value = 'translate'
  else if (mode === 'argument') shellSection.value = 'review'
  else if (shellSection.value === 'translate' || shellSection.value === 'review')
    shellSection.value = 'write'
})

async function handleShellRecent(path: string) {
  navigateTo('write')
  await openProject(path).catch((error) =>
    pushError(error instanceof Error ? error.message : '无法打开最近项目'),
  )
}

const showSettings = ref(false)
const { uiZoom, applyUiZoom, handleUiZoomShortcut } = useUiZoom()

function openLegacySettings() {
  showSettings.value = true
}

function handleShellSectionChange(event: Event) {
  const section = (event as CustomEvent).detail
  if (
    section === 'translate' ||
    section === 'write' ||
    section === 'mindmap' ||
    section === 'review'
  ) {
    shellSection.value = section
  }
}

// Register voice commands
registerAllVoiceCommands()

// ── Agent 独立窗口模式 ──
const { isAgentOnly, onAgentWindowClose } = useAppWindow()

function openAgentDocs() {
  toggleAgentChat(true)
}
const { cleanup: editorCleanup } = useEditor()

// ── 语音助手 ──────────────────────────────────────────────────
const voiceCmd = useVoiceCommand()

function handleVoiceCommandTrigger() {
  // Don't force-switch mode or open agent — let the router decide. Clear the
  // previous result so a new listening session never shows stale feedback.
  useVoiceRouter().clearLastResult()
}

function handleVoiceToggleTheme() {
  toggleTheme()
}

function handleVoiceCommandSubmit(e: Event) {
  const { text } = (e as CustomEvent).detail
  if (!text?.trim()) return
  logger.debug('[voice] submitting:', text.trim())

  voiceCmd.setProcessing()

  useVoiceRouter()
    .routeCommand(text.trim())
    .then((result) => {
      if (result.type === 'chat') {
        // Fallback: send to agent chat (existing behavior)
        // Ensure editor mode + agent panel open so user sees the response
        navigateTo('write')
        toggleAgentChat(true)
        const { sendMessage, sending } = useAgentChat()
        const { rootDir } = useFileTree()
        const { activeTab } = useEditor()

        if (sending.value) {
          logger.warn('[voice] Agent is busy; voice request was not submitted')
          voiceCmd.fail(t('voice.agentBusy'))
          return
        }

        // Close voice overlay immediately — user sees response in AgentPanel
        voiceCmd.done()

        sendMessage(
          text.trim(),
          '',
          '',
          rootDir.value || undefined,
          activeTab.value?.path || undefined,
        )
          .then(() => {
            logger.debug('[voice] sendMessage resolved')
          })
          .catch((err) => {
            logger.warn('[voice] sendMessage failed:', err)
          })
      } else {
        // Command dispatched
        logger.debug(
          '[voice] command executed:',
          result.commandId,
          result.success ? 'ok' : result.error,
        )
        if (result.success) voiceCmd.finish()
        else voiceCmd.fail(result.error || t('voice.commandFailed'))
      }
    })
    .catch((err) => {
      logger.warn('[voice] routeCommand failed:', err)
      voiceCmd.fail(err instanceof Error ? err.message : t('voice.commandFailed'))
    })
}

// Read voice settings from localStorage
interface VoiceSettings {
  enabled?: boolean
  hotkey?: string
  wakeWordEnabled?: boolean
  wakeWordPhrase?: string
  sensitivity?: 'low' | 'medium' | 'high'
  language?: string
}
function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem('voice-settings')
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

const voiceSettings = loadVoiceSettings()
// Alt+Space is a Windows system shortcut (window menu) — auto-migrate
if (voiceSettings.hotkey === 'Alt+Space') {
  voiceSettings.hotkey = 'Alt+Shift+V'
  try {
    localStorage.setItem(
      'voice-settings',
      JSON.stringify({ ...voiceSettings, hotkey: 'Alt+Shift+V' }),
    )
  } catch {
    /* ignore */
  }
}
const hotkey = useGlobalHotkey(voiceSettings.hotkey || 'Alt+Shift+V', () => {
  if (voiceSettings.enabled !== false) voiceCmd.triggerVoiceCommand()
})
const wakeWord = useWakeWord(() => {
  if (voiceSettings.enabled !== false) voiceCmd.triggerVoiceCommand()
})

// Start wake word detection on initial mount
if (voiceSettings.wakeWordEnabled !== false) {
  wakeWord.startWakeWord().catch(() => {})
}

async function applyVoiceSettings(settings: Required<VoiceSettings>) {
  const previousHotkey = voiceSettings.hotkey || 'Alt+Shift+V'
  Object.assign(voiceSettings, settings)
  if (settings.hotkey && settings.hotkey !== previousHotkey) {
    await hotkey.changeHotkey(settings.hotkey)
  }
  if (
    settings.enabled !== false &&
    settings.wakeWordEnabled !== false &&
    voiceCmd.state.value === 'idle'
  ) {
    wakeWord.startWakeWord().catch(() => {})
  } else {
    wakeWord.stopWakeWord()
  }
}

window.addEventListener('voice-command-trigger', handleVoiceCommandTrigger)
window.addEventListener('voice-command-submit', handleVoiceCommandSubmit)
window.addEventListener('voice-toggle-theme', handleVoiceToggleTheme)

// Pause wake word during active voice command, resume when idle
watch(
  () => voiceCmd.state.value,
  (s) => {
    if (s !== 'idle') wakeWord?.stopWakeWord()
    else if (voiceSettings.wakeWordEnabled !== false) wakeWord?.startWakeWord().catch(() => {})
  },
)

const healthOk = ref(false)
const backendRestarting = ref(false)
const ollamaOk = ref(false)
const ollamaLoading = ref(false)
const ollamaError = ref<string | null>(null)
const cloudOk = ref(false)
const cloudError = ref<string | null>(null)
const cloudChecking = ref(false)
const tectonicOk = ref(false)
const tectonicChecking = ref(false)
const updateChecking = ref(false)
const updateResult = ref<UpdateCheckResult | null>(null)
const globalDragging = ref(false)
const mouseX = ref(0)
const mouseY = ref(0)
const { isDark, toggleTheme } = useAppTheme()
watch(_openFullArgMapTick, () => {
  navigateTo('review')
})
const appBootLoading = ref(true)
const bootLoadingStartedAt = Date.now()
const minBootLoadingMs = 1400
let bootSafetyTimer: ReturnType<typeof setTimeout> | null = null
const showRecoveryBanner = ref(false)

function handleRecoveryView() {
  showRecoveryBanner.value = false
  navigateTo('translate')
}

function handleRecoveryDiscard() {
  showRecoveryBanner.value = false
  discardPersisted()
}

function finishBootLoading() {
  if (bootSafetyTimer) {
    clearTimeout(bootSafetyTimer)
    bootSafetyTimer = null
  }
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
const providerPresets = ref<Record<string, { name: string; base_url: string; models: string[] }>>(
  {},
)

const ollamaModel = ref('qwen3:8b')
const ollamaModels = ref<string[]>([])
const ollamaModelsLoading = ref(false)

const proxyUrl = ref('')

// --- 窗口控制 ---

const { handleMinimize, handleToggleMaximize, handleClose } = useAppWindow()

// --- 自定义背景 ---

const {
  bgSettings,
  bgDataUrl,
  bgAssetUrl,
  backgroundLayerStyle,
  loadBgSettings,
  saveBgSettings,
  pickBackground,
  pathToDataUrl,
  clearBackground,
  onOpacityChange,
  initBackground,
} = useBackground()

// --- 阅读设置 ---

const {
  readSettings,
  loadReadSettings,
  saveReadSettings,
  onFontSizeChange,
  onLineHeightChange,
  onFontFamilyChange,
  onColorChange,
} = useReadSettings()

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

// --- 拖拽处理 ---

let dragCounter = 0
let timer: ReturnType<typeof setInterval> | null = null
let unlistenDragDrop: (() => void) | null = null

onMounted(async () => {
  window.addEventListener('keydown', handleUiZoomShortcut)
  await applyUiZoom(uiZoom.value)
  checkArgumentMapV2Flag().catch(() => {})
  window.addEventListener('shell-section-change', handleShellSectionChange)
  loadRecentProjects().catch(() => {})
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
      isDark.value = saved === 'dark'
    } catch (e) {
      logger.warn('loadTheme failed:', e)
    }

    // Load background settings + pre-render data URL
    initBackground()

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
    if (ollamaOk.value) refreshOllamaModels()
    checkTectonic()
    if (engineType.value === 'cloud') {
      const r = await checkCloudApi()
      cloudOk.value = r.ok
      cloudError.value = r.error ?? null
    }
    timer = setInterval(async () => {
      // Backend availability is a global shell concern. Keep polling even when
      // a failed request has moved the feature state to `error`, otherwise the
      // settings drawer can remain falsely "online" and hide its restart action.
      const prev = healthOk.value
      healthOk.value = await checkHealth()
      if (prev && !healthOk.value) {
        setBackendError(t('app.backendOffline'))
      }
      if (!healthOk.value || state.status !== 'idle') return

      if (engineType.value === 'ollama') {
        ollamaOk.value = await checkOllama()
      } else {
        const r = await checkCloudApi()
        cloudOk.value = r.ok
        cloudError.value = r.error ?? null
      }
    }, 8000)

    // Check for updates (5s delay, silent on failure)
    setTimeout(async () => {
      const result = await checkForUpdate().catch(() => undefined)
      if (result) updateResult.value = result
    }, 5000)

    // Tauri v2 native drag-drop events (WebView2 intercepts HTML5 drag)
    try {
      unlistenDragDrop = await getCurrentWindow().onDragDropEvent((event) => {
        if (event.payload.type === 'enter') {
          globalDragging.value = true
        } else if (event.payload.type === 'drop') {
          globalDragging.value = false
          const paths = event.payload.paths
          const supportedExts = [
            '.pdf',
            '.docx',
            '.doc',
            '.txt',
            '.md',
            '.html',
            '.htm',
            '.epub',
            '.rtf',
            '.tex',
            '.csv',
            '.pptx',
            '.xlsx',
            '.srt',
            '.json',
            '.xml',
            '.log',
          ]
          if (
            paths.length > 0 &&
            supportedExts.some((ext) => paths[0].toLowerCase().endsWith(ext))
          ) {
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
  window.removeEventListener('keydown', handleUiZoomShortcut)
  window.removeEventListener('shell-section-change', handleShellSectionChange)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('voice-command-trigger', handleVoiceCommandTrigger)
  window.removeEventListener('voice-command-submit', handleVoiceCommandSubmit)
  window.removeEventListener('voice-toggle-theme', handleVoiceToggleTheme)
  hotkey.cleanup()
  wakeWord?.cleanup()
  voiceCmd.cleanup()
  if (timer) clearInterval(timer)
  if (unlistenDragDrop) unlistenDragDrop()
  if (bootSafetyTimer) {
    clearTimeout(bootSafetyTimer)
    bootSafetyTimer = null
  }
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
      refreshOllamaModels()
    }
  } finally {
    ollamaLoading.value = false
  }
}

async function refreshOllamaModels() {
  ollamaModelsLoading.value = true
  try {
    ollamaModels.value = await fetchOllamaModels()
  } catch {
    ollamaModels.value = []
  } finally {
    ollamaModelsLoading.value = false
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
  } catch (e) {
    logger.warn('tectonic check failed:', e)
  } finally {
    tectonicChecking.value = false
  }
}

function handleTectonic() {
  if (tectonicOk.value) return
  tectonicChecking.value = true
  fetch(`${API_BASE}/api/tectonic/install`, { method: 'POST' })
    .then((r) =>
      r.ok ? r.json() : r.json().then((d) => Promise.reject(d.detail || t('app.installFailed'))),
    )
    .then((data) => {
      tectonicOk.value = data.success !== false
      if (data.version) {
        // show brief success
      }
    })
    .catch((e) => {
      console.error('Tectonic install failed:', e)
      // Fallback: open download page
      window.open('https://github.com/typst/tectonic/releases/latest', '_blank')
    })
    .finally(() => {
      tectonicChecking.value = false
    })
}

// --- Engine settings ---

async function loadEngineSettings() {
  const presets = await getProviderPresets()
  if (presets) providerPresets.value = presets

  const config = await getConfig()
  if (config?.translator) {
    const t = config.translator
    engineType.value = (t.engine as 'ollama' | 'cloud') || 'ollama'
    if (t.model) ollamaModel.value = t.model
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
    translator: { engine: engineType.value, model: ollamaModel.value },
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
  if (backendRestarting.value) return
  backendRestarting.value = true
  info(t('app.restartingBackend'))
  try {
    const ok = await restartBackend()
    if (ok) {
      healthOk.value = true
      clearBackendError()
      // The app may have mounted while the backend was unavailable and fallen
      // back to local UI defaults. Reload the authoritative runtime config after
      // recovery so the model badge and settings do not falsely show Ollama.
      await loadEngineSettings()
      if (engineType.value === 'cloud') {
        const result = await checkCloudApi()
        cloudOk.value = result.ok
        cloudError.value = result.error ?? null
      }
      success(t('app.restartSuccess'))
    } else {
      pushError(t('app.restartFailed'))
    }
  } finally {
    backendRestarting.value = false
  }
}

async function handleCheckUpdate() {
  updateChecking.value = true
  try {
    const result = await checkForUpdate({ notify: false })
    updateResult.value = result ?? null
    if (!result) info(t('settingsCenter.updateUnavailable'))
  } finally {
    updateChecking.value = false
  }
}

async function openReleasePage(url: string) {
  if (!/^https:\/\/github\.com\//i.test(url)) return
  try {
    const { open: openExternal } = await import('@tauri-apps/plugin-shell')
    await openExternal(url)
  } catch {
    window.open(url, '_blank', 'noopener,noreferrer')
  }
}
</script>

<style>
/* Design tokens are in src/styles/tokens.css — imported by main.ts */
*,
*::before,
*::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
html {
  background: var(--c-app-bg);
  opacity: 1 !important;
}

body {
  font-family: var(--font-sans), var(--font-zh);
  background: var(--c-app-bg);
  color: var(--c-text-0);
  -webkit-font-smoothing: antialiased;
}

[data-theme='light'],
[data-theme='light'] body,
[data-theme='light'] #app {
  background: #faf8f3;
}

/* ── Focus indicator — 键盘可访问 ── */
button:focus-visible,
[role='button']:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
.u-interactive:focus-visible,
[tabindex]:not([tabindex='-1']):focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}

/* ── Typography scale: 标题衬线 / 正文无衬线 ── */
h1,
h2,
h3,
h4,
h5,
h6 {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-weight: 600;
  color: var(--c-text-0);
  line-height: var(--leading-tight);
}
h1 {
  font-size: var(--text-display-lg);
  letter-spacing: var(--tracking-display);
}
h2 {
  font-size: var(--text-display);
  letter-spacing: var(--tracking-tight);
}
h3 {
  font-size: var(--text-2xl);
}
h4 {
  font-size: var(--text-xl);
}
h5 {
  font-size: var(--text-lg);
}
h6 {
  font-size: var(--text-base);
}

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
  background-size:
    300px 300px,
    400px 400px,
    300px 300px;
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
  background: var(--c-app-bg);
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
[data-theme='light'] .bg-paper-overlay {
  opacity: 0.055;
}

/* ── Ambient light orb — 砚池流光，缓慢漂移 ── */
.ambient-orb {
  position: fixed;
  z-index: 0;
  pointer-events: none;
  width: 900px;
  height: 900px;
  border-radius: 50%;
  background: radial-gradient(
    circle at center,
    rgba(91, 108, 255, 0.1) 0%,
    rgba(91, 108, 255, 0.05) 30%,
    transparent 70%
  );
  filter: blur(70px);
  animation: orb-drift 28s ease-in-out infinite;
  opacity: 0.85;
  transition: transform 1.2s var(--ease-out);
}
@keyframes orb-drift {
  0% {
    top: -300px;
    left: -200px;
    transform: scale(1);
  }
  25% {
    top: 20%;
    left: 70%;
    transform: scale(1.2);
  }
  50% {
    top: 60%;
    left: 40%;
    transform: scale(0.85);
  }
  75% {
    top: 10%;
    left: 10%;
    transform: scale(1.1);
  }
  100% {
    top: -300px;
    left: -200px;
    transform: scale(1);
  }
}

/* Second orb — 朱砂微光 */
.ambient-orb::after {
  content: '';
  position: fixed;
  width: 700px;
  height: 700px;
  border-radius: 50%;
  background: radial-gradient(
    circle at center,
    rgba(200, 80, 58, 0.06) 0%,
    rgba(200, 80, 58, 0.02) 40%,
    transparent 70%
  );
  filter: blur(80px);
  animation: orb-drift-2 34s ease-in-out infinite;
}
@keyframes orb-drift-2 {
  0% {
    top: 70%;
    left: 80%;
    transform: scale(1.1);
  }
  33% {
    top: 10%;
    left: 30%;
    transform: scale(0.8);
  }
  66% {
    top: 50%;
    left: -100px;
    transform: scale(1.15);
  }
  100% {
    top: 70%;
    left: 80%;
    transform: scale(1.1);
  }
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
  background: radial-gradient(
    circle at 40% 40%,
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
  0% {
    transform: translate(0, 0) scale(0.6);
    opacity: 0;
  }
  10% {
    opacity: 0.85;
  }
  25% {
    transform: translate(40px, -30px) scale(1.1);
    opacity: 0.6;
  }
  50% {
    transform: translate(-25px, -60px) scale(0.85);
    opacity: 0.35;
  }
  75% {
    transform: translate(-50px, -15px) scale(1.05);
    opacity: 0.6;
  }
  90% {
    opacity: 0;
  }
  100% {
    transform: translate(10px, 10px) scale(0.6);
    opacity: 0;
  }
}

/* Light mode adjustments */
[data-theme='light'] .ambient-orb {
  background: radial-gradient(
    circle at center,
    rgba(91, 108, 255, 0.06) 0%,
    rgba(91, 108, 255, 0.02) 30%,
    transparent 70%
  );
  opacity: 0.65;
}
[data-theme='light'] .ambient-orb::after {
  background: radial-gradient(
    circle at center,
    rgba(200, 80, 58, 0.035) 0%,
    rgba(200, 80, 58, 0.012) 40%,
    transparent 70%
  );
}
[data-theme='light'] .ink-particle {
  background: radial-gradient(
    circle at 40% 40%,
    rgba(91, 108, 255, 0.1) 0%,
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
  background: var(--c-app-bg);
}

/* ── Drag Overlay ── */
.drag-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
  border: 0;
  background: color-mix(in srgb, var(--c-app-bg) 94%, transparent);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
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
  min-width: 280px;
  padding: 32px 36px;
  border: 1px solid var(--c-border);
  border-radius: 12px;
  background: var(--c-panel);
  box-shadow: var(--elevation-2);
}
.drag-ring {
  width: 56px;
  height: 56px;
  border-radius: 10px;
  border: 1px solid var(--c-border);
  background: var(--c-accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-accent);
}
.drag-label {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--c-text-0);
}
.drag-hint {
  font-size: var(--text-sm);
  color: var(--c-text-2);
}
/* Drag overlay transition */
.drag-fade-enter-active,
.drag-fade-leave-active {
  transition: opacity var(--motion-base) var(--ease-out);
}
.drag-fade-enter-from,
.drag-fade-leave-to {
  opacity: 0;
}

.app-loading-fade-enter-active {
  transition: opacity 320ms var(--ease-out);
}
.app-loading-fade-leave-active {
  transition:
    opacity 320ms var(--ease-out),
    transform 320ms var(--ease-out);
}
.app-loading-fade-enter-from {
  opacity: 0;
}
.app-loading-fade-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

/* ── Agent icon active state (kept here because it's part of topbar) ── */
.editor-mode {
  flex: 1;
  min-height: 0;
}

/* ── Mode container: KeepAlive + Transition ── */
.mode-container {
  flex: 1;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.mode-container > * {
  flex: 1;
  min-height: 0;
}

/* Mode switch animation — replaces Transition mode="out-in" */
.mode-enter {
  animation: mode-cross 300ms var(--ease-out);
}
@keyframes mode-cross {
  0% {
    opacity: 0;
    transform: translateY(6px);
  }
  100% {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── Scrollbar — 研墨定制 ── */
::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--c-surface-5);
  border-radius: 3px;
  transition: background var(--motion-fast) var(--ease-out);
}
::-webkit-scrollbar-thumb:hover {
  background: var(--c-accent);
}
::-webkit-scrollbar-corner {
  background: transparent;
}

/* ── Light mode overrides ── */

/* Light mode global tweaks */
[data-theme='light'] ::-webkit-scrollbar-thumb {
  background: var(--c-surface-4);
}
[data-theme='light'] ::-webkit-scrollbar-thumb:hover {
  background: var(--c-accent);
}
[data-theme='light'] body::after {
  opacity: 0.032;
}
/* ── View Transition (theme switch) ── */
::view-transition-old(root) {
  animation: vt-old-out 220ms var(--ease-out);
  mix-blend-mode: normal;
}
::view-transition-new(root) {
  animation: vt-new-in 220ms var(--ease-out);
  mix-blend-mode: normal;
}
@keyframes vt-old-out {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}
@keyframes vt-new-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

/* ── Recovery Banner ── */
.recovery-banner {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 300;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  max-width: min(620px, calc(100vw - 32px));
  padding: 10px 12px 10px 16px;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  border-left: 3px solid var(--c-warn);
  border-radius: 10px;
  box-shadow: var(--elevation-2);
}
.recovery-text {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--c-text-1);
  line-height: 1.45;
}
.recovery-actions {
  display: flex;
  gap: 4px;
}

@media (max-width: 720px) {
  .recovery-banner {
    align-items: flex-start;
    flex-direction: column;
  }
  .recovery-actions {
    width: 100%;
    justify-content: flex-end;
  }
}

/* ── Wallpaper-aware semi-transparent backgrounds ── */
.app.has-wallpaper .content-overlay {
  background: transparent;
}
.app.has-wallpaper {
  --editor-bg: rgba(19, 19, 21, 0.82);
  --sidebar-bg: rgba(19, 19, 21, 0.75);
  --toolbar-bg: rgba(19, 19, 21, 0.78);
  --panel-bg: rgba(19, 19, 21, 0.8);
  --border-color: rgba(46, 46, 52, 0.6);
  --hover-bg: rgba(46, 46, 52, 0.7);
  --active-bg: rgba(66, 66, 74, 0.7);
  --code-bg: rgba(35, 35, 40, 0.75);
  --input-bg: rgba(35, 35, 40, 0.75);
}
[data-theme='light'] .app.has-wallpaper {
  --editor-bg: rgba(250, 250, 250, 0.88);
  --sidebar-bg: rgba(244, 244, 247, 0.85);
  --toolbar-bg: rgba(244, 244, 247, 0.88);
  --panel-bg: rgba(250, 250, 250, 0.88);
  --border-color: rgba(204, 204, 210, 0.6);
  --hover-bg: rgba(226, 226, 230, 0.8);
  --active-bg: rgba(212, 212, 218, 0.8);
  --code-bg: rgba(240, 240, 243, 0.85);
  --input-bg: rgba(244, 244, 247, 0.85);
}
</style>
