<template>
  <div
    class="floating-toolbar"
    :class="{ collapsed }"
    :style="{ left: `${position.x}px`, top: `${position.y}px` }"
    @pointerdown.stop="startDrag"
  >
    <div class="toolbar-grip" :title="t('mindmap.dragToolbar')" />

    <template v-if="collapsed">
      <button class="primary" @click.stop="$emit('add-child')" :disabled="!canAdd">{{ t('mindmap.childNode') }}</button>
      <button class="workflow-primary" @click.stop="$emit('save')">{{ t('mindmap.save') }}</button>
      <button class="icon-btn" :title="t('mindmap.expandToolbar')" @click.stop="$emit('update:collapsed', false)">▣</button>
    </template>

    <template v-else>
      <div class="toolbar-group structure-group" :aria-label="t('mindmap.structure')">
        <span class="group-label">{{ t('mindmap.structure') }}</span>
        <button @click.stop="$emit('reset-map')" :title="t('mindmap.newMap')">{{ t('mindmap.newMap') }}</button>
        <button @click.stop="$emit('add-child')" :disabled="!canAdd" :title="t('mindmap.childNode')">{{ t('mindmap.childNode') }}</button>
        <button
          :class="{ active: connecting }"
          @click.stop="$emit('start-connect')"
          :disabled="!canAdd"
          :title="t('mindmap.connectNode')"
        >
          {{ t("mindmap.connect2") }}
        </button>
        <button @click.stop="$emit('delete-node')" :disabled="!canDelete" :title="t('mindmap.deleteNode')">{{ t('mindmap.delete') }}</button>
      </div>

      <div class="toolbar-group view-group" :aria-label="t('mindmap.view')">
        <span class="group-label">{{ t('mindmap.view') }}</span>
        <button class="icon-btn" @click.stop="$emit('zoom-in')" :title="t('mindmap.zoomIn')">+</button>
        <button class="icon-btn" @click.stop="$emit('zoom-out')" :title="t('mindmap.zoomOut')">-</button>
        <button @click.stop="$emit('reset-view')" :title="t('mindmap.resetView')">{{ t('mindmap.reset') }}</button>
        <button @click.stop="$emit('fit-view')" :title="t('mindmap.fitView')">{{ t('mindmap.fit') }}</button>
      </div>

      <div class="toolbar-group ai-group optional-on-small" :aria-label="t('mindmap.aiAssist')">
        <span class="group-label">AI</span>
        <button @click.stop="$emit('ai-expand')" :disabled="!canAdd || expanding" :title="t('mindmap.aiExpand')">
          {{ expanding ? t('mindmap.expanding') : t('mindmap.aiExpandBtn') }}
        </button>
        <button @click.stop="$emit('analyze')" :disabled="analyzing" :title="t('mindmap.aiCheck')">
          {{ analyzing ? t('mindmap.checking') : t('mindmap.aiCheckBtn') }}
        </button>
      </div>

      <div class="toolbar-group workflow-group" :aria-label="t('mindmap.workflow')">
        <span class="group-label">{{ t('mindmap.workflow') }}</span>
        <button class="subtle-on-small" @click.stop="$emit('auto-layout')" :title="t('mindmap.autoLayout')">{{ t('mindmap.autoLayoutBtn') }}</button>
        <button class="workflow-primary" @click.stop="$emit('save')" :title="t('mindmap.saveToProject')">{{ t('mindmap.save') }}</button>
        <button class="workflow-primary" @click.stop="$emit('enter-editor')" :title="t('mindmap.enterEditor')">{{ t('mindmap.editor') }}</button>
      </div>

      <div class="toolbar-group utility-group">
        <button class="icon-btn help-btn" :class="{ active: showHelp }" @click.stop="toggleHelp" :title="t('mindmap.shortcuts')">?</button>
        <button class="icon-btn" :title="t('mindmap.collapseToolbar')" @click.stop="$emit('update:collapsed', true)">▥</button>
        <button class="icon-btn more-btn" :class="{ active: showMore }" :title="t('mindmap.more')" @click.stop="toggleMore">⋯</button>
      </div>
    </template>

    <div v-if="showMore && !collapsed" class="more-panel" @click.stop @pointerdown.stop>
      <button @click="$emit('ai-expand')" :disabled="!canAdd || expanding">{{ expanding ? t('mindmap.expanding2') : t('mindmap.aiExpand2') }}</button>
      <button @click="$emit('analyze')" :disabled="analyzing">{{ analyzing ? t('mindmap.checking2') : t('mindmap.aiCheck2') }}</button>
      <button @click="$emit('auto-layout')">{{ t('mindmap.autoLayout') }}</button>
      <button @click="$emit('reset-layout')">{{ t('mindmap.resetLayout') }}</button>
      <button @click="$emit('save')">{{ t('mindmap.saveToProject') }}</button>
      <button @click="$emit('enter-editor')">{{ t('mindmap.enterEditor') }}</button>
      <button @click="toggleHelp">{{ t('mindmap.shortcuts') }}</button>
    </div>

    <div v-if="showHelp" class="shortcut-panel" @click.stop @pointerdown.stop>
      <div class="shortcut-title">{{ t('mindmap.shortcuts') }}</div>
      <div class="shortcut-row"><kbd>Tab</kbd> {{ t('mindmap.shortcutAddChild') }}</div>
      <div class="shortcut-row"><kbd>Enter</kbd> {{ t('mindmap.shortcutAddSibling') }}</div>
      <div class="shortcut-row"><kbd>F2</kbd> / Double-click {{ t('mindmap.shortcutEditNode') }}</div>
      <div class="shortcut-row"><kbd>Del</kbd> {{ t('mindmap.shortcutDeleteEdge') }}</div>
      <div class="shortcut-row"><kbd>↑</kbd><kbd>↓</kbd><kbd>←</kbd><kbd>→</kbd> {{ t('mindmap.shortcutNavigate') }}</div>
      <div class="shortcut-row"><kbd>Ctrl+Z</kbd> {{ t('mindmap.shortcutUndo') }}</div>
      <div class="shortcut-row"><kbd>Ctrl+Shift+Z</kbd> {{ t('mindmap.shortcutRedo') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

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
  box-shadow: var(--elevation-2);
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
  border-color: color-mix(in srgb, var(--c-accent) 28%, var(--border-color));
  background: color-mix(in srgb, var(--active-bg) 32%, transparent);
}
.workflow-group {
  border-color: color-mix(in srgb, var(--c-accent) 38%, var(--border-color));
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
  border-color: var(--c-accent);
  color: var(--c-accent);
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
  background: var(--c-accent);
  border-color: var(--c-accent);
  color: #fff;
  font-weight: 650;
}
.workflow-primary {
  box-shadow: 0 4px 12px color-mix(in srgb, var(--c-accent) 18%, transparent);
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
