<template>
  <aside class="app-sidebar">
    <div class="brand-block">
      <span class="brand-mark">研</span>
      <div class="brand-copy"><strong>研墨</strong><span>Scholar Assistant</span></div>
    </div>

    <nav class="primary-nav" :aria-label="t('shell.primaryNav')">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="nav-item"
        :class="{ active: activeModule === item.key }"
        @click="$emit('navigate', item.key)"
      >
        <component :is="item.icon" :size="20" stroke-width="1.8" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <RecentFiles class="sidebar-recents" :items="recentFiles" @open="$emit('openRecent', $event)" />

    <div class="sidebar-footer">
      <ModelStatus :provider="provider" :model="model" :online="modelOnline" />
      <div class="user-row">
        <span class="user-avatar">研</span>
        <div class="user-copy"><strong>{{ t('shell.localUser') }}</strong><span>{{ t('shell.localWorkspace') }}</span></div>
        <div class="user-actions">
          <button type="button" class="settings-button" :title="t('topbar.agentAssistant')" @click="$emit('agent')"><Bot :size="18" /></button>
          <button type="button" class="settings-button" :title="t('topbar.settings')" @click="$emit('settings')"><Settings :size="18" /></button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bot, Languages, PenLine, Share2, SquareCheckBig, Settings } from 'lucide-vue-next'
import RecentFiles from './RecentFiles.vue'
import ModelStatus from './ModelStatus.vue'

defineProps<{
  activeModule: 'translate' | 'write' | 'mindmap' | 'review'
  recentFiles: Array<{ name: string; path: string }>
  provider: string
  model: string
  modelOnline?: boolean
}>()
defineEmits<{
  navigate: [module: 'translate' | 'write' | 'mindmap' | 'review']
  openRecent: [path: string]
  settings: []
  agent: []
}>()

const { t } = useI18n()
const navItems = computed(() => [
  { key: 'translate' as const, label: t('shell.translate'), icon: Languages },
  { key: 'write' as const, label: t('shell.write'), icon: PenLine },
  { key: 'mindmap' as const, label: t('shell.think'), icon: Share2 },
  { key: 'review' as const, label: t('shell.review'), icon: SquareCheckBig },
])
</script>

<style scoped>
.app-sidebar { width: var(--shell-sidebar-width); flex: 0 0 var(--shell-sidebar-width); min-height: 0; display: flex; flex-direction: column; padding: 22px 14px 16px; border-right: 1px solid var(--c-border); background: var(--c-nav); overflow: hidden; }
.brand-block { display: flex; align-items: center; gap: 11px; padding: 0 8px 24px; }
.brand-mark { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 10px; background: var(--brand-red); color: #fff; font-family: var(--font-serif-zh); font-size: 21px; font-weight: 700; box-shadow: 0 2px 5px rgba(102, 44, 31, .15); }
.brand-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.brand-copy strong { color: var(--c-text-0); font: 700 19px/1.2 var(--font-serif-zh), var(--font-serif); }
.brand-copy span { color: var(--c-text-3); font-size: 11px; white-space: nowrap; }
.primary-nav { display: flex; flex-direction: column; gap: 5px; }
.nav-item { width: 100%; height: 44px; display: flex; align-items: center; gap: 12px; padding: 0 12px; border: 0; border-radius: 8px; background: transparent; color: var(--c-text-1); font: 500 14px/1 var(--font-sans), var(--font-zh); cursor: pointer; }
.nav-item:hover { background: color-mix(in srgb, var(--c-panel) 55%, transparent); color: var(--c-text-0); }
.nav-item.active { color: var(--c-accent); background: var(--c-accent-soft); font-weight: 650; }
.sidebar-recents { margin-top: 20px; }
.sidebar-footer { margin-top: auto; display: grid; gap: 12px; }
.user-row { display: flex; align-items: center; gap: 9px; min-width: 0; padding: 3px 4px; }
.user-avatar { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: #c8baa7; color: #fff; font: 600 15px/1 var(--font-serif-zh); }
.user-copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.user-copy strong { color: var(--c-text-0); font-size: 12px; }
.user-copy span { color: var(--c-text-3); font-size: 10px; }
.settings-button { margin-left: auto; width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 7px; background: transparent; color: var(--c-text-2); cursor: pointer; }
.settings-button:hover { background: color-mix(in srgb, var(--c-panel) 60%, transparent); color: var(--c-text-0); }
.user-actions { display: flex; margin-left: auto; }
@media (max-width: 1180px) { .app-sidebar { width: 208px; flex-basis: 208px; } }
@media (max-width: 1040px) {
  .app-sidebar { width: 76px; flex-basis: 76px; padding-inline: 10px; align-items: center; }
  .brand-block { padding-inline: 0; } .brand-copy, .nav-item span, .sidebar-recents, .user-copy, .model-status { display: none; }
  .nav-item { width: 48px; justify-content: center; padding: 0; }
  .sidebar-footer { width: 100%; } .user-row { justify-content: center; } .user-avatar { display: none; } .settings-button { display: grid; margin: 0; } .user-actions { margin: 0; flex-direction: column; }
}
</style>
