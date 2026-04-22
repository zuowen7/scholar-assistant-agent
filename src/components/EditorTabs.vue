<template>
  <div class="editor-tabs">
    <div class="tabs-list">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="tab"
        :class="{ active: tab.id === activeTabId }"
        @click="setActiveTab(tab.id)"
      >
        <span class="tab-name">
          <span v-if="tab.isModified" class="tab-dot"></span>
          {{ tab.name }}
        </span>
        <button
          class="tab-close"
          @click.stop="handleClose(tab.id)"
          title="Close"
        >
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
    <button class="tab-new" @click="openNewUntitled" title="New File">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 5v14M5 12h14"/>
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useEditor } from '../composables/useEditor'

const { tabs, activeTabId, setActiveTab, closeTab, openNewUntitled } = useEditor()

function handleClose(id: string) {
  closeTab(id)
}
</script>

<style scoped>
.editor-tabs {
  display: flex;
  align-items: center;
  background: var(--toolbar-bg);
  border-bottom: 1px solid var(--border-color);
  height: 36px;
  overflow: hidden;
}

.tabs-list {
  display: flex;
  align-items: stretch;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
}

.tabs-list::-webkit-scrollbar { height: 0; }

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  min-width: 80px;
  max-width: 180px;
  height: 100%;
  cursor: pointer;
  border-right: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 12px;
  flex-shrink: 0;
  position: relative;
  transition: background 0.1s, color 0.1s;
}

.tab:hover { background: var(--hover-bg); color: var(--text-primary); }

.tab.active {
  background: var(--editor-bg);
  color: var(--text-primary);
  border-bottom: 2px solid var(--accent);
}

.tab-name {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  flex: 1;
}

.tab-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.tab-close {
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 2px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  opacity: 0;
  transition: opacity 0.1s, background 0.1s;
  flex-shrink: 0;
}
.tab:hover .tab-close,
.tab.active .tab-close { opacity: 1; }
.tab-close:hover { background: var(--active-bg); }

.tab-new {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 10px;
  height: 100%;
  display: flex;
  align-items: center;
  border-left: 1px solid var(--border-color);
  flex-shrink: 0;
}
.tab-new:hover { background: var(--hover-bg); color: var(--text-primary); }
</style>
