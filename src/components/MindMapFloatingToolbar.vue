<template>
  <div
    class="floating-toolbar"
    :class="{ collapsed }"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    @pointerdown.stop="startDrag"
  >
    <div class="toolbar-grip" title="拖动工具栏" />

    <template v-if="collapsed">
      <button class="primary" @click.stop="$emit('add-child')" :disabled="!canAdd">子节点</button>
      <button class="workflow-primary" @click.stop="$emit('save')">保存</button>
      <button class="icon-btn" title="展开工具栏" @click.stop="$emit('update:collapsed', false)">▣</button>
    </template>

    <template v-else>
      <div class="toolbar-group structure-group" aria-label="结构操作">
        <span class="group-label">结构</span>
        <button @click.stop="$emit('reset-map')" title="新建导图">新建</button>
        <button @click.stop="$emit('add-child')" :disabled="!canAdd" title="新增子节点">子节点</button>
        <button
          :class="{ active: connecting }"
          @click.stop="$emit('start-connect')"
          :disabled="!canAdd"
          title="连接节点"
        >
          连接
        </button>
        <button @click.stop="$emit('delete-node')" :disabled="!canDelete" title="删除节点">删除</button>
      </div>

      <div class="toolbar-group view-group" aria-label="视图操作">
        <span class="group-label">视图</span>
        <button class="icon-btn" @click.stop="$emit('zoom-in')" title="放大">+</button>
        <button class="icon-btn" @click.stop="$emit('zoom-out')" title="缩小">-</button>
        <button @click.stop="$emit('reset-view')" title="重置视图">重置</button>
        <button @click.stop="$emit('fit-view')" title="适应视图">适应</button>
      </div>

      <div class="toolbar-group ai-group optional-on-small" aria-label="AI 辅助">
        <span class="group-label">AI</span>
        <button @click.stop="$emit('ai-expand')" :disabled="!canAdd || expanding" title="AI 展开子主题">
          {{ expanding ? '展开中' : 'AI 展开' }}
        </button>
        <button @click.stop="$emit('analyze')" :disabled="analyzing" title="AI 检查思维链">
          {{ analyzing ? '检查中' : 'AI 检查' }}
        </button>
      </div>

      <div class="toolbar-group workflow-group" aria-label="工作流">
        <span class="group-label">工作流</span>
        <button class="subtle-on-small" @click.stop="$emit('auto-layout')" title="自动整理布局">整理</button>
        <button class="workflow-primary" @click.stop="$emit('save')" title="保存到当前工程">保存</button>
        <button class="workflow-primary" @click.stop="$emit('enter-editor')" title="进入编辑器">编辑器</button>
      </div>

      <div class="toolbar-group utility-group">
        <button class="icon-btn help-btn" :class="{ active: showHelp }" @click.stop="toggleHelp" title="快捷键">?</button>
        <button class="icon-btn" title="收起工具栏" @click.stop="$emit('update:collapsed', true)">▥</button>
        <button class="icon-btn more-btn" :class="{ active: showMore }" title="更多" @click.stop="toggleMore">⋯</button>
      </div>
    </template>

    <div v-if="showMore && !collapsed" class="more-panel" @click.stop @pointerdown.stop>
      <button @click="$emit('ai-expand')" :disabled="!canAdd || expanding">{{ expanding ? '展开中' : 'AI 展开' }}</button>
      <button @click="$emit('analyze')" :disabled="analyzing">{{ analyzing ? '检查中' : 'AI 检查' }}</button>
      <button @click="$emit('auto-layout')">整理布局</button>
      <button @click="$emit('reset-layout')">恢复默认布局</button>
      <button @click="$emit('save')">保存到当前工程</button>
      <button @click="$emit('enter-editor')">进入编辑器</button>
      <button @click="toggleHelp">快捷键</button>
    </div>

    <div v-if="showHelp" class="shortcut-panel" @click.stop @pointerdown.stop>
      <div class="shortcut-title">快捷键</div>
      <div class="shortcut-row"><kbd>Tab</kbd> 添加子节点</div>
      <div class="shortcut-row"><kbd>Enter</kbd> 添加同级节点</div>
      <div class="shortcut-row"><kbd>F2</kbd> / 双击 编辑节点</div>
      <div class="shortcut-row"><kbd>Del</kbd> 删除悬停的连线</div>
      <div class="shortcut-row"><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd> 导航节点</div>
      <div class="shortcut-row"><kbd>Ctrl+Z</kbd> 撤销</div>
      <div class="shortcut-row"><kbd>Ctrl+Shift+Z</kbd> 重做</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  position: { x: number; y: number }
  canAdd: boolean
  canDelete: boolean
  connecting: boolean
  analyzing: boolean
  expanding: boolean
  collapsed: boolean
}>()

const showHelp = ref(false)
const showMore = ref(false)

const emit = defineEmits<{
  (e: 'update:position', value: { x: number; y: number }): void
  (e: 'update:collapsed', value: boolean): void
  (e: 'reset-map'): void
  (e: 'add-child'): void
  (e: 'ai-expand'): void
  (e: 'analyze'): void
  (e: 'start-connect'): void
  (e: 'delete-node'): void
  (e: 'zoom-in'): void
  (e: 'zoom-out'): void
  (e: 'reset-view'): void
  (e: 'fit-view'): void
  (e: 'save'): void
  (e: 'enter-editor'): void
  (e: 'auto-layout'): void
  (e: 'reset-layout'): void
}>()

function toggleHelp() {
  showHelp.value = !showHelp.value
  if (showHelp.value) showMore.value = false
}

function toggleMore() {
  showMore.value = !showMore.value
  if (showMore.value) showHelp.value = false
}

function startDrag(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.tagName === 'BUTTON') return

  const origin = {
    pointerX: event.clientX,
    pointerY: event.clientY,
    x: props.position.x,
    y: props.position.y,
  }
  const toolbar = event.currentTarget as HTMLElement
  toolbar.setPointerCapture(event.pointerId)

  const move = (moveEvent: PointerEvent) => {
    emit('update:position', {
      x: Math.max(8, origin.x + moveEvent.clientX - origin.pointerX),
      y: Math.max(8, origin.y + moveEvent.clientY - origin.pointerY),
    })
  }

  const up = (upEvent: PointerEvent) => {
    toolbar.removeEventListener('pointermove', move)
    toolbar.removeEventListener('pointerup', up)
    toolbar.removeEventListener('pointercancel', up)
    if (toolbar.hasPointerCapture(upEvent.pointerId)) toolbar.releasePointerCapture(upEvent.pointerId)
  }

  toolbar.addEventListener('pointermove', move)
  toolbar.addEventListener('pointerup', up)
  toolbar.addEventListener('pointercancel', up)
}
</script>

<style scoped>
.floating-toolbar {
  position: absolute;
  z-index: 10;
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 6px;
  max-width: calc(100% - 18px);
  min-height: 38px;
  padding: 5px;
  border: 1px solid color-mix(in srgb, var(--border-color) 52%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-bg) 82%, transparent);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  cursor: grab;
  user-select: none;
}
.floating-toolbar.collapsed {
  max-height: 40px;
}
.floating-toolbar:active {
  cursor: grabbing;
}
.toolbar-grip {
  width: 7px;
  height: 24px;
  border-radius: 4px;
  background:
    radial-gradient(circle, var(--text-secondary) 1px, transparent 1.5px) 0 0 / 4px 4px;
  opacity: 0.38;
  flex-shrink: 0;
}
.toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-height: 29px;
  padding: 2px;
  border: 1px solid color-mix(in srgb, var(--border-color) 42%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--toolbar-bg) 54%, transparent);
  flex-shrink: 0;
}
.group-label {
  padding: 0 5px;
  color: color-mix(in srgb, var(--text-secondary) 78%, transparent);
  font-size: 11px;
  font-weight: 700;
  line-height: 25px;
}
.ai-group {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--border-color));
  background: color-mix(in srgb, var(--active-bg) 32%, transparent);
}
.workflow-group {
  border-color: color-mix(in srgb, var(--accent) 38%, var(--border-color));
}
.utility-group {
  background: color-mix(in srgb, var(--toolbar-bg) 38%, transparent);
}
button {
  height: 25px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  padding: 0 7px;
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}
button:hover:not(:disabled),
button.active {
  background: var(--hover-bg);
  border-color: var(--accent);
  color: var(--accent);
}
button:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}
.icon-btn {
  width: 25px;
  padding: 0;
  font-weight: 700;
}
.primary,
.workflow-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}
.workflow-primary {
  box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 18%, transparent);
}
.more-panel,
.shortcut-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  max-width: min(300px, calc(100vw - 24px));
  background: color-mix(in srgb, var(--c-surface-2) 96%, transparent);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: var(--space-3);
  z-index: 20;
}
.more-panel {
  min-width: 156px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.more-panel button {
  width: 100%;
  text-align: left;
}
.shortcut-panel {
  min-width: 220px;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.shortcut-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--c-text-2);
  margin-bottom: var(--space-1);
}
.shortcut-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--c-text-0);
  line-height: 1.6;
}
.shortcut-row kbd {
  display: inline-block;
  padding: 1px 5px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  background: var(--c-surface-4);
  border: 1px solid var(--c-surface-3);
  border-radius: 4px;
  color: var(--c-accent);
  white-space: nowrap;
}
@media (max-width: 1180px) {
  .floating-toolbar {
    flex-wrap: wrap;
    max-height: min(94px, calc(100% - 16px));
  }

  .optional-on-small,
  .subtle-on-small,
  .group-label {
    display: none;
  }
}
@media (max-width: 760px) {
  button {
    height: 25px;
    padding: 0 6px;
    font-size: 11px;
  }
}
</style>
