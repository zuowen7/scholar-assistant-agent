<template>
  <div class="tree-node" @contextmenu.prevent="showContextMenu">
    <div
      class="tree-item u-interactive"
      :class="{ active: activeFile === entry.path, dir: entry.isDir }"
      :style="{ paddingLeft: depth * 16 + 8 + 'px' }"
      tabindex="0"
      role="treeitem"
      :aria-expanded="entry.isDir ? expanded : undefined"
      @click="handleClick"
      @keydown.enter.prevent="handleClick"
      @keydown.space.prevent="handleClick"
      @pointermove="onPointerMove"
    >
      <span
        v-if="entry.isDir"
        class="tree-chevron"
        :class="{ open: expanded }"
        aria-hidden="true"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 6 15 12 9 18"/></svg>
      </span>
      <span v-else class="tree-chevron-spacer" aria-hidden="true" />
      <span class="tree-icon" :data-expanded="expanded || undefined">{{ entry.isDir ? (expanded ? '📂' : '📁') : '📄' }}</span>
      <template v-if="isRenaming">
        <input
          ref="renameInput"
          class="rename-input"
          :value="newName"
          @input="newName = ($event.target as HTMLInputElement).value"
          @keydown.enter="confirmRename"
          @keydown.escape="cancelRename"
          @blur="confirmRename"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="tree-name">{{ entry.name }}</span>
      </template>
    </div>
    <Transition name="v-unfurl">
      <div v-if="entry.isDir && expanded" class="tree-children">
        <!-- 目录加载骨架 -->
        <div v-if="loadingChildren" class="tree-skeleton" :style="{ paddingLeft: (depth + 1) * 16 + 8 + 'px' }">
          <div v-for="i in skeletonCount" :key="i" class="tree-skeleton-row" :style="{ '--stagger-i': i - 1 } as any">
            <UiSkeleton shape="circle" :width="12" :height="12" />
            <UiSkeleton shape="line" :width="`${44 + (i * 13) % 40}%`" :height="9" />
          </div>
        </div>
        <template v-else-if="entry.children">
          <FileTreeNode
            v-for="(child, ci) in entry.children"
            :key="child.path"
            :entry="child"
            :depth="depth + 1"
            :active-file="activeFile"
            :style="{ '--stagger-i': Math.min(ci, 12) } as any"
            class="anim-fade-in-up anim-stagger"
            @select="(e: FileEntry) => $emit('select', e)"
            @action="(a: string, p: string, n: string) => $emit('action', a, p, n)"
          />
        </template>
      </div>
    </Transition>
  </div>

  <!-- Context menu -->
  <Teleport to="body">
    <Transition name="v-scale-in">
      <div
        v-if="ctx.visible"
        class="ctx-menu"
        :style="{ left: ctx.x + 'px', top: ctx.y + 'px', transformOrigin: ctx.origin }"
      >
        <template v-if="entry.isDir">
          <button class="ctx-item" @click="action('new-file')">{{ t('files.newFile') }}</button>
          <button class="ctx-item" @click="action('new-folder')">{{ t('files.newFolder') }}</button>
          <div class="ctx-sep" />
        </template>
        <button class="ctx-item" @click="action('cut')">{{ t('files.cut') }}</button>
        <button class="ctx-item" @click="action('copy')">{{ t('files.copy') }}</button>
        <button v-if="canPaste" class="ctx-item" @click="action('paste')">{{ t('files.paste') }}</button>
        <div v-if="canPaste" class="ctx-sep" />
        <button class="ctx-item" @click="action('rename')">{{ t('files.rename') }}</button>
        <button class="ctx-item ctx-danger" @click="action('delete')">{{ t('files.delete') }}</button>
        <div class="ctx-sep" />
        <button class="ctx-item" @click="action('copy-path')">{{ t('files.copyPath') }}</button>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, nextTick, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import type { FileEntry } from '../types'
import { useFileTree } from '../composables/useFileTree'
import UiSkeleton from './ui/UiSkeleton.vue'

const props = defineProps<{
  entry: FileEntry
  depth: number
  activeFile: string | null
}>()

const emit = defineEmits<{
  (e: 'select', entry: FileEntry): void
  (e: 'action', action: string, path: string, extra: string): void
}>()

const { getClipboard } = useFileTree()

const expanded = ref(false)
const loadingChildren = ref(false)
const isRenaming = ref(false)
const newName = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

// 展开时显示的骨架行数（依据 children 数量，缺省给个轻量占位）
const skeletonCount = computed(() => {
  const n = props.entry.children?.length ?? 0
  return Math.min(Math.max(n || 3, 2), 5)
})

// 墨韵涟漪：跟踪指针位置，让 hover 高光从光标处扩散
function onPointerMove(e: PointerEvent) {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  el.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`)
  el.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`)
}

const ctx = reactive({ visible: false, x: 0, y: 0, origin: 'top left' })
const canPaste = computed(() => {
  if (!props.entry.isDir) return false
  const cb = getClipboard()
  return cb !== null
})

function handleClick() {
  if (props.entry.isDir) {
    const next = !expanded.value
    expanded.value = next
    // 展开时若有较多子项，先显示骨架，给一个可见的"加载"反馈节拍
    if (next && (props.entry.children?.length ?? 0) > 6) {
      loadingChildren.value = true
      requestAnimationFrame(() => {
        setTimeout(() => { loadingChildren.value = false }, 180)
      })
    } else {
      loadingChildren.value = false
    }
  } else {
    emit('select', props.entry)
  }
}

function showContextMenu(e: MouseEvent) {
  ctx.x = e.clientX
  ctx.y = e.clientY
  ctx.origin = 'top left'
  // Clamp to viewport
  nextTick(() => {
    if (ctx.y + 240 > window.innerHeight) { ctx.y = window.innerHeight - 250; ctx.origin = 'bottom left' }
    if (ctx.x + 160 > window.innerWidth) { ctx.x = window.innerWidth - 170; ctx.origin = ctx.origin.replace('left', 'right') }
  })
  ctx.visible = true
  const close = () => { ctx.visible = false; document.removeEventListener('click', close); document.removeEventListener('contextmenu', close) }
  setTimeout(() => { document.addEventListener('click', close); document.addEventListener('contextmenu', close) }, 0)
}

function action(a: string) {
  ctx.visible = false
  if (a === 'new-file') {
    const name = prompt(t('files.newFilePrompt'), 'untitled.md')
    if (name) emit('action', 'new-file', props.entry.path, name)
    return
  }
  if (a === 'new-folder') {
    const name = prompt(t('files.newFolder'), 'new_folder')
    if (name) emit('action', 'new-folder', props.entry.path, name)
    return
  }
  if (a === 'rename') {
    newName.value = props.entry.name
    isRenaming.value = true
    nextTick(() => {
      renameInput.value?.focus()
      const dotIdx = props.entry.name.lastIndexOf('.')
      renameInput.value?.setSelectionRange(0, dotIdx > 0 ? dotIdx : props.entry.name.length)
    })
    return
  }
  emit('action', a, props.entry.path, props.entry.name)
}

async function confirmRename() {
  if (!isRenaming.value) return
  isRenaming.value = false
  const trimmed = newName.value.trim()
  if (trimmed && trimmed !== props.entry.name) {
    emit('action', 'rename', props.entry.path, trimmed)
  }
}

function cancelRename() {
  isRenaming.value = false
}
</script>

<style scoped>
.tree-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 12px;
  cursor: pointer;
  font-size: 13px;
  color: var(--c-text-1);
  position: relative;
  border-radius: var(--radius-xs);
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
}
/* u-interactive 自带 hover 抬升/按压回弹，这里中和位移避免树行抖动 */
.tree-item.u-interactive:not(:disabled):hover { transform: none; }
.tree-item.u-interactive:not(:disabled):active { transform: scale(0.99); }

/* 左侧选中/悬浮指示条 */
.tree-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 2px;
  bottom: 2px;
  width: 2px;
  border-radius: 0 2px 2px 0;
  background: var(--c-accent);
  opacity: 0;
  transform: scaleY(0.6);
  transition: opacity var(--motion-fast) var(--ease-out),
              transform var(--motion-base) var(--ease-spring);
}
.tree-item:hover::before { opacity: 0.55; transform: scaleY(1); }
.tree-item.active::before { opacity: 1; transform: scaleY(1); }
.tree-item:hover { background: var(--c-surface-2); color: var(--c-text-0); }
.tree-item.active { background: var(--c-accent-soft); color: var(--c-text-0); }

/* 键盘焦点环 */
.tree-item:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
  z-index: 2;
}

/* 墨韵涟漪 — 悬浮时从光标处扩散 */
.tree-item::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(circle at var(--mx, 50%) var(--my, 50%), var(--c-accent) 0%, transparent 65%);
  opacity: 0;
  pointer-events: none;
  z-index: 0;
  transition: opacity var(--motion-base) var(--ease-brush);
}
.tree-item:hover::after { opacity: 0.05; }
.tree-item.active::after { opacity: 0.07; }

.tree-item > * { position: relative; z-index: 1; }

/* 文件夹展开折叠箭头 */
.tree-chevron {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--c-text-3);
  transform: rotate(0deg);
  transition: transform var(--motion-base) var(--ease-spring),
              color var(--motion-fast) var(--ease-out);
}
.tree-chevron.open { transform: rotate(90deg); color: var(--c-text-1); }
.tree-item:hover .tree-chevron { color: var(--c-text-1); }
.tree-chevron-spacer { width: 12px; flex-shrink: 0; }

.tree-icon { font-size: 12px; flex-shrink: 0; filter: grayscale(0.3); }
.tree-item.dir .tree-icon { filter: none; }
.tree-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* 文件夹图标展开微缩放 */
.tree-item.dir .tree-icon {
  transition: transform var(--motion-base) var(--ease-spring);
}
.tree-item.dir[data-expanded] .tree-icon { transform: scale(1.1); }

/* 子节点容器 */
.tree-children { overflow: hidden; }

/* 目录加载骨架 */
.tree-skeleton { display: flex; flex-direction: column; gap: 7px; padding-top: 4px; padding-bottom: 4px; }
.tree-skeleton-row {
  display: flex;
  align-items: center;
  gap: 8px;
  opacity: 0;
  animation: tree-sk-in var(--motion-base) var(--ease-out) both;
  animation-delay: calc(var(--stagger-i, 0) * var(--motion-stagger));
}
@keyframes tree-sk-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }

.rename-input {
  flex: 1;
  min-width: 0;
  background: var(--c-surface-3);
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-xs);
  color: var(--c-text-0);
  font-size: 13px;
  font-family: inherit;
  padding: 0 4px;
  outline: none;
  height: 20px;
  box-shadow: var(--ring-focus);
}

.ctx-menu {
  position: fixed;
  z-index: 9999;
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  padding: var(--space-1) 0;
  min-width: 160px;
  box-shadow: var(--elevation-3);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  text-align: left;
  background: none;
  border: none;
  color: var(--c-text-1);
  font-size: 13px;
  padding: 6px 16px;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out),
              padding-left var(--motion-fast) var(--ease-out);
}
.ctx-item:hover { background: var(--c-surface-3); color: var(--c-text-0); padding-left: 19px; }
.ctx-item:active { background: var(--c-surface-4); }
.ctx-item:focus-visible { outline: none; background: var(--c-surface-3); box-shadow: inset var(--ring-focus); }
.ctx-item.ctx-danger { color: var(--c-danger); }
.ctx-item.ctx-danger:hover { background: var(--c-danger-bg); color: var(--c-danger); }
.ctx-sep { height: 1px; background: var(--c-surface-3); margin: 4px 8px; }

@media (prefers-reduced-motion: reduce) {
  .tree-chevron,
  .tree-item,
  .tree-item.dir .tree-icon,
  .tree-item::before,
  .tree-item::after,
  .ctx-item { transition: none; }
  .tree-skeleton-row { animation: none; opacity: 1; }
  .tree-item.u-interactive:not(:disabled):active { transform: none; }
}
</style>
