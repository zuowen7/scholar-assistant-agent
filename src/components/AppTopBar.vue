<template>
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
        @update:model-value="$emit('update:appMode', $event as any)"
      />
    </div>

    <!-- ── Right: Actions ──────────────────────────────────── -->
    <div class="topbar-right">

      <!-- Status cluster -->
      <StatusCluster
        :health-ok="healthOk"
        :engine-type="engineType"
        :ollama-ok="ollamaOk"
        :ollama-loading="ollamaLoading"
        :cloud-ok="cloudOk"
        :tectonic-ok="tectonicOk"
        :tectonic-checking="tectonicChecking"
        @toggle-ollama="$emit('toggle-ollama')"
        @handle-tectonic="$emit('handle-tectonic')"
      />

      <div class="topbar-sep" />

      <!-- Unified Settings popover -->
      <UiPopover ref="settingsPopoverRef" :width="320" align="end" :offset="8">
        <template #trigger>
          <button
            class="topbar-icon-btn"
            :class="{ active: settingsPopoverOpen }"
            title="设置"
            @click="settingsPopoverOpen = !settingsPopoverOpen"
          >
            <Settings :size="15" :stroke-width="1.6" />
          </button>
        </template>

        <div class="settings-popover">
          <div class="sp-header">
            <span class="sp-title">设置</span>
          </div>
          <UiSegmented
            v-model="settingsTab"
            :options="settingsTabOptions"
            size="sm"
            full
            class="sp-tabs"
          />

          <!-- Engine tab -->
          <div v-show="settingsTab === 'engine'" class="sp-body">
            <div class="sp-section-label">翻译引擎</div>
            <UiSegmented
              :model-value="engineType"
              :options="engineOptions"
              size="sm"
              full
              @update:model-value="$emit('update:engineType', $event as any); $emit('save-engine-settings')"
            />
            <template v-if="engineType === 'cloud'">
              <div class="sp-gap" />
              <div class="sp-section-label">云端配置</div>
              <div class="sp-field">
                <label class="sp-label">供应商</label>
                <select
                  :value="cloudConfig.provider"
                  class="sp-select"
                  @change="$emit('provider-change'); $emit('update:cloudConfig', { ...cloudConfig, provider: ($event.target as HTMLSelectElement).value })"
                >
                  <option v-for="(preset, key) in providerPresets" :key="key" :value="key">{{ preset.name }}</option>
                </select>
              </div>
              <div class="sp-field">
                <label class="sp-label">API Key</label>
                <input
                  type="password"
                  :value="cloudConfig.api_key"
                  class="sp-input"
                  placeholder="输入 API Key"
                  @input="$emit('update:cloudConfig', { ...cloudConfig, api_key: ($event.target as HTMLInputElement).value })"
                />
              </div>
              <div class="sp-field">
                <label class="sp-label">Base URL</label>
                <input
                  type="text"
                  :value="cloudConfig.base_url"
                  class="sp-input"
                  placeholder="https://api.openai.com/v1"
                  @input="$emit('update:cloudConfig', { ...cloudConfig, base_url: ($event.target as HTMLInputElement).value })"
                />
              </div>
              <div class="sp-field">
                <label class="sp-label">模型</label>
                <div class="sp-row">
                  <input
                    type="text"
                    :value="cloudConfig.model"
                    class="sp-input"
                    placeholder="gpt-4o"
                    @input="$emit('update:cloudConfig', { ...cloudConfig, model: ($event.target as HTMLInputElement).value })"
                  />
                  <select
                    v-if="providerPresets[cloudConfig.provider]?.models?.length"
                    class="sp-select sp-select-narrow"
                    @change="$emit('update:cloudConfig', { ...cloudConfig, model: ($event.target as HTMLSelectElement).value })"
                  >
                    <option value="" disabled selected>预设</option>
                    <option v-for="m in providerPresets[cloudConfig.provider]?.models" :key="m" :value="m">{{ m }}</option>
                  </select>
                </div>
              </div>
              <div class="sp-actions">
                <UiButton variant="secondary" size="sm" :loading="cloudChecking" :disabled="!cloudConfig.api_key" @click="$emit('test-cloud')">测试连接</UiButton>
                <UiButton variant="primary" size="sm" @click="$emit('save-engine-settings')">保存</UiButton>
              </div>
              <div v-if="cloudConfig.api_key" class="sp-status" :class="cloudOk ? 'ok' : 'off'">
                {{ cloudOk ? '已连接' : '未连接' }}
              </div>
              <div v-if="cloudError" class="sp-error">{{ cloudError }}</div>
            </template>
          </div>

          <!-- Display tab -->
          <div v-show="settingsTab === 'display'" class="sp-body">
            <div class="sp-section-label">文字排版</div>
            <div class="sp-slider">
              <div class="sp-slider-label"><span>字号</span><span>{{ readSettings.fontSize }}px</span></div>
              <input type="range" min="12" max="28" :value="readSettings.fontSize" class="sp-range" @input="$emit('font-size-change', $event)" />
            </div>
            <div class="sp-slider">
              <div class="sp-slider-label"><span>行高</span><span>{{ readSettings.lineHeight }}</span></div>
              <input type="range" min="14" max="32" :value="Math.round(readSettings.lineHeight * 10)" class="sp-range" @input="$emit('line-height-change', $event)" />
            </div>
            <div class="sp-field">
              <label class="sp-label">字体</label>
              <select :value="readSettings.fontFamily" class="sp-select" @change="$emit('font-family-change', ($event.target as HTMLSelectElement).value)">
                <option value="system-ui">系统默认</option>
                <option value="'Noto Sans SC', sans-serif">思源黑体</option>
                <option value="'Noto Serif SC', serif">思源宋体</option>
                <option value="'LXGW WenKai', serif">霞鹜文楷</option>
                <option value="'Microsoft YaHei', sans-serif">微软雅黑</option>
                <option value="SimSun, serif">宋体</option>
              </select>
            </div>
            <div class="sp-field">
              <label class="sp-label">译文颜色</label>
              <div class="sp-color-row">
                <input type="color" :value="readSettings.transColor" class="sp-color" @input="$emit('color-change', ($event.target as HTMLInputElement).value)" />
                <span class="sp-color-hex">{{ readSettings.transColor }}</span>
              </div>
            </div>
          </div>

          <!-- Network tab -->
          <div v-show="settingsTab === 'network'" class="sp-body">
            <div class="sp-section-label">HTTP 代理</div>
            <div class="sp-field">
              <label class="sp-label">代理地址</label>
              <input
                type="text"
                :value="proxyUrl"
                class="sp-input"
                placeholder="http://127.0.0.1:7897 或留空"
                @input="$emit('update:proxyUrl', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="sp-actions">
              <UiButton variant="primary" size="sm" @click="$emit('save-proxy')">保存代理</UiButton>
            </div>
            <p class="sp-hint">留空则不使用代理。重启后端后生效。</p>
          </div>

          <!-- Background tab -->
          <div v-show="settingsTab === 'background'" class="sp-body">
            <div class="sp-section-label">自定义背景</div>
            <div class="sp-actions">
              <UiButton variant="secondary" size="sm" @click="$emit('pick-background')">
                <template #icon-left><Upload :size="13" :stroke-width="1.8" /></template>
                选择文件
              </UiButton>
              <UiButton variant="danger" size="sm" :disabled="!bgSettings.path" @click="$emit('clear-background')">
                <template #icon-left><Trash2 :size="13" :stroke-width="1.8" /></template>
                清除
              </UiButton>
            </div>
            <div v-if="bgSettings.path" class="sp-bg-path">{{ bgSettings.path.split(/[\\/]/).pop() }}</div>
            <div class="sp-slider">
              <div class="sp-slider-label"><span>不透明度</span><span>{{ bgSettings.opacity }}%</span></div>
              <input type="range" min="5" max="100" :value="bgSettings.opacity" class="sp-range" @input="$emit('opacity-change', $event)" />
            </div>
          </div>
        </div>
      </UiPopover>

      <!-- Agent toggle -->
      <button
        class="topbar-icon-btn"
        :class="{ active: showAgentChat }"
        title="Agent 助手"
        @click="$emit('update:showAgentChat', !showAgentChat)"
      >
        <MessageSquare :size="15" :stroke-width="1.6" />
      </button>

      <!-- Theme toggle -->
      <button
        class="topbar-icon-btn"
        :title="isDark ? '切换日间模式' : '切换夜间模式'"
        @click="$emit('toggle-theme')"
      >
        <Sun v-if="isDark" :size="15" :stroke-width="1.6" />
        <Moon v-else :size="15" :stroke-width="1.6" />
      </button>

      <!-- Window controls -->
      <div class="window-controls">
        <button class="win-btn minimize" title="最小化" @click="$emit('window-minimize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><line x1="2" y1="5" x2="8" y2="5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </button>
        <button class="win-btn maximize" title="最大化" @click="$emit('window-maximize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="2" y="2" width="6" height="6" fill="none" stroke="currentColor" stroke-width="1.2" rx="1"/></svg>
        </button>
        <button class="win-btn close" title="关闭" @click="$emit('window-close')">
          <svg width="10" height="10" viewBox="0 0 10 10"><line x1="2.5" y1="2.5" x2="7.5" y2="7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><line x1="7.5" y1="2.5" x2="2.5" y2="7.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Settings, Sun, Moon, Upload, Trash2, MessageSquare } from './ui/icons'
import UiSegmented from './ui/UiSegmented.vue'
import UiButton from './ui/UiButton.vue'
import UiPopover from './ui/UiPopover.vue'
import StatusCluster from './StatusCluster.vue'
import type { AppMode } from '../types'

defineProps<{
  appMode: AppMode
  isDark: boolean
  showAgentChat: boolean
  engineType: 'ollama' | 'cloud'
  cloudConfig: { provider: string; api_key: string; base_url: string; model: string; max_tokens: number }
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
  (e: 'update:proxyUrl', value: string): void
  (e: 'toggle-theme'): void
  (e: 'toggle-ollama'): void
  (e: 'handle-tectonic'): void
  (e: 'save-engine-settings'): void
  (e: 'test-cloud'): void
  (e: 'provider-change'): void
  (e: 'save-proxy'): void
  (e: 'pick-background'): void
  (e: 'clear-background'): void
  (e: 'opacity-change', event: Event): void
  (e: 'font-size-change', event: Event): void
  (e: 'line-height-change', event: Event): void
  (e: 'save-read-settings'): void
  (e: 'font-family-change', value: string): void
  (e: 'color-change', value: string): void
  (e: 'window-minimize'): void
  (e: 'window-maximize'): void
  (e: 'window-close'): void
}>()

const settingsPopoverRef = ref<InstanceType<typeof UiPopover> | null>(null)
const settingsPopoverOpen = computed(() => settingsPopoverRef.value?.open ?? false)
const settingsTab = ref<'engine' | 'display' | 'network' | 'background'>('engine')

const modeOptions = [
  { value: 'translate' as AppMode, label: '翻译' },
  { value: 'editor' as AppMode, label: '编辑' },
]

const settingsTabOptions = [
  { value: 'engine', label: '引擎' },
  { value: 'display', label: '显示' },
  { value: 'network', label: '网络' },
  { value: 'background', label: '背景' },
]

const engineOptions = [
  { value: 'ollama' as const, label: '本地 Ollama' },
  { value: 'cloud' as const, label: '云端 API' },
]
</script>

<style scoped>
/* ── Topbar shell ─────────────────────────────────────────── */
.topbar {
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0 12px 0 0;
  gap: 0;
  background: var(--topbar-bg);
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
  position: relative;
  z-index: 210;
  -webkit-app-region: drag;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}

/* ── Brand ────────────────────────────────────────────────── */
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px 0 12px;
  height: 100%;
  flex-shrink: 0;
  border-right: 1px solid var(--c-surface-3);
}
.logo {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: linear-gradient(135deg, var(--c-accent) 0%, #a78bfa 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  color: #fff;
  flex-shrink: 0;
}
.brand-name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--c-text-0);
  letter-spacing: 0.01em;
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
  height: 18px;
  background: var(--c-surface-3);
  margin: 0 4px;
  flex-shrink: 0;
}

/* ── Icon buttons ─────────────────────────────────────────── */
.topbar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
  flex-shrink: 0;
}
.topbar-icon-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.topbar-icon-btn.active { color: var(--c-accent-hover); background: var(--c-accent-bg); }

/* ── Window controls ──────────────────────────────────────── */
.window-controls {
  display: flex;
  align-items: center;
  margin-left: 4px;
  border-left: 1px solid var(--c-surface-3);
  padding-left: 4px;
}
.win-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 30px;
  border: none;
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  border-radius: var(--radius-xs);
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}
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
.sp-input, .sp-select {
  width: 100%;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--motion-fast) var(--ease-out);
  box-sizing: border-box;
}
.sp-input:focus, .sp-select:focus { border-color: var(--c-accent); }
.sp-select {
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 26px;
}

.sp-row { display: flex; gap: 4px; }
.sp-row .sp-input { flex: 1; min-width: 0; }
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
.sp-status.ok { color: var(--c-success); background: rgba(74, 222, 128, 0.09); }
.sp-status.off { color: var(--c-danger); background: var(--c-danger-bg); }
.sp-error { font-size: var(--text-xs); color: var(--c-text-2); text-align: center; }
.sp-hint { font-size: var(--text-xs); color: var(--c-text-3); line-height: var(--leading-normal); }

.sp-slider { display: flex; flex-direction: column; gap: 6px; }
.sp-slider-label {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xs);
  color: var(--c-text-2);
}
.sp-range {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 3px;
  border-radius: 2px;
  background: var(--c-surface-3);
  outline: none;
  cursor: pointer;
}
.sp-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--c-accent);
  cursor: pointer;
  transition: transform var(--motion-fast) var(--ease-spring);
}
.sp-range::-webkit-slider-thumb:hover { transform: scale(1.25); }

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
.sp-color-hex { font-size: var(--text-xs); color: var(--c-text-3); font-family: ui-monospace, monospace; }

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
:global(.light) .topbar {
  --topbar-bg: rgba(255, 255, 255, 0.6);
}
:global(.light) .brand-name { color: var(--c-text-1); }
</style>
