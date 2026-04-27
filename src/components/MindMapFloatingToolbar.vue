<template>
  <div
    class="floating-toolbar"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    @pointerdown.stop="startDrag"
  >
    <div class="toolbar-grip" title="拖动工具组" />
    <button @click.stop="$emit('reset-map')" title="新建导图">新建</button>
    <button @click.stop="$emit('add-child')" :disabled="!canAdd" title="新增子节点">子节点</button>
    <button @click.stop="$emit('ai-expand')" :disabled="!canAdd || expanding" title="AI 智能展开子主题">
      {{ expanding ? '展开中' : 'AI 展开' }}
    </button>
    <button @click.stop="$emit('analyze')" :disabled="analyzing" title="AI 检查思维链">
      {{ analyzing ? '检查中' : 'AI 检查' }}
    </button>
    <button
      :class="{ active: connecting }"
      @click.stop="$emit('start-connect')"
      :disabled="!canAdd"
      title="连接节点"
    >
      连接
    </button>
    <button @click.stop="$emit('delete-node')" :disabled="!canDelete" title="删除节点">删除</button>
    <span class="divider" />
    <button class="icon-btn" @click.stop="$emit('zoom-in')" title="放大">+</button>
    <button class="icon-btn" @click.stop="$emit('zoom-out')" title="缩小">-</button>
    <button @click.stop="$emit('reset-view')" title="重置视图">重置</button>
    <button @click.stop="$emit('fit-view')" title="适应视图">适应</button>
    <span class="divider" />
    <button @click.stop="$emit('auto-layout')" title="自动整理布局">整理</button>
    <button class="primary" @click.stop="$emit('save')" title="保存到当前工程">保存</button>
    <button class="primary" @click.stop="$emit('enter-editor')" title="进入编辑器">编辑器</button>
    <span class="divider" />
    <button class="icon-btn help-btn" :class="{ active: showHelp }" @click.stop="showHelp = !showHelp" title="快捷键">?</button>
    <div v-if="showHelp" class="shortcut-panel" @click.stop @pointerdown.stop>
      <div class="shortcut-title">快捷键</div>
      <div class="shortcut-row"><kbd>Tab</kbd> 添加子节点</div>
      <div class="shortcut-row"><kbd>Enter</kbd> 添加兄弟节点</div>
      <div class="shortcut-row"><kbd>F2</kbd> / 双击 编辑节点</div>
      <div class="shortcut-row"><kbd>Del</kbd> 删除悬停的连线</div>
      <div class="shortcut-row"><kbd>←</kbd><kbd>→</kbd><kbd>↑</kbd><kbd>↓</kbd> 导航节点</div>
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
}>()

const showHelp = ref(false)

const emit = defineEmits<{
  (e: 'update:position', value: { x: number; y: number }): void
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
}>()

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
  flex-wrap: wrap;
  gap: 6px;
  max-width: calc(100% - 16px);
  max-height: min(132px, calc(100% - 16px));
  overflow: auto;
  min-height: 38px;
  padding: 6px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: color-mix(in srgb, var(--panel-bg) 92%, transparent);
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  cursor: grab;
  user-select: none;
}
.floating-toolbar:active {
  cursor: grabbing;
}
.toolbar-grip {
  width: 8px;
  height: 24px;
  border-radius: 4px;
  background:
    radial-gradient(circle, var(--text-secondary) 1px, transparent 1.5px) 0 0 / 4px 4px;
  opacity: 0.55;
  flex-shrink: 0;
}
button {
  height: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--text-primary);
  padding: 0 9px;
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
  width: 28px;
  padding: 0;
  font-weight: 700;
}
.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
  font-weight: 650;
}
.divider {
  width: 1px;
  height: 22px;
  background: var(--border-color);
  flex-shrink: 0;
}
@media (max-width: 760px) {
  .floating-toolbar {
    width: min(320px, calc(100% - 16px));
    align-items: flex-start;
    overflow: auto;
  }

  button {
    height: 26px;
    padding: 0 7px;
    font-size: 11px;
  }

  .divider {
    display: none;
  }
}

.help-btn {
  font-weight: 700;
  font-size: 13px;
}
.shortcut-panel {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 220px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  z-index: 20;
}
.shortcut-title {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--c-text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
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
</style>
