<template>
  <UiPopover ref="popoverRef" :width="400" align="end" :offset="8" @open="onOpen">
    <template #trigger>
      <button
        class="dp-trigger"
        :class="{ active: isOpen, 'has-errors': unreadErrorCount > 0 }"
        :title="t('editor.debugTitle')"
      >
        <Terminal :size="15" :stroke-width="1.6" />
        <span v-if="unreadErrorCount > 0" class="dp-badge-count">
          {{ unreadErrorCount > 99 ? '99+' : unreadErrorCount }}
        </span>
      </button>
    </template>

    <div class="dp-panel">
      <div class="dp-header">
        <span class="dp-title">{{ t('editor.debugTitle') }}</span>
        <div class="dp-header-actions">
          <UiSegmented v-model="tab" :options="tabOptions" size="sm" />
          <button class="dp-clear-btn" :title="t('settings.clear')" @click="clearCurrentTab">{{ t('settings.clear') }}</button>
        </div>
      </div>

      <!-- 前端错误 -->
      <div v-show="tab === 'frontend'" class="dp-list">
        <div v-if="errorLog.length === 0" class="dp-empty">{{ t('editor.debugNoErrors') }}</div>
        <div v-for="entry in errorLog" :key="entry.id" class="dp-entry" :class="entry.level">
          <span class="dp-ts">{{ entry.ts }}</span>
          <span class="dp-level" :class="entry.level">{{ entry.level === 'danger' ? 'ERR' : 'WARN' }}</span>
          <span class="dp-msg">{{ entry.message }}</span>
        </div>
      </div>

      <!-- 后端日志 -->
      <div v-show="tab === 'backend'" class="dp-list">
        <div v-if="loading" class="dp-empty">{{ t('general.loading') }}</div>
        <div v-else-if="fetchError" class="dp-empty dp-fetch-error">{{ fetchError }}</div>
        <template v-else>
          <div class="dp-path-row" :title="logPath">
            <span class="dp-path-label">{{ t('editor.debugLogFile') }}</span>
            <span class="dp-path-value">{{ logPath }}</span>
            <button class="dp-open-btn" @click="openLogFolder">{{ t('editor.debugOpenDir') }}</button>
          </div>
          <div v-if="logLines.length === 0" class="dp-empty">{{ t('editor.debugNoLogs') }}</div>
          <div v-for="(line, i) in logLines" :key="i" class="dp-line">{{ line }}</div>
        </template>
      </div>
    </div>
  </UiPopover>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { errorLog, unreadErrorCount, clearErrorLog, markErrorsRead, useToast } from '../composables/useToast'
import { Terminal } from './ui/icons'
import UiPopover from './ui/UiPopover.vue'
import UiSegmented from './ui/UiSegmented.vue'
import { API_BASE as apiBase } from '../utils/api'

const { pushError } = useToast()

const popoverRef = ref<InstanceType<typeof UiPopover> | null>(null)
const isOpen = computed(() => popoverRef.value?.open ?? false)

const tab = ref<'frontend' | 'backend'>('frontend')
const tabOptions = [
  { value: 'frontend', label: t('general.error') },
  { value: 'backend', label: t('topbar.backend') },
]

const logLines = ref<string[]>([])
const logPath = ref('')
const loading = ref(false)
const fetchError = ref('')

async function fetchLogs() {
  loading.value = true
  fetchError.value = ''
  try {
    const res = await fetch(`${apiBase}/api/logs?n=100`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    logLines.value = data.lines ?? []
    logPath.value = data.path ?? ''
  } catch (e) {
    fetchError.value = e instanceof Error ? e.message : t('editor.debugFetchFailed')
  } finally {
    loading.value = false
  }
}

function onOpen() {
  markErrorsRead()
  if (tab.value === 'backend') fetchLogs()
}

watch(tab, (t) => {
  if (t === 'backend' && isOpen.value) fetchLogs()
})

function clearCurrentTab() {
  if (tab.value === 'backend') {
    logLines.value = []
    fetchError.value = ''
  } else {
    clearErrorLog()
  }
}

async function openLogFolder() {
  if (!logPath.value) return
  const dir = logPath.value.replace(/[/\\][^/\\]+$/, '')
  try {
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(dir)
  } catch {
    // Tauri open() scope may reject local paths; try shell command fallback
    try {
      const { Command } = await import('@tauri-apps/plugin-shell')
      const isWin = /windows/i.test(navigator.userAgent || '')
      if (isWin) {
        await Command.create('explorer', [dir]).execute()
      } else {
        await Command.create('open', [dir]).execute()
      }
    } catch {
      pushError('无法打开日志目录：' + dir)
    }
  }
}
</script>

<style scoped>
/* ── Trigger button ───────────────────────────────────────── */
.dp-trigger {
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
.dp-trigger::after {
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
.dp-trigger:hover::after { opacity: 0.12; transform: scale(1.18); }
.dp-trigger:hover  { background: var(--c-surface-2); color: var(--c-text-0); }
.dp-trigger.active { color: var(--c-accent-hover); background: var(--c-accent-bg); }
.dp-trigger.has-errors { color: var(--c-danger); }

/* Unread count badge */
.dp-badge-count {
  position: absolute;
  top: 3px;
  right: 3px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  background: var(--c-danger);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  line-height: 14px;
  text-align: center;
  pointer-events: none;
}

/* ── Panel layout ─────────────────────────────────────────── */
.dp-panel { display: flex; flex-direction: column; gap: 0; }

.dp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: var(--space-2);
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--c-surface-3);
}
.dp-title { font-size: var(--text-sm); font-weight: 600; color: var(--c-text-0); }
.dp-header-actions { display: flex; gap: 6px; align-items: center; }

.dp-clear-btn {
  border: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-3);
  font-size: var(--text-xs);
  padding: 2px 8px;
  border-radius: var(--radius-control);
  cursor: pointer;
}
.dp-clear-btn:hover { background: var(--c-surface-2); color: var(--c-text-1); }

/* ── Log list ─────────────────────────────────────────────── */
.dp-list {
  max-height: 340px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
  scrollbar-width: thin;
}

.dp-empty {
  padding: 20px 0;
  text-align: center;
  font-size: var(--text-xs);
  color: var(--c-text-3);
}
.dp-fetch-error { color: var(--c-danger); }

/* Frontend error entries */
.dp-entry {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  line-height: 1.5;
}
.dp-entry:hover { background: var(--c-surface-2); }
.dp-entry.danger { border-left: 2px solid var(--c-danger); }
.dp-entry.warn   { border-left: 2px solid var(--c-warn); }

.dp-ts {
  color: var(--c-text-3);
  font-size: 10px;
  white-space: nowrap;
  flex-shrink: 0;
  padding-top: 1px;
}
.dp-level {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  white-space: nowrap;
  flex-shrink: 0;
}
.dp-level.danger { background: color-mix(in srgb, var(--c-danger) 15%, transparent); color: var(--c-danger); }
.dp-level.warn   { background: color-mix(in srgb, var(--c-warn) 15%, transparent);   color: var(--c-warn); }

.dp-msg { color: var(--c-text-1); word-break: break-all; flex: 1; }

/* Backend log path row */
.dp-path-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px 6px;
  font-size: 10px;
  color: var(--c-text-3);
  border-bottom: 1px solid var(--c-surface-3);
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.dp-path-label { flex-shrink: 0; }
.dp-path-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--c-text-2);
  font-family: var(--font-mono, monospace);
  font-size: 10px;
}
.dp-open-btn {
  border: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-3);
  font-size: 10px;
  padding: 1px 7px;
  border-radius: var(--radius-control);
  cursor: pointer;
  flex-shrink: 0;
}
.dp-open-btn:hover { background: var(--c-surface-2); color: var(--c-text-1); }

/* Backend log lines */
.dp-line {
  font-family: var(--font-mono, monospace);
  font-size: 10px;
  color: var(--c-text-2);
  padding: 1px 6px;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
}
.dp-line:hover { background: var(--c-surface-2); }
</style>
