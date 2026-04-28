<template>
  <div class="editor-tabs">
    <div class="tabs-scroll" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        role="tab"
        class="tab-item"
        :class="{ active: tab.id === activeTabId, modified: tab.isModified }"
        :aria-selected="tab.id === activeTabId"
        :title="tab.path || tab.name || 'Untitled'"
        @click="setActiveTab(tab.id)"
      >
        <FileText :size="12" :stroke-width="1.6" class="tab-icon" />
        <span class="tab-name">{{ tab.name || 'Untitled' }}</span>
        <span v-if="tab.isModified" class="modified-dot" title="未保存" />
        <span
          class="tab-close"
          role="button"
          tabindex="-1"
          title="关闭"
          aria-label="关闭标签"
          @click.stop="closeTab(tab.id)"
        >
          <X :size="11" :stroke-width="2.2" />
        </span>
      </button>
    </div>
    <button class="new-tab-btn" title="新建文件" aria-label="新建文件" @click="openNewUntitled">
      <Plus :size="14" :stroke-width="2" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { FileText, X, Plus } from './ui/icons'
import { useEditor } from '../composables/useEditor'

const { tabs, activeTabId, setActiveTab, closeTab, openNewUntitled } = useEditor()
</script>

<style scoped>
.editor-tabs {
  display: flex;
  align-items: stretch;
  height: 38px;
  background: var(--sidebar-bg);
  border-bottom: 1px solid var(--border-color);
  overflow: hidden;
  flex-shrink: 0;
}

.tabs-scroll {
  display: flex;
  align-items: stretch;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}
.tabs-scroll::-webkit-scrollbar { display: none; }

.tab-item {
  position: relative;
  height: 100%;
  min-width: 100px;
  max-width: 180px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px 0 12px;
  border: none;
  border-right: 1px solid var(--border-color);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  font: inherit;
  font-size: var(--text-sm);
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}

/* Bottom accent line for active tab */
.tab-item::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: transparent;
  transition: background var(--motion-fast) var(--ease-out);
}

.tab-item:hover { background: var(--hover-bg); color: var(--c-text-1); }
.tab-item.active { background: var(--editor-bg); color: var(--c-text-0); }
.tab-item.active::after { background: var(--c-accent); }

.tab-icon { flex-shrink: 0; opacity: 0.45; }
.tab-item.active .tab-icon { opacity: 0.7; color: var(--c-accent); }

.tab-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.modified-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-accent);
}

.tab-close {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--c-text-3);
  opacity: 0;
  transition: opacity var(--motion-fast), background var(--motion-fast), color var(--motion-fast);
  cursor: pointer;
}
.tab-item:hover .tab-close,
.tab-item.active .tab-close { opacity: 1; }
.tab-close:hover { background: var(--hover-bg); color: var(--c-danger); }

.new-tab-btn {
  flex-shrink: 0;
  width: 36px;
  border: none;
  border-left: 1px solid var(--border-color);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--motion-fast), color var(--motion-fast);
}
.new-tab-btn:hover { background: var(--hover-bg); color: var(--c-text-0); }
</style>
