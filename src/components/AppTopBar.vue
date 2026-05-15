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
          <button class="status-trigger" :class="overallStatus" title="服务状态" aria-label="服务状态">
            <span class="status-dot" />
            <span class="status-label">{{ engineType === 'ollama' ? 'Ollama' : '云端' }}</span>
          </button>
        </template>
        <div class="status-popover">
          <div class="sp-header">
            <span class="sp-title">服务状态</span>
          </div>

          <div class="status-rows">
            <div class="status-row">
              <span class="sr-dot" :class="healthOk ? 'ok' : 'off'" />
              <span class="sr-label">后端</span>
              <span class="sr-state">{{ healthOk ? '在线' : '离线' }}</span>
            </div>
            <template v-if="engineType === 'ollama'">
              <div class="status-row">
                <span class="sr-dot" :class="ollamaOk ? 'ok' : 'off'" />
                <span class="sr-label">Ollama</span>
                <span class="sr-state">
                  <template v-if="ollamaLoading">启动中…</template>
                  <template v-else>{{ ollamaOk ? '在线' : '离线' }}</template>
                </span>
                <UiButton v-if="!ollamaOk && !ollamaLoading" variant="ghost" size="sm" @click="$emit('toggle-ollama')">启动</UiButton>
              </div>
            </template>
            <template v-else>
              <div class="status-row">
                <span class="sr-dot" :class="cloudOk ? 'ok' : 'off'" />
                <span class="sr-label">云端 API</span>
                <span class="sr-state">{{ cloudOk ? '已连接' : '未连接' }}</span>
              </div>
            </template>
            <div class="status-row">
              <span class="sr-dot" :class="tectonicOk ? 'ok' : 'off'" />
              <span class="sr-label">LaTeX</span>
              <span class="sr-state">{{ tectonicChecking ? '检测…' : tectonicOk ? '就绪' : '未安装' }}</span>
              <UiButton v-if="!tectonicOk && !tectonicChecking" variant="ghost" size="sm" @click="$emit('handle-tectonic')">安装</UiButton>
            </div>
          </div>

          <div class="sp-divider" />

          <!-- Engine switch inside popover -->
          <div class="sp-section-label">翻译引擎</div>
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
            title="设置"
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
                  placeholder="输入 API Key"
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
                <label class="sp-label">模型</label>
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
                    <option value="" disabled selected>预设</option>
                    <option v-for="m in providerPresets[cloudConfig.provider]?.models" :key="m" :value="m">{{ m }}</option>
                  </UiSelect>
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
            <UiSlider
              label="字号"
              :model-value="readSettings.fontSize"
              :min="12"
              :max="28"
              suffix="px"
              @update:model-value="$emit('font-size-change', $event)"
            />
            <UiSlider
              label="行高"
              :model-value="Math.round(readSettings.lineHeight * 10)"
              :min="14"
              :max="32"
              @update:model-value="$emit('line-height-change', $event)"
            />
            <div class="sp-field">
              <label class="sp-label">字体</label>
              <UiSelect
                :model-value="readSettings.fontFamily"
                @update:model-value="$emit('font-family-change', $event)"
              >
                <option value="system-ui">系统默认</option>
                <option value="'Noto Sans SC', sans-serif">思源黑体</option>
                <option value="'Noto Serif SC', serif">思源宋体</option>
                <option value="'LXGW WenKai', serif">霞鹜文楷</option>
                <option value="'Microsoft YaHei', sans-serif">微软雅黑</option>
                <option value="SimSun, serif">宋体</option>
              </UiSelect>
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
              <UiInput
                :model-value="proxyUrl"
                placeholder="http://127.0.0.1:7897 或留空"
                @update:model-value="$emit('update:proxyUrl', $event)"
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
            <UiSlider
              label="不透明度"
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
        title="Agent 助手"
        @click="$emit('update:showAgentChat', !showAgentChat)"
      >
        <MessageSquare :size="15" :stroke-width="1.6" />
      </button>

      <!-- Debug panel -->
      <DebugPanel />

      <!-- Theme toggle -->
      <button
        class="topbar-icon-btn"
        :title="isDark ? '切换日间模式' : '切换夜间模式'"
        @click="$emit('toggle-theme', $event)"
      >
        <Sun v-if="isDark" :size="15" :stroke-width="1.6" />
        <Moon v-else :size="15" :stroke-width="1.6" />
      </button>

      <!-- Window controls -->
      <div class="window-controls">
        <button class="win-btn minimize" title="最小化" aria-label="最小化窗口" @click="$emit('window-minimize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><line x1="2" y1="5" x2="8" y2="5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        </button>
        <button class="win-btn maximize" title="最大化" aria-label="最大化窗口" @click="$emit('window-maximize')">
          <svg width="10" height="10" viewBox="0 0 10 10"><rect x="2" y="2" width="6" height="6" fill="none" stroke="currentColor" stroke-width="1.2" rx="1"/></svg>
        </button>
        <button class="win-btn close" title="关闭" aria-label="关闭窗口" @click="$emit('window-close')">
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
import { argMapV2Enabled } from '../composables/useArgumentMap'
import { Settings, Sun, Moon, Upload, Trash2, MessageSquare } from './ui/icons'
import UiSegmented from './ui/UiSegmented.vue'
import UiButton from './ui/UiButton.vue'
import UiPopover from './ui/UiPopover.vue'
import UiInput from './ui/UiInput.vue'
import UiSelect from './ui/UiSelect.vue'
import UiSlider from './ui/UiSlider.vue'
import DebugPanel from './DebugPanel.vue'
import type { AppMode } from '../types'

const props = defineProps<{
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
  (e: 'toggle-theme', event?: MouseEvent): void
  (e: 'toggle-ollama'): void
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
  { value: 'translate' as AppMode, label: '翻译' },
  { value: 'editor' as AppMode, label: '编辑' },
  ...(argMapV2Enabled.value ? [{ value: 'argument' as AppMode, label: '论证' }] : []),
])

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
/* Ink bleed hover — 墨韵涟漪 */
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
