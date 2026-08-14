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
      <kbd class="tb-kbd">Ctrl+K · AI</kbd>
      <button
        v-if="speech.isSupported"
        class="tb-btn u-interactive"
        :class="{ active: speech.status.value === 'listening' }"
        :title="
          speech.status.value === 'listening' ? t('editor.voiceStop') : t('editor.voiceStart')
        "
        :aria-label="t('editor.voiceStart')"
        @click="toggleSpeech"
      >
        <Mic :size="15" :stroke-width="1.7" />
      </button>
    </div>

    <div class="tb-right">
      <Transition name="v-slide-up">
        <div v-if="message" class="export-toast">{{ message }}</div>
      </Transition>

      <button
        class="tb-btn u-interactive"
        :class="{ active: activeRightTab === 'preview' }"
        :title="t('editor.preview')"
        :aria-label="t('editor.preview')"
        @click="$emit('toggle-right', 'preview')"
      >
        <Eye :size="15" :stroke-width="1.7" />
      </button>
      <button
        class="tb-btn u-interactive"
        :class="{ active: agentOpen }"
        :title="t('editor.rightAgent')"
        :aria-label="t('editor.rightAgent')"
        @click="$emit('toggle-right', 'agent')"
      >
        <Bot :size="15" :stroke-width="1.7" />
      </button>
      <button
        class="tb-btn u-interactive"
        :class="{ active: activeRightTab === 'argument' }"
        :title="t('editor.argumentMap')"
        :aria-label="t('editor.argumentMap')"
        @click="$emit('toggle-right', 'argument')"
      >
        <GitBranch :size="15" :stroke-width="1.7" />
      </button>
      <div class="tb-divider" />

      <UiDropdown :items="moreItems" :width="230" align="end">
        <template #trigger>
          <button
            class="tb-btn u-interactive"
            :title="t('editor.moreTools')"
            :aria-label="t('editor.moreTools')"
          >
            <MoreHorizontal :size="15" :stroke-width="1.7" />
          </button>
        </template>
      </UiDropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { Eye, Bot, GitBranch, MoreHorizontal, ScanText, BarChart3 } from './ui/icons'
import { Image, Table, Sigma, Quote, Library, CheckCircle } from './ui/icons'
import { Mic } from './ui/icons'
import UiDropdown from './ui/UiDropdown.vue'
import type { DropdownItem } from './ui/UiDropdown.vue'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import type { VisionAnalysisType } from '../composables/useEditorVision'

const speech = useSpeechRecognition({
  onResult: (text) => {
    if (text.trim()) emit('voice-update', text.trim())
  },
})

function resetVoiceAccumulated() {
  speech.resetAccumulated()
}

function toggleSpeech() {
  if (speech.status.value === 'listening') {
    const text = speech.stop()
    if (text.trim()) emit('voice-stop', text.trim())
  } else {
    emit('voice-start')
    speech.start()
  }
}

defineProps<{
  activeRightTab: string | null
  agentOpen: boolean
  message: string
}>()

const emit = defineEmits<{
  'toggle-right': [tab: 'preview' | 'agent' | 'argument']
  'open-image-picker': []
  'insert-table': []
  'insert-inline-formula': []
  'insert-block-formula': []
  'open-vision-picker': []
  'run-compliance': []
  'process-citations': []
  'zotero-insert': []
  'vision-selected': [file: File, mode: VisionAnalysisType]
  'image-selected': [file: File]
  'voice-text': [text: string]
  'voice-start': []
  'voice-update': [text: string]
  'voice-stop': [text: string]
}>()

const imageInputRef = ref<HTMLInputElement | null>(null)
const visionInputRef = ref<HTMLInputElement | null>(null)
const pendingVisionMode = ref<VisionAnalysisType>('general')

function openImagePicker() {
  imageInputRef.value?.click()
}

function pickVision(mode: VisionAnalysisType) {
  pendingVisionMode.value = mode
  visionInputRef.value?.click()
}

function handleImageSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) emit('image-selected', file)
}

function handleVisionSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (file) emit('vision-selected', file, pendingVisionMode.value)
}

defineExpose({ resetVoiceAccumulated })

const moreItems = computed<DropdownItem[]>(() => [
  { label: t('editor.insert') },
  { text: t('editor.image'), icon: Image, onClick: openImagePicker },
  { text: t('editor.table'), icon: Table, onClick: () => emit('insert-table') },
  { text: t('editor.inlineFormula'), icon: Sigma, onClick: () => emit('insert-inline-formula') },
  { text: t('editor.blockFormula'), icon: Sigma, onClick: () => emit('insert-block-formula') },
  { divider: true },
  { label: t('editor.analysis') },
  { text: t('editor.visionLabel'), icon: Eye, onClick: () => pickVision('general') },
  { text: t('editor.visionOcr'), icon: ScanText, onClick: () => pickVision('ocr') },
  { text: t('editor.visionChart'), icon: BarChart3, onClick: () => pickVision('chart') },
  { text: t('editor.visionTable'), icon: Table, onClick: () => pickVision('table') },
  { text: t('editor.visionFormula'), icon: Sigma, onClick: () => pickVision('formula') },
  { text: t('editor.complianceCheck'), icon: CheckCircle, onClick: () => emit('run-compliance') },
  { divider: true },
  { label: t('editor.cite') },
  { text: t('editor.citeNumber'), icon: Quote, onClick: () => emit('process-citations') },
  { text: t('editor.zoteroSearch'), icon: Library, onClick: () => emit('zotero-insert') },
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

.tb-left,
.tb-right {
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
  transition:
    background var(--motion-fast) var(--ease-out),
    color var(--motion-fast) var(--ease-out);
  flex-shrink: 0;
}
.tb-btn:hover {
  background: var(--c-surface-4);
  color: var(--c-text-0);
}
.tb-btn:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
.tb-btn.active {
  background: var(--c-accent-soft);
  color: var(--c-accent);
  box-shadow: inset 0 0 0 1px var(--c-accent-soft);
}
.tb-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

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

.hidden-file-input {
  display: none;
}
</style>
