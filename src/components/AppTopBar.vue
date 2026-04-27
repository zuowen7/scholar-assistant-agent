<template>
  <header class="topbar" data-tauri-drag-region>
    <div class="brand">
      <span class="logo">S</span>
      <div>
        <h1>Scholar Assistant</h1>
        <p>学术写作智能助手</p>
      </div>
    </div>
    <div class="mode-switch">
      <button class="mode-tab" :class="{ active: appMode === 'translate' }" @click="$emit('update:appMode', 'translate')">Translate</button>
      <button class="mode-tab" :class="{ active: appMode === 'editor' }" @click="$emit('update:appMode', 'editor')">Editor</button>
    </div>
    <div class="topbar-right">
      <!-- Engine settings -->
      <div class="settings-wrapper">
        <button class="topbar-icon-btn settings-btn" :class="{ active: showEngineSettings }" @click.stop="showEngineSettings = !showEngineSettings; showSettings = false" title="翻译引擎设置">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
          </svg>
        </button>
        <div v-if="showEngineSettings" class="settings-panel engine-panel" @click.stop>
          <div class="settings-title">翻译引擎</div>
          <div class="engine-switch">
            <button class="engine-tab" :class="{ active: engineType === 'ollama' }" @click="$emit('update:engineType', 'ollama'); $emit('save-engine-settings')">
              本地 Ollama
            </button>
            <button class="engine-tab" :class="{ active: engineType === 'cloud' }" @click="$emit('update:engineType', 'cloud'); $emit('save-engine-settings')">
              云端 API
            </button>
          </div>
          <div v-if="engineType === 'cloud'" class="cloud-settings">
            <div class="cloud-field">
              <label>供应商</label>
              <select :value="cloudConfig.provider" @change="$emit('provider-change')" class="cloud-select">
                <option v-for="(preset, key) in providerPresets" :key="key" :value="key">{{ preset.name }}</option>
              </select>
            </div>
            <div class="cloud-field">
              <label>API Key</label>
              <input type="password" :value="cloudConfig.api_key" @input="$emit('update:cloudConfig', { ...cloudConfig, api_key: ($event.target as HTMLInputElement).value })" class="cloud-input" placeholder="输入 API Key" />
            </div>
            <div class="cloud-field">
              <label>Base URL</label>
              <input type="text" :value="cloudConfig.base_url" @input="$emit('update:cloudConfig', { ...cloudConfig, base_url: ($event.target as HTMLInputElement).value })" class="cloud-input" placeholder="https://api.openai.com/v1" />
            </div>
            <div class="cloud-field">
              <label>模型</label>
              <div class="model-input-row">
                <input type="text" :value="cloudConfig.model" @input="$emit('update:cloudConfig', { ...cloudConfig, model: ($event.target as HTMLInputElement).value })" class="cloud-input" placeholder="gpt-4o" />
                <select v-if="providerPresets[cloudConfig.provider]?.models?.length" class="cloud-select model-select" @change="$emit('update:cloudConfig', { ...cloudConfig, model: ($event.target as HTMLSelectElement).value })">
                  <option value="" disabled selected>预设</option>
                  <option v-for="m in providerPresets[cloudConfig.provider]?.models || []" :key="m" :value="m">{{ m }}</option>
                </select>
              </div>
            </div>
            <div class="cloud-actions">
              <button class="settings-action-btn" :disabled="cloudChecking || !cloudConfig.api_key" @click="$emit('test-cloud')">
                <template v-if="cloudChecking">测试中...</template>
                <template v-else>测试连接</template>
              </button>
              <button class="settings-action-btn primary-btn" @click="$emit('save-engine-settings')">保存</button>
            </div>
            <div v-if="cloudConfig.api_key" class="cloud-status-hint" :class="cloudOk ? 'ok' : 'off'">
              {{ cloudOk ? '已连接' : '未连接' }}
            </div>
            <div v-if="cloudError" class="cloud-error-hint">{{ cloudError }}</div>
          </div>
          <!-- Proxy -->
          <div class="settings-section-label" style="margin-top: 12px;">网络代理</div>
          <div class="cloud-field">
            <label>代理地址</label>
            <input type="text" :value="proxyUrl" @input="$emit('update:proxyUrl', ($event.target as HTMLInputElement).value)" class="cloud-input" placeholder="http://127.0.0.1:7897 或留空" />
          </div>
          <div class="cloud-actions">
            <button class="settings-action-btn primary-btn" @click="$emit('save-proxy')">保存代理</button>
          </div>
        </div>
      </div>

      <!-- Display settings -->
      <div class="settings-wrapper">
        <button class="topbar-icon-btn settings-btn" :class="{ active: showSettings }" @click.stop="showSettings = !showSettings; showEngineSettings = false" title="背景设置">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <div v-if="showSettings" class="settings-panel settings-panel-wide" @click.stop>
          <div class="settings-title">显示设置</div>
          <div class="settings-section-label">阅读</div>
          <div class="settings-slider">
            <label>字号: {{ readSettings.fontSize }}px</label>
            <input type="range" min="12" max="28" :value="readSettings.fontSize" @input="$emit('font-size-change', $event)" class="opacity-slider" />
          </div>
          <div class="settings-slider">
            <label>行高: {{ readSettings.lineHeight }}</label>
            <input type="range" min="14" max="32" :value="Math.round(readSettings.lineHeight * 10)" @input="$emit('line-height-change', $event)" class="opacity-slider" />
          </div>
          <div class="cloud-field">
            <label>字体</label>
            <select :value="readSettings.fontFamily" @change="$emit('font-family-change', ($event.target as HTMLSelectElement).value)" class="cloud-select">
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
              <input type="color" :value="readSettings.transColor" @input="$emit('color-change', ($event.target as HTMLInputElement).value)" class="color-picker" />
              <span class="color-hex">{{ readSettings.transColor }}</span>
            </div>
          </div>
          <!-- Background -->
          <div class="settings-section-label" style="margin-top: 10px;">背景</div>
          <div class="settings-actions">
            <button class="settings-action-btn" @click="$emit('pick-background')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              选择背景
            </button>
            <button class="settings-action-btn danger" @click="$emit('clear-background')" :disabled="!bgSettings.path">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
              </svg>
              清除背景
            </button>
          </div>
          <div class="settings-slider">
            <label>不透明度: {{ bgSettings.opacity }}%</label>
            <input type="range" min="5" max="100" :value="bgSettings.opacity" @input="$emit('opacity-change', $event)" class="opacity-slider" />
          </div>
        </div>
      </div>

      <!-- Agent toggle -->
      <button class="topbar-icon-btn" :class="{ active: showAgentChat }" @click="$emit('update:showAgentChat', !showAgentChat)" title="Agent 助手">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>

      <!-- Theme toggle -->
      <button class="topbar-icon-btn" @click="$emit('toggle-theme')" :title="isDark ? '切换日间模式' : '切换夜间模式'">
        <svg v-if="isDark" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      </button>

      <!-- Health pills -->
      <span class="pill" :class="healthOk ? 'ok' : 'off'">
        <span class="pill-dot"></span>后端
      </span>
      <template v-if="engineType === 'ollama'">
        <button class="pill pill-btn" :class="ollamaOk ? 'ok' : 'off'" @click="$emit('toggle-ollama')" :disabled="ollamaLoading">
          <span class="pill-dot"></span>
          <template v-if="ollamaLoading">启动中...</template>
          <template v-else-if="ollamaOk">Ollama 在线</template>
          <template v-else>启动 Ollama</template>
        </button>
        <span v-if="ollamaError" class="pill error-text">{{ ollamaError }}</span>
      </template>
      <template v-if="engineType === 'cloud'">
        <span class="pill" :class="cloudOk ? 'ok' : 'off'">
          <span class="pill-dot"></span>
          <template v-if="cloudOk">云端已连接</template>
          <template v-else>云端未连接</template>
        </span>
      </template>

      <button class="pill pill-btn" :class="tectonicOk ? 'ok' : 'off'" @click="$emit('handle-tectonic')" :disabled="tectonicChecking">
        <span class="pill-dot"></span>
        <template v-if="tectonicChecking">检测中...</template>
        <template v-else-if="tectonicOk">LaTeX 在线</template>
        <template v-else>安装 LaTeX</template>
      </button>

      <!-- Window controls -->
      <div class="window-controls">
        <button class="win-btn minimize" @click="$emit('window-minimize')" title="最小化">
          <svg width="12" height="12" viewBox="0 0 12 12"><line x1="2" y1="6" x2="10" y2="6" stroke="currentColor" stroke-width="1.2"/></svg>
        </button>
        <button class="win-btn maximize" @click="$emit('window-maximize')" title="最大化">
          <svg width="12" height="12" viewBox="0 0 12 12"><rect x="2" y="2" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1.2" rx="1"/></svg>
        </button>
        <button class="win-btn close" @click="$emit('window-close')" title="关闭">
          <svg width="12" height="12" viewBox="0 0 12 12"><line x1="2" y1="2" x2="10" y2="10" stroke="currentColor" stroke-width="1.2"/><line x1="10" y1="2" x2="2" y2="10" stroke="currentColor" stroke-width="1.2"/></svg>
        </button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
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

const showEngineSettings = ref(false)
const showSettings = ref(false)

function onDocumentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.settings-wrapper')) {
    showEngineSettings.value = false
    showSettings.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<style scoped>
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; min-width: 0;
  padding: 12px 16px; background: var(--topbar-bg);
  border-bottom: 1px solid var(--c-surface-3); flex-shrink: 0;
  -webkit-app-region: drag;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  position: relative; z-index: 210;
}
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 0 1 240px; }
.logo {
  width: 32px; height: 32px; border-radius: 8px;
  background: linear-gradient(135deg, var(--c-accent), #a78bfa);
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 15px; color: #fff;
}
.brand h1 { font-size: 14px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.brand p { font-size: 11px; color: var(--c-text-3); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.mode-switch {
  display: flex; background: rgba(255,255,255,0.06);
  border-radius: 6px; padding: 2px; gap: 2px;
}
.mode-tab {
  background: none; border: none;
  color: var(--c-text-2);
  padding: 4px 14px; border-radius: 4px;
  font-size: 12px; cursor: pointer; transition: all 0.15s;
}
.mode-tab:hover { color: var(--c-text-1); }
.mode-tab.active { background: rgba(255,255,255,0.1); color: #fff; }

.topbar-right { display: flex; gap: 8px; align-items: center; min-width: 0; flex-shrink: 1; justify-content: flex-end; }

.settings-wrapper { position: relative; -webkit-app-region: no-drag; }

.topbar-icon-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 6px;
  background: transparent; border: none; color: var(--c-text-3);
  cursor: pointer; transition: all 0.15s;
}
.topbar-icon-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.topbar-icon-btn.active { color: var(--c-accent-hover); background: var(--c-accent-bg); }

.settings-panel {
  position: absolute; top: 100%; right: 0; margin-top: 6px;
  width: 240px; background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3); border-radius: var(--radius-lg);
  padding: 14px; box-shadow: 0 8px 32px var(--c-shadow);
  z-index: 220; -webkit-app-region: no-drag;
  max-height: calc(100vh - 60px); overflow-y: auto; overflow-x: hidden;
}
.settings-panel-wide { width: 280px; }

.settings-title { font-size: 13px; font-weight: 600; color: var(--c-text-0); margin-bottom: 12px; }
.settings-section-label { font-size: 11px; font-weight: 600; color: var(--c-text-3); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }

.settings-actions { display: flex; gap: 6px; margin-bottom: 14px; }
.settings-action-btn {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 4px;
  padding: 7px 8px; border: 1px solid var(--c-surface-3); border-radius: 7px;
  background: var(--c-surface-2); color: var(--c-text-2);
  font-size: 12px; font-family: inherit; cursor: pointer; transition: all 0.15s;
}
.settings-action-btn:hover { background: var(--c-surface-3); color: var(--c-text-0); }
.settings-action-btn.danger:hover { background: var(--c-danger-bg); border-color: var(--c-danger-border); color: var(--c-danger); }
.settings-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.settings-action-btn.primary-btn { background: var(--c-accent) !important; color: #fff !important; border-color: var(--c-accent) !important; }
.settings-action-btn.primary-btn:hover { opacity: 0.9; }

.settings-slider { display: flex; flex-direction: column; gap: 6px; }
.settings-slider label { font-size: 11px; color: var(--c-text-3); }
.opacity-slider {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 4px; border-radius: 2px;
  background: var(--c-surface-2); outline: none; cursor: pointer;
}
.opacity-slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--c-accent); cursor: pointer; transition: transform 0.15s;
}
.opacity-slider::-webkit-slider-thumb:hover { transform: scale(1.2); }

.engine-panel { width: 320px; right: 0; }
.engine-switch { display: flex; gap: 4px; background: var(--c-surface-2); border-radius: 8px; padding: 3px; margin-bottom: 14px; }
.engine-tab {
  flex: 1; padding: 6px 10px; border: none; border-radius: 6px;
  background: transparent; color: var(--c-text-3);
  font-size: 12px; font-weight: 500; font-family: inherit;
  cursor: pointer; transition: all 0.15s;
}
.engine-tab.active { background: var(--c-accent); color: #fff; }
.engine-tab:not(.active):hover { color: var(--c-text-0); }

.cloud-settings { display: flex; flex-direction: column; gap: 10px; }
.cloud-field { display: flex; flex-direction: column; gap: 4px; }
.cloud-field label { font-size: 11px; color: var(--c-text-3); font-weight: 500; }
.cloud-input, .cloud-select {
  width: 100%; padding: 7px 10px; border: 1px solid var(--c-surface-3);
  border-radius: 7px; background: var(--c-surface-2); color: var(--c-text-0);
  font-size: 12px; font-family: inherit; outline: none;
  transition: border-color 0.15s; box-sizing: border-box;
}
.cloud-input:focus, .cloud-select:focus { border-color: var(--c-accent); }
.cloud-select {
  cursor: pointer; -webkit-appearance: none; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2371717a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center; padding-right: 24px;
}
.model-input-row { display: flex; gap: 4px; }
.model-input-row .cloud-input { flex: 1; }
.model-select { width: auto; min-width: 70px; flex-shrink: 0; }
.cloud-actions { display: flex; gap: 6px; margin-top: 4px; }
.cloud-actions .settings-action-btn { flex: 1; }

.cloud-status-hint { text-align: center; font-size: 12px; font-weight: 500; padding: 6px; border-radius: 6px; }
.cloud-status-hint.ok { color: var(--c-success); background: rgba(74, 222, 128, 0.08); }
.cloud-status-hint.off { color: var(--c-danger); background: var(--c-danger-bg); }
.cloud-error-hint { text-align: center; font-size: 11px; color: var(--c-text-2); padding: 4px 6px; margin-top: 4px; }

.color-row { display: flex; align-items: center; gap: 8px; }
.color-picker { width: 32px; height: 26px; border: 1px solid var(--c-surface-3); border-radius: 4px; cursor: pointer; padding: 0; background: none; }
.color-hex { font-size: 11px; color: var(--c-text-3); font-family: monospace; }

.window-controls { display: flex; align-items: center; margin-left: 4px; -webkit-app-region: no-drag; }
.win-btn {
  display: flex; align-items: center; justify-content: center;
  width: 34px; height: 30px; background: transparent; border: none;
  color: var(--c-text-3); cursor: pointer; transition: all 0.12s; border-radius: 4px;
}
.win-btn:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.win-btn.close:hover { background: var(--c-danger); color: #fff; }

.pill {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; padding: 5px 10px; border-radius: 20px;
  background: var(--c-surface-2); color: var(--c-text-3);
  border: none; font-family: inherit;
  -webkit-app-region: no-drag; white-space: nowrap;
}
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--c-text-3); flex-shrink: 0; }
.pill.ok .pill-dot { background: var(--c-success); box-shadow: 0 0 6px var(--c-success); }
.pill.ok { color: var(--c-success); }
.pill.off .pill-dot { background: var(--c-danger); }

.pill-btn { cursor: pointer; transition: all 0.2s; }
.pill-btn:hover { background: var(--c-surface-3); }
.pill-btn:disabled { opacity: 0.5; cursor: wait; }
.pill-btn.ok { cursor: default; }
.pill-btn.ok:hover { background: var(--c-surface-2); }

.error-text {
  color: var(--c-danger); font-size: 11px;
  background: var(--c-danger-bg); border: 1px solid var(--c-danger-border);
  max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

@media (max-width: 760px) {
  .topbar { gap: 6px; padding: 8px; }
  .brand { flex: 0 1 auto; gap: 6px; }
  .brand h1, .brand p { display: none; }
  .logo { width: 28px; height: 28px; border-radius: 8px; font-size: 14px; }
  .mode-switch { padding: 2px; gap: 1px; }
  .mode-tab { padding: 3px 8px; font-size: 11px; }
  .topbar-right { gap: 3px; margin-left: auto; }
  .topbar-icon-btn { width: 28px; height: 28px; }
}

@media (max-width: 520px) {
  .topbar-right .pill { max-width: 68px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}
</style>
