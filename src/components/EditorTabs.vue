<template>
  <div class="editor-tabs" :class="{ dark: isDark }">
    <div class="tabs-list">
      <div
        v-for="tab in tabs"
        :key="tab.id"
        class="tab-item"
        :class="{ active: tab.id === activeTabId, modified: tab.isModified }"
        @click="setActiveTab(tab.id)"
      >
        <span class="tab-name" :title="tab.path || 'Untitled'">
          {{ tab.name || 'Untitled' }}
          <span v-if="tab.isModified" class="modified-dot">●</span>
        </span>
        <button class="tab-close" @click.stop="closeTab(tab.id)" title="关闭">✕</button>
      </div>
    </div>
    <button class="new-tab-btn" @click="openNewUntitled" title="新建标签">+</button>
  </div>
</template>

<script setup lang="ts">
import { useEditor } from '../composables/useEditor'

const { tabs, activeTabId, setActiveTab, closeTab, openNewUntitled } = useEditor()
const isDark = document.documentElement.classList.contains('dark')
</script>

<style scoped>
.editor-tabs {
  display: flex; align-items: center;
  background: #f5f5f5; border-bottom: 1px solid #ddd;
  height: 38px; padding: 0 6px; gap: 2px; overflow-x: auto;
}
.editor-tabs.dark { background: #252525; border-color: #333; }
.editor-tabs::-webkit-scrollbar { height: 3px; }
.editor-tabs::-webkit-scrollbar-thumb { background: #ccc; border-radius: 3px; }
.dark .editor-tabs::-webkit-scrollbar-thumb { background: #555; }

.tabs-list { display: flex; align-items: center; gap: 1px; overflow-x: auto; flex: 1; }

.tab-item {
  display: flex; align-items: center; gap: 6px;
  padding: 0 10px; height: 30px; border-radius: 4px 4px 0 0;
  cursor: pointer; font-size: 12.5px; color: #666;
  background: transparent; border: 1px solid transparent;
  white-space: nowrap; min-width: 80px; max-width: 160px;
  transition: background 0.15s;
}
.tab-item:hover { background: #e8e8e8; }
.dark .tab-item { color: #aaa; }
.dark .tab-item:hover { background: #333; }

.tab-item.active {
  background: #fff; border-color: #ccc;
  color: #1a1a1a; font-weight: 500;
}
.dark .tab-item.active {
  background: #1e1e1e; border-color: #444; color: #e0e0e0;
}

.tab-name {
  overflow: hidden; text-overflow: ellipsis; flex: 1;
}
.modified-dot { color: #4a9eff; font-size: 10px; margin-left: 2px; }

.tab-close {
  background: none; border: none; font-size: 10px;
  color: #999; cursor: pointer; padding: 0 2px; line-height: 1;
  border-radius: 2px; opacity: 0; transition: opacity 0.15s;
}
.tab-item:hover .tab-close { opacity: 1; }
.tab-close:hover { background: rgba(0,0,0,0.1); color: #333; }
.dark .tab-close:hover { background: rgba(255,255,255,0.1); color: #e0e0e0; }

.new-tab-btn {
  flex-shrink: 0; width: 26px; height: 26px; border-radius: 4px;
  border: none; background: transparent; cursor: pointer;
  font-size: 18px; color: #888; line-height: 1;
  transition: background 0.15s;
}
.new-tab-btn:hover { background: #ddd; color: #333; }
.dark .new-tab-btn { color: #888; }
.dark .new-tab-btn:hover { background: #333; color: #e0e0e0; }
</style>
