<template>
  <div class="editor-tabs">
    <div class="tabs-list">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="tab-item"
        :class="{ active: tab.id === activeTabId, modified: tab.isModified }"
        @click="setActiveTab(tab.id)"
      >
        <span class="tab-name" :title="tab.path || 'Untitled'">
          {{ tab.name || 'Untitled' }}
          <span v-if="tab.isModified" class="modified-dot"></span>
        </span>
        <span class="tab-close" role="button" title="关闭" @click.stop="closeTab(tab.id)">×</span>
      </button>
    </div>
    <button class="new-tab-btn" @click="openNewUntitled" title="新建标签">+</button>
  </div>
</template>

<script setup lang="ts">
import { useEditor } from '../composables/useEditor'

const { tabs, activeTabId, setActiveTab, closeTab, openNewUntitled } = useEditor()
</script>

<style scoped>
.editor-tabs {
  display: flex;
  align-items: end;
  height: 40px;
  padding: 0 8px;
  gap: 4px;
  overflow: hidden;
  background: var(--toolbar-bg);
  border-bottom: 1px solid var(--border-color);
}

.tabs-list {
  display: flex;
  align-items: end;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
}
.tabs-list::-webkit-scrollbar { height: 3px; }
.tabs-list::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 999px; }

.tab-item {
  height: 34px;
  min-width: 112px;
  max-width: 180px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 10px 0 12px;
  border: 1px solid transparent;
  border-bottom: none;
  border-radius: 7px 7px 0 0;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  transition: background 0.14s, color 0.14s, border-color 0.14s;
}
.tab-item:hover { background: var(--hover-bg); color: var(--text-primary); }
.tab-item.active {
  background: var(--editor-bg);
  border-color: var(--border-color);
  color: var(--text-primary);
}

.tab-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  text-align: left;
}

.modified-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 6px;
  border-radius: 50%;
  background: var(--accent);
  vertical-align: middle;
}

.tab-close {
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: var(--text-secondary);
  opacity: 0;
  transition: opacity 0.14s, background 0.14s, color 0.14s;
}
.tab-item:hover .tab-close,
.tab-item.active .tab-close { opacity: 1; }
.tab-close:hover { background: var(--hover-bg); color: var(--text-primary); }

.new-tab-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  margin-bottom: 4px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}
.new-tab-btn:hover { background: var(--hover-bg); color: var(--text-primary); }
</style>
