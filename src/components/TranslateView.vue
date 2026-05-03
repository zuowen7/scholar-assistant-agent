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

      <!-- Live preview -->
      <TransitionGroup v-if="state.translations.length > 0" name="live-slide" tag="div" class="live-preview">
        <div
          v-for="t in state.translations.slice(-3)"
          :key="t.index"
          class="live-item"
        >
          <p class="live-orig">{{ t.original_preview }}</p>
          <p class="live-trans">{{ t.translated_preview }}</p>
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
          <UiButton variant="primary" size="sm" @click="downloadResult">
            <template #icon-left><Download :size="13" :stroke-width="2" /></template>
            下载
          </UiButton>
          <UiButton variant="secondary" size="sm" @click="doExportBilingualDocx()">
            <template #icon-left><FileText :size="13" :stroke-width="2" /></template>
            双语 Word
          </UiButton>
          <UiButton variant="secondary" size="sm" @click="reset">新翻译</UiButton>
        </div>
      </div>

      <!-- Export error banner (shown in done state) -->
      <div v-if="state.errorMessage" class="export-error-banner">
        <AlertCircle :size="14" :stroke-width="2" />
        <span class="error-text">{{ state.errorMessage }}</span>
      </div>

      <!-- ── 对照视图：按块（block-by-block alignment） ── -->
      <div v-if="viewMode === 'bilingual'" class="block-view">
        <div
          v-for="(b, i) in renderableBlocks"
          :key="b.id"
          class="block-pair"
          :class="['type-' + b.type, b.translatable ? '' : 'untranslatable']"
        >
          <span class="block-num">{{ i + 1 }}</span>
          <div class="block-body">
            <!-- 标题：双语紧邻，保留层级感 -->
            <template v-if="b.type === 'heading'">
              <component :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`" class="block-heading-orig">{{ stripHeadingMark(b.original) }}</component>
              <component v-if="b.translated" :is="`h${Math.min(Math.max(b.level || 2, 1), 6)}`" class="block-heading-trans">{{ stripHeadingMark(b.translated) }}</component>
            </template>
            <!-- 公式 / 代码 / 表格：原样渲染 markdown，不译 -->
            <div v-else-if="!b.translatable" class="block-untranslated" v-html="renderBlock(b.original, b.type)" />
            <!-- 普通段落 / 列表 / 图表标注：原文+译文 -->
            <template v-else>
              <div class="block-orig" v-html="renderBlock(b.original, b.type)" />
              <div v-if="b.translated" class="block-trans" v-html="renderBlock(b.translated, b.type)" />
              <div v-else class="block-pending">翻译中…</div>
            </template>
          </div>
        </div>
      </div>

      <!-- ── 译文视图：纯译文阅读模式 ── -->
      <div v-else-if="viewMode === 'translation'" class="reading-view">
        <article class="prose" v-html="translationOnlyHtml" />
      </div>

      <!-- ── 全文视图：双语 markdown 渲染（导出预览） ── -->
      <div v-else class="reading-view">
        <article class="prose" v-html="bilingualMarkdownHtml" />
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { UploadCloud, AlertCircle, Check, CheckCircle, Download, FileText } from './ui/icons'
import UiButton from './ui/UiButton.vue'
import UiSegmented from './ui/UiSegmented.vue'
import { useTranslate } from '../composables/useTranslate'
import { renderMarkdown, renderBlock } from '../utils/markdown'

const props = defineProps<{
  healthOk: boolean
  readSettings: { fontSize: number; lineHeight: number; fontFamily: string; transColor: string }
}>()

defineEmits<{
  (e: 'restart-backend'): void
  (e: 'open-agent-docs'): void
}>()

const { state, translate, reset, downloadResult, overallProgress, exportBilingualDocx } = useTranslate()

const viewMode = ref<'bilingual' | 'translation' | 'markdown'>('bilingual')
const zoneHover = ref(false)

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
  { value: 'markdown' as const, label: '全文' },
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

/** 译文视图：把所有可翻译块的译文按 markdown 拼接渲染 */
const translationOnlyHtml = computed(() => {
  const parts: string[] = []
  for (const b of state.blocks) {
    if (!b.translatable) {
      parts.push(b.original)  // 公式/代码/表格保留原样
    } else if (b.translated) {
      parts.push(b.type === 'heading' ? `${'#'.repeat(Math.min(Math.max(b.level || 2, 1), 6))} ${stripHeadingMark(b.translated)}` : b.translated)
    }
  }
  return renderMarkdown(parts.join('\n\n'))
})

/** 全文视图：直接渲染后端格式化好的 bilingual markdown */
const bilingualMarkdownHtml = computed(() => renderMarkdown(state.finalContent))

/** 标题文本去掉 markdown 标记 */
function stripHeadingMark(s: string): string {
  return s.replace(/^#{1,6}\s+/, '').trim()
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

/* ── Block view（核心：按块对照） ── */
.block-view {
  flex: 1;
  overflow-y: auto;
  max-width: 1100px;
  width: 100%;
  margin: var(--space-4) auto 0;
  padding-bottom: var(--space-6);
}

.block-pair {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  border-radius: var(--radius-md);
  transition: background var(--motion-fast) var(--ease-out);
}
.block-pair:hover { background: var(--c-surface-1); }
.block-pair + .block-pair { border-top: 1px solid var(--c-surface-3); }

.block-num {
  text-align: right;
  font-size: var(--text-xs);
  color: var(--c-text-3);
  padding-top: 6px;
  font-variant-numeric: tabular-nums;
}
.block-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* 普通段落 */
.block-orig {
  font-size: var(--text-sm);
  color: var(--c-text-2);
  line-height: var(--leading-relaxed);
  word-break: break-word;
  padding: var(--space-2) var(--space-3);
  background: var(--c-surface-2);
  border-radius: var(--radius-sm);
}
.block-orig :deep(p) { margin: 0; }
.block-orig :deep(p + p) { margin-top: var(--space-2); }

.block-trans {
  font-size: var(--read-fs, 15px);
  color: var(--read-trans-color, var(--c-text-0));
  line-height: var(--read-lh, 1.9);
  word-break: break-word;
  font-family: var(--read-ff, system-ui);
  padding: var(--space-2) var(--space-3);
  border-left: 2px solid var(--c-accent);
}
.block-trans :deep(p) { margin: 0; }
.block-trans :deep(p + p) { margin-top: var(--space-2); }

.block-pending {
  font-size: var(--text-xs);
  color: var(--c-text-3);
  font-style: italic;
  padding: var(--space-2) var(--space-3);
  border-left: 2px dashed var(--c-surface-3);
}

/* 标题块 — 双语并列展示，保持 h1/h2/h3 视觉层级 */
.block-pair.type-heading .block-body { gap: var(--space-1); }
.block-heading-orig {
  margin: 0;
  color: var(--c-text-2);
  font-weight: 500;
}
.block-heading-trans {
  margin: 0 0 var(--space-2) 0;
  color: var(--c-text-0);
  font-family: var(--read-ff, system-ui);
}

/* 不可翻译块（公式/代码/表格）— 单栏原样展示 */
.block-untranslated {
  padding: var(--space-3) var(--space-4);
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  overflow-x: auto;
}
.block-untranslated :deep(pre) {
  margin: 0;
  background: transparent;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 13px;
}
.block-untranslated :deep(table) {
  border-collapse: collapse;
  width: 100%;
}
.block-untranslated :deep(th),
.block-untranslated :deep(td) {
  border: 1px solid var(--c-surface-3);
  padding: 4px 8px;
  font-size: var(--text-sm);
}

/* 公式特殊样式 — KaTeX 默认居中对齐 */
.block-pair.type-formula .block-untranslated {
  text-align: center;
  font-size: 1.05em;
}

/* 图表标注：弱化呈现 */
.block-pair.type-figure_caption .block-orig,
.block-pair.type-figure_caption .block-trans {
  font-size: var(--text-sm);
  font-style: italic;
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
