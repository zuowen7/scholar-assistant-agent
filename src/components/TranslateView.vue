<template>
  <main class="tv-main">

    <!-- ── Ink splash — 文件拖入瞬间溅落 ── -->
    <Transition name="v-splash">
      <div v-if="splashActive" class="ink-splash" aria-hidden="true">
        <span class="splash-ring" />
        <span class="splash-ring splash-ring--2" />
        <span class="splash-ring splash-ring--3" />
        <span class="splash-drop" v-for="i in 16" :key="i" :style="{ '--i': i }" />
      </div>
    </Transition>

    <!-- ── Idle / Error ──────────────────────────────────────── -->
    <div v-if="state.status === 'idle' || state.status === 'error'" class="upload-scene">
      <div class="scene-mesh" aria-hidden="true" />

      <div class="upload-hero">
        <!-- Left: serif hero -->
        <div class="hero-left">
          <!-- Decorative ink brush stroke -->
          <svg class="hero-brushstroke" viewBox="0 0 180 12" aria-hidden="true">
            <path class="brushstroke-path" d="M2 6 C20 2 45 10 70 5 C95 0 120 8 145 4 C160 2 172 8 178 6"
              fill="none" stroke="var(--c-accent)" stroke-width="2.5" stroke-linecap="round" opacity="0.35" />
          </svg>
          <div class="hero-fishtail" aria-hidden="true" />
          <h2 class="hero-title">学术文献翻译</h2>
          <p class="hero-sub">Scholar Translator</p>
        </div>

        <!-- Right: drop-zone card -->
        <div
          class="drop-zone"
          :class="{ hover: zoneHover }"
          role="button"
          tabindex="0"
          aria-label="选择文件"
          @click="openFilePicker"
          @keydown.enter="openFilePicker"
          @dragenter.prevent="zoneHover = true"
          @dragleave="zoneHover = false"
        >
          <!-- Ink bloom SVG background -->
          <div class="dz-bloom" aria-hidden="true">
            <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" class="bloom-svg">
              <defs>
                <radialGradient id="bloom-grad-a" cx="50%" cy="50%" r="50%">
                  <stop offset="0%"   stop-color="#5b6cff" stop-opacity="0.22"/>
                  <stop offset="55%"  stop-color="#5b6cff" stop-opacity="0.10"/>
                  <stop offset="100%" stop-color="#5b6cff" stop-opacity="0"/>
                </radialGradient>
                <radialGradient id="bloom-grad-b" cx="55%" cy="45%" r="50%">
                  <stop offset="0%"   stop-color="#a78bfa" stop-opacity="0.14"/>
                  <stop offset="100%" stop-color="#a78bfa" stop-opacity="0"/>
                </radialGradient>
                <filter id="ink-bloom" x="-30%" y="-30%" width="160%" height="160%">
                  <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="4" seed="5" result="noise" />
                  <feDisplacementMap in="SourceGraphic" in2="noise" scale="38" xChannelSelector="R" yChannelSelector="G" />
                </filter>
              </defs>
              <!-- Soft background glow (no distortion) -->
              <circle cx="100" cy="100" r="88" fill="url(#bloom-grad-a)" />
              <!-- Distorted ink blot — main -->
              <circle cx="100" cy="105" r="60" fill="rgba(91,108,255,0.18)" filter="url(#ink-bloom)" />
              <!-- Purple accent blob -->
              <circle cx="115" cy="82" r="42" fill="url(#bloom-grad-b)" filter="url(#ink-bloom)" />
            </svg>
          </div>
          <!-- Orbiting highlight -->
          <div class="dz-orbit" aria-hidden="true" />

          <!-- Ink drop animation — 墨滴溅落 -->
          <div class="dz-inkdrop" aria-hidden="true">
            <svg viewBox="0 0 24 32" class="inkdrop-svg">
              <defs>
                <filter id="drop-blur" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur stdDeviation="0.4" />
                </filter>
              </defs>
              <!-- Drop body -->
              <path class="inkdrop-shape" d="M12 2 C6 10 4 16 4 20 C4 25.5 7.6 30 12 30 C16.4 30 20 25.5 20 20 C20 16 18 10 12 2Z"
                fill="var(--c-accent)" opacity="0.5" filter="url(#drop-blur)" />
              <!-- Splash ring -->
              <ellipse class="inkdrop-splash" cx="12" cy="28" rx="2" ry="1" fill="none" stroke="var(--c-accent)" stroke-width="1.5" opacity="0" />
            </svg>
          </div>

          <div class="dz-icon-wrap">
            <UploadCloud :size="28" :stroke-width="1.4" class="dz-icon" />
          </div>
          <span class="dz-label">点击选择文件</span>
          <span class="dz-hint">或将文件拖入窗口任意位置</span>
        </div>
      </div>

      <!-- Format chips -->
      <div class="format-row">
        <span v-for="fmt in formatList" :key="fmt" class="fmt-chip">{{ fmt }}</span>
      </div>

      <!-- Error banner -->
      <div v-if="state.status === 'error' && state.errorMessage" class="error-banner">
        <AlertCircle :size="14" :stroke-width="2" />
        <span class="error-text">{{ state.errorMessage }}</span>
        <UiButton v-if="!healthOk" variant="danger" size="sm" @click="$emit('restart-backend')">重启后端</UiButton>
      </div>
    </div>

    <!-- ── Working ────────────────────────────────────────────── -->
    <div v-else-if="state.status !== 'done'" class="work-scene">
      <div class="work-card">

        <!-- Step strip -->
        <div class="stepper">
          <div
            v-for="(label, idx) in stepLabels"
            :key="idx"
            class="step"
            :class="{
              done: idx + 1 < state.currentStep,
              active: idx + 1 === state.currentStep,
            }"
          >
            <div class="step-connector" v-if="idx > 0" />
            <div class="step-dot-wrap">
              <div class="step-dot">
                <Check v-if="idx + 1 < state.currentStep" :size="11" :stroke-width="3" />
                <span v-else>{{ idx + 1 }}</span>
              </div>
            </div>
            <span class="step-label">{{ label }}</span>
          </div>
        </div>

        <!-- Progress -->
        <div class="progress-area">
          <div class="progress-meta">
            <span class="progress-msg">{{ state.stepMessage || '准备中…' }}</span>
            <span class="progress-pct">{{ progress }}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: progress + '%' }" />
          </div>
        </div>

        <!-- Chunk sub-progress -->
        <div v-if="state.currentStep === 4 && state.totalChunks > 0" class="chunk-bar">
          <div class="chunk-track">
            <div class="chunk-fill" :style="{ width: `${(state.completedChunks / state.totalChunks) * 100}%` }" />
          </div>
          <span class="chunk-label">{{ state.completedChunks }} / {{ state.totalChunks }} 块</span>
        </div>

        <!-- Parsed info tags -->
        <div v-if="state.parsedInfo" class="info-chips">
          <span class="info-chip">{{ state.parsedInfo.pages }} 页</span>
          <span class="info-chip">{{ state.parsedInfo.chars.toLocaleString() }} 字符</span>
          <span v-if="state.parsedInfo.dual_column_pages" class="info-chip accent">{{ state.parsedInfo.dual_column_pages }} 页双栏</span>
        </div>
      </div>

      <!-- Live preview -->
      <TransitionGroup v-if="state.blocks.filter(b => b.translated).length > 0" name="live-slide" tag="div" class="live-preview">
        <div
          v-for="b in state.blocks.filter(b => b.translated && b.translatable).slice(-3)"
          :key="b.id"
          class="live-item"
        >
          <p class="live-orig">{{ b.original.substring(0, 200) }}{{ b.original.length > 200 ? '...' : '' }}</p>
          <p class="live-trans">{{ b.translated.substring(0, 200) }}{{ b.translated.length > 200 ? '...' : '' }}</p>
        </div>
      </TransitionGroup>
    </div>

    <!-- ── Done ───────────────────────────────────────────────── -->
    <div v-else class="done-wrapper">
      <!-- 卷轴滚轴 — 上下两根装饰条 -->
      <div class="scroll-roller scroll-roller--top" aria-hidden="true">
        <div class="roller-knob roller-knob--left" />
        <div class="roller-body" />
        <div class="roller-knob roller-knob--right" />
      </div>

      <!-- 墨粒子爆发 — 翻译完成时从中心四散 -->
      <div class="ink-burst" :class="{ 'ink-burst--active': burstPhase }" aria-hidden="true">
        <span class="burst-dot" v-for="i in 20" :key="i" :style="{ '--i': i }" />
      </div>

      <!-- Seal 印章 -->
      <Transition name="v-stamp">
        <div v-if="sealVisible" class="done-seal" aria-hidden="true">
          <svg viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg" class="seal-svg">
            <defs>
              <filter id="stamp-rough" x="-5%" y="-5%" width="110%" height="110%">
                <feTurbulence type="fractalNoise" baseFrequency="0.065" numOctaves="3" seed="8" result="noise"/>
                <feDisplacementMap in="SourceGraphic" in2="noise" scale="1.2" xChannelSelector="R" yChannelSelector="G"/>
              </filter>
            </defs>
            <rect x="2" y="2" width="52" height="52" rx="3" fill="var(--vermilion-0)" filter="url(#stamp-rough)"/>
            <rect x="3.5" y="3.5" width="49" height="49" rx="2.5" fill="none" stroke="#fff" stroke-width="1.5" stroke-opacity="0.55"/>
            <rect x="7" y="7" width="42" height="42" rx="1.5" fill="none" stroke="#fff" stroke-width="0.8" stroke-opacity="0.35"/>
            <line x1="10" y1="28" x2="46" y2="28" stroke="#fff" stroke-width="0.7" stroke-opacity="0.3"/>
            <text x="28" y="19.5" text-anchor="middle" dominant-baseline="middle" fill="#fff" fill-opacity="0.95" font-family="var(--font-serif-zh)" font-size="15" font-weight="700" letter-spacing="0.5">研</text>
            <text x="28" y="36.5" text-anchor="middle" dominant-baseline="middle" fill="#fff" fill-opacity="0.95" font-family="var(--font-serif-zh)" font-size="15" font-weight="700" letter-spacing="0.5">墨</text>
          </svg>
        </div>
      </Transition>

      <div class="result-scene" :class="{ unfurling }" :style="readStyleVars">

      <!-- Result action bar -->
      <div class="result-bar">
        <div class="result-bar-left">
          <div class="done-title-group">
            <span class="done-label">翻译完成</span>
            <span v-if="state.blocks.length" class="done-meta">
              {{ state.blocks.length }} 块 · {{ paragraphCount }} 段
            </span>
          </div>
          <span v-if="state.misalignedChunks > 0" class="warn-tag">{{ state.misalignedChunks }} 块对齐回退</span>
          <span v-if="state.ragIngested" class="done-rag-hint" @click="$emit('open-agent-docs')">已加入知识库</span>
        </div>
        <div class="result-bar-right">
          <UiSegmented
            v-model="viewMode"
            :options="viewOptions"
            size="sm"
          />
          <div class="bar-sep" />
          <UiDropdown :items="exportMenuItems" align="end">
            <template #trigger>
              <UiButton variant="primary" size="sm">
                <template #icon-left><Download :size="13" :stroke-width="2" /></template>
                导出
                <template #icon-right><ChevronDown :size="13" :stroke-width="2" /></template>
              </UiButton>
            </template>
          </UiDropdown>
          <UiButton variant="ghost" size="sm" @click="reset">新翻译</UiButton>
        </div>
      </div>

      <!-- Export error banner -->
      <div v-if="state.errorMessage" class="export-error-banner">
        <AlertCircle :size="14" :stroke-width="2" />
        <span class="error-text">{{ state.errorMessage }}</span>
      </div>

      <!-- ── 对照视图：左右双栏按块对齐 ── -->
      <Transition name="v-fade" mode="out-in">
        <div v-if="viewMode === 'bilingual'" key="bilingual" class="dual-view">
          <div
            v-for="(b, i) in renderableBlocks"
            :key="b.id"
            class="dual-row"
            :class="['type-' + b.type]"
          >
            <!-- 标题：跨栏 -->
            <template v-if="b.type === 'heading'">
              <component :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`" class="dual-heading-orig">{{ stripHeadingMark(b.original) }}</component>
              <component v-if="b.translated" :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`" class="dual-heading-trans">{{ stripHeadingMark(b.translated) }}</component>
            </template>
            <!-- 公式/代码/表格：跨栏单列居中 -->
            <div v-else-if="!b.translatable" class="dual-untranslated" v-html="renderBlock(b.original, b.type)" />
            <!-- 翻译失败：跨栏红色卡片 -->
            <div v-else-if="b.status === 'failed'" class="dual-failed">
              <div class="dual-orig" v-html="renderBlock(b.original, b.type)" />
              <div class="failed-card">
                <AlertCircle :size="14" :stroke-width="2" />
                <span>翻译失败</span>
                <UiButton
                  v-if="!retryingBlockIds.has(b.id)"
                  variant="secondary"
                  size="sm"
                  @click="retryFailedBlock(b.id)"
                >
                  重试
                </UiButton>
                <span v-else class="retrying">重试中…</span>
              </div>
            </div>
            <!-- 普通段落：左原 / 右译 -->
            <template v-else>
              <div
                class="dual-orig"
                v-html="renderSentenceMarked(b.original, 'en', b.id, 'orig')"
                @mouseover="handleSentenceMouseEnter"
                @mouseleave="clearSentHover()"
              />
              <div v-if="b.translated"
                class="dual-trans"
                v-html="renderSentenceMarked(b.translated, 'zh', b.id, 'trans')"
                @mouseover="handleSentenceMouseEnter"
                @mouseleave="clearSentHover()"
              />
              <div v-else class="dual-pending">翻译中…</div>
            </template>
          </div>
        </div>

        <!-- ── 译文视图：纯译文阅读模式 ── -->
        <div v-else key="translation" class="reading-view">
          <article class="prose" v-html="translationOnlyHtml" />
        </div>
      </Transition>
      </div><!-- /result-scene -->

      <!-- 底部卷轴滚轴 -->
      <div class="scroll-roller scroll-roller--bottom" aria-hidden="true">
        <div class="roller-knob roller-knob--left" />
        <div class="roller-body" />
        <div class="roller-knob roller-knob--right" />
      </div>
    </div><!-- /done-wrapper -->
  </main>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, toRaw } from 'vue'
import { UploadCloud, AlertCircle, Check, Download, FileText, ChevronDown } from './ui/icons'
import UiButton from './ui/UiButton.vue'
import UiSegmented from './ui/UiSegmented.vue'
import UiDropdown from './ui/UiDropdown.vue'
import { API_BASE } from '../utils/api'
import { useTranslate } from '../composables/useTranslate'
import { renderMarkdown, renderBlock } from '../utils/markdown'
import { findCorrespondingSentenceIdx, splitSentences, type Sentence } from '../utils/sentenceAlign'
import type { DropdownItem } from './ui/UiDropdown.vue'

const props = defineProps<{
  healthOk: boolean
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
}>()

defineEmits<{
  (e: 'restart-backend'): void
  (e: 'open-agent-docs'): void
}>()

const { state, translate, reset, downloadResult, overallProgress, exportBilingualDocx, exportTranslationOnlyDocx, exportTranslationOnlyMarkdown } = useTranslate()

const viewMode = ref<'bilingual' | 'translation'>('bilingual')
const zoneHover = ref(false)
const retryingBlockIds = ref<Set<string>>(new Set())
const sealVisible = ref(false)
const unfurling = ref(false)
const burstPhase = ref(false)
const splashActive = ref(false)

// 文件拖入溅落 — idle → uploading 瞬间触发
watch(() => state.status, (newStatus, oldStatus) => {
  if ((newStatus === 'uploading' || newStatus === 'parsing') && oldStatus === 'idle') {
    splashActive.value = true
    setTimeout(() => { splashActive.value = false }, 750)
  }
})

// 卷轴展开 + 印章 + 墨粒子爆发 — 多阶段动画序列
watch(() => state.status, (newStatus, oldStatus) => {
  if (newStatus === 'done' && oldStatus !== 'done') {
    burstPhase.value = false
    unfurling.value = true
    sealVisible.value = false
    // 阶段1: 卷轴展开 ~600ms
    // 阶段2: 印章落下 (在卷轴展开中途开始)
    setTimeout(() => { sealVisible.value = true }, 400)
    // 阶段3: 墨粒子爆发 (印章落下后)
    setTimeout(() => { burstPhase.value = true }, 750)
    // 清理
    setTimeout(() => { unfurling.value = false }, 800)
  }
})

onMounted(() => {
  if (state.status === 'done') {
    sealVisible.value = true
  }
})

async function retryFailedBlock(blockId: string) {
  if (!state.taskId) return

  retryingBlockIds.value.add(blockId)

  try {
    const resp = await fetch(`${API_BASE}/api/translate/${state.taskId}/retry_block`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: blockId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '重试失败' }))
      throw new Error(err.detail || '重试失败')
    }

    const result = await resp.json()

    // toRaw unwraps readonly() for intentional mutation of reactive state
    const s = toRaw(state) as any
    const idx = s.blocks.findIndex((b: any) => b.id === blockId)
    if (idx !== -1) {
      s.blocks[idx].translated = result.translated
      s.blocks[idx].status = result.status
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    console.error('重试块翻译失败:', msg)
  } finally {
    retryingBlockIds.value.delete(blockId)
  }
}

const exportMenuItems = computed<DropdownItem[]>(() => [
  {
    text: '双语 Markdown',
    icon: FileText,
    onClick: () => downloadResult(),
  },
  {
    text: '双语 Word',
    icon: FileText,
    onClick: () => doExportBilingualDocx(),
  },
  {
    text: '仅译文 Markdown',
    icon: FileText,
    onClick: () => exportTranslationOnlyMarkdown(),
  },
  {
    text: '仅译文 Word',
    icon: FileText,
    onClick: () => exportTranslationOnlyDocx(),
  },
])

interface HoveredPair {
  blockId: string
  origIdx: number
  transIdx: number
}
const hoveredPair = ref<HoveredPair | null>(null)

async function doExportBilingualDocx() {
  try {
    await exportBilingualDocx()
  } catch (err) {
    console.error('Bilingual PDF export failed:', err)
  }
}

const stepLabels = ['解析文档', '清洗文本', '智能分块', '翻译', '格式化']
const formatList = ['PDF', 'Word', 'PPT', 'Excel', 'TXT', 'Markdown', 'HTML', 'EPUB', 'LaTeX', 'JSON', '…']

const viewOptions = [
  { value: 'bilingual' as const, label: '对照' },
  { value: 'translation' as const, label: '译文' },
]

const progress = computed(() => overallProgress())

const readStyleVars = computed(() => {
  const vars: Record<string, string | number> = {
    '--read-fs': `${props.readSettings.fontSize}px`,
    '--read-lh': props.readSettings.lineHeight,
    '--read-ff': props.readSettings.fontFamily,
  }
  if (props.readSettings.transColor) {
    vars['--read-trans-color'] = props.readSettings.transColor
  }
  return vars
})

const renderableBlocks = computed(() => state.blocks)

const translationOnlyHtml = computed(() => {
  const parts: string[] = []
  for (const b of state.blocks) {
    if (b.status === 'failed') continue
    if (!b.translatable) {
      parts.push(b.original)
    } else if (b.translated) {
      parts.push(b.type === 'heading' ? `${'#'.repeat(Math.min(Math.max(b.level || 2, 1), 6))} ${stripHeadingMark(b.translated)}` : b.translated)
    }
  }
  return renderMarkdown(parts.join('\n\n'))
})

function stripHeadingMark(s: string): string {
  return s.replace(/^#{1,6}\s+/, '').trim()
}

function onSentHover(blockId: string, sentIdx: number, side: 'orig' | 'trans') {
  const block = state.blocks.find(b => b.id === blockId)
  if (!block || !block.translated) return

  const lang = side === 'orig' ? 'en' : 'zh'
  const text = side === 'orig' ? block.original : block.translated
  const otherText = side === 'orig' ? block.translated : block.original

  const sentences = splitSentences(text, lang)
  const otherSentences = splitSentences(otherText, lang === 'en' ? 'zh' : 'en')

  if (sentIdx < 0 || sentIdx >= sentences.length) return

  const otherIdx = findCorrespondingSentenceIdx(
    sentences,
    text.length,
    otherSentences,
    otherText.length,
    sentIdx,
  )

  hoveredPair.value = {
    blockId,
    origIdx: side === 'orig' ? sentIdx : otherIdx,
    transIdx: side === 'orig' ? otherIdx : sentIdx,
  }
}

function clearSentHover() {
  hoveredPair.value = null
}

function renderSentenceMarked(text: string, lang: 'en' | 'zh', blockId: string, side: 'orig' | 'trans'): string {
  const sentences = splitSentences(text, lang)
  if (sentences.length <= 1) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  const parts = sentences.map((sent, idx) => {
    const escaped = sent.text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    return `<span data-sent-idx="${idx}" data-block-id="${blockId}" data-side="${side}" class="sent">${escaped}</span>`
  })

  return parts.join(' ')
}

function handleSentenceMouseEnter(e: MouseEvent) {
  const target = e.target as HTMLElement
  const sentIdxStr = target.getAttribute('data-sent-idx')
  const blockId = target.getAttribute('data-block-id')
  const side = target.getAttribute('data-side') as 'orig' | 'trans' | null

  if (sentIdxStr === null || blockId === null || side === null) return

  const sentIdx = parseInt(sentIdxStr, 10)
  onSentHover(blockId, sentIdx, side)
  updateSentenceHighlight(blockId, side, sentIdx)
}

function updateSentenceHighlight(blockId: string, side: 'orig' | 'trans', sentIdx: number) {
  document.querySelectorAll('.sent-active').forEach(el => {
    el.classList.remove('sent-active')
  })

  const block = state.blocks.find(b => b.id === blockId)
  if (!block || !block.translated) return

  const otherSide = side === 'orig' ? 'trans' : 'orig'
  const lang = side === 'orig' ? 'en' : 'zh'
  const otherLang = side === 'orig' ? 'zh' : 'en'

  const text = side === 'orig' ? block.original : block.translated
  const otherText = side === 'orig' ? block.translated : block.original

  const sentences = splitSentences(text, lang)
  const otherSentences = splitSentences(otherText, otherLang)

  const otherIdx = findCorrespondingSentenceIdx(
    sentences,
    text.length,
    otherSentences,
    otherText.length,
    sentIdx,
  )

  const origSentSelector = `.dual-orig [data-block-id="${blockId}"][data-side="orig"][data-sent-idx="${sentIdx}"]`
  const origSentEl = document.querySelector(origSentSelector)
  if (origSentEl) origSentEl.classList.add('sent-active')

  const transSentSelector = `.dual-trans [data-block-id="${blockId}"][data-side="trans"][data-sent-idx="${otherIdx}"]`
  const transSentEl = document.querySelector(transSentSelector)
  if (transSentEl) transSentEl.classList.add('sent-active')
}

function handleSentenceClick(e: MouseEvent) {
  // reserved
}

const paragraphCount = computed(() =>
  state.blocks.filter(b => b.type === 'paragraph').length
)

function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.docx,.doc,.txt,.md,.log,.html,.htm,.epub,.rtf,.tex,.csv,.pptx,.xlsx,.srt,.json,.xml'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) translate(file)
  }
  input.click()
}
</script>

<style scoped>
/* ── Layout ───────────────────────────────────────────────── */
.tv-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

/* ══════════════════════════════════════════════════════════
   INK SPLASH — 文件拖入瞬间墨滴溅落
═══════════════════════════════════════════════════════════ */
.ink-splash {
  position: fixed;
  inset: 0;
  z-index: 500;
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 溅落涟漪 — 3 层同心环逐层扩散 */
.splash-ring {
  position: absolute;
  width: 0;
  height: 0;
  border-radius: 50%;
  border: 3px solid var(--c-accent);
  opacity: 0;
  animation: splash-ripple 700ms var(--ease-brush) forwards;
}
.splash-ring--2 { animation-delay: 60ms; }
.splash-ring--3 { animation-delay: 130ms; }
@keyframes splash-ripple {
  0%   { width: 0; height: 0; opacity: 0.7; border-width: 3px; }
  60%  { opacity: 0.25; }
  100% { width: 600px; height: 600px; opacity: 0; border-width: 0.5px; }
}

/* 溅落飞沫 — 16 颗墨滴沿径向飞出 */
.splash-drop {
  --angle: calc(var(--i, 1) * 22.5deg);
  --dist: calc(40px + var(--i, 1) * 16px);
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-accent);
  opacity: 0;
  animation: splash-droplet 650ms var(--ease-brush) forwards;
  animation-delay: calc(var(--i, 1) * 22ms);
}
@keyframes splash-droplet {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0);
  }
  15% { opacity: 0.8; }
  100% {
    opacity: 0;
    transform:
      translate(
        calc(-50% + cos(var(--angle)) * var(--dist)),
        calc(-50% + sin(var(--angle)) * var(--dist))
      )
      scale(0.3);
  }
}

/* 溅落进出场过渡 */
.v-splash-enter-active { animation: splash-in 120ms var(--ease-brush); }
.v-splash-leave-active { animation: splash-out 500ms var(--ease-out); }
@keyframes splash-in  { from { opacity: 0; } to { opacity: 1; } }
@keyframes splash-out { from { opacity: 1; } to { opacity: 0; } }

/* ══════════════════════════════════════════════════════════
   UPLOAD / IDLE — asymmetric two-column
═══════════════════════════════════════════════════════════ */
.upload-scene {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.scene-mesh {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 60% 50% at 30% 60%, rgba(91,108,255,0.06) 0%, transparent 70%),
    radial-gradient(ellipse 50% 40% at 75% 35%, rgba(167,139,250,0.04) 0%, transparent 65%);
}

.upload-hero {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-8);
  width: 100%;
  max-width: 720px;
  padding: var(--space-7) var(--space-4);
}

/* ── Hero left: serif title with fishtail accent ── */
.hero-left {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex-shrink: 0;
  padding-left: var(--space-5);
}

/* Ink brush stroke decoration above title */
.hero-brushstroke {
  position: absolute;
  top: -14px;
  left: 14px;
  width: 140px;
  height: 14px;
  overflow: visible;
  pointer-events: none;
}
.brushstroke-path {
  stroke-dasharray: 180;
  stroke-dashoffset: 180;
  animation: brush-draw 1s var(--ease-brush) forwards;
  animation-delay: 0.2s;
}
@keyframes brush-draw {
  to { stroke-dashoffset: 0; }
}

.hero-fishtail {
  position: absolute;
  left: 0;
  top: 4px;
  width: 4px;
  height: 32px;
  background: var(--vermilion-0);
  border-radius: 2px;
}

.hero-title {
  font-family: var(--font-serif-zh);
  font-size: var(--text-display-lg);
  font-weight: 700;
  color: var(--c-text-0);
  letter-spacing: var(--tracking-display);
  line-height: var(--leading-display);
  margin: 0;
  text-shadow:
    0 0 40px rgba(91, 108, 255, 0.18),
    0 2px 4px rgba(0, 0, 0, 0.4);
}

.hero-sub {
  font-family: var(--font-serif);
  font-size: 20px;
  font-style: italic;
  font-weight: 400;
  color: var(--c-text-3);
  margin: 0;
  letter-spacing: var(--tracking-tight);
}

/* ── Drop zone: glass card with ink bloom ── */
.drop-zone {
  position: relative;
  flex: 1;
  min-width: 280px;
  padding: var(--space-6) var(--space-5);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  background: var(--c-glass);
  border: 1.5px dashed color-mix(in srgb, var(--accent-0) 40%, transparent);
  border-radius: var(--radius-card);
  cursor: pointer;
  outline: none;
  overflow: hidden;
  transition:
    border-color var(--motion-base) var(--ease-out),
    background var(--motion-base) var(--ease-out),
    box-shadow var(--motion-base) var(--ease-out),
    transform var(--motion-base) var(--ease-out);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.drop-zone:hover,
.drop-zone.hover {
  border-color: var(--accent-0);
  background: var(--c-accent-soft);
  box-shadow: 0 24px 48px var(--accent-glow), 0 1px 0 var(--accent-1) inset;
  transform: translateY(-2px);
}
.drop-zone:hover .dz-icon,
.drop-zone.hover .dz-icon { color: var(--accent-1); }

/* Ink bloom SVG */
.dz-bloom {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.6;
  transition: opacity var(--motion-slow);
}
.drop-zone:hover .dz-bloom,
.drop-zone.hover .dz-bloom { opacity: 1; }

.bloom-svg {
  width: 100%;
  height: 100%;
  animation: bloom-drift 18s ease-in-out infinite alternate;
}
.drop-zone:hover .bloom-svg,
.drop-zone.hover .bloom-svg { animation-duration: 6s; }

@keyframes bloom-drift {
  0%   { transform: scale(1) rotate(0deg); }
  100% { transform: scale(1.15) rotate(8deg); }
}

/* Orbiting border highlight */
.dz-orbit {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-card);
  pointer-events: none;
  background: conic-gradient(from var(--orbit-angle, 0deg),
    transparent 0%,
    transparent 85%,
    var(--accent-1) 94%,
    var(--accent-0) 98%,
    transparent 100%
  );
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  padding: 2px;
  animation: orbit 10s linear infinite;
  opacity: 0.7;
}
.drop-zone:hover .dz-orbit,
.drop-zone.hover .dz-orbit { opacity: 1; }

@keyframes orbit {
  from { --orbit-angle: 0deg; }
  to   { --orbit-angle: 360deg; }
}

/* ── Ink drop animation: 墨滴溅落 ── */
.dz-inkdrop {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  width: 28px;
  height: 36px;
  z-index: 2;
  pointer-events: none;
  opacity: 0;
}
.inkdrop-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}
.inkdrop-shape {
  transform-origin: center bottom;
}
.inkdrop-splash {
  transform-origin: center;
}

/* Trigger on drop-zone hover */
.drop-zone:hover .dz-inkdrop,
.drop-zone.hover .dz-inkdrop {
  animation: inkdrop-fall 2.4s var(--ease-brush) infinite;
}
.drop-zone:hover .inkdrop-shape,
.drop-zone.hover .inkdrop-shape {
  animation: inkdrop-squish 2.4s var(--ease-brush) infinite;
}
.drop-zone:hover .inkdrop-splash,
.drop-zone.hover .inkdrop-splash {
  animation: inkdrop-ring 2.4s var(--ease-brush) infinite;
}

@keyframes inkdrop-fall {
  0%    { opacity: 0; transform: translateX(-50%) translateY(-10px); }
  10%   { opacity: 0.7; }
  35%   { opacity: 0.85; transform: translateX(-50%) translateY(32px); }
  40%   { opacity: 0; transform: translateX(-50%) translateY(32px); }
  100%  { opacity: 0; transform: translateX(-50%) translateY(-10px); }
}
@keyframes inkdrop-squish {
  0%, 35% { transform: scaleY(1) scaleX(1); }
  38%     { transform: scaleY(0.4) scaleX(1.5); }
  45%     { transform: scaleY(0.25) scaleX(2); }
  55%     { transform: scaleY(0.15) scaleX(2.5); opacity: 0.4; }
  70%     { transform: scaleY(1) scaleX(1); opacity: 0.5; }
  100%    { transform: scaleY(1) scaleX(1); }
}
@keyframes inkdrop-ring {
  0%, 39% { opacity: 0; transform: scale(0.3); }
  42%     { opacity: 0.5; transform: scale(0.6); }
  55%     { opacity: 0; transform: scale(3); }
  100%    { opacity: 0; transform: scale(0.3); }
}

/* Register custom property for orbit animation */
@property --orbit-angle {
  syntax: '<angle>';
  inherits: false;
  initial-value: 0deg;
}

.dz-icon-wrap {
  position: relative;
  z-index: 1;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 1.5px solid var(--c-surface-3);
  background: var(--c-surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color var(--motion-base) var(--ease-out),
              background var(--motion-base) var(--ease-out);
}
.drop-zone:hover .dz-icon-wrap,
.drop-zone.hover .dz-icon-wrap {
  border-color: var(--accent-0);
  background: var(--c-accent-soft);
}
.dz-icon {
  color: var(--c-text-3);
  transition: color var(--motion-base) var(--ease-out);
}
.dz-label {
  position: relative;
  z-index: 1;
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--c-text-0);
}
.dz-hint {
  position: relative;
  z-index: 1;
  font-size: var(--text-sm);
  color: var(--c-text-3);
}

/* Format chips */
.format-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-1);
  margin-top: var(--space-4);
  max-width: 720px;
  padding: 0 var(--space-4);
  font-feature-settings: "tnum";
}
.fmt-chip {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  font-size: var(--text-xs);
  color: var(--c-text-3);
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  max-width: 720px;
  padding: var(--space-3) var(--space-4);
  margin-top: var(--space-3);
  background: var(--c-danger-bg);
  border: 1px solid var(--c-danger-border);
  border-radius: var(--radius-lg);
  color: var(--c-danger);
}
.error-text { flex: 1; font-size: var(--text-sm); min-width: 0; }
.export-error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  margin: var(--space-2) 0;
  background: var(--c-danger-bg);
  border: 1px solid var(--c-danger-border);
  border-radius: var(--radius-md);
  color: var(--c-danger);
  font-size: var(--text-sm);
}

/* ══════════════════════════════════════════════════════════
   WORKING
══════════════════════════════════════════════════════════ */
.work-scene {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-7) var(--space-4) var(--space-4);
  gap: var(--space-4);
  overflow-y: auto;
}

.work-card {
  width: 100%;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-card);
  padding: var(--space-5);
  box-shadow: var(--elevation-2);
}

/* Stepper */
.stepper {
  display: flex;
  align-items: flex-start;
}
.step {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  position: relative;
}

.step-connector {
  position: absolute;
  top: 15px;
  right: 50%;
  width: 100%;
  height: 1px;
  background: var(--c-surface-3);
  z-index: 0;
  transition: background var(--motion-slow) var(--ease-out);
}
.step.done .step-connector,
.step.active .step-connector { background: var(--c-accent); }

.step-dot-wrap { position: relative; z-index: 1; }
.step-dot {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1.5px solid var(--c-surface-3);
  background: var(--c-surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--c-text-3);
  transition:
    border-color var(--motion-base) var(--ease-out),
    background var(--motion-base) var(--ease-out),
    color var(--motion-base) var(--ease-out);
}
.step.done .step-dot {
  border-color: var(--c-success);
  background: var(--c-success-bg);
  color: var(--c-success);
  animation: step-done-pop 400ms var(--ease-spring);
}
@keyframes step-done-pop {
  0%   { transform: scale(0.85); }
  60%  { transform: scale(1.15); }
  100% { transform: scale(1); }
}
.step.active .step-dot {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
  color: var(--c-accent-hover);
  box-shadow: 0 0 0 4px var(--c-accent-ring);
  animation: step-pulse 1.8s ease-in-out infinite;
}
/* 墨晕扩散 — 当前步骤的背景光晕 */
.step.active .step-dot::before {
  content: '';
  position: absolute;
  inset: -10px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--c-accent) 0%, transparent 70%);
  opacity: 0;
  animation: step-ink-bloom 2.2s ease-in-out infinite;
  pointer-events: none;
  z-index: -1;
}
@keyframes step-ink-bloom {
  0%, 100% { opacity: 0; transform: scale(0.6); }
  50%      { opacity: 0.08; transform: scale(1.3); }
}
@keyframes step-pulse {
  0%, 100% { box-shadow: 0 0 0 3px var(--c-accent-ring); }
  50% { box-shadow: 0 0 0 6px transparent; }
}

.step-label {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  text-align: center;
  transition: color var(--motion-base) var(--ease-out);
}
.step.done .step-label { color: var(--c-success); }
.step.active .step-label { color: var(--c-accent-hover); font-weight: 600; }

/* Progress */
.progress-area { display: flex; flex-direction: column; gap: var(--space-2); }
.progress-meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.progress-msg { font-size: var(--text-sm); color: var(--c-text-1); font-weight: 500; }
.progress-pct { font-size: var(--text-md); color: var(--c-accent-hover); font-weight: 700; font-variant-numeric: tabular-nums; }

.progress-track {
  height: 6px;
  background: var(--c-surface-2);
  border-radius: var(--radius-pill);
  position: relative;
  overflow: visible;
}
.progress-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  /* 墨渗透渐变 — 左（已干，略深）→ 右（湿墨，亮） */
  background:
    linear-gradient(90deg,
      rgba(91, 108, 255, 0.55) 0%,
      rgba(91, 108, 255, 0.7) 60%,
      rgba(120, 140, 255, 0.9) 85%,
      rgba(160, 175, 255, 0.95) 100%
    );
  transition: width 0.45s var(--ease-brush);
  position: relative;
  box-shadow:
    0 0 10px rgba(91, 108, 255, 0.25),  /* 湿墨光晕 */
    inset 0 1px 0 rgba(255, 255, 255, 0.12);  /* 表面张力高光 */
}

/* Leading edge wet ink glow — 笔锋湿墨光点 */
.progress-fill::before {
  content: '';
  position: absolute;
  right: 0;
  top: 50%;
  transform: translate(50%, -50%);
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(91, 108, 255, 0.35) 0%, transparent 70%);
  filter: blur(3px);
  animation: wet-edge-breathe 1.2s ease-in-out infinite;
}
@keyframes wet-edge-breathe {
  0%, 100% { opacity: 0.5; transform: translate(50%, -50%) scale(0.9); }
  50%      { opacity: 1; transform: translate(50%, -50%) scale(1.2); }
}

/* Shimmer — 宣纸吸墨渗化，非机械扫描 */
.progress-fill::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background:
    linear-gradient(105deg,
      transparent 0%,
      transparent 30%,
      rgba(255, 255, 255, 0.08) 45%,
      rgba(255, 255, 255, 0.16) 50%,
      rgba(255, 255, 255, 0.08) 55%,
      transparent 70%,
      transparent 100%
    );
  background-size: 250% 100%;
  animation: ink-seep 2.4s ease-in-out infinite;
}
@keyframes ink-seep {
  from { background-position: 250% 0; }
  to   { background-position: -250% 0; }
}

/* Chunk sub-progress */
.chunk-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.chunk-track {
  flex: 1;
  height: 3px;
  background: var(--c-surface-2);
  border-radius: var(--radius-pill);
  overflow: hidden;
}
.chunk-fill {
  height: 100%;
  background: var(--c-success);
  border-radius: var(--radius-pill);
  transition: width 0.3s var(--ease-out);
}
.chunk-label { font-size: var(--text-xs); color: var(--c-text-3); white-space: nowrap; font-variant-numeric: tabular-nums; }

/* Info chips */
.info-chips { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.info-chip {
  padding: 2px 10px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-pill);
  font-size: var(--text-xs);
  color: var(--c-text-2);
}
.info-chip.accent { background: var(--c-accent-bg); border-color: transparent; color: var(--c-accent-hover); }

/* Live preview — stack-card */
.live-preview {
  width: 100%;
  max-width: 560px;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.live-item {
  padding: var(--space-3) var(--space-4);
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-left: 3px solid var(--c-accent);
  border-radius: var(--radius-md);
  transition: transform var(--motion-base) var(--ease-out),
              opacity var(--motion-base) var(--ease-out);
}
.live-item:not(:last-child) {
  transform: scale(0.98);
  opacity: 0.7;
}
.live-orig {
  font-size: var(--text-sm);
  color: var(--c-text-3);
  line-height: var(--leading-normal);
  margin-bottom: var(--space-1);
}
.live-trans {
  font-size: var(--text-md);
  color: var(--c-text-0);
  line-height: var(--leading-relaxed);
}

/* Live slide transitions */
.live-slide-enter-active { transition: all var(--motion-base) var(--ease-out); }
.live-slide-enter-from { opacity: 0; transform: translateY(8px); }

/* ══════════════════════════════════════════════════════════
   DONE / RESULT — signature moment
   Stage: flash → scroll unfurl → seal → ink burst
══════════════════════════════════════════════════════════ */
.done-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  position: relative;
  overflow: hidden;
}

/* ── Scroll rollers — 卷轴上下木轴装饰 ── */
.scroll-roller {
  position: relative;
  z-index: 15;
  display: flex;
  align-items: center;
  height: 10px;
  margin: 0 var(--space-5);
  opacity: 0;
  animation: roller-slide-in 500ms var(--ease-emphasis) forwards;
}
.scroll-roller--top    { animation-delay: 0ms; }
.scroll-roller--bottom { animation-delay: 120ms; }

@keyframes roller-slide-in {
  from { opacity: 0; transform: scaleX(0.3); }
  to   { opacity: 1; transform: scaleX(1); }
}

.roller-body {
  flex: 1;
  height: 4px;
  background: linear-gradient(to bottom, var(--c-surface-4), var(--c-surface-3) 40%, var(--c-surface-4));
  border-radius: 2px;
}

.roller-knob {
  width: 14px;
  height: 10px;
  background: linear-gradient(to bottom, var(--c-surface-3), var(--c-surface-4));
  border-radius: 3px;
  flex-shrink: 0;
}
.roller-knob--left  { margin-right: 4px; }
.roller-knob--right { margin-left: 4px; }

/* ── Seal — 印章定位 ── */
.done-wrapper .done-seal {
  position: absolute;
  top: 24px;
  right: 28px;
  z-index: 20;
  pointer-events: none;
}

/* ── Result scene — 卷轴展开 ── */
.result-scene {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 0 var(--space-5) var(--space-5);
}
.result-scene.unfurling {
  animation: scroll-unfurl 700ms var(--ease-emphasis);
}
@keyframes scroll-unfurl {
  from {
    clip-path: inset(48% 0 48% 0);
    opacity: 0;
  }
  to {
    clip-path: inset(0 0 0 0);
    opacity: 1;
  }
}

/* ── Ink burst — 墨粒子爆发，从中心四散 ── */
.ink-burst {
  position: absolute;
  inset: 0;
  z-index: 10;
  pointer-events: none;
  overflow: hidden;
}
.burst-dot {
  --angle: calc(var(--i, 1) * 18deg);
  --dist: calc(60px + var(--i, 1) * 22px);
  position: absolute;
  top: 50%;
  left: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--c-accent);
  opacity: 0;
}
.ink-burst--active .burst-dot {
  animation: burst-fly 900ms var(--ease-brush) forwards;
  animation-delay: calc(var(--i, 1) * 18ms);
}
@keyframes burst-fly {
  0% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(0);
  }
  8% {
    opacity: 0.8;
  }
  100% {
    opacity: 0;
    transform:
      translate(
        calc(-50% + cos(var(--angle)) * var(--dist)),
        calc(-50% + sin(var(--angle)) * var(--dist))
      )
      scale(0.4);
  }
}

/* ── Vermilion seal stamp ── */
.seal-svg {
  width: 64px;
  height: 64px;
  filter: drop-shadow(0 3px 10px rgba(200, 80, 58, 0.4));
}

/* ── Stamp transition ── */
.v-stamp-enter-active {
  animation: stamp-down 560ms var(--ease-brush);
}
.v-stamp-leave-active {
  transition: opacity 200ms ease-in, transform 200ms ease-in;
}
.v-stamp-leave-to {
  opacity: 0;
  transform: scale(0.8);
}
@keyframes stamp-down {
  0%   { opacity: 0; transform: translateY(-30px) rotate(-10deg) scale(0.65); }
  35%  { opacity: 1; transform: translateY(4px) rotate(1.5deg) scale(1.05); }
  50%  { opacity: 1; transform: translateY(-2px) rotate(-0.5deg) scale(0.97); }
  65%  { opacity: 1; transform: translateY(1px) rotate(0.2deg) scale(1.01); }
  80%  { opacity: 1; transform: translateY(0) rotate(0deg) scale(0.995); }
  100% { opacity: 1; transform: translateY(0) rotate(0deg) scale(1); }
}

/* Ink splash ring around seal */
.done-seal::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--vermilion-0);
  opacity: 0;
  pointer-events: none;
  animation: seal-splash 640ms var(--ease-brush) forwards;
  animation-delay: 260ms;
}
@keyframes seal-splash {
  0%   { width: 10px; height: 10px; opacity: 0.5; border-width: 2px; }
  100% { width: 100px; height: 100px; opacity: 0; border-width: 1px; }
  100% { width: 70px; height: 70px; opacity: 0; border-width: 0.5px; }
}

.result-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) 0;
  border-bottom: 1px solid var(--c-surface-3);
  flex-shrink: 0;
}
.result-bar-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.done-title-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.done-label {
  font-family: var(--font-serif-zh);
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--c-text-0);
  letter-spacing: var(--tracking-tight);
  text-shadow: 0 0 24px rgba(200, 80, 58, 0.12);
}
.done-meta {
  font-family: var(--font-serif);
  font-size: var(--text-xs);
  font-style: italic;
  color: var(--c-text-3);
}
.done-rag-hint {
  font-size: var(--text-xs); color: var(--c-accent); cursor: pointer;
  padding: 2px 8px; border-radius: 4px; border: 1px solid var(--c-accent);
  transition: background 0.15s;
}
.done-rag-hint:hover { background: var(--c-accent-bg); }

.result-bar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}
.bar-sep { width: 1px; height: 20px; background: var(--c-surface-3); }

/* ── Dual view ── */
.dual-view {
  flex: 1;
  overflow-y: auto;
  max-width: 1200px;
  width: 100%;
  margin: var(--space-4) auto 0;
  padding: var(--space-4);
  padding-bottom: var(--space-6);
}

.dual-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-5);
  padding: var(--space-4) 0;
  transition: background var(--motion-fast) var(--ease-out);
}
/* 段落行交替微光 — 书简斑驳感 */
.dual-row:nth-child(even) { background: var(--c-surface-2); }
.dual-row + .dual-row { border-top: 1px solid var(--c-sent-border); }
.dual-row:first-child { border-top: none; }

.dual-orig {
  font-size: 14px;
  color: var(--c-text-2);
  line-height: 1.7;
  word-break: break-word;
  padding-left: var(--space-2);
}
.dual-orig :deep(p) { margin: 0; }
.dual-orig :deep(p + p) { margin-top: var(--space-2); }

.dual-trans {
  font-size: var(--read-fs, 15px);
  color: var(--read-trans-color, var(--c-text-0));
  line-height: var(--read-lh, 1.8);
  word-break: break-word;
  font-family: var(--read-ff, system-ui);
  padding-right: var(--space-2);
}
.dual-trans :deep(p) { margin: 0; }
.dual-trans :deep(p + p) { margin-top: var(--space-2); }

/* Sentence highlighting with vermilion annotation line */
.dual-orig :deep(.sent),
.dual-trans :deep(.sent) {
  transition: background-color 0.15s ease, border-radius 0.15s ease, box-shadow 0.15s ease;
  padding: 1px 2px;
  border-radius: 2px;
  cursor: default;
}

.dual-orig :deep(.sent:hover),
.dual-trans :deep(.sent:hover) {
  background-color: var(--c-accent-soft);
}

.dual-orig :deep(.sent.sent-active) {
  background-color: var(--c-accent-soft);
  box-shadow: inset 2px 0 0 var(--vermilion-0);
}
.dual-trans :deep(.sent.sent-active) {
  background-color: var(--c-accent-soft);
  box-shadow: inset 2px 0 0 var(--vermilion-0);
}

.dual-pending {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-style: italic;
}

/* Headings — 跨栏，加淡色底横线贯穿 */
.dual-row.type-heading {
  grid-template-columns: 1fr;
  padding: var(--space-5) 0 var(--space-3);
  margin-top: var(--space-3);
  background: none;
  position: relative;
}
.dual-row.type-heading + .dual-row { border-top: none; }
.dual-row.type-heading::before {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(to right, var(--c-accent) 0%, var(--c-accent) 15%, transparent 60%);
  opacity: 0.3;
}
.dual-heading-orig {
  margin: 0;
  color: var(--c-text-3);
  font-size: 0.85em;
  font-weight: 400;
}
.dual-heading-trans {
  margin: var(--space-1) 0 0;
  color: var(--c-text-0);
  font-family: var(--font-serif-zh), var(--font-serif);
  font-weight: 600;
}

/* Untranslated blocks */
.dual-untranslated {
  grid-column: 1 / -1;
  padding: var(--space-3);
  background: var(--c-surface-2);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}
.dual-untranslated :deep(pre) {
  margin: 0;
  background: transparent;
  font-family: var(--font-mono);
  font-size: 13px;
}
.dual-untranslated :deep(table) {
  border-collapse: collapse;
  width: 100%;
}
.dual-untranslated :deep(th),
.dual-untranslated :deep(td) {
  border: 1px solid var(--c-surface-3);
  padding: 4px 8px;
  font-size: var(--text-sm);
}

.dual-row.type-formula .dual-untranslated {
  text-align: center;
  font-size: 1.05em;
}

/* Failed blocks — vermilion left bar */
.dual-failed {
  grid-column: 1 / -1;
  padding: var(--space-3);
  background: var(--c-danger-bg);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--vermilion-0);
}

.dual-failed .dual-orig {
  padding: 0;
}

.failed-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
  font-size: var(--text-sm);
  color: var(--c-danger);
}

.failed-card button {
  margin-left: auto;
}

.retrying {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-style: italic;
}

/* Narrow screens */
@media (max-width: 900px) {
  .upload-hero {
    flex-direction: column;
    text-align: center;
    gap: var(--space-5);
  }
  .hero-left { padding-left: var(--space-4); align-items: center; }
  .hero-fishtail { display: none; }
  .hero-title { font-size: var(--text-display); }
  .drop-zone { min-width: unset; width: 100%; }
  .dual-row { grid-template-columns: 1fr; gap: var(--space-2); }
  .dual-orig {
    padding-bottom: var(--space-2);
    border-bottom: 1px dashed var(--c-surface-3);
  }
  .dual-failed { grid-template-columns: 1fr; }
}

/* ── Reading view ── */
.reading-view {
  flex: 1;
  overflow-y: auto;
  margin-top: var(--space-4);
}

.warn-tag {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 1px 6px;
  font-size: var(--text-xs);
  background: var(--c-warn-bg);
  color: var(--c-warn);
  border-radius: var(--radius-pill);
}

.prose {
  max-width: 72ch;
  margin: 0 auto;
  font-size: var(--read-fs, 15px);
  line-height: var(--read-lh, 1.8);
  color: var(--read-trans-color, var(--c-text-0));
  font-family: var(--read-ff, system-ui);
}
:deep(.prose) h1 {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: var(--text-display);
  font-weight: 700;
  margin: var(--space-7) 0 var(--space-4);
  color: var(--c-text-0);
  letter-spacing: var(--tracking-display);
  line-height: var(--leading-tight);
}
:deep(.prose) h2 {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: var(--space-6) 0 var(--space-3);
  color: var(--c-text-0);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--c-surface-3);
  letter-spacing: var(--tracking-tight);
}
:deep(.prose) h3 {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: var(--text-xl);
  font-weight: 600;
  margin: var(--space-5) 0 var(--space-2);
  color: var(--c-text-1);
}
:deep(.prose) p { margin-bottom: var(--space-4); }
:deep(.prose) strong { color: var(--c-text-0); font-weight: 600; }
:deep(.prose) blockquote {
  border-left: 3px solid var(--c-accent);
  padding: var(--space-2) var(--space-4);
  color: var(--c-text-2);
  margin: var(--space-4) 0;
  background: var(--c-accent-bg2);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
:deep(.prose) hr {
  border: none;
  border-top: 1px solid var(--c-surface-3);
  margin: var(--space-5) 0;
}

/* ══════════════════════════════════════════════════════════
   LIGHT MODE OVERRIDES
══════════════════════════════════════════════════════════ */
:global([data-theme="light"]) .hero-title {
  text-shadow: none;
}
:global([data-theme="light"]) .scene-mesh {
  background:
    radial-gradient(ellipse 60% 50% at 30% 60%, rgba(91,108,255,0.03) 0%, transparent 70%),
    radial-gradient(ellipse 50% 40% at 75% 35%, rgba(167,139,250,0.02) 0%, transparent 65%);
}
:global([data-theme="light"]) .drop-zone {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-color: rgba(91, 108, 255, 0.25);
}
:global([data-theme="light"]) .drop-zone:hover,
:global([data-theme="light"]) .drop-zone.hover {
  background: rgba(91, 108, 255, 0.06);
  box-shadow: 0 12px 32px rgba(91, 108, 255, 0.10), 0 1px 0 rgba(91, 108, 255, 0.15) inset;
}
:global([data-theme="light"]) .work-card {
  box-shadow: var(--elevation-2);
}
</style>
