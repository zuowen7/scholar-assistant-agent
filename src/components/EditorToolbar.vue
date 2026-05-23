<template>
  <div class="editor-toolbar" @click.stop>
    <input
      ref="imageInputRef"
      class="hidden-file-input"
      type="file"
      accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
      @change="handleImageSelected"
    />
    <input
      ref="visionInputRef"
      class="hidden-file-input"
      type="file"
      accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
      @change="handleVisionSelected"
    />

    <div class="tb-left">
      <button class="tb-btn u-interactive" title="新建论文" aria-label="新建论文" @click="$emit('new-paper')">
        <FilePlus :size="15" :stroke-width="1.7" />
      </button>
      <button class="tb-btn u-interactive" title="保存 (Ctrl+S)" aria-label="保存" @click="$emit('save')">
        <Save :size="15" :stroke-width="1.7" />
      </button>
      <div class="tb-divider" />
      <kbd class="tb-kbd">Ctrl+K · AI</kbd>
    </div>

    <div class="tb-right">
      <Transition name="v-slide-up">
        <div v-if="exportLoading" class="export-status">
          <UiSpinner size="sm" label="导出中" />
        </div>
        <div v-else-if="message" class="export-toast">{{ message }}</div>
      </Transition>

      <button
        class="tb-btn u-interactive"
        title="思维导图"
        aria-label="思维导图"
        @click="$emit('open-mindmap')"
      >
        <Workflow :size="15" :stroke-width="1.7" />
      </button>
      <button
        class="tb-btn u-interactive"
        :class="{ active: activeRightTab === 'preview' }"
        title="预览"
        aria-label="预览"
        @click="$emit('toggle-right', 'preview')"
      >
        <Eye :size="15" :stroke-width="1.7" />
      </button>
      <button
        class="tb-btn u-interactive"
        :class="{ active: activeRightTab === 'ai' }"
        title="AI 编辑"
        aria-label="AI 编辑面板"
        @click="$emit('toggle-right', 'ai')"
      >
        <Bot :size="15" :stroke-width="1.7" />
      </button>
      <button
        class="tb-btn u-interactive"
        :class="{ active: activeRightTab === 'argument' }"
        title="论证导图"
        aria-label="论证导图"
        @click="$emit('toggle-right', 'argument')"
      >
        <GitBranch :size="15" :stroke-width="1.7" />
      </button>
      <div class="tb-divider" />

      <UiDropdown :items="moreItems" :width="230" align="end">
        <template #trigger>
          <button class="tb-btn u-interactive" title="更多工具" aria-label="更多工具">
            <MoreHorizontal :size="15" :stroke-width="1.7" />
          </button>
        </template>
        <template v-if="templates.length" #default>
          <div class="dd-template-row">
            <span class="dd-template-label">LaTeX 模板</span>
            <select
              class="dd-template-select"
              :value="selectedTemplate"
              :disabled="exportLoading"
              @change="$emit('select-template', ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </div>
        </template>
      </UiDropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { FilePlus, Save, Eye, Bot, GitBranch, Workflow, MoreHorizontal } from './ui/icons'
import { Image, Table, Sigma, Quote, Library, Code2, CheckCircle, Download } from './ui/icons'
import UiDropdown from './ui/UiDropdown.vue'
import UiSpinner from './ui/UiSpinner.vue'
import type { DropdownItem } from './ui/UiDropdown.vue'

defineProps<{
  activeRightTab: string | null
  templates: { id: string; name: string }[]
  selectedTemplate: string
  exportLoading: boolean
  message: string
}>()

const emit = defineEmits<{
  'new-paper': []
  save: []
  'open-mindmap': []
  'toggle-right': [tab: 'preview' | 'ai' | 'argument']
  'select-template': [id: string]
  'open-image-picker': []
  'insert-table': []
  'insert-inline-formula': []
  'insert-block-formula': []
  'open-vision-picker': []
  'run-compliance': []
  'process-citations': []
  'zotero-insert': []
  'export-word': []
  'export-latex': []
  'export-pdf': []
  'vision-selected': [file: File]
  'image-selected': [file: File]
}>()

const imageInputRef = ref<HTMLInputElement | null>(null)
const visionInputRef = ref<HTMLInputElement | null>(null)

function openImagePicker() { imageInputRef.value?.click() }
function openVisionPicker() { visionInputRef.value?.click() }

function handleImageSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) emit('image-selected', file)
}

function handleVisionSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) emit('vision-selected', file)
}

const moreItems = computed<DropdownItem[]>(() => [
  { label: '插入' },
  { text: '图片', icon: Image, onClick: openImagePicker },
  { text: '表格 3×3', icon: Table, onClick: () => emit('insert-table') },
  { text: '行内公式', icon: Sigma, onClick: () => emit('insert-inline-formula') },
  { text: '块级公式', icon: Sigma, onClick: () => emit('insert-block-formula') },
  { divider: true },
  { label: '分析' },
  { text: 'OCR / Vision', icon: Eye, onClick: openVisionPicker },
  { text: '论文合规检查', icon: CheckCircle, onClick: () => emit('run-compliance') },
  { divider: true },
  { label: '引用' },
  { text: '编号引用', icon: Quote, onClick: () => emit('process-citations') },
  { text: 'Zotero 搜索', icon: Library, onClick: () => emit('zotero-insert') },
  { divider: true },
  { label: '导出' },
  { text: 'Word (.docx)', icon: Download, onClick: () => emit('export-word') },
  { text: 'LaTeX (.tex)', icon: Code2, onClick: () => emit('export-latex') },
  { text: 'PDF', icon: Download, onClick: () => emit('export-pdf') },
])
</script>

<style scoped>
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--c-surface-3);
  background: var(--c-surface-1);
  min-height: 40px;
  flex-shrink: 0;
}

.tb-left, .tb-right {
  display: flex;
  align-items: center;
  gap: 2px;
}

.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--c-text-3);
  cursor: pointer;
  transition: background var(--motion-fast) var(--ease-out),
              color var(--motion-fast) var(--ease-out);
  flex-shrink: 0;
}
.tb-btn:hover { background: var(--c-surface-4); color: var(--c-text-0); }
.tb-btn:focus-visible { outline: none; box-shadow: var(--ring-focus); }
.tb-btn.active { background: var(--c-accent-soft); color: var(--c-accent); box-shadow: inset 0 0 0 1px var(--c-accent-soft); }
.tb-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.tb-divider {
  width: 1px;
  height: 16px;
  background: var(--c-surface-3);
  margin: 0 4px;
  flex-shrink: 0;
}

.tb-kbd {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--c-surface-3);
  border-radius: 4px;
  background: var(--c-surface-4);
  color: var(--c-text-3);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: default;
  flex-shrink: 0;
}

.export-status {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--c-accent-soft);
  border: 1px solid var(--c-accent-soft);
  white-space: nowrap;
}

.export-toast {
  font-size: 11px;
  color: var(--c-success);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--c-success-bg);
  border: 1px solid var(--c-success-border);
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hidden-file-input { display: none; }

.dd-template-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 8px;
  border-top: 1px solid var(--c-surface-3);
  margin-top: 4px;
}
.dd-template-label {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  white-space: nowrap;
  flex-shrink: 0;
}
.dd-template-select {
  flex: 1;
  min-width: 0;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-1);
  font-size: var(--text-sm);
  padding: 4px 6px;
  cursor: pointer;
  outline: none;
}
.dd-template-select:hover { border-color: var(--c-accent); }
.dd-template-select:disabled { opacity: 0.5; cursor: not-allowed; }
.dd-template-select option { background: var(--c-surface-2); }
</style>
