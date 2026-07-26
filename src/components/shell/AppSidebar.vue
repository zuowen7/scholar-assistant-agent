<template>
  <aside class="app-sidebar">
    <button type="button" class="brand-block" :title="t('shell.home')" @click="$emit('home')">
      <span class="brand-mark" aria-hidden="true">研</span>
      <div class="brand-copy"><strong>研墨</strong><span>Scholar Assistant</span></div>
    </button>

    <button type="button" class="project-switcher" @click="$emit('home')">
      <span class="project-kicker">{{ t('shell.projectWorkspace') }}</span>
      <strong>{{ projectName || t('shell.noProject') }}</strong>
    </button>

    <nav class="primary-nav" :aria-label="t('shell.primaryNav')">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        class="nav-item"
        :class="{ active: activeModule === item.key }"
        :aria-current="activeModule === item.key ? 'page' : undefined"
        :title="item.label"
        :disabled="item.requiresWorkspace && !workspaceActive"
        @click="$emit('navigate', item.key)"
      >
        <component :is="item.icon" :size="20" stroke-width="1.8" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="sidebar-footer">
      <ModelStatus :provider="provider" :model="model" :online="modelOnline" />
      <button
        type="button"
        class="agent-dock-button"
        :class="{ active: agentOpen }"
        data-testid="workspace-agent"
        @click="$emit('agent')"
      >
        <Bot :size="18" stroke-width="1.8" aria-hidden="true" />
        <span>{{ t('topbar.agentAssistant') }}</span>
      </button>
      <div class="user-row">
        <span class="user-avatar">研</span>
        <div class="user-copy">
          <strong>{{ t('shell.localUser') }}</strong
          ><span>{{ t('shell.localWorkspace') }}</span>
        </div>
        <div class="user-actions">
          <button
            type="button"
            class="settings-button"
            :title="t('topbar.settings')"
            @click="$emit('settings')"
          >
            <Settings :size="18" />
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bot, Download, Files, Library, SquareCheckBig, Settings } from 'lucide-vue-next'
import ModelStatus from './ModelStatus.vue'

defineProps<{
  activeModule: 'draft' | 'sources' | 'review' | 'export' | null
  projectName?: string | null
  workspaceActive?: boolean
  agentOpen?: boolean
  provider: string
  model: string
  modelOnline?: boolean
}>()
defineEmits<{
  navigate: [module: 'draft' | 'sources' | 'review' | 'export']
  home: []
  settings: []
  agent: []
}>()

const { t } = useI18n()
const navItems = computed(() => [
  { key: 'draft' as const, label: t('shell.draft'), icon: Files, requiresWorkspace: true },
  { key: 'sources' as const, label: t('shell.sources'), icon: Library, requiresWorkspace: false },
  {
    key: 'review' as const,
    label: t('shell.review'),
    icon: SquareCheckBig,
    requiresWorkspace: true,
  },
  { key: 'export' as const, label: t('shell.export'), icon: Download, requiresWorkspace: true },
])
</script>

<style scoped>
.app-sidebar {
  width: var(--shell-sidebar-width);
  flex: 0 0 var(--shell-sidebar-width);
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 22px 14px 16px;
  border-right: 1px solid var(--c-border);
  background: var(--c-nav);
  overflow: hidden;
}
.brand-block {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 8px 24px;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.brand-mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: var(--brand-red);
  color: #fff;
  font-family: var(--font-serif-zh);
  font-size: 21px;
  font-weight: 700;
  box-shadow: 0 2px 5px rgba(102, 44, 31, 0.15);
}
.brand-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.brand-copy strong {
  color: var(--c-text-0);
  font:
    700 19px/1.2 var(--font-serif-zh),
    var(--font-serif);
}
.brand-copy span {
  color: var(--c-text-3);
  font-size: 11px;
  white-space: nowrap;
}
.primary-nav {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.project-switcher {
  width: 100%;
  display: grid;
  gap: 3px;
  margin: 0 0 16px;
  padding: 10px 12px;
  border: 1px solid var(--c-border);
  border-radius: 9px;
  background: var(--c-surface-1);
  color: var(--c-text-0);
  text-align: left;
  cursor: pointer;
}
.project-switcher:hover {
  border-color: var(--c-accent-ring);
  background: var(--c-surface-2);
}
.project-switcher strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.project-kicker {
  color: var(--c-text-3);
  font-size: 10px;
}
.nav-item {
  width: 100%;
  height: 44px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--c-text-1);
  font:
    500 14px/1 var(--font-sans),
    var(--font-zh);
  cursor: pointer;
}
.nav-item:hover {
  background: color-mix(in srgb, var(--c-panel) 55%, transparent);
  color: var(--c-text-0);
}
.nav-item.active {
  color: var(--c-accent);
  background: var(--c-accent-soft);
  font-weight: 650;
}
.nav-item:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.sidebar-footer {
  margin-top: auto;
  display: grid;
  gap: 12px;
}
.agent-dock-button {
  width: 100%;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 11px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--c-surface-1);
  color: var(--c-text-1);
  cursor: pointer;
}
.agent-dock-button:hover,
.agent-dock-button.active {
  border-color: var(--c-accent-ring);
  color: var(--c-accent);
  background: var(--c-accent-soft);
}
.user-row {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 3px 4px;
}
.user-avatar {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #c8baa7;
  color: #fff;
  font: 600 15px/1 var(--font-serif-zh);
}
.user-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.user-copy strong {
  color: var(--c-text-0);
  font-size: 12px;
}
.user-copy span {
  color: var(--c-text-3);
  font-size: 10px;
}
.settings-button {
  margin-left: auto;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--c-text-2);
  cursor: pointer;
}
.settings-button:hover {
  background: color-mix(in srgb, var(--c-panel) 60%, transparent);
  color: var(--c-text-0);
}
.user-actions {
  display: flex;
  margin-left: auto;
}
@media (max-width: 1180px) {
  .app-sidebar {
    width: 208px;
    flex-basis: 208px;
  }
}
@media (max-width: 1040px) {
  .app-sidebar {
    width: 76px;
    flex-basis: 76px;
    padding-inline: 10px;
    align-items: center;
  }
  .brand-block {
    padding-inline: 0;
  }
  .brand-copy,
  .project-switcher,
  .nav-item span,
  .agent-dock-button span,
  .user-copy,
  .model-status {
    display: none;
  }
  .nav-item {
    width: 48px;
    justify-content: center;
    padding: 0;
  }
  .sidebar-footer {
    width: 100%;
  }
  .user-row {
    justify-content: center;
  }
  .user-avatar {
    display: none;
  }
  .settings-button {
    display: grid;
    margin: 0;
  }
  .user-actions {
    margin: 0;
    flex-direction: column;
  }
}
@media (max-height: 650px) {
  .app-sidebar {
    padding-top: 12px;
    padding-bottom: 10px;
    overflow-y: auto;
  }
  .brand-block {
    padding-bottom: 12px;
  }
  .project-switcher {
    margin-bottom: 8px;
    padding-block: 7px;
  }
  .nav-item {
    height: 38px;
  }
  .sidebar-footer {
    margin-top: 14px;
    gap: 7px;
  }
}
</style>
