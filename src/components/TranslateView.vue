<template>
  <main class="translation-workspace">
    <template v-if="state.status === 'idle' || state.status === 'error'">
      <header class="translation-hero">
        <div>
          <p class="translation-kicker">{{ t('translate.workspaceKicker') }}</p>
          <h1>{{ t('translate.heroTitle') }}</h1>
          <p>{{ t('translate.workspaceDescription') }}</p>
        </div>
        <span class="service-state" :class="healthOk ? 'online' : 'offline'">
          <i />{{ healthOk ? t('status.online') : t('status.offline') }}
        </span>
      </header>

      <section class="translation-start" aria-labelledby="translation-start-title">
        <div
          class="drop-zone"
          :class="{ hover: zoneHover }"
          role="button"
          tabindex="0"
          :aria-label="t('translate.selectFile')"
          @click="openFilePicker"
          @keydown.enter="openFilePicker"
          @keydown.space.prevent="openFilePicker"
          @dragenter.prevent="zoneHover = true"
          @dragover.prevent="zoneHover = true"
          @dragleave.prevent="zoneHover = false"
          @drop.prevent="zoneHover = false"
        >
          <span class="drop-icon" aria-hidden="true"
            ><UploadCloud :size="25" :stroke-width="1.6"
          /></span>
          <div class="drop-copy">
            <strong id="translation-start-title">{{ t('translate.clickToSelect') }}</strong>
            <span>{{ t('translate.dragHint') }}</span>
          </div>
          <UiButton variant="primary" size="sm" tabindex="-1">{{
            t('translate.selectFile')
          }}</UiButton>
        </div>

        <div class="format-strip" :aria-label="t('translate.supportedFormats')">
          <span>{{ t('translate.supportedFormats') }}</span>
          <ul>
            <li v-for="fmt in formatList" :key="fmt">{{ fmt }}</li>
          </ul>
        </div>

        <div
          v-if="state.status === 'error' && state.errorMessage"
          class="state-banner state-banner--error"
          role="alert"
        >
          <AlertCircle :size="17" :stroke-width="1.8" />
          <div>
            <strong>{{ t('general.error') }}</strong
            ><span>{{ state.errorMessage }}</span>
          </div>
          <UiButton
            v-if="!healthOk"
            variant="secondary"
            size="sm"
            :loading="backendRestarting"
            @click="$emit('restart-backend')"
            >{{ t('translate.restartBackend') }}</UiButton
          >
        </div>
      </section>
    </template>

    <template v-else-if="state.status !== 'done'">
      <header class="workspace-header">
        <div>
          <p class="translation-kicker">{{ t('translate.workspaceKicker') }}</p>
          <h1>{{ t('translate.processingTitle') }}</h1>
          <p>{{ state.stepMessage || t('translate.preparing') }}</p>
        </div>
        <div class="processing-actions">
          <div class="progress-number">
            <strong>{{ progress }}%</strong><span>{{ t('translate.completed') }}</span>
          </div>
          <UiButton variant="ghost" size="sm" @click="startNewTranslation">{{
            t('general.cancel')
          }}</UiButton>
        </div>
      </header>

      <div class="processing-layout">
        <section class="process-panel" :aria-label="t('translate.processingTitle')">
          <ol class="step-list">
            <li
              v-for="(label, idx) in stepLabels"
              :key="label"
              :class="{ done: idx + 1 < state.currentStep, active: idx + 1 === state.currentStep }"
            >
              <span class="step-marker"
                ><Check
                  v-if="idx + 1 < state.currentStep"
                  :size="13"
                  :stroke-width="2.5"
                /><template v-else>{{ idx + 1 }}</template></span
              >
              <div>
                <strong>{{ label }}</strong
                ><span>{{ stepStatus(idx + 1) }}</span>
              </div>
            </li>
          </ol>

          <div class="progress-block">
            <div class="progress-copy">
              <span>{{ state.stepMessage || t('translate.preparing') }}</span
              ><strong>{{ progress }}%</strong>
            </div>
            <div
              class="progress-track"
              role="progressbar"
              :aria-valuenow="progress"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <i :style="{ width: `${progress}%` }" />
            </div>
            <div v-if="state.currentStep === 4 && state.totalChunks > 0" class="chunk-progress">
              <span>{{ t('translate.chunkProgress') }}</span>
              <strong>{{ state.completedChunks }} / {{ state.totalChunks }}</strong>
            </div>
          </div>

          <dl v-if="state.parsedInfo" class="document-facts">
            <div>
              <dt>{{ t('translate.pages') }}</dt>
              <dd>{{ state.parsedInfo.pages }}</dd>
            </div>
            <div>
              <dt>{{ t('translate.chars') }}</dt>
              <dd>{{ state.parsedInfo.chars.toLocaleString() }}</dd>
            </div>
            <div v-if="state.parsedInfo.dual_column_pages">
              <dt>{{ t('translate.dualColumnPages') }}</dt>
              <dd>{{ state.parsedInfo.dual_column_pages }}</dd>
            </div>
          </dl>
        </section>

        <section class="live-panel" aria-live="polite">
          <header>
            <div>
              <p class="translation-kicker">{{ t('translate.livePreview') }}</p>
              <h2>{{ t('translate.currentOutput') }}</h2>
            </div>
            <span
              >{{ state.blocks.filter((b) => b.translated).length }} /
              {{ state.blocks.filter((b) => b.translatable).length }}</span
            >
          </header>
          <div v-if="state.blocks.some((b) => b.translated)" class="live-list">
            <article
              v-for="b in state.blocks.filter((b) => b.translated && b.translatable).slice(-4)"
              :key="b.id"
            >
              <p class="live-original">{{ truncate(b.original, 220) }}</p>
              <p class="live-translation">{{ truncate(b.translated, 220) }}</p>
            </article>
          </div>
          <div v-else class="live-empty">
            <FileText :size="24" :stroke-width="1.4" />
            <p>{{ t('translate.previewPending') }}</p>
          </div>
        </section>
      </div>
    </template>

    <template v-else>
      <header class="result-header">
        <div class="result-title">
          <p class="translation-kicker">{{ t('translate.workspaceKicker') }}</p>
          <h1>{{ t('translate.translationComplete') }}</h1>
          <div class="result-meta">
            <span>{{
              t('translate.blocksAndParagraphs', {
                blocks: state.blocks.length,
                paragraphs: paragraphCount,
              })
            }}</span>
            <button v-if="state.ragIngested" type="button" @click="$emit('open-agent-docs')">
              {{ t('translate.addedToLibrary') }}
            </button>
            <span v-else-if="state.ragStatus === 'queued'">{{ t('sources.rag.queued') }}</span>
            <span v-else-if="state.ragStatus === 'failed'" class="warning-text">{{
              t('sources.rag.failed')
            }}</span>
            <span v-if="state.misalignedChunks > 0" class="warning-text">{{
              t('translate.misalignedChunks', { count: state.misalignedChunks })
            }}</span>
          </div>
        </div>
        <div class="result-actions">
          <label class="result-search">
            <Search :size="13" :stroke-width="1.8" />
            <input
              v-model="searchQuery"
              type="search"
              :placeholder="t('translate.searchResult')"
              :aria-label="t('translate.searchResult')"
            />
            <span v-if="searchQuery">{{ renderableBlocks.length }}</span>
          </label>
          <UiSegmented v-model="viewMode" :options="viewOptions" size="sm" />
          <UiDropdown :items="exportMenuItems" align="end">
            <template #trigger>
              <UiButton variant="primary" size="sm">
                <template #icon-left><Download :size="14" :stroke-width="2" /></template>
                {{ t('translate.export') }}
                <template #icon-right><ChevronDown :size="13" :stroke-width="2" /></template>
              </UiButton>
            </template>
          </UiDropdown>
          <UiButton variant="ghost" size="sm" @click="startNewTranslation">{{
            t('translate.newTranslate')
          }}</UiButton>
        </div>
      </header>

      <div
        v-if="state.errorMessage"
        class="state-banner state-banner--error result-error"
        role="alert"
      >
        <AlertCircle :size="17" :stroke-width="1.8" />
        <div>
          <strong>{{ t('general.error') }}</strong
          ><span>{{ state.errorMessage }}</span>
        </div>
      </div>

      <details v-if="qaSummary.totalFlags > 0" class="quality-panel">
        <summary>
          <span><AlertTriangle :size="16" :stroke-width="1.8" />{{ t('translate.qa.title') }}</span>
          <span class="quality-summary"
            >{{ qaSummary.totalFlags }} · {{ t('translate.qa.score') }}
            {{ qaSummary.avgScore }}</span
          >
        </summary>
        <div class="quality-list">
          <section v-for="(w, wi) in state.qaWarnings" :key="wi">
            <header>
              <strong>{{ t('translate.qa.paragraph') }} {{ w.chunkIndex + 1 }}</strong
              ><span>{{ sectionLabel(w.sectionType) }} · {{ w.score }}</span>
            </header>
            <p v-for="(f, fi) in w.flags" :key="fi" :class="`quality-${f.severity}`">
              <strong>{{ flagTypeLabel(f.type) }}</strong
              >{{ f.message }}<em v-if="f.suggestion">{{ f.suggestion }}</em>
            </p>
          </section>
        </div>
      </details>

      <div class="reader-shell" :style="readStyleVars">
        <div v-if="viewMode === 'bilingual'" class="reader-columns" aria-hidden="true">
          <span>{{ t('translate.sourceText') }}</span
          ><span>{{ t('translate.translatedText') }}</span>
        </div>

        <div v-if="searchQuery && renderableBlocks.length === 0" class="result-empty">
          <SearchX :size="24" :stroke-width="1.5" />
          <strong>{{ t('translate.noSearchResults') }}</strong>
          <span>{{ t('translate.noSearchResultsHint') }}</span>
        </div>

        <div v-else-if="viewMode === 'bilingual'" class="dual-view">
          <article
            v-for="b in renderableBlocks"
            :key="b.id"
            class="dual-row"
            :class="`type-${b.type}`"
          >
            <template v-if="b.type === 'heading'">
              <component
                :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`"
                class="dual-heading-orig"
                >{{ stripHeadingMark(b.original) }}</component
              >
              <component
                v-if="b.translated"
                :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`"
                class="dual-heading-trans"
                >{{ stripHeadingMark(b.translated) }}</component
              >
            </template>
            <TranslationBlockHtml
              v-else-if="!b.translatable"
              class="dual-untranslated"
              :text="b.original"
              :block-type="b.type"
            />
            <template v-else-if="b.status === 'failed'">
              <TranslationBlockHtml class="dual-orig" :text="b.original" :block-type="b.type" />
              <div class="failed-card">
                <span
                  ><AlertCircle :size="15" :stroke-width="1.8" />{{
                    t('translate.translationFailed')
                  }}</span
                >
                <UiButton
                  v-if="!retryingBlockIds.has(b.id)"
                  variant="secondary"
                  size="sm"
                  @click="retryFailedBlock(b.id)"
                  >{{ t('translate.retry') }}</UiButton
                >
                <UiSpinner v-else size="sm" :label="t('translate.retrying')" />
                <p v-if="retryErrors.get(b.id)">{{ retryErrors.get(b.id) }}</p>
              </div>
            </template>
            <template v-else>
              <TranslationBlockHtml
                class="dual-orig"
                :text="b.original"
                mode="sentence"
                lang="en"
                :block-id="b.id"
                side="orig"
                @mouseover="handleSentenceMouseEnter"
                @mouseleave="clearSentHover"
              />
              <TranslationBlockHtml
                v-if="b.translated"
                class="dual-trans"
                :text="b.translated"
                mode="sentence"
                lang="zh"
                :block-id="b.id"
                side="trans"
                @mouseover="handleSentenceMouseEnter"
                @mouseleave="clearSentHover"
              />
              <div v-else class="dual-pending">
                <UiSpinner size="sm" :label="t('translate.translating')" />
              </div>
            </template>
          </article>
        </div>

        <div v-else class="reading-view">
          <article class="prose" v-html="translationOnlyHtml" />
        </div>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  ChevronDown,
  Database,
  Download,
  FileText,
  PresentationScreen,
  Search,
  SearchX,
  UploadCloud,
} from './ui/icons'
import UiButton from './ui/UiButton.vue'
import UiDropdown from './ui/UiDropdown.vue'
import type { DropdownItem } from './ui/UiDropdown.vue'
import UiSegmented from './ui/UiSegmented.vue'
import UiSpinner from './ui/UiSpinner.vue'
import TranslationBlockHtml from './TranslationBlockHtml.vue'
import { useTranslate } from '../composables/useTranslate'
import { renderMarkdown } from '../utils/markdown'
import { findCorrespondingSentenceIndices, splitSentences } from '../utils/sentenceAlign'
import { filterTranslationBlocks } from '../utils/translationSearch'

const { t } = useI18n()
const props = defineProps<{
  healthOk: boolean
  backendRestarting: boolean
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
}>()
defineEmits<{ (e: 'restart-backend'): void; (e: 'open-agent-docs'): void }>()

const {
  state,
  translate,
  reset,
  downloadResult,
  overallProgress,
  retryBlock,
  exportBilingualDocx,
  exportTranslationOnlyDocx,
  exportTranslationOnlyMarkdown,
  exportPPTX,
  exportDataAvailability,
} = useTranslate()
const viewMode = ref<'bilingual' | 'translation'>('bilingual')
const searchQuery = ref('')
const zoneHover = ref(false)
const retryingBlockIds = ref(new Set<string>())
const retryErrors = ref(new Map<string, string>())

onMounted(() => {
  window.addEventListener('voice-translate-new', handleVoiceTranslateNew)
  window.addEventListener('voice-translate-retry', handleVoiceTranslateRetry)
  window.addEventListener('voice-translate-export', handleVoiceTranslateExport as EventListener)
})
onBeforeUnmount(() => {
  window.removeEventListener('voice-translate-new', handleVoiceTranslateNew)
  window.removeEventListener('voice-translate-retry', handleVoiceTranslateRetry)
  window.removeEventListener('voice-translate-export', handleVoiceTranslateExport as EventListener)
})

function handleVoiceTranslateNew() {
  startNewTranslation()
  openFilePicker()
}
function handleVoiceTranslateRetry() {
  state.blocks.filter((b) => b.status === 'failed').forEach((b) => retryFailedBlock(b.id))
}
function handleVoiceTranslateExport(event: Event) {
  const { format } = (event as CustomEvent).detail
  if (state.status !== 'done') return
  const actions: Record<string, () => unknown> = {
    'bilingual-docx': exportBilingualDocx,
    'translation-docx': exportTranslationOnlyDocx,
    'bilingual-md': downloadResult,
    'translation-md': exportTranslationOnlyMarkdown,
    pptx: exportPPTX,
  }
  actions[format]?.()
}

async function retryFailedBlock(blockId: string) {
  if (!state.taskId) return
  retryingBlockIds.value.add(blockId)
  retryErrors.value.delete(blockId)
  try {
    await retryBlock(blockId)
  } catch (error) {
    const message = error instanceof Error ? error.message : t('translate.unknownError')
    retryErrors.value.set(blockId, message)
  } finally {
    retryingBlockIds.value.delete(blockId)
  }
}

const exportMenuItems = computed<DropdownItem[]>(() => [
  { text: t('translate.exportMenu.bilingualMd'), icon: FileText, onClick: downloadResult },
  { text: t('translate.exportMenu.bilingualWord'), icon: FileText, onClick: exportBilingualDocx },
  {
    text: t('translate.exportMenu.translationOnlyMd'),
    icon: FileText,
    onClick: exportTranslationOnlyMarkdown,
  },
  {
    text: t('translate.exportMenu.translationOnlyWord'),
    icon: FileText,
    onClick: exportTranslationOnlyDocx,
  },
  { divider: true },
  { text: t('translate.exportMenu.pptx'), icon: PresentationScreen, onClick: exportPPTX },
  { text: 'Data Availability', icon: Database, onClick: exportDataAvailability },
])
const stepLabels = computed(() => [
  t('translate.steps.parse'),
  t('translate.steps.clean'),
  t('translate.steps.chunk'),
  t('translate.steps.translate'),
  t('translate.steps.format'),
])
const formatList = ['PDF', 'DOCX', 'PPTX', 'XLSX', 'TXT', 'MD', 'HTML', 'EPUB', 'LaTeX', 'JSON']
const viewOptions = computed(() => [
  { value: 'bilingual' as const, label: t('translate.view.bilingual') },
  { value: 'translation' as const, label: t('translate.view.translation') },
])
const progress = computed(() => overallProgress())
const paragraphCount = computed(
  () => state.blocks.filter((block) => block.type === 'paragraph').length,
)
const renderableBlocks = computed(() => filterTranslationBlocks(state.blocks, searchQuery.value))
const readStyleVars = computed(() => ({
  '--read-fs': `${props.readSettings.fontSize}px`,
  '--read-lh': props.readSettings.lineHeight,
  '--read-ff': props.readSettings.fontFamily,
  ...(props.readSettings.transColor ? { '--read-trans-color': props.readSettings.transColor } : {}),
}))
const qaSummary = computed(() => {
  const totalFlags = state.qaWarnings.reduce((sum, warning) => sum + warning.flags.length, 0)
  const score = state.qaWarnings.reduce((sum, warning) => sum + warning.score, 0)
  return {
    totalFlags,
    avgScore: state.qaWarnings.length ? Math.round(score / state.qaWarnings.length) : 100,
  }
})
const translationOnlyHtml = computed(() =>
  renderMarkdown(
    renderableBlocks.value
      .flatMap((block) => {
        if (block.status === 'failed') return []
        if (!block.translatable) return [block.original]
        if (!block.translated) return []
        return [
          block.type === 'heading'
            ? `${'#'.repeat(Math.min(Math.max(block.level || 2, 1), 6))} ${stripHeadingMark(block.translated)}`
            : block.translated,
        ]
      })
      .join('\n\n'),
  ),
)

function stepStatus(step: number) {
  if (step < state.currentStep) return t('translate.stepDone')
  if (step === state.currentStep) return t('translate.stepActive')
  return t('translate.stepWaiting')
}
function startNewTranslation() {
  searchQuery.value = ''
  reset()
}
function truncate(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit)}…` : value
}
function stripHeadingMark(value: string) {
  return value.replace(/^#{1,6}\s+/, '').trim()
}
function sectionLabel(value: string) {
  const keys: Record<string, string> = {
    introduction: 'introduction',
    results: 'results',
    discussion: 'discussion',
    methods: 'methods',
    conclusion: 'conclusion',
    abstract: 'abstract',
    references: 'references',
  }
  return keys[value] ? t(`translate.section.${keys[value]}`) : value
}
function flagTypeLabel(value: string) {
  const keys: Record<string, string> = {
    overclaim: 'overclaim',
    sentence_length: 'sentence_length',
    mixed_tense: 'mixed_tense',
    hedging: 'hedging',
  }
  return keys[value] ? t(`translate.flag.${keys[value]}`) : value
}

function clearSentHover() {
  document
    .querySelectorAll('.sent-active')
    .forEach((element) => element.classList.remove('sent-active'))
}
function handleSentenceMouseEnter(event: MouseEvent) {
  const target = (event.target as HTMLElement).closest<HTMLElement>('[data-sent-idx]')
  if (!target) return
  const index = Number(target.dataset.sentIdx)
  const blockId = target.dataset.blockId
  const side = target.dataset.side as 'orig' | 'trans' | undefined
  if (!blockId || !side || Number.isNaN(index)) return
  updateSentenceHighlight(blockId, side, index)
}
function updateSentenceHighlight(blockId: string, side: 'orig' | 'trans', sentIdx: number) {
  clearSentHover()
  const block = state.blocks.find((item) => item.id === blockId)
  if (!block?.translated) return
  const sourceText = side === 'orig' ? block.original : block.translated
  const targetText = side === 'orig' ? block.translated : block.original
  const sourceLang = side === 'orig' ? 'en' : 'zh'
  const targetLang = side === 'orig' ? 'zh' : 'en'
  const otherIndices = findCorrespondingSentenceIndices(
    splitSentences(sourceText, sourceLang),
    splitSentences(targetText, targetLang),
    sentIdx,
  )
  const ownSelector = `[data-block-id="${CSS.escape(blockId)}"][data-side="${side}"][data-sent-idx="${sentIdx}"]`
  const otherSide = side === 'orig' ? 'trans' : 'orig'
  document.querySelector(ownSelector)?.classList.add('sent-active')
  otherIndices.forEach((otherIndex) => {
    const otherSelector = `[data-block-id="${CSS.escape(blockId)}"][data-side="${otherSide}"][data-sent-idx="${otherIndex}"]`
    document.querySelector(otherSelector)?.classList.add('sent-active')
  })
}
function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept =
    '.pdf,.docx,.doc,.txt,.md,.log,.html,.htm,.epub,.rtf,.tex,.csv,.pptx,.xlsx,.srt,.json,.xml'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) translate(file)
  }
  input.click()
}
</script>

<style scoped>
.translation-workspace {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  background: var(--c-app-bg);
  color: var(--c-text-0);
}
.translation-hero,
.workspace-header,
.result-header {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  padding: 34px 42px 24px;
  border-bottom: 1px solid var(--c-border);
}
.translation-hero {
  width: min(1030px, calc(100% - 64px));
  box-sizing: border-box;
  align-self: center;
  padding: 54px 0 25px;
}
.translation-kicker {
  margin: 0 0 7px;
  color: var(--brand-red);
  font-size: 11px;
  font-weight: 680;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}
h1,
h2,
p {
  margin-top: 0;
}
.translation-hero h1,
.workspace-header h1,
.result-header h1 {
  margin-bottom: 7px;
  font-family: var(--font-serif-zh);
  font-size: clamp(22px, 2.2vw, 30px);
  font-weight: 650;
  letter-spacing: -0.025em;
  line-height: 1.25;
}
.translation-hero > div > p:last-child,
.workspace-header > div > p:last-child {
  max-width: 610px;
  margin: 0;
  color: var(--c-text-2);
  font-size: 13px;
  line-height: 1.65;
}
.service-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 4px;
  color: var(--c-text-2);
  font-size: 12px;
  white-space: nowrap;
}
.service-state i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-danger);
}
.service-state.online i {
  background: var(--c-success);
}
.translation-start {
  width: min(1030px, calc(100% - 64px));
  align-self: center;
  padding: 28px 0 56px;
}
.drop-zone {
  display: grid;
  min-height: 170px;
  box-sizing: border-box;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  padding: 28px 32px;
  border: 1px dashed var(--c-border-strong);
  border-radius: 11px;
  background: var(--c-panel);
  cursor: pointer;
  outline: none;
  transition:
    border-color var(--motion-fast),
    background var(--motion-fast);
}
.drop-zone:hover,
.drop-zone.hover {
  border-color: var(--c-accent);
  background: color-mix(in srgb, var(--c-accent-soft) 42%, var(--c-panel));
}
.drop-zone:focus-visible {
  box-shadow: var(--ring-focus);
}
.drop-icon {
  display: grid;
  width: 50px;
  height: 50px;
  place-items: center;
  border-radius: 10px;
  background: var(--c-accent-soft);
  color: var(--c-accent);
}
.drop-copy {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}
.drop-copy strong {
  font-size: 15px;
  font-weight: 650;
}
.drop-copy span {
  color: var(--c-text-2);
  font-size: 12px;
  line-height: 1.5;
}
.format-strip {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  padding: 16px 2px;
  color: var(--c-text-3);
  font-size: 11px;
}
.format-strip > span {
  padding-top: 4px;
  white-space: nowrap;
}
.format-strip ul {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}
.format-strip li {
  padding: 3px 10px;
  border-left: 1px solid var(--c-border);
  color: var(--c-text-2);
}
.format-strip li:first-child {
  border-left: 0;
}
.state-banner {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 12px 14px;
  border-radius: 9px;
  font-size: 12px;
}
.state-banner > div {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}
.state-banner strong {
  font-size: 12px;
}
.state-banner span {
  overflow-wrap: anywhere;
}
.state-banner--error {
  border: 1px solid var(--c-danger-border);
  background: var(--c-danger-bg);
  color: var(--c-danger-fg);
}
.workspace-header {
  padding-top: 28px;
}
.processing-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.progress-number {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.progress-number strong {
  color: var(--c-accent);
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}
.progress-number span {
  color: var(--c-text-3);
  font-size: 11px;
}
.processing-layout {
  display: grid;
  min-height: 0;
  flex: 1;
  grid-template-columns: minmax(270px, 340px) minmax(0, 1fr);
  overflow: hidden;
}
.process-panel {
  min-width: 0;
  overflow-y: auto;
  padding: 28px 30px;
  border-right: 1px solid var(--c-border);
  background: var(--c-panel);
}
.step-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.step-list li {
  position: relative;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 11px;
  min-height: 54px;
  color: var(--c-text-3);
}
.step-list li:not(:last-child)::after {
  position: absolute;
  top: 27px;
  bottom: 0;
  left: 13px;
  width: 1px;
  background: var(--c-border);
  content: '';
}
.step-marker {
  position: relative;
  z-index: 1;
  display: grid;
  width: 26px;
  height: 26px;
  box-sizing: border-box;
  place-items: center;
  border: 1px solid var(--c-border);
  border-radius: 50%;
  background: var(--c-panel);
  font-size: 11px;
}
.step-list li.done .step-marker {
  border-color: var(--c-success);
  background: var(--c-success-bg);
  color: var(--c-success);
}
.step-list li.active .step-marker {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
  color: var(--c-accent);
  box-shadow: 0 0 0 3px var(--c-accent-ring);
}
.step-list li > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-top: 3px;
}
.step-list strong {
  color: var(--c-text-1);
  font-size: 12px;
  font-weight: 620;
}
.step-list li.active strong {
  color: var(--c-accent);
}
.step-list li > div span {
  font-size: 11px;
}
.progress-block {
  margin-top: 12px;
  padding-top: 18px;
  border-top: 1px solid var(--c-border);
}
.progress-copy,
.chunk-progress {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--c-text-2);
  font-size: 11px;
}
.progress-copy strong,
.chunk-progress strong {
  color: var(--c-text-1);
  font-variant-numeric: tabular-nums;
}
.progress-track {
  height: 5px;
  margin: 9px 0 12px;
  overflow: hidden;
  border-radius: 4px;
  background: var(--c-surface-2);
}
.progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-accent);
  transition: width 0.3s var(--ease-out);
}
.document-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 22px 0 0;
  overflow: hidden;
  border: 1px solid var(--c-border);
  border-radius: 9px;
  background: var(--c-border);
}
.document-facts div {
  padding: 10px 11px;
  background: var(--c-app-bg);
}
.document-facts dt {
  color: var(--c-text-3);
  font-size: 10px;
}
.document-facts dd {
  margin: 4px 0 0;
  color: var(--c-text-1);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.live-panel {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  padding: 28px 36px;
}
.live-panel > header {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--c-border);
}
.live-panel h2 {
  margin: 0;
  font-family: var(--font-serif-zh);
  font-size: 18px;
  font-weight: 620;
}
.live-panel > header > span {
  color: var(--c-text-3);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.live-list {
  min-height: 0;
  overflow-y: auto;
}
.live-list article {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 28px;
  padding: 18px 4px;
  border-bottom: 1px solid var(--c-border);
}
.live-list p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
}
.live-original {
  color: var(--c-text-2);
}
.live-translation {
  color: var(--c-text-0);
}
.live-empty {
  display: grid;
  min-height: 260px;
  flex: 1;
  place-content: center;
  justify-items: center;
  gap: 10px;
  color: var(--c-text-3);
}
.live-empty p {
  margin: 0;
  font-size: 12px;
}
.result-header {
  align-items: center;
  padding-top: 20px;
  padding-bottom: 16px;
}
.result-title h1 {
  margin-bottom: 4px;
  font-size: 23px;
}
.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: var(--c-text-3);
  font-size: 11px;
}
.result-meta button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--c-accent);
  font: inherit;
  cursor: pointer;
}
.warning-text {
  color: var(--c-warn);
}
.result-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.result-error {
  margin: 12px 42px 0;
}
.result-search {
  display: flex;
  width: min(190px, 22vw);
  height: 30px;
  box-sizing: border-box;
  align-items: center;
  gap: 6px;
  padding: 0 8px;
  border: 1px solid var(--c-border);
  border-radius: 8px;
  background: var(--input-bg);
  color: var(--c-text-3);
}
.result-search:focus-within {
  border-color: var(--c-accent);
  box-shadow: var(--ring-focus);
}
.result-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--c-text-0);
  font: inherit;
  font-size: 11px;
}
.result-search input::-webkit-search-cancel-button {
  display: none;
}
.result-search > span {
  color: var(--c-text-3);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.quality-panel {
  flex: 0 0 auto;
  margin: 12px 42px 0;
  border: 1px solid var(--c-warn-border);
  border-radius: 9px;
  background: var(--c-warn-bg);
}
.quality-panel summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 13px;
  color: var(--c-warn-fg);
  font-size: 12px;
  cursor: pointer;
}
.quality-panel summary > span:first-child {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 620;
}
.quality-summary {
  font-variant-numeric: tabular-nums;
}
.quality-list {
  max-height: 220px;
  overflow-y: auto;
  padding: 0 13px 12px;
}
.quality-list section {
  padding: 10px 0;
  border-top: 1px solid var(--c-warn-border);
}
.quality-list header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
  font-size: 11px;
}
.quality-list p {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 10px;
  margin: 5px 0;
  color: var(--c-text-1);
  font-size: 11px;
  line-height: 1.5;
}
.quality-list em {
  grid-column: 2;
  color: var(--c-text-2);
  font-style: normal;
}
.reader-shell {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}
.reader-columns {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  padding: 10px 46px;
  border-bottom: 1px solid var(--c-border);
  background: var(--c-panel);
  color: var(--c-text-3);
  font-size: 10px;
  font-weight: 620;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}
.result-empty {
  display: grid;
  min-height: 280px;
  flex: 1;
  place-content: center;
  justify-items: center;
  gap: 7px;
  color: var(--c-text-3);
  text-align: center;
}
.result-empty strong {
  color: var(--c-text-1);
  font-size: 13px;
}
.result-empty span {
  max-width: 340px;
  font-size: 11px;
  line-height: 1.5;
}
.dual-view,
.reading-view {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 0 42px 54px;
}
.dual-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 32px;
  padding: 20px 4px;
  border-bottom: 1px solid var(--c-border);
}
.dual-row:hover {
  background: color-mix(in srgb, var(--c-accent-soft) 28%, transparent);
}
.dual-orig,
.dual-trans {
  min-width: 0;
  font-size: 13px;
  line-height: 1.75;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.dual-orig {
  color: var(--c-text-2);
}
.dual-trans {
  color: var(--read-trans-color, var(--c-text-0));
  font-family: var(--read-ff, system-ui);
  font-size: var(--read-fs, 15px);
  line-height: var(--read-lh, 1.8);
}
.dual-heading-orig,
.dual-heading-trans {
  margin: 5px 0 0;
  font-family: var(--font-serif-zh);
  font-size: 16px;
  line-height: 1.4;
}
.dual-heading-orig {
  color: var(--c-text-2);
  font-weight: 500;
}
.dual-heading-trans {
  color: var(--c-text-0);
  font-weight: 650;
}
.dual-untranslated {
  grid-column: 1 / -1;
  padding: 12px 14px;
  overflow-x: auto;
  border-left: 2px solid var(--c-border-strong);
  background: var(--c-surface-1);
}
.dual-pending {
  display: flex;
  align-items: center;
}
.failed-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  padding: 11px 12px;
  border-left: 3px solid var(--c-danger);
  background: var(--c-danger-bg);
  color: var(--c-danger-fg);
  font-size: 12px;
}
.failed-card > span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-right: auto;
}
.failed-card p {
  flex-basis: 100%;
  margin: 0;
  overflow-wrap: anywhere;
}
.dual-orig :deep(.sent),
.dual-trans :deep(.sent) {
  padding: 1px 2px;
  border-radius: 3px;
  transition:
    background var(--motion-fast),
    box-shadow var(--motion-fast);
}
.dual-orig :deep(.sent:hover),
.dual-trans :deep(.sent:hover),
.dual-orig :deep(.sent-active),
.dual-trans :deep(.sent-active) {
  background: var(--c-accent-soft);
  box-shadow: inset 2px 0 var(--c-accent);
}
.reading-view {
  padding-top: 34px;
}
.prose {
  max-width: 74ch;
  margin: 0 auto;
  color: var(--read-trans-color, var(--c-text-0));
  font-family: var(--read-ff, system-ui);
  font-size: var(--read-fs, 15px);
  line-height: var(--read-lh, 1.8);
}
.prose :deep(h1),
.prose :deep(h2),
.prose :deep(h3) {
  font-family: var(--font-serif-zh);
}
.prose :deep(h1) {
  font-size: 25px;
}
.prose :deep(h2) {
  margin-top: 30px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--c-border);
  font-size: 20px;
}
.prose :deep(pre),
.prose :deep(table) {
  max-width: 100%;
  overflow: auto;
}
button:focus-visible,
summary:focus-visible,
.result-meta button:focus-visible {
  outline: none;
  box-shadow: var(--ring-focus);
}
@media (max-width: 900px) {
  .translation-hero,
  .translation-start {
    width: calc(100% - 40px);
  }
  .translation-hero,
  .workspace-header,
  .result-header {
    padding-left: 24px;
    padding-right: 24px;
  }
  .translation-hero {
    padding-left: 0;
    padding-right: 0;
  }
  .processing-layout {
    grid-template-columns: 250px minmax(0, 1fr);
  }
  .process-panel {
    padding: 24px 20px;
  }
  .live-panel {
    padding: 24px;
  }
  .live-list article {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .result-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .result-search {
    width: 160px;
  }
  .reader-columns {
    padding-left: 28px;
    padding-right: 28px;
  }
  .dual-view,
  .reading-view {
    padding-left: 24px;
    padding-right: 24px;
  }
}
@media (max-width: 720px) {
  .translation-hero {
    padding-top: 34px;
  }
  .drop-zone {
    min-height: 210px;
    grid-template-columns: 1fr;
    justify-items: center;
    text-align: center;
  }
  .format-strip {
    flex-direction: column;
    gap: 8px;
  }
  .processing-layout {
    display: flex;
    overflow-y: auto;
    flex-direction: column;
  }
  .process-panel {
    overflow: visible;
    border-right: 0;
    border-bottom: 1px solid var(--c-border);
  }
  .step-list {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
  .step-list li {
    grid-template-columns: 1fr;
    justify-items: center;
    text-align: center;
  }
  .step-list li:not(:last-child)::after {
    top: 13px;
    bottom: auto;
    left: 50%;
    width: 100%;
    height: 1px;
  }
  .step-list li > div {
    align-items: center;
  }
  .step-list li > div span {
    display: none;
  }
  .live-panel {
    min-height: 320px;
    overflow: visible;
  }
  .result-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .result-actions {
    width: 100%;
    justify-content: flex-start;
  }
  .result-search {
    width: 100%;
  }
  .result-error,
  .quality-panel {
    margin-left: 20px;
    margin-right: 20px;
  }
  .reader-columns {
    display: none;
  }
  .dual-row {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .dual-orig {
    padding-bottom: 10px;
    border-bottom: 1px dashed var(--c-border);
  }
  .dual-untranslated {
    grid-column: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .progress-track i {
    transition: none;
  }
}
</style>
