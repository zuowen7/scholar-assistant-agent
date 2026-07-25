<template>
  <AppDialog
    :model-value="modelValue"
    variant="drawer"
    :title="t('settingsCenter.title')"
    :subtitle="t('settingsCenter.subtitle')"
    :close-label="t('topbar.close')"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="settings-layout">
      <nav class="settings-nav" :aria-label="t('settingsCenter.sections')">
        <button
          v-for="item in tabs"
          :key="item.value"
          type="button"
          :class="{ active: tab === item.value }"
          @click="tab = item.value"
        >
          <component :is="item.icon" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="settings-content">
        <section v-if="tab === 'engine'" class="settings-page">
          <SettingsHeading
            :title="t('settings.engineLabel')"
            :description="t('settingsCenter.engineDescription')"
          />

          <div class="setting-card">
            <div class="setting-copy">
              <h4>{{ t('settings.engineLabel') }}</h4>
              <p>
                {{
                  engineType === 'cloud'
                    ? t('settingsCenter.cloudDescription')
                    : t('settingsCenter.localDescription')
                }}
              </p>
            </div>
            <div class="segmented" role="radiogroup" :aria-label="t('settings.engineLabel')">
              <button
                type="button"
                :class="{ active: engineType === 'ollama' }"
                @click="changeEngine('ollama')"
              >
                {{ t('settings.localOllama') }}
              </button>
              <button
                type="button"
                :class="{ active: engineType === 'cloud' }"
                @click="changeEngine('cloud')"
              >
                {{ t('settings.cloudApi') }}
              </button>
            </div>
          </div>

          <template v-if="engineType === 'cloud'">
            <div class="form-section">
              <label class="field">
                <span>{{ t('settings.provider') }}</span>
                <select
                  :value="cloudConfig.provider"
                  @change="changeProvider(($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="(preset, key) in providerPresets" :key="key" :value="key">
                    {{ preset.name }}
                  </option>
                </select>
              </label>
              <label class="field">
                <span>API Key</span>
                <input
                  type="password"
                  autocomplete="off"
                  :value="cloudConfig.api_key"
                  :placeholder="t('settings.apiKeyPlaceholder')"
                  @input="patchCloud('api_key', ($event.target as HTMLInputElement).value)"
                />
              </label>
              <label class="field field--wide">
                <span>Base URL</span>
                <input
                  type="url"
                  spellcheck="false"
                  :value="cloudConfig.base_url"
                  @input="patchCloud('base_url', ($event.target as HTMLInputElement).value)"
                />
              </label>
              <label class="field">
                <span>{{ t('settings.model') }}</span>
                <input
                  v-if="!activePreset?.models?.length"
                  :value="cloudConfig.model"
                  @input="patchCloud('model', ($event.target as HTMLInputElement).value)"
                />
                <select
                  v-else
                  :value="cloudConfig.model"
                  @change="patchCloud('model', ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="model in activePreset.models" :key="model" :value="model">
                    {{ model }}
                  </option>
                </select>
              </label>
            </div>
            <div class="action-row">
              <span class="connection-state" :class="cloudOk ? 'ok' : 'warn'">
                <i />{{
                  cloudChecking
                    ? t('status.detecting')
                    : cloudOk
                      ? t('status.connected')
                      : t('status.disconnected')
                }}
              </span>
              <UiButton
                variant="secondary"
                size="sm"
                :loading="cloudChecking"
                :disabled="!cloudConfig.api_key"
                @click="$emit('test-cloud')"
                >{{ t('settings.testConnection') }}</UiButton
              >
              <UiButton variant="primary" size="sm" @click="$emit('save-engine-settings')">{{
                t('settings.save')
              }}</UiButton>
            </div>
            <p v-if="cloudError" class="inline-error" role="alert">{{ cloudError }}</p>
          </template>

          <template v-else>
            <div class="form-section">
              <label class="field field--wide">
                <span>{{ t('settings.localModel') }}</span>
                <select
                  v-if="ollamaModels.length"
                  :value="ollamaModel"
                  @change="selectOllamaModel(($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="model in ollamaModels" :key="model" :value="model">
                    {{ model }}
                  </option>
                </select>
                <input
                  v-else
                  :value="ollamaModel"
                  spellcheck="false"
                  @input="$emit('update:ollamaModel', ($event.target as HTMLInputElement).value)"
                />
              </label>
            </div>
            <div class="action-row">
              <span class="connection-state" :class="ollamaOk ? 'ok' : 'warn'">
                <i />{{
                  ollamaLoading
                    ? t('status.starting')
                    : ollamaOk
                      ? t('status.online')
                      : t('status.offline')
                }}
              </span>
              <UiButton
                v-if="!ollamaOk"
                variant="secondary"
                size="sm"
                :loading="ollamaLoading"
                @click="$emit('toggle-ollama')"
                >{{ t('topbar.start') }}</UiButton
              >
              <UiButton
                variant="secondary"
                size="sm"
                :loading="ollamaModelsLoading"
                @click="$emit('refresh-ollama-models')"
                >{{ t('settings.refreshModels') }}</UiButton
              >
              <UiButton variant="primary" size="sm" @click="$emit('save-engine-settings')">{{
                t('settings.save')
              }}</UiButton>
            </div>
            <p v-if="ollamaError" class="inline-error" role="alert">{{ ollamaError }}</p>
            <p v-else-if="!ollamaOk" class="form-hint">{{ t('settings.installOllamaHint') }}</p>
          </template>

          <div class="setting-row setting-row--service">
            <div class="setting-copy">
              <h4>Tectonic</h4>
              <p>{{ t('settingsCenter.tectonicDescription') }}</p>
            </div>
            <span class="connection-state" :class="tectonicOk ? 'ok' : 'warn'"
              ><i />{{
                tectonicChecking
                  ? t('status.detecting')
                  : tectonicOk
                    ? t('status.ready')
                    : t('status.notInstalled')
              }}</span
            >
            <UiButton
              v-if="!tectonicOk"
              variant="secondary"
              size="sm"
              :loading="tectonicChecking"
              @click="$emit('handle-tectonic')"
              >{{ t('topbar.install') }}</UiButton
            >
          </div>
        </section>

        <section v-else-if="tab === 'display'" class="settings-page">
          <SettingsHeading
            :title="t('settings.display')"
            :description="t('settingsCenter.displayDescription')"
          />
          <div class="setting-row">
            <div class="setting-copy">
              <h4>{{ t('settingsCenter.appearance') }}</h4>
              <p>{{ isDark ? t('settingsCenter.darkActive') : t('settingsCenter.lightActive') }}</p>
            </div>
            <button
              class="theme-toggle"
              type="button"
              :aria-pressed="isDark"
              @click="$emit('toggle-theme', $event)"
            >
              <span :class="{ active: !isDark }">{{ t('settingsCenter.light') }}</span>
              <span :class="{ active: isDark }">{{ t('settingsCenter.dark') }}</span>
            </button>
          </div>
          <label class="field field--wide">
            <span>{{ t('settings.language') }}</span>
            <select
              :value="currentLocale"
              @change="setLocale(($event.target as HTMLSelectElement).value as SupportedLocale)"
            >
              <option value="zh-CN">简体中文</option>
              <option value="en-US">English</option>
            </select>
          </label>
          <div class="divider" />
          <SettingsHeading
            :title="t('settings.typography')"
            :description="t('settingsCenter.typographyDescription')"
            compact
          />
          <div class="range-row">
            <label for="settings-font-size">{{ t('settings.fontSize') }}</label>
            <input
              id="settings-font-size"
              type="range"
              min="13"
              max="24"
              :value="readSettings.fontSize"
              @input="$emit('font-size-change', Number(($event.target as HTMLInputElement).value))"
            />
            <output>{{ readSettings.fontSize }} px</output>
          </div>
          <div class="range-row">
            <label for="settings-line-height">{{ t('settings.lineHeight') }}</label>
            <input
              id="settings-line-height"
              type="range"
              min="14"
              max="26"
              :value="Math.round(readSettings.lineHeight * 10)"
              @input="
                $emit('line-height-change', Number(($event.target as HTMLInputElement).value))
              "
            />
            <output>{{ readSettings.lineHeight.toFixed(1) }}</output>
          </div>
          <div class="range-row">
            <label for="settings-ui-zoom">{{ t('settingsCenter.uiZoom') }}</label>
            <input
              id="settings-ui-zoom"
              type="range"
              min="80"
              max="200"
              step="10"
              :value="Math.round(uiZoom * 100)"
              @input="
                $emit('ui-zoom-change', Number(($event.target as HTMLInputElement).value) / 100)
              "
            />
            <output>{{ Math.round(uiZoom * 100) }}%</output>
          </div>
          <p class="form-hint">{{ t('settingsCenter.uiZoomHint') }}</p>
          <div class="form-section form-section--compact">
            <label class="field">
              <span>{{ t('settings.fontFamily') }}</span>
              <select
                :value="readSettings.fontFamily"
                @change="$emit('font-family-change', ($event.target as HTMLSelectElement).value)"
              >
                <option value="system-ui">{{ t('settings.systemDefault') }}</option>
                <option value="'Noto Serif SC', serif">Noto Serif SC</option>
                <option value="Georgia, serif">Georgia</option>
                <option value="'Courier New', monospace">Courier New</option>
              </select>
            </label>
            <label class="field">
              <span>{{ t('settings.transColor') }}</span>
              <span class="color-field">
                <input
                  type="color"
                  :value="readSettings.transColor || '#4E4A40'"
                  @input="$emit('color-change', ($event.target as HTMLInputElement).value)"
                />
                <code>{{ readSettings.transColor || t('settings.systemDefault') }}</code>
              </span>
            </label>
          </div>
          <div class="reading-preview" :style="previewStyle">
            <span>{{ t('settingsCenter.previewLabel') }}</span>
            <p>{{ t('settingsCenter.previewText') }}</p>
          </div>
        </section>

        <section v-else-if="tab === 'network'" class="settings-page">
          <SettingsHeading
            :title="t('settings.network')"
            :description="t('settingsCenter.networkDescription')"
          />
          <label class="field field--wide">
            <span>{{ t('settings.proxyAddress') }}</span>
            <input
              :value="proxyUrl"
              spellcheck="false"
              :placeholder="t('settings.proxyPlaceholder')"
              @input="$emit('update:proxyUrl', ($event.target as HTMLInputElement).value)"
            />
          </label>
          <p class="form-hint">{{ t('settings.proxyHint') }}</p>
          <div class="action-row">
            <span class="connection-state" :class="healthOk ? 'ok' : 'warn'"
              ><i />{{ t('topbar.backend') }} ·
              {{ healthOk ? t('status.online') : t('status.offline') }}</span
            >
            <UiButton variant="primary" size="sm" @click="$emit('save-proxy')">{{
              t('settings.saveProxy')
            }}</UiButton>
          </div>
        </section>

        <section v-else-if="tab === 'background'" class="settings-page">
          <SettingsHeading
            :title="t('settings.customBackground')"
            :description="t('settingsCenter.backgroundDescription')"
          />
          <div class="background-preview" :class="{ empty: !bgSettings.path }">
            <span v-if="!bgSettings.path">{{ t('settingsCenter.noBackground') }}</span>
            <span v-else class="background-path" :title="bgSettings.path">{{
              bgSettings.path
            }}</span>
          </div>
          <div class="action-row action-row--start">
            <UiButton variant="secondary" size="sm" @click="$emit('pick-background')">{{
              t('settings.chooseFile')
            }}</UiButton>
            <UiButton
              variant="danger"
              size="sm"
              :disabled="!bgSettings.path"
              @click="$emit('clear-background')"
              >{{ t('settings.clear') }}</UiButton
            >
          </div>
          <div class="range-row">
            <label for="settings-opacity">{{ t('settings.opacity') }}</label>
            <input
              id="settings-opacity"
              type="range"
              min="5"
              max="80"
              :value="bgSettings.opacity"
              @input="$emit('opacity-change', Number(($event.target as HTMLInputElement).value))"
            />
            <output>{{ bgSettings.opacity }}%</output>
          </div>
        </section>

        <section v-else-if="tab === 'voice'" class="settings-page">
          <SettingsHeading
            :title="t('voice.title')"
            :description="t('settingsCenter.voiceDescription')"
          />
          <label class="setting-row">
            <div class="setting-copy">
              <h4>{{ t('voice.enabled') }}</h4>
              <p>{{ t('settingsCenter.voiceEnabledDescription') }}</p>
            </div>
            <input
              class="switch"
              type="checkbox"
              :checked="voiceSettings.enabled"
              @change="updateVoice('enabled', ($event.target as HTMLInputElement).checked)"
            />
          </label>
          <div class="form-section">
            <label class="field">
              <span>{{ t('voice.hotkey') }}</span>
              <input
                :value="voiceSettings.hotkey"
                spellcheck="false"
                @change="updateVoice('hotkey', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label class="field">
              <span>{{ t('voice.language') }}</span>
              <select
                :value="voiceSettings.language"
                @change="updateVoice('language', ($event.target as HTMLSelectElement).value)"
              >
                <option value="zh-CN">简体中文</option>
                <option value="en-US">English</option>
              </select>
            </label>
          </div>
          <label class="setting-row">
            <div class="setting-copy">
              <h4>{{ t('voice.wakeWordEnabled') }}</h4>
              <p>{{ t('settingsCenter.wakeWordDescription') }}</p>
            </div>
            <input
              class="switch"
              type="checkbox"
              :checked="voiceSettings.wakeWordEnabled"
              @change="updateVoice('wakeWordEnabled', ($event.target as HTMLInputElement).checked)"
            />
          </label>
          <div class="form-section">
            <label class="field">
              <span>{{ t('voice.wakeWord') }}</span>
              <input
                :value="voiceSettings.wakeWordPhrase"
                :disabled="!voiceSettings.wakeWordEnabled"
                @input="updateVoice('wakeWordPhrase', ($event.target as HTMLInputElement).value)"
              />
            </label>
            <label class="field">
              <span>{{ t('voice.sensitivity') }}</span>
              <select
                :value="voiceSettings.sensitivity"
                :disabled="!voiceSettings.wakeWordEnabled"
                @change="
                  updateVoice(
                    'sensitivity',
                    ($event.target as HTMLSelectElement).value as VoiceSettings['sensitivity'],
                  )
                "
              >
                <option value="low">{{ t('voice.low') }}</option>
                <option value="medium">{{ t('voice.medium') }}</option>
                <option value="high">{{ t('voice.high') }}</option>
              </select>
            </label>
          </div>
          <p v-if="!speechSupported" class="inline-error" role="status">
            {{ t('voice.notSupported') }}
          </p>
        </section>

        <section v-else class="settings-page">
          <SettingsHeading
            :title="t('settingsCenter.systemTitle')"
            :description="t('settingsCenter.systemDescription')"
          />

          <div class="service-list">
            <div class="setting-row setting-row--service">
              <div class="setting-copy">
                <h4>{{ t('topbar.backend') }}</h4>
                <p>{{ t('settingsCenter.backendDescription') }}</p>
              </div>
              <span class="connection-state" :class="healthOk ? 'ok' : 'warn'"
                ><i />{{ healthOk ? t('status.online') : t('status.offline') }}</span
              >
              <UiButton
                v-if="!healthOk"
                variant="secondary"
                size="sm"
                :loading="backendRestarting"
                @click="$emit('restart-backend')"
                >{{ t('translate.restartBackend') }}</UiButton
              >
            </div>
            <div class="setting-row setting-row--service">
              <div class="setting-copy">
                <h4>
                  {{
                    engineType === 'cloud' ? activePreset?.name || cloudConfig.provider : 'Ollama'
                  }}
                </h4>
                <p>{{ t('settingsCenter.modelServiceDescription') }}</p>
              </div>
              <span
                class="connection-state"
                :class="(engineType === 'cloud' ? cloudOk : ollamaOk) ? 'ok' : 'warn'"
                ><i />{{
                  (engineType === 'cloud' ? cloudOk : ollamaOk)
                    ? t('status.connected')
                    : t('status.disconnected')
                }}</span
              >
            </div>
            <div class="setting-row setting-row--service">
              <div class="setting-copy">
                <h4>Tectonic</h4>
                <p>{{ t('settingsCenter.tectonicDescription') }}</p>
              </div>
              <span class="connection-state" :class="tectonicOk ? 'ok' : 'warn'"
                ><i />{{ tectonicOk ? t('status.ready') : t('status.notInstalled') }}</span
              >
            </div>
          </div>

          <div class="divider" />
          <SettingsHeading
            :title="t('settingsCenter.updateTitle')"
            :description="t('settingsCenter.updateDescription')"
            compact
          />
          <div class="setting-row">
            <div class="setting-copy">
              <h4>{{ updateLabel }}</h4>
              <p>{{ updateDetail }}</p>
            </div>
            <UiButton
              v-if="updateResult?.status === 'available'"
              variant="primary"
              size="sm"
              @click="$emit('open-release', updateResult.releaseUrl)"
              >{{ t('settingsCenter.viewRelease') }}</UiButton
            >
            <UiButton
              variant="secondary"
              size="sm"
              :loading="updateChecking"
              @click="$emit('check-update')"
              >{{ t('settingsCenter.checkUpdate') }}</UiButton
            >
          </div>

          <div class="divider" />
          <SettingsHeading
            :title="t('settingsCenter.diagnosticsTitle')"
            :description="t('settingsCenter.diagnosticsDescription')"
            compact
          />
          <div class="setting-row">
            <div class="setting-copy">
              <h4>{{ t('editor.debugTitle') }}</h4>
              <p>{{ t('settingsCenter.logDescription') }}</p>
            </div>
            <DebugPanel />
          </div>
        </section>
      </div>
    </div>
  </AppDialog>
</template>

<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SupportedLocale } from '../../i18n'
import { useLocale } from '../../composables/useLocale'
import AppDialog from '../shell/AppDialog.vue'
import UiButton from '../ui/UiButton.vue'
import SettingsHeading from './SettingsHeading.vue'
import DebugPanel from '../DebugPanel.vue'
import type { UpdateCheckResult } from '../../composables/useUpdateChecker'

interface CloudConfig {
  provider: string
  api_key: string
  base_url: string
  model: string
  max_tokens: number
}
interface VoiceSettings {
  enabled: boolean
  hotkey: string
  wakeWordEnabled: boolean
  wakeWordPhrase: string
  sensitivity: 'low' | 'medium' | 'high'
  language: string
}

const props = defineProps<{
  modelValue: boolean
  isDark: boolean
  engineType: 'ollama' | 'cloud'
  cloudConfig: CloudConfig
  ollamaModel: string
  ollamaModels: string[]
  ollamaModelsLoading: boolean
  providerPresets: Record<string, { name: string; base_url: string; models: string[] }>
  cloudChecking: boolean
  cloudOk: boolean
  cloudError: string | null
  healthOk: boolean
  backendRestarting: boolean
  ollamaOk: boolean
  ollamaLoading: boolean
  ollamaError: string | null
  tectonicOk: boolean
  tectonicChecking: boolean
  bgSettings: { path: string; type: 'image' | 'video'; opacity: number }
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
  uiZoom: number
  proxyUrl: string
  updateChecking: boolean
  updateResult: UpdateCheckResult | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:engineType': [value: 'ollama' | 'cloud']
  'update:cloudConfig': [value: CloudConfig]
  'update:ollamaModel': [value: string]
  'update:proxyUrl': [value: string]
  'toggle-theme': [event?: MouseEvent]
  'toggle-ollama': []
  'refresh-ollama-models': []
  'handle-tectonic': []
  'save-engine-settings': []
  'test-cloud': []
  'provider-change': [provider: string]
  'save-proxy': []
  'pick-background': []
  'clear-background': []
  'opacity-change': [value: number]
  'font-size-change': [value: number]
  'line-height-change': [value: number]
  'font-family-change': [value: string]
  'color-change': [value: string]
  'ui-zoom-change': [value: number]
  'voice-settings-change': [value: VoiceSettings]
  'restart-backend': []
  'check-update': []
  'open-release': [url: string]
}>()

const { t } = useI18n()
const { currentLocale, setLocale } = useLocale()
const tab = ref<'engine' | 'display' | 'network' | 'background' | 'voice' | 'system'>('engine')
const speechSupported = !!(window.SpeechRecognition || window.webkitSpeechRecognition)

function icon(paths: string[]) {
  return () =>
    h(
      'svg',
      { viewBox: '0 0 24 24', 'aria-hidden': 'true' },
      paths.map((d) => h('path', { d })),
    )
}

const tabs = computed(() => [
  {
    value: 'engine' as const,
    label: t('settings.engine'),
    icon: icon(['M4 7h16M7 3v8M4 17h16M17 13v8']),
  },
  {
    value: 'display' as const,
    label: t('settings.display'),
    icon: icon(['M4 5h16v12H4zM9 21h6M12 17v4']),
  },
  {
    value: 'network' as const,
    label: t('settings.network'),
    icon: icon(['M5 12a7 7 0 0 1 14 0M8 15a4 4 0 0 1 8 0M11 18a1 1 0 0 1 2 0']),
  },
  {
    value: 'background' as const,
    label: t('settings.background'),
    icon: icon(['M4 5h16v14H4zM7 15l3-3 3 3 2-2 3 3M16 9h.01']),
  },
  {
    value: 'voice' as const,
    label: t('voice.title'),
    icon: icon(['M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0zM5 10v1a7 7 0 0 0 14 0v-1M12 18v3']),
  },
  {
    value: 'system' as const,
    label: t('settingsCenter.systemTitle'),
    icon: icon([
      'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
      'M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1',
    ]),
  },
])

const activePreset = computed(() => props.providerPresets[props.cloudConfig.provider])
const previewStyle = computed(() => ({
  fontSize: `${props.readSettings.fontSize}px`,
  lineHeight: String(props.readSettings.lineHeight),
  fontFamily: props.readSettings.fontFamily,
  color: props.readSettings.transColor || undefined,
}))
const updateLabel = computed(() => {
  if (!props.updateResult) return t('settingsCenter.updateUnknown')
  return props.updateResult.status === 'available'
    ? t('settingsCenter.updateAvailable', { version: props.updateResult.remoteVersion })
    : t('settingsCenter.updateCurrent')
})
const updateDetail = computed(() => {
  if (!props.updateResult) return t('settingsCenter.updateNotChecked')
  return t('settingsCenter.versionDetail', {
    local: props.updateResult.localVersion,
    remote: props.updateResult.remoteVersion,
  })
})

const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  enabled: true,
  hotkey: 'Alt+Shift+V',
  wakeWordEnabled: true,
  wakeWordPhrase: '小研',
  sensitivity: 'medium',
  language: 'zh-CN',
}

function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem('voice-settings')
    return raw ? { ...DEFAULT_VOICE_SETTINGS, ...JSON.parse(raw) } : { ...DEFAULT_VOICE_SETTINGS }
  } catch {
    return { ...DEFAULT_VOICE_SETTINGS }
  }
}

const voiceSettings = ref<VoiceSettings>(loadVoiceSettings())

function updateVoice<K extends keyof VoiceSettings>(key: K, value: VoiceSettings[K]) {
  voiceSettings.value = { ...voiceSettings.value, [key]: value }
  try {
    localStorage.setItem('voice-settings', JSON.stringify(voiceSettings.value))
  } catch {
    /* storage can be unavailable */
  }
  emit('voice-settings-change', voiceSettings.value)
}

function changeEngine(value: 'ollama' | 'cloud') {
  emit('update:engineType', value)
  emit('save-engine-settings')
}

function patchCloud<K extends keyof CloudConfig>(key: K, value: CloudConfig[K]) {
  emit('update:cloudConfig', { ...props.cloudConfig, [key]: value })
}

function changeProvider(provider: string) {
  emit('update:cloudConfig', { ...props.cloudConfig, provider })
  emit('provider-change', provider)
}

function selectOllamaModel(model: string) {
  emit('update:ollamaModel', model)
  emit('save-engine-settings')
}
</script>

<style scoped>
.settings-layout {
  display: grid;
  min-height: 0;
  grid-template-columns: 164px minmax(0, 1fr);
}
.settings-nav {
  padding: 16px 10px;
  border-right: 1px solid var(--c-border);
  background: var(--c-nav);
}
.settings-nav button {
  display: flex;
  width: 100%;
  height: 38px;
  align-items: center;
  gap: 10px;
  margin-bottom: 3px;
  padding: 0 11px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--c-text-2);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.settings-nav button:hover {
  background: color-mix(in srgb, var(--c-panel) 68%, transparent);
  color: var(--c-text-0);
}
.settings-nav button.active {
  background: var(--c-panel);
  color: var(--c-text-0);
  box-shadow: inset 3px 0 var(--brand-red);
}
.settings-nav svg {
  width: 17px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.6;
}
.settings-content {
  min-width: 0;
  overflow: auto;
}
.settings-page {
  padding: 28px 30px 42px;
}
.setting-card,
.setting-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 15px 0;
  border-bottom: 1px solid var(--c-border);
}
.setting-card {
  padding: 16px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-surface-1);
}
.setting-copy {
  min-width: 0;
  flex: 1;
}
.setting-copy h4 {
  margin: 0;
  color: var(--c-text-0);
  font-size: 13px;
  font-weight: 620;
}
.setting-copy p {
  margin: 4px 0 0;
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.5;
}
.segmented {
  display: inline-flex;
  flex: 0 0 auto;
  padding: 3px;
  border-radius: 8px;
  background: var(--c-surface-2);
}
.segmented button {
  height: 30px;
  padding: 0 11px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--c-text-2);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.segmented button.active {
  background: var(--c-panel);
  color: var(--c-text-0);
  box-shadow: var(--elevation-1);
}
.form-section {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 22px;
}
.form-section--compact {
  margin-top: 16px;
}
.field {
  display: grid;
  gap: 7px;
  color: var(--c-text-1);
  font-size: 12px;
}
.field--wide {
  grid-column: 1 / -1;
  margin-top: 20px;
}
.field input:not([type='color']),
.field select {
  width: 100%;
  height: 38px;
  box-sizing: border-box;
  padding: 0 11px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  outline: none;
  background: var(--input-bg);
  color: var(--c-text-0);
  font: inherit;
  font-size: 13px;
}
.field input:focus,
.field select:focus {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}
.field input:disabled,
.field select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.action-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}
.action-row--start {
  justify-content: flex-start;
}
.connection-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-right: auto;
  color: var(--c-text-2);
  font-size: 12px;
}
.connection-state i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-warn);
}
.connection-state.ok i {
  background: var(--c-success);
}
.inline-error {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-left: 3px solid var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger-fg);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.form-hint {
  margin: 10px 0 0;
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.55;
}
.divider {
  height: 1px;
  margin: 26px 0;
  background: var(--c-border);
}
.theme-toggle {
  display: inline-flex;
  padding: 3px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font: inherit;
  cursor: pointer;
}
.theme-toggle span {
  padding: 6px 11px;
  border-radius: 6px;
  font-size: 12px;
}
.theme-toggle span.active {
  background: var(--c-panel);
  color: var(--c-text-0);
  box-shadow: var(--elevation-1);
}
.range-row {
  display: grid;
  grid-template-columns: 84px minmax(120px, 1fr) 54px;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
  color: var(--c-text-1);
  font-size: 12px;
}
.range-row input {
  width: 100%;
  accent-color: var(--c-accent);
}
.range-row output {
  color: var(--c-text-2);
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.color-field {
  display: flex;
  height: 38px;
  align-items: center;
  gap: 9px;
  padding: 0 10px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--input-bg);
}
.color-field input {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  background: transparent;
}
.color-field code {
  min-width: 0;
  color: var(--c-text-2);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reading-preview {
  margin-top: 22px;
  padding: 20px;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-app-bg);
}
.reading-preview span {
  display: block;
  margin-bottom: 10px;
  color: var(--c-text-3);
  font-family: system-ui;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.reading-preview p {
  margin: 0;
}
.background-preview {
  display: flex;
  height: 112px;
  align-items: flex-end;
  margin-top: 22px;
  padding: 14px;
  overflow: hidden;
  border: 1px solid var(--c-border);
  border-radius: 10px;
  background: var(--c-nav);
  color: var(--c-text-2);
  font-size: 12px;
}
.background-preview.empty {
  align-items: center;
  justify-content: center;
  border-style: dashed;
}
.background-path {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.switch {
  position: relative;
  width: 38px;
  height: 22px;
  flex: 0 0 auto;
  appearance: none;
  border: 1px solid var(--c-border);
  border-radius: 999px;
  background: var(--c-surface-3);
  cursor: pointer;
  transition: background var(--motion-fast);
}
.switch::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--c-panel);
  box-shadow: var(--elevation-1);
  transition: transform var(--motion-fast);
}
.switch:checked {
  border-color: var(--c-accent);
  background: var(--c-accent);
}
.switch:checked::after {
  transform: translateX(16px);
}
.switch:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.setting-row--service {
  margin-top: 24px;
}
.service-list .setting-row--service {
  margin-top: 0;
}
.service-list .setting-row--service:first-child {
  margin-top: 18px;
}
.service-list + .divider {
  margin-top: 10px;
}

button:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}

@media (max-width: 720px) {
  .settings-layout {
    grid-template-columns: 1fr;
  }
  .settings-nav {
    display: flex;
    gap: 3px;
    overflow-x: auto;
    padding: 9px 10px;
    border-right: 0;
    border-bottom: 1px solid var(--c-border);
  }
  .settings-nav button {
    width: auto;
    min-width: max-content;
    margin: 0;
  }
  .settings-nav button.active {
    box-shadow: inset 0 -2px var(--brand-red);
  }
  .settings-page {
    padding: 22px 18px 38px;
  }
  .form-section {
    grid-template-columns: 1fr;
  }
  .field--wide {
    grid-column: auto;
  }
  .setting-card {
    align-items: flex-start;
    flex-direction: column;
  }
  .segmented {
    width: 100%;
  }
  .segmented button {
    flex: 1;
  }
}
</style>
