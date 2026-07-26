<template>
  <div class="app-shell">
    <div
      class="shell-drag-rail"
      data-testid="window-drag-rail"
      :aria-label="t('shell.windowDragRegion')"
      @mousedown="startWindowDrag"
      @dblclick="toggleMaximize"
    />
    <AppSidebar
      :active-module="activeModule"
      :project-name="projectName"
      :workspace-active="workspaceActive"
      :agent-open="agentOpen"
      :provider="provider"
      :model="model"
      :model-online="modelOnline"
      @navigate="$emit('navigate', $event)"
      @home="$emit('home')"
      @settings="$emit('settings')"
      @agent="$emit('agent')"
    />
    <main class="app-shell-main"><slot /></main>
    <slot name="assistant" />
    <div class="shell-window-controls" :aria-label="t('shell.windowControls')">
      <button
        type="button"
        :title="t('topbar.minimize')"
        :aria-label="t('topbar.minimize')"
        @click="minimize"
      >
        <Minus :size="14" aria-hidden="true" />
      </button>
      <button
        type="button"
        :title="t('topbar.maximize')"
        :aria-label="t('topbar.maximize')"
        @click="toggleMaximize"
      >
        <Square :size="12" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="close"
        :title="t('topbar.close')"
        :aria-label="t('topbar.close')"
        @click="closeWindow"
      >
        <X :size="14" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import AppSidebar from './AppSidebar.vue'
import { Minus, Square, X } from 'lucide-vue-next'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { getCurrentWebview } from '@tauri-apps/api/webview'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
defineProps<{
  activeModule: 'draft' | 'sources' | 'review' | null
  projectName?: string | null
  workspaceActive?: boolean
  agentOpen?: boolean
  provider: string
  model: string
  modelOnline?: boolean
}>()
defineEmits<{
  navigate: [module: 'draft' | 'sources' | 'review']
  home: []
  settings: []
  agent: []
}>()

async function minimize() {
  try {
    await getCurrentWindow().minimize()
  } catch {
    /* web */
  }
}
async function toggleMaximize() {
  try {
    await getCurrentWindow().toggleMaximize()
  } catch {
    /* web */
  }
}
async function closeWindow() {
  try {
    await getCurrentWindow().close()
  } catch {
    /* web */
  }
}
async function startWindowDrag(event: MouseEvent) {
  if (event.button !== 0) return
  try {
    await getCurrentWindow().startDragging()
  } catch {
    /* browser preview */
  }
}

const zoomSteps = [0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2]
let zoomIndex = zoomSteps.indexOf(1)

async function applyZoom(index: number) {
  zoomIndex = Math.max(0, Math.min(zoomSteps.length - 1, index))
  try {
    await getCurrentWebview().setZoom(zoomSteps[zoomIndex])
  } catch {
    /* browser preview */
  }
}

function handleZoomShortcut(event: KeyboardEvent) {
  if (!(event.ctrlKey || event.metaKey)) return
  if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    void applyZoom(zoomIndex + 1)
  } else if (event.key === '-') {
    event.preventDefault()
    void applyZoom(zoomIndex - 1)
  } else if (event.key === '0') {
    event.preventDefault()
    void applyZoom(zoomSteps.indexOf(1))
  }
}

onMounted(() => window.addEventListener('keydown', handleZoomShortcut))
onBeforeUnmount(() => window.removeEventListener('keydown', handleZoomShortcut))
</script>

<style scoped>
.app-shell {
  position: relative;
  width: 100%;
  height: 100%;
  min-width: 0;
  display: flex;
  background: var(--c-app-bg);
}
.app-shell-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--c-app-bg);
}
.shell-drag-rail {
  position: fixed;
  z-index: 900;
  top: 0;
  left: var(--shell-sidebar-width);
  right: 94px;
  height: 13px;
  cursor: default;
}
.shell-window-controls {
  position: fixed;
  z-index: 950;
  top: 5px;
  right: 7px;
  display: flex;
  opacity: 0.48;
  transition: opacity 120ms ease;
}
.shell-window-controls:hover {
  opacity: 1;
}
.shell-window-controls button {
  width: 28px;
  height: 25px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
}
.shell-window-controls button:hover {
  background: var(--c-surface-2);
  color: var(--c-text-0);
}
.shell-window-controls button.close:hover {
  background: #c94b3d;
  color: #fff;
}
@media (max-width: 1180px) {
  .shell-drag-rail {
    left: 208px;
  }
}
@media (max-width: 1040px) {
  .shell-drag-rail {
    left: 76px;
  }
}
</style>
