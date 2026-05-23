<template>
  <div class="editor-tabs">
    <div class="tabs-scroll" role="tablist">
      <TransitionGroup name="v-list-stagger">
        <button
          v-for="(tab, i) in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          class="tab-item"
          :class="{ active: tab.id === activeTabId, modified: tab.isModified }"
          :style="{ '--stagger-i': i }"
          :aria-selected="tab.id === activeTabId"
          :title="tab.path || tab.name || 'Untitled'"
          @click="setActiveTab(tab.id)"
        >
          <FileText :size="12" :stroke-width="1.6" class="tab-icon" />
          <span class="tab-name">{{ tab.name || 'Untitled' }}</span>
          <Transition name="v-spring">
            <span v-if="tab.isModified" class="modified-dot" title="未保存" />
          </Transition>
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
      </TransitionGroup>
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
  background: var(--c-surface-1);
  border-bottom: 1px solid var(--c-surface-3);
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
  border-right: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  font: inherit;
  font-size: var(--text-sm);
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}

/* Bottom accent line for active tab — grows from center */
.tab-item::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  right: 50%;
  height: 2px;
  background: var(--vermilion-0);
  opacity: 0;
  transition: left var(--motion-base) var(--ease-spring),
              right var(--motion-base) var(--ease-spring),
              opacity var(--motion-fast) var(--ease-out);
}

.tab-item:hover { background: var(--c-surface-4); color: var(--c-text-1); }
.tab-item:active { background: var(--c-surface-5); }
.tab-item:focus-visible { outline: none; box-shadow: inset var(--ring-focus); }
.tab-item.active { background: var(--c-surface-2); color: var(--c-text-0); }
.tab-item.active::after { left: 0; right: 0; opacity: 1; }

.tab-icon { flex-shrink: 0; opacity: 0.45; transition: opacity var(--motion-fast), color var(--motion-fast); }
.tab-item:hover .tab-icon { opacity: 0.65; }
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
  box-shadow: 0 0 0 0 var(--c-accent-ring);
  animation: dot-pulse 2s var(--ease-smooth) infinite;
}
@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 0 0 var(--c-accent-ring); }
  50%      { box-shadow: 0 0 0 3px transparent; }
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
  transform: scale(0.8);
  transition: opacity var(--motion-fast) var(--ease-out),
              transform var(--motion-fast) var(--ease-spring),
              background var(--motion-fast), color var(--motion-fast);
  cursor: pointer;
}
.tab-item:hover .tab-close,
.tab-item.active .tab-close { opacity: 1; transform: scale(1); }
.tab-close:hover { background: var(--c-danger-bg); color: var(--c-danger); transform: scale(1.12); }
.tab-close:active { transform: scale(0.9); }

.new-tab-btn {
  flex-shrink: 0;
  width: 36px;
  border: none;
  border-left: 1px solid var(--c-surface-3);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--motion-fast), color var(--motion-fast), transform var(--motion-fast) var(--ease-spring);
}
.new-tab-btn:hover { background: var(--c-surface-4); color: var(--c-text-0); }
.new-tab-btn:hover :deep(svg) { transform: rotate(90deg); }
.new-tab-btn :deep(svg) { transition: transform var(--motion-base) var(--ease-spring); }
.new-tab-btn:active { transform: scale(0.9); }
.new-tab-btn:focus-visible { outline: none; box-shadow: inset var(--ring-focus); }

@media (prefers-reduced-motion: reduce) {
  .modified-dot { animation: none; }
  .new-tab-btn:hover :deep(svg) { transform: none; }
}
</style>
