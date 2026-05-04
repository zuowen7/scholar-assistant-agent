<template>
  <main class="tv-main">

    <!-- ── Idle / Error ──────────────────────────────────────── -->
    <div v-if="state.status === 'idle' || state.status === 'error'" class="upload-scene">
      <div class="scene-mesh" aria-hidden="true" />

      <div class="upload-hero">
        <h2 class="hero-title">学术文献翻译</h2>
        <p class="hero-sub">上传文档，AI 逐步解析、翻译并生成对照译文</p>

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
          <div class="dz-icon-wrap">
            <UploadCloud :size="28" :stroke-width="1.4" class="dz-icon" />
          </div>
          <span class="dz-label">点击选择文件</span>
          <span class="dz-hint">或将文件拖入窗口任意位置</span>
        </div>

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

      <!-- Live preview：显示最新3个完整段落（P1-3） -->
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
    <div v-else class="result-scene" :style="readStyleVars">

      <!-- Result action bar -->
      <div class="result-bar">
        <div class="result-bar-left">
          <CheckCircle :size="16" :stroke-width="2.2" class="done-icon" />
          <span class="done-label">翻译完成</span>
          <span v-if="state.blocks.length" class="done-meta">
            {{ state.blocks.length }} 块 · {{ paragraphCount }} 段
            <span v-if="state.misalignedChunks > 0" class="warn-tag">{{ state.misalignedChunks }} 块对齐回退</span>
          </span>
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
          <UiButton variant="secondary" size="sm" @click="reset">新翻译</UiButton>
        </div>
      </div>

      <!-- Export error banner (shown in done state) -->
      <div v-if="state.errorMessage" class="export-error-banner">
        <AlertCircle :size="14" :stroke-width="2" />
        <span class="error-text">{{ state.errorMessage }}</span>
      </div>

      <!-- ── 对照视图：左右双栏按块对齐 ── -->
      <div v-if="viewMode === 'bilingual'" class="dual-view">
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
      <div v-else class="reading-view">
        <article class="prose" v-html="translationOnlyHtml" />
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { UploadCloud, AlertCircle, Check, CheckCircle, Download, FileText, ChevronDown } from './ui/icons'
import UiButton from './ui/UiButton.vue'
import UiSegmented from './ui/UiSegmented.vue'
import UiDropdown from './ui/UiDropdown.vue'
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

// ── 失败块重试（P2-2） ──
async function retryFailedBlock(blockId: string) {
  if (!state.taskId) return

  retryingBlockIds.value.add(blockId)

  try {
    const resp = await fetch(`${API_URL}/api/translate/${state.taskId}/retry_block`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ block_id: blockId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '重试失败' }))
      throw new Error(err.detail || '重试失败')
    }

    const result = await resp.json()

    // 更新本地状态
    const block = state.blocks.find(b => b.id === blockId)
    if (block) {
      block.translated = result.translated
      block.status = result.status
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    console.error('重试块翻译失败:', msg)
  } finally {
    retryingBlockIds.value.delete(blockId)
  }
}

// ── 导出菜单（P2-1） ──
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

// ── 句对齐hover状态 ──
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

const readStyleVars = computed(() => ({
  '--read-fs': `${props.readSettings.fontSize}px`,
  '--read-lh': props.readSettings.lineHeight,
  '--read-ff': props.readSettings.fontFamily,
  '--read-trans-color': props.readSettings.transColor,
}))

// ── Block-based rendering（不再做前端句子切分） ──

/** 渲染时只展示真正有内容的块（即时翻译流中已到的块全展示，未到的也展示原文骨架） */
const renderableBlocks = computed(() => state.blocks)

/** 译文视图：把所有可翻译块的译文按 markdown 拼接渲染，跳过失败块 */
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

/** 标题文本去掉 markdown 标记 */
function stripHeadingMark(s: string): string {
  return s.replace(/^#{1,6}\s+/, '').trim()
}

// ── 句对齐hover处理 ──
/** hover原文句子时，找到对应的译文句子 */
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

/** 清除hover状态 */
function clearSentHover() {
  hoveredPair.value = null
}

/** 渲染带句子标记的HTML（用于普通段落） */
function renderSentenceMarked(text: string, lang: 'en' | 'zh', blockId: string, side: 'orig' | 'trans'): string {
  const sentences = splitSentences(text, lang)
  if (sentences.length <= 1) {
    // 只有一句，使用原有渲染逻辑
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

/** 处理句子mouseenter事件（事件委托） */
function handleSentenceMouseEnter(e: MouseEvent) {
  const target = e.target as HTMLElement
  const sentIdxStr = target.getAttribute('data-sent-idx')
  const blockId = target.getAttribute('data-block-id')
  const side = target.getAttribute('data-side') as 'orig' | 'trans' | null

  if (sentIdxStr === null || blockId === null || side === null) return

  const sentIdx = parseInt(sentIdxStr, 10)
  onSentHover(blockId, sentIdx, side)

  // 手动更新DOM高亮
  updateSentenceHighlight(blockId, side, sentIdx)
}

/** 更新句子高亮状态 */
function updateSentenceHighlight(blockId: string, side: 'orig' | 'trans', sentIdx: number) {
  // 清除之前的高亮
  document.querySelectorAll('.sent-active').forEach(el => {
    el.classList.remove('sent-active')
  })

  // 找到对应的块
  const block = state.blocks.find(b => b.id === blockId)
  if (!block || !block.translated) return

  // 计算对应的句子索引
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

  // 高亮原文中的当前句子
  const origSentSelector = `.dual-orig [data-block-id="${blockId}"][data-side="orig"][data-sent-idx="${sentIdx}"]`
  const origSentEl = document.querySelector(origSentSelector)
  if (origSentEl) {
    origSentEl.classList.add('sent-active')
  }

  // 高亮译文中的对应句子
  const transSentSelector = `.dual-trans [data-block-id="${blockId}"][data-side="trans"][data-sent-idx="${otherIdx}"]`
  const transSentEl = document.querySelector(transSentSelector)
  if (transSentEl) {
    transSentEl.classList.add('sent-active')
  }
}

/** 处理句子点击事件（暂不使用，保留接口） */
function handleSentenceClick(e: MouseEvent) {
  // 预留接口，可用于点击句子复制等操作
}

/** 段落计数（仅 paragraph 类型）——用于显示元信息 */
const paragraphCount = computed(() =>
  state.blocks.filter(b => b.type === 'paragraph').length
)

// ── File picker ──

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
   UPLOAD / IDLE
══════════════════════════════════════════════════════════ */
.upload-scene {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

/* Ambient mesh gradient in the background */
.scene-mesh {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 60% 50% at 30% 60%, rgba(99,102,241,0.07) 0%, transparent 70%),
    radial-gradient(ellipse 50% 40% at 75% 35%, rgba(167,139,250,0.05) 0%, transparent 65%);
}

.upload-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  width: 100%;
  max-width: 480px;
  padding: var(--space-6) var(--space-4);
  text-align: center;
}

.hero-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--c-text-0);
  letter-spacing: -0.02em;
  line-height: var(--leading-tight);
  margin: 0;
}
.hero-sub {
  font-size: var(--text-base);
  color: var(--c-text-2);
  line-height: var(--leading-normal);
  margin: -var(--space-2) 0 0;
}

.drop-zone {
  width: 100%;
  padding: var(--space-6) var(--space-5);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  background: var(--c-glass);
  border: 2px dashed var(--c-glass-border);
  border-radius: var(--radius-xl);
  cursor: pointer;
  outline: none;
  transition:
    border-color var(--motion-base) var(--ease-out),
    background var(--motion-base) var(--ease-out),
    box-shadow var(--motion-base) var(--ease-out);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.drop-zone:hover,
.drop-zone.hover {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
  box-shadow: 0 0 48px rgba(99, 102, 241, 0.12);
}
.drop-zone:hover .dz-icon,
.drop-zone.hover .dz-icon { color: var(--c-accent-hover); }

.dz-icon-wrap {
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
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
}
.dz-icon { color: var(--c-text-3); transition: color var(--motion-base) var(--ease-out); }
.dz-label { font-size: var(--text-base); font-weight: 600; color: var(--c-text-0); }
.dz-hint { font-size: var(--text-sm); color: var(--c-text-3); }

/* Format chips */
.format-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-1);
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
  padding: var(--space-3) var(--space-4);
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
  border-radius: var(--radius-xl);
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

/* Connecting line between steps */
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
  background: rgba(74, 222, 128, 0.10);
  color: var(--c-success);
}
.step.active .step-dot {
  border-color: var(--c-accent);
  background: var(--c-accent-soft);
  color: var(--c-accent-hover);
  box-shadow: 0 0 0 4px var(--c-accent-ring);
  animation: step-pulse 1.8s ease-in-out infinite;
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
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--c-accent), var(--c-accent-hover));
  transition: width 0.45s var(--ease-out);
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

/* Live preview */
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
   DONE / RESULT
══════════════════════════════════════════════════════════ */
.result-scene {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 0 var(--space-5) var(--space-5);
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
.done-icon { color: var(--c-success); flex-shrink: 0; }
.done-label { font-size: var(--text-base); font-weight: 600; color: var(--c-text-0); }
.done-meta { font-size: var(--text-sm); color: var(--c-text-3); }
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

/* ── Dual view（左右双栏对照） ── */
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
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--c-surface-3);
}

.dual-orig {
  font-size: 14px;
  color: var(--c-text-2);
  line-height: 1.7;
  word-break: break-word;
}
.dual-orig :deep(p) { margin: 0; }
.dual-orig :deep(p + p) { margin-top: var(--space-2); }

.dual-trans {
  font-size: var(--read-fs, 15px);
  color: var(--read-trans-color, var(--c-text-0));
  line-height: var(--read-lh, 1.8);
  word-break: break-word;
  font-family: var(--read-ff, system-ui);
}
.dual-trans :deep(p) { margin: 0; }
.dual-trans :deep(p + p) { margin-top: var(--space-2); }

/* 句子高亮样式 */
.dual-orig :deep(.sent),
.dual-trans :deep(.sent) {
  transition: background-color 0.15s ease, border-radius 0.15s ease;
  padding: 1px 2px;
  border-radius: 2px;
  cursor: default;
}

.dual-orig :deep(.sent:hover),
.dual-trans :deep(.sent:hover) {
  background-color: var(--c-accent-soft, rgba(99, 102, 241, 0.08));
}

.dual-orig :deep(.sent.sent-active),
.dual-trans :deep(.sent.sent-active) {
  background-color: var(--c-accent-soft, rgba(99, 102, 241, 0.15));
  box-shadow: 0 0 0 1px var(--c-accent-4, rgba(99, 102, 241, 0.2));
}

.dual-pending {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-style: italic;
}

/* 标题跨栏 */
.dual-row.type-heading { grid-template-columns: 1fr; }
.dual-heading-orig {
  margin: 0;
  color: var(--c-text-3);
  font-size: 0.85em;
  font-weight: 400;
}
.dual-heading-trans {
  margin: var(--space-1) 0 0;
  color: var(--c-text-0);
  font-family: var(--read-ff, system-ui);
}

/* 公式/代码跨栏居中 */
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
  font-family: ui-monospace, SFMono-Regular, monospace;
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

/* 公式居中 */
.dual-row.type-formula .dual-untranslated {
  text-align: center;
  font-size: 1.05em;
}

/* 翻译失败块 */
/* 翻译失败块 */
.dual-failed {
  grid-column: 1 / -1;
  padding: var(--space-3);
  background: var(--c-danger-soft, rgba(239, 68, 68, 0.05));
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--c-danger-5, #ef4444);
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
  color: var(--c-danger-5, #ef4444);
}

.failed-card button {
  margin-left: auto;
}

.retrying {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-style: italic;
}

/* 窄屏自适应 */
@media (max-width: 900px) {
  .dual-row { grid-template-columns: 1fr; gap: var(--space-2); }
  .dual-orig {
    padding-bottom: var(--space-2);
    border-bottom: 1px dashed var(--c-surface-3);
  }
  .dual-failed { grid-template-columns: 1fr; }
}

/* ── Reading view（译文 / 全文 markdown） ── */
.reading-view {
  flex: 1;
  overflow-y: auto;
  margin-top: var(--space-4);
}

/* 警告标签 */
.warn-tag {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 1px 6px;
  font-size: var(--text-xs);
  background: var(--c-warning-bg, rgba(255,180,50,0.15));
  color: var(--c-warning, #d49a2c);
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
  font-size: var(--text-2xl);
  font-weight: 700;
  margin: var(--space-6) 0 var(--space-4);
  color: var(--c-text-0);
  letter-spacing: -0.01em;
  line-height: var(--leading-tight);
}
:deep(.prose) h2 {
  font-size: var(--text-xl);
  font-weight: 600;
  margin: var(--space-6) 0 var(--space-3);
  color: var(--c-text-0);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--c-surface-3);
}
:deep(.prose) h3 {
  font-size: var(--text-lg);
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
</style>
