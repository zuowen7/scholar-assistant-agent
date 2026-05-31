<template>
  <div class="topbar-wrapper">
  <header class="topbar" data-tauri-drag-region>

    <!-- ── Left: Brand ──────────────────────────────────────── -->
    <div class="brand" data-tauri-drag-region>
      <div class="logo" aria-hidden="true">研</div>
      <span class="brand-name">研墨</span>
    </div>

    <!-- ── Center: Mode switch ─────────────────────────────── -->
    <div class="topbar-center" data-tauri-drag-region>
      <UiSegmented
        :model-value="appMode"
        :options="modeOptions"
        size="sm"
        vermilion-indicator
        @update:model-value="$emit('update:appMode', $event as any)"
      />
    </div>

    <!-- ── Right: Actions ──────────────────────────────────── -->
    <div class="topbar-right">

      <!-- Status dot + engine chip -->
      <UiPopover ref="statusPopoverRef" :width="300" align="end" :offset="8">
        <template #trigger>
          <button class="status-trigger" :class="overallStatus" :title="t('topbar.serviceStatus')" :aria-label="t('topbar.serviceStatus')">
            <span class="status-dot" />
            <span class="status-label">{{ engineType === 'ollama' ? 'Ollama' : t('topbar.cloud') }}</span>
          </button>
        </template>
        <div class="status-popover">
          <div class="sp-header">
            <span class="sp-title">{{ t('topbar.serviceStatus') }}</span>
          </div>

          <div class="status-rows">
            <div class="status-row">
              <span class="sr-dot" :class="healthOk ? 'ok' : 'off'" />
              <span class="sr-label">{{ t('topbar.backend') }}</span>
              <span class="sr-state">{{ healthOk ? t('status.online') : t('status.offline') }}</span>
            </div>
            <template v-if="engineType === 'ollama'">
              <div class="status-row">
                <span class="sr-dot" :class="ollamaOk ? 'ok' : 'off'" />
                <span class="sr-label">Ollama</span>
                <span class="sr-state">
                  <template v-if="ollamaLoading">{{ t('status.starting') }}</template>
                  <template v-else>{{ ollamaOk ? t('status.online') : t('status.offline') }}</template>
                </span>
                <UiButton v-if="!ollamaOk && !ollamaLoading" variant="ghost" size="sm" @click="$emit('toggle-ollama')">{{ t('topbar.start') }}</UiButton>
              </div>
            </template>
            <template v-else>
              <div class="status-row">
                <span class="sr-dot" :class="cloudOk ? 'ok' : 'off'" />
                <span class="sr-label">{{ t('settings.cloudApi') }}</span>
                <span class="sr-state">{{ cloudOk ? t('status.connected') : t('status.disconnected') }}</span>
              </div>
            </template>
            <div class="status-row">
              <span class="sr-dot" :class="tectonicOk ? 'ok' : 'off'" />
              <span class="sr-label">LaTeX</span>
              <span class="sr-state">{{ tectonicChecking ? t('status.detecting') : tectonicOk ? t('status.ready') : t('status.notInstalled') }}</span>
              <UiButton v-if="!tectonicOk && !tectonicChecking" variant="ghost" size="sm" @click="$emit('handle-tectonic')">{{ t('topbar.install') }}</UiButton>
            </div>
          </div>

          <div class="sp-divider" />

          <!-- Engine switch inside popover -->
          <div class="sp-section-label">{{ t('settings.engineLabel') }}</div>
          <UiSegmented
            :model-value="engineType"
            :options="engineOptions"
            size="sm"
            full
            @update:model-value="$emit('update:engineType', $event as any); $emit('save-engine-settings')"
          />
        </div>
      </UiPopover>

      <div class="topbar-sep" />

      <!-- Unified Settings popover -->
      <UiPopover ref="settingsPopoverRef" :width="380" align="end" :offset="8">
        <template #trigger>
          <button
            class="topbar-icon-btn"
            :class="{ active: settingsPopoverOpen }"
            :title="t('topbar.settings')"
          >
            <Settings :size="15" :stroke-width="1.6" />
          </button>
        </template>

        <div class="settings-popover">
          <div class="sp-header">
            <span class="sp-title">{{ t('topbar.settings') }}</span>
          </div>
          <UiSegmented
            v-model="settingsTab"
            :options="settingsTabOptions"
            size="sm"
            full
            class="sp-tabs"
          />

          <div class="sp-lang-row">
            <label class="sp-label">{{ t('settings.language') }}</label>
            <UiSelect
              :model-value="currentLocale"
              @update:model-value="setLocale($event as any)"
            >
              <option value="zh-CN">简体中文</option>
              <option value="en-US">English</option>
            </UiSelect>
          </div>

          <!-- Engine tab -->
          <div v-show="settingsTab === 'engine'" class="sp-body">
            <div class="sp-section-label">{{ t('settings.engineLabel') }}</div>
            <UiSegmented
              :model-value="engineType"
              :options="engineOptions"
              size="sm"
              full
              @update:model-value="$emit('update:engineType', $event as any); $emit('save-engine-settings')"
            />
            <template v-if="engineType === 'cloud'">
              <div class="sp-gap" />
              <div class="sp-section-label">{{ t('settings.cloudConfig') }}</div>
              <div class="sp-field">
                <label class="sp-label">{{ t('settings.provider') }}</label>
                <UiSelect
                  :model-value="cloudConfig.provider"
                  @update:model-value="$emit('update:cloudConfig', { ...cloudConfig, provider: $event }); $emit('provider-change', $event)"
                >
                  <option v-for="(preset, key) in providerPresets" :key="key" :value="key">{{ preset.name }}</option>
                </UiSelect>
              </div>
              <div class="sp-field">
                <label class="sp-label">API Key</label>
                <UiInput
                  type="password"
                  :model-value="cloudConfig.api_key"
                  :placeholder="t('settings.apiKeyPlaceholder')"
                  @update:model-value="$emit('update:cloudConfig', { ...cloudConfig, api_key: $event })"
                />
              </div>
              <div class="sp-field">
                <label class="sp-label">Base URL</label>
                <UiInput
                  :model-value="cloudConfig.base_url"
                  placeholder="https://api.openai.com/v1"
                  @update:model-value="$emit('update:cloudConfig', { ...cloudConfig, base_url: $event })"
                />
              </div>
              <div class="sp-field">
                <label class="sp-label">{{ t('settings.model') }}</label>
                <div class="sp-row">
                  <UiInput
                    :model-value="cloudConfig.model"
                    placeholder="gpt-4o"
                    @update:model-value="$emit('update:cloudConfig', { ...cloudConfig, model: $event })"
                  />
                  <UiSelect
                    v-if="providerPresets[cloudConfig.provider]?.models?.length"
                    class="sp-select-narrow"
                    @update:model-value="$emit('update:cloudConfig', { ...cloudConfig, model: $event })"
                  >
                    <option value="" disabled selected>{{ t('settings.preset') }}</option>
                    <option v-for="m in providerPresets[cloudConfig.provider]?.models" :key="m" :value="m">{{ m }}</option>
                  </UiSelect>
                </div>
              </div>
              <div class="sp-actions">
                <UiButton variant="secondary" size="sm" :loading="cloudChecking" :disabled="!cloudConfig.api_key" @click="$emit('test-cloud')">{{ t('settings.testConnection') }}</UiButton>
                <UiButton variant="primary" size="sm" @click="$emit('save-engine-settings')">{{ t('settings.save') }}</UiButton>
              </div>
              <div v-if="cloudConfig.api_key" class="sp-status" :class="cloudOk ? 'ok' : 'off'">
                {{ cloudOk ? t('status.connected') : t('status.disconnected') }}
              </div>
              <div v-if="cloudError" class="sp-error">{{ cloudError }}</div>
            </template>
            <template v-if="engineType === 'ollama'">
              <div class="sp-gap" />
              <div class="sp-section-label">Ollama 设置</div>
              <div class="sp-field">
                <label class="sp-label">本地模型</label>
                <div class="sp-row">
                  <UiSelect
                    :model-value="ollamaModel"
                    @update:model-value="$emit('update:ollamaModel', $event as string); $emit('save-engine-settings')"
                  >
                    <option v-if="ollamaModels.length === 0" :value="ollamaModel">{{ ollamaModel }}</option>
                    <option v-for="m in ollamaModels" :key="m" :value="m">{{ m }}</option>
                  </UiSelect>
                  <UiButton variant="ghost" size="sm" :disabled="ollamaModelsLoading" @click="$emit('refreshOllamaModels')">
                    {{ ollamaModelsLoading ? '...' : '刷新' }}
                  </UiButton>
                </div>
              </div>
              <div v-if="ollamaModels.length" class="sp-status ok">{{ ollamaModels.length }} 个模型已就绪</div>
            </template>
          </div>

          <!-- Display tab -->
          <div v-show="settingsTab === 'display'" class="sp-body">
            <div class="sp-section-label">{{ t('settings.typography') }}</div>
            <UiSlider
              :label="t('settings.fontSize')"
              :model-value="readSettings.fontSize"
              :min="12"
              :max="28"
              suffix="px"
              @update:model-value="$emit('font-size-change', $event)"
            />
            <UiSlider
              :label="t('settings.lineHeight')"
              :model-value="Math.round(readSettings.lineHeight * 10)"
              :min="14"
              :max="32"
              @update:model-value="$emit('line-height-change', $event)"
            />
            <div class="sp-field">
              <label class="sp-label">{{ t('settings.fontFamily') }}</label>
              <UiSelect
                :model-value="readSettings.fontFamily"
                @update:model-value="$emit('font-family-change', $event)"
              >
                <option value="system-ui">{{ t('settings.systemDefault') }}</option>
                <option value="'Noto Sans SC', sans-serif">思源黑体</option>
                <option value="'Noto Serif SC', serif">思源宋体</option>
                <option value="'LXGW WenKai', serif">霞鹜文楷</option>
                <option value="'Microsoft YaHei', sans-serif">微软雅黑</option>
                <option value="SimSun, serif">宋体</option>
              </UiSelect>
            </div>
            <div class="sp-field">
              <label class="sp-label">{{ t('settings.transColor') }}</label>
              <div class="sp-color-row">
                <input type="color" :value="readSettings.transColor" class="sp-color" @input="$emit('color-change', ($event.target as HTMLInputElement).value)" />
                <span class="sp-color-hex">{{ readSettings.transColor }}</span>
              </div>
            </div>
          </div>

          <!-- Network tab -->
          <div v-show="settingsTab === 'network'" class="sp-body">
            <div class="sp-section-label">{{ t('settings.httpProxy') }}</div>
            <div class="sp-field">
              <label class="sp-label">{{ t('settings.proxyAddress') }}</label>
              <UiInput
                :model-value="proxyUrl"
                :placeholder="t('settings.proxyPlaceholder')"
                @update:model-value="$emit('update:proxyUrl', $event)"
              />
            </div>
            <div class="sp-actions">
              <UiButton variant="primary" size="sm" @click="$emit('save-proxy')">{{ t('settings.saveProxy') }}</UiButton>
            </div>
            <p class="sp-hint">{{ t('settings.proxyHint') }}</p>
          </div>

          <!-- Background tab -->
          <div v-show="settingsTab === 'background'" class="sp-body">
            <div class="sp-section-label">{{ t('settings.customBackground') }}</div>
            <div class="sp-actions">
              <UiButton variant="secondary" size="sm" @click="$emit('pick-background')">
                <template #icon-left><Upload :size="13" :stroke-width="1.8" /></template>
                {{ t('settings.chooseFile') }}
              </UiButton>
              <UiButton variant="danger" size="sm" :disabled="!bgSettings.path" @click="$emit('clear-background')">
                <template #icon-left><Trash2 :size="13" :stroke-width="1.8" /></template>
                {{ t('settings.clear') }}
              </UiButton>
            </div>
            <div v-if="bgSettings.path" class="sp-bg-path">{{ bgSettings.path.split(/[\\/]/).pop() }}</div>
            <UiSlider
              :label="t('settings.opacity')"
              :model-value="bgSettings.opacity"
              :min="5"
              :max="100"
              suffix="%"
              @update:model-value="$emit('opacity-change', $event)"
            />
          </div>
        </div>
      </UiPopover>

      <!-- Agent toggle -->
      <button
        class="topbar-icon-btn"
        :class="{ active: showAgentChat }"
        :title="t('topbar.agentAssistant')"
        @click="$emit('update:showAgentChat', !showAgentChat)"
      >
        <MessageSquare :size="15" :stroke-width="1.6" />
      </button>

      <!-- Debug panel -->
      <DebugPanel />

      <!-- Theme toggle -->
      <button
        class="topbar-icon-btn"
        :title="isDark ? t('topbar.switchLight') : t('topbar.switchDark')"
        @click="$emit('toggle-theme', $event)"
      >
        <Sun v-if="isDark" :size="15" :stroke-width="1.6" />
        <Moon v-else :size="15" :stroke-width="1.6" />
      </button>

      <!-- Window controls -->
      <div class="window-controls">
        <button class="win-btn minimize" :title="t('topbar.minimize')" :aria-label="t('topbar.minimize')" @click="$emit('window-minimize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><line x1="2" y1="5" x2="8" y2="5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </button>
        <button class="win-btn maximize" :title="t('topbar.maximize')" :aria-label="t('topbar.maximize')" @click="$emit('window-maximize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="2" y="2" width="6" height="6" fill="none" stroke="currentColor" stroke-width="1.2" rx="1"/></svg>
        </button>
        <button class="win-btn close" :title="t('topbar.close')" :aria-label="t('topbar.close')" @click="$emit('window-close')">
          <svg width="10" height="10" viewBox="0 0 10 10"><line x1="2.5" y1="2.5" x2="7.5" y2="7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><line x1="7.5" y1="2.5" x2="2.5" y2="7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>
  </header>
  <!-- Separator line: fading gradient -->
  <div class="topbar-fade-line" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { argMapV2Enabled } from '../composables/useArgumentMap'
import { useLocale } from '../composables/useLocale'
import { Settings, Sun, Moon, Upload, Trash2, MessageSquare } from './ui/icons'
import UiSegmented from './ui/UiSegmented.vue'
import UiButton from './ui/UiButton.vue'
import UiPopover from './ui/UiPopover.vue'
import UiInput from './ui/UiInput.vue'
import UiSelect from './ui/UiSelect.vue'
import UiSlider from './ui/UiSlider.vue'
import DebugPanel from './DebugPanel.vue'
import type { AppMode } from '../types'

const { t } = useI18n()
const { currentLocale, setLocale } = useLocale()

const props = defineProps<{
  appMode: AppMode
  isDark: boolean
  showAgentChat: boolean
  engineType: 'ollama' | 'cloud'
  cloudConfig: { provider: string; api_key: string; base_url: string; model: string; max_tokens: number }
  ollamaModel: string
  ollamaModels: string[]
  ollamaModelsLoading: boolean
  providerPresets: Record<string, { name: string; base_url: string; models: string[] }>
  cloudChecking: boolean
  cloudOk: boolean
  cloudError: string | null
  healthOk: boolean
  ollamaOk: boolean
  ollamaLoading: boolean
  ollamaError: string | null
  tectonicOk: boolean
  tectonicChecking: boolean
  bgSettings: { path: string; type: 'image' | 'video'; opacity: number }
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
  proxyUrl: string
}>()

defineEmits<{
  (e: 'update:appMode', value: AppMode): void
  (e: 'update:showAgentChat', value: boolean): void
  (e: 'update:engineType', value: 'ollama' | 'cloud'): void
  (e: 'update:cloudConfig', value: any): void
  (e: 'update:ollamaModel', value: string): void
  (e: 'update:proxyUrl', value: string): void
  (e: 'toggle-theme', event?: MouseEvent): void
  (e: 'toggle-ollama'): void
  (e: 'refreshOllamaModels'): void
  (e: 'handle-tectonic'): void
  (e: 'save-engine-settings'): void
  (e: 'test-cloud'): void
  (e: 'provider-change', provider: string): void
  (e: 'save-proxy'): void
  (e: 'pick-background'): void
  (e: 'clear-background'): void
  (e: 'opacity-change', value: number): void
  (e: 'font-size-change', value: number): void
  (e: 'line-height-change', value: number): void
  (e: 'save-read-settings'): void
  (e: 'font-family-change', value: string): void
  (e: 'color-change', value: string): void
  (e: 'window-minimize'): void
  (e: 'window-maximize'): void
  (e: 'window-close'): void
}>()

const settingsPopoverRef = ref<InstanceType<typeof UiPopover> | null>(null)
const statusPopoverRef = ref<InstanceType<typeof UiPopover> | null>(null)
const settingsPopoverOpen = computed(() => settingsPopoverRef.value?.open ?? false)
const settingsTab = ref<'engine' | 'display' | 'network' | 'background'>('engine')

const modeOptions = computed(() => [
  { value: 'translate' as AppMode, label: t('mode.translate') },
  { value: 'editor' as AppMode, label: t('mode.edit') },
  ...(argMapV2Enabled.value ? [{ value: 'argument' as AppMode, label: t('mode.argument') }] : []),
])

const settingsTabOptions = computed(() => [
  { value: 'engine', label: t('settings.engine') },
  { value: 'display', label: t('settings.display') },
  { value: 'network', label: t('settings.network') },
  { value: 'background', label: t('settings.background') },
])

const engineOptions = computed(() => [
  { value: 'ollama' as const, label: t('settings.localOllama') },
  { value: 'cloud' as const, label: t('settings.cloudApi') },
])

const overallStatus = computed(() => {
  if (!props.healthOk) return 'danger'
  if (props.engineType === 'ollama' && !props.ollamaOk) return 'warn'
  if (props.engineType === 'cloud' && !props.cloudOk) return 'warn'
  return 'ok'
})
</script>

<style scoped>
/* ── Topbar wrapper (provides margin for floating) ──────── */
.topbar-wrapper {
  flex-shrink: 0;
  position: relative;
  z-index: 210;
}

/* ── Topbar shell — floating glass bar ─────────────────── */
.topbar {
  display: flex;
  align-items: center;
  height: 52px;
  padding: 0 20px;
  gap: 0;
  background: color-mix(in srgb, var(--ink-1) 72%, transparent);
  backdrop-filter: blur(20px) saturate(1.6);
  -webkit-backdrop-filter: blur(20px) saturate(1.6);
  border: 1px solid var(--ink-4);
  border-radius: var(--radius-card);
  margin: 8px 12px 0;
  -webkit-app-region: drag;
}

/* ── Fade line separator ────────────────────────────────── */
.topbar-fade-line {
  height: 1px;
  margin: 0 28px;
  background: linear-gradient(to right, transparent, var(--ink-4) 20%, var(--ink-4) 80%, transparent);
}

/* ── Brand ────────────────────────────────────────────────── */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px 0 4px;
  height: 100%;
  flex-shrink: 0;
  border-right: 1px solid var(--ink-4);
}
.logo {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--c-accent-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
  color: #fff;
  flex-shrink: 0;
  font-family: var(--font-serif-zh);
}
.brand-name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--c-text-0);
  font-family: var(--font-serif-zh);
  letter-spacing: var(--tracking-tight);
}

/* ── Center ───────────────────────────────────────────────── */
.topbar-center {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  -webkit-app-region: drag;
}

/* ── Right ────────────────────────────────────────────────── */
.topbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  -webkit-app-region: no-drag;
  padding-left: 8px;
}

.topbar-sep {
  width: 1px;
  height: 20px;
  background: var(--ink-4);
  margin: 0 4px;
  flex-shrink: 0;
}

/* ── Status trigger ─────────────────────────────────────── */
.status-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  color: var(--c-text-2);
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              border-color var(--motion-fast) var(--ease-out);
}
.status-trigger:hover { background: var(--c-surface-3); }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 1px solid transparent;
}
.status-trigger.ok .status-dot    { background: var(--c-success); box-shadow: 0 0 4px var(--c-success); }
.status-trigger.warn .status-dot  { background: var(--c-warn);    box-shadow: 0 0 4px var(--c-warn); }
.status-trigger.danger .status-dot{ background: var(--c-danger);  box-shadow: 0 0 4px var(--c-danger); }
.status-label { font-feature-settings: "tnum"; }

/* ── Status popover ─────────────────────────────────────── */
.status-popover { display: flex; flex-direction: column; gap: 0; }
.status-rows { display: flex; flex-direction: column; gap: var(--space-2); }
.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.sr-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sr-dot.ok  { background: var(--c-success); }
.sr-dot.off { background: var(--c-danger); }
.sr-label {
  font-size: var(--text-sm);
  color: var(--c-text-1);
  min-width: 60px;
}
.sr-state {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--c-text-3);
}
.sp-divider {
  height: 1px;
  background: var(--c-surface-3);
  margin: var(--space-3) 0;
}

/* ── Icon buttons ─────────────────────────────────────────── */
.topbar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--radius-control);
  border: none;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  position: relative;
  transition: background var(--motion-fast) var(--ease-brush),
              color var(--motion-fast) var(--ease-brush);
  flex-shrink: 0;
}
.topbar-icon-btn::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: inherit;
  background: radial-gradient(circle at center, var(--c-accent) 0%, transparent 70%);
  opacity: 0;
  transform: scale(0.7);
  transition: opacity 340ms var(--ease-brush), transform 380ms var(--ease-brush);
  pointer-events: none;
  z-index: -1;
  filter: blur(5px);
}
.topbar-icon-btn:hover::after { opacity: 0.12; transform: scale(1.18); }
.topbar-icon-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.topbar-icon-btn.active { color: var(--c-accent-hover); background: var(--c-accent-bg); }

/* ── Window controls ──────────────────────────────────────── */
.window-controls {
  display: flex;
  align-items: center;
  margin-left: 4px;
  border-left: 1px solid var(--ink-4);
  padding-left: 6px;
  gap: 2px;
}
.win-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  border: none;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  border-radius: 50%;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
  opacity: 0.5;
}
.window-controls:hover .win-btn { opacity: 1; width: 32px; height: 28px; border-radius: var(--radius-xs); }
.win-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.win-btn.close:hover { background: var(--c-danger); color: #fff; }

/* ── Settings popover content ─────────────────────────────── */
.settings-popover { display: flex; flex-direction: column; gap: 0; }

.sp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--space-2);
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--c-surface-3);
}
.sp-title { font-size: var(--text-sm); font-weight: 600; color: var(--c-text-0); }

.sp-tabs { margin-bottom: var(--space-3); }

.sp-body { display: flex; flex-direction: column; gap: var(--space-3); }
.sp-gap { height: var(--space-1); }

.sp-section-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--c-text-3);
}

.sp-field { display: flex; flex-direction: column; gap: 5px; }
.sp-label { font-size: var(--text-xs); color: var(--c-text-2); font-weight: 500; }

.sp-row { display: flex; gap: 4px; }
.sp-row :deep(.ui-input-wrap) { flex: 1; min-width: 0; }
.sp-select-narrow { width: 70px; flex-shrink: 0; }

.sp-actions { display: flex; gap: 6px; }
.sp-actions .ui-btn { flex: 1; }

.sp-status {
  text-align: center;
  font-size: var(--text-xs);
  font-weight: 500;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
}
.sp-status.ok { color: var(--c-success); background: var(--c-success-bg); }
.sp-status.off { color: var(--c-danger); background: var(--c-danger-bg); }
.sp-error { font-size: var(--text-xs); color: var(--c-text-2); text-align: center; }
.sp-hint { font-size: var(--text-xs); color: var(--c-text-3); line-height: var(--leading-normal); }

.sp-color-row { display: flex; align-items: center; gap: 8px; }
.sp-color {
  width: 32px;
  height: 26px;
  padding: 0;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-xs);
  cursor: pointer;
  background: none;
}
.sp-color-hex { font-size: var(--text-xs); color: var(--c-text-3); font-family: var(--font-mono); }

.sp-bg-path {
  font-size: var(--text-xs);
  color: var(--c-text-2);
  background: var(--c-surface-2);
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Light mode ───────────────────────────────────────────── */
:global([data-theme="light"]) .topbar {
  background: color-mix(in srgb, #ffffff 80%, transparent);
  border-color: var(--border-color);
  box-shadow: 0 1px 3px rgba(20, 20, 40, 0.06);
}
:global([data-theme="light"]) .topbar-fade-line {
  background: linear-gradient(to right, transparent, var(--c-surface-3) 20%, var(--c-surface-3) 80%, transparent);
}
:global([data-theme="light"]) .brand-name { color: var(--c-text-0); }

</style>
