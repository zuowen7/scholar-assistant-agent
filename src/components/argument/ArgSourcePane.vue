<template>
  <div class="arg-source-pane">
    <!-- Header -->
    <div class="source-header">
      <span class="source-title">原文</span>
      <div class="source-load-btns">
        <button
          class="source-btn"
          :class="{ active: state.source.mode === 'translation' }"
          @click="doLoadTranslation"
        >从翻译结果</button>
        <button
          class="source-btn"
          :class="{ active: state.source.mode === 'editor' }"
          @click="doLoadEditor"
        >从编辑器</button>
        <button
          class="source-btn"
          :class="{ active: state.source.mode === 'paste' && state.source.text }"
          @click="showPaste = !showPaste"
        >粘贴文本</button>
      </div>
      <button
        v-if="state.source.mode === 'translation'"
        class="source-side-toggle"
        :title="state.source.side === 'trans' ? '切换显示原文' : '切换显示译文'"
        @click="toggleSide"
      >{{ state.source.side === 'trans' ? '译 ⇄' : '原 ⇄' }}</button>
      <button
        class="extract-btn"
        :disabled="!hasContent || !state.graph || state.extracting"
        :title="state.graph ? '从当前原文提取 Toulmin 论证图' : '请先创建或打开一张论证图'"
        @click="doExtract"
      >{{ state.extracting ? '提取中…' : '提取论证' }}</button>
    </div>

    <!-- Paste input area -->
    <div v-if="showPaste" class="source-paste-area">
      <textarea
        v-model="pasteText"
        class="source-paste-input"
        rows="4"
        placeholder="粘贴原文或译文…"
        @keydown.enter.ctrl.prevent="confirmPaste"
      />
      <div class="paste-actions">
        <button class="paste-btn paste-btn--primary" @click="confirmPaste">确定</button>
        <button class="paste-btn" @click="showPaste = false">取消</button>
      </div>
    </div>

    <!-- Rendered sentence content -->
    <div ref="containerRef" class="source-content">
      <div v-if="!hasContent" class="source-empty">
        选择原文来源后，点击句子可将其绑定到论证节点
      </div>

      <div
        v-for="block in renderedBlocks"
        :key="block.id"
        class="source-block"
      >
        <span
          v-for="sent in block.sentences"
          :key="`${sent.blockId}:${sent.sentIdx}`"
          class="sent"
          :class="{
            'arg-mapped': isMapped(sent.blockId, sent.sentIdx),
            'arg-mapped-active': isActive(sent.blockId, sent.sentIdx),
          }"
          :data-block-id="sent.blockId"
          :data-sent-idx="sent.sentIdx"
          :data-side="state.source.side"
          @click.stop="onSentenceClick(sent, $event)"
        >{{ sent.text }}</span>
      </div>
    </div>

    <!-- Bind popup (teleported to body to avoid clipping) -->
    <Teleport to="body">
      <div
        v-if="bindPopup.visible"
        class="arg-bind-popup"
        :style="{ left: bindPopup.x + 'px', top: bindPopup.y + 'px' }"
        @click.stop
      >
        <div class="bind-quote">「{{ bindPopup.sentence?.text?.slice(0, 50) }}{{ (bindPopup.sentence?.text?.length ?? 0) > 50 ? '…' : '' }}」</div>
        <div class="bind-actions">
          <button
            v-if="state.selectedNodeId"
            class="bind-btn bind-btn--primary"
            @click="bindToCurrentNode"
          >绑定到当前节点</button>
          <div class="bind-sep">或新建节点：</div>
          <div class="bind-new-btns">
            <button
              v-for="nt in NODE_TYPE_OPTIONS"
              :key="nt.value"
              class="bind-btn"
              :class="`type-${nt.value}`"
              @click="bindAndCreate(nt.value)"
            >{{ nt.label }}</button>
          </div>
          <button class="bind-btn bind-btn--cancel" @click="bindPopup.visible = false">取消</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { NodeType } from '../../composables/useArgumentMap'
import {
  useArgumentMap,
  focusSpan,
  setPastedSource,
  loadSourceFromTranslation,
  loadSourceFromEditor,
} from '../../composables/useArgumentMap'
import { splitSentences } from '../../utils/sentenceAlign'

const { state, addSpan, upsertNode, extractArgument } = useArgumentMap()

async function doExtract() {
  await extractArgument(state.source.text, state.source.label, state.source.side)
}

// ── Source load ────────────────────────────────────────────────────────────────

const showPaste = ref(false)
const pasteText = ref('')

function doLoadTranslation() { loadSourceFromTranslation() }
function doLoadEditor() { loadSourceFromEditor() }

function confirmPaste() {
  if (pasteText.value.trim()) setPastedSource(pasteText.value.trim())
  showPaste.value = false
  pasteText.value = ''
}

function toggleSide() {
  state.source.side = state.source.side === 'trans' ? 'orig' : 'trans'
}

// ── Sentence rendering ─────────────────────────────────────────────────────────

interface RenderedSentence {
  text: string
  blockId: string
  sentIdx: number
  charStart: number
  charEnd: number
}

interface RenderedBlock {
  id: string
  sentences: RenderedSentence[]
}

function detectLang(text: string): 'en' | 'zh' {
  const zh = (text.match(/[一-鿿]/g) ?? []).length
  return zh / (text.length || 1) > 0.15 ? 'zh' : 'en'
}

const renderedBlocks = computed<RenderedBlock[]>(() => {
  const src = state.source
  if (src.mode === 'translation' && src.blocks.length) {
    return src.blocks
      .filter(b => b.translatable)
      .map(block => {
        const text = src.side === 'trans' ? (block.translated || block.original) : (block.original || block.translated)
        const sentences = splitSentences(text || '', detectLang(text || ''))
        return {
          id: block.id,
          sentences: sentences.map((s, idx) => ({
            text: s.text, blockId: block.id, sentIdx: idx, charStart: s.start, charEnd: s.end,
          })),
        }
      })
  }
  if ((src.mode === 'paste' || src.mode === 'editor') && src.text) {
    const sentences = splitSentences(src.text, detectLang(src.text))
    return [{
      id: '_virtual_',
      sentences: sentences.map((s, idx) => ({
        text: s.text, blockId: '_virtual_', sentIdx: idx, charStart: s.start, charEnd: s.end,
      })),
    }]
  }
  return []
})

const hasContent = computed(() => renderedBlocks.value.some(b => b.sentences.length > 0))

// ── Span ↔ sentence mapping ────────────────────────────────────────────────────

function _matchSpanToSentences(
  map: Map<string, { nodeId: string; spanId: string }>,
  span: { node_id: string; id: string; char_start?: number | null; char_end?: number | null; quote?: string },
  text: string,
  blockId: string,
) {
  const sentences = splitSentences(text, detectLang(text))
  if (span.char_start != null && span.char_end != null) {
    for (let i = 0; i < sentences.length; i++) {
      const s = sentences[i]
      if (s.end > span.char_start && s.start < span.char_end) {
        map.set(`${blockId}:${i}`, { nodeId: span.node_id, spanId: span.id })
      }
    }
  } else if (span.quote) {
    const q = span.quote.slice(0, 30)
    for (let i = 0; i < sentences.length; i++) {
      if (sentences[i].text.includes(q) || span.quote.includes(sentences[i].text.slice(0, 30))) {
        map.set(`${blockId}:${i}`, { nodeId: span.node_id, spanId: span.id })
      }
    }
  }
}

const spanSentenceMap = computed(() => {
  const map = new Map<string, { nodeId: string; spanId: string }>()
  if (!state.graph) return map

  // Determine the default block ID for spans without block_id (from extraction)
  const defaultBlockId =
    state.source.mode === 'paste' || state.source.mode === 'editor'
      ? '_virtual_'
      : null

  for (const span of state.graph.spans) {
    if (span.block_id) {
      const block = state.source.blocks.find(b => b.id === span.block_id)
      if (!block) continue
      const text = state.source.side === 'trans'
        ? (block.translated || block.original)
        : (block.original || block.translated)
      if (!text) continue
      _matchSpanToSentences(map, span, text, span.block_id)
    } else if (defaultBlockId && state.source.text) {
      // Spans without block_id (from AI extraction) match against paste/editor source text
      _matchSpanToSentences(map, span, state.source.text, defaultBlockId)
    }
  }
  return map
})

const activeNodeSet = computed(() => new Set(state.highlightNodeIds))

function isMapped(blockId: string, sentIdx: number) {
  return spanSentenceMap.value.has(`${blockId}:${sentIdx}`)
}

function isActive(blockId: string, sentIdx: number) {
  const entry = spanSentenceMap.value.get(`${blockId}:${sentIdx}`)
  return !!entry && activeNodeSet.value.has(entry.nodeId)
}

// Auto-scroll to active sentence when highlight changes
const containerRef = ref<HTMLElement | null>(null)
watch(
  () => state.highlightNodeIds,
  () => {
    nextTick(() => {
      const el = containerRef.value?.querySelector('.sent.arg-mapped-active')
      if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  },
  { deep: true },
)

// ── Bind popup ─────────────────────────────────────────────────────────────────

const NODE_TYPE_OPTIONS: { value: NodeType; label: string }[] = [
  { value: 'claim', label: '主张' },
  { value: 'grounds', label: '依据' },
  { value: 'warrant', label: '论证保证' },
  { value: 'backing', label: '支撑' },
  { value: 'qualifier', label: '限定' },
  { value: 'rebuttal', label: '反驳' },
]

const bindPopup = reactive<{
  visible: boolean
  sentence: RenderedSentence | null
  x: number
  y: number
}>({ visible: false, sentence: null, x: 0, y: 0 })

function onSentenceClick(sent: RenderedSentence, event: MouseEvent) {
  // If a span already maps here, focus the corresponding node
  const entry = spanSentenceMap.value.get(`${sent.blockId}:${sent.sentIdx}`)
  if (entry) focusSpan(entry.spanId)

  // Show bind popup
  bindPopup.visible = true
  bindPopup.sentence = sent
  bindPopup.x = Math.min(event.clientX + 6, window.innerWidth - 270)
  bindPopup.y = Math.min(event.clientY + 10, window.innerHeight - 210)
}

async function bindToCurrentNode() {
  const sent = bindPopup.sentence
  if (!sent || !state.selectedNodeId || !state.graph) return
  await addSpan({
    node_id: state.selectedNodeId,
    source_type: 'selection',
    block_id: sent.blockId === '_virtual_' ? null : sent.blockId,
    side: state.source.side,
    char_start: sent.charStart,
    char_end: sent.charEnd,
    quote: sent.text,
    source_label: state.source.label || undefined,
  })
  bindPopup.visible = false
}

async function bindAndCreate(nodeType: NodeType) {
  const sent = bindPopup.sentence
  if (!sent || !state.graph) return
  const node = await upsertNode({ node_type: nodeType, text: sent.text })
  await addSpan({
    node_id: node.id,
    source_type: 'selection',
    block_id: sent.blockId === '_virtual_' ? null : sent.blockId,
    side: state.source.side,
    char_start: sent.charStart,
    char_end: sent.charEnd,
    quote: sent.text,
    source_label: state.source.label || undefined,
  })
  bindPopup.visible = false
}

// Close popup on outside click
function onDocClick() { bindPopup.visible = false }
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.arg-source-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-surface-0);
  border-right: 1px solid var(--c-surface-2);
  min-width: 0;
  overflow: hidden;
}

/* Header */
.source-header {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border-bottom: 1px solid var(--c-surface-2);
  background: var(--c-surface-1);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.source-title {
  font-size: 10px;
  font-weight: 700;
  color: var(--c-text-2);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  white-space: nowrap;
  flex-shrink: 0;
}

.source-load-btns { display: flex; gap: 3px; flex-wrap: wrap; }

.source-btn {
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-1);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: background 100ms, border-color 100ms;
  white-space: nowrap;
}
.source-btn:hover { background: var(--c-surface-3); }
.source-btn.active {
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.source-side-toggle {
  margin-left: auto;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-1);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.source-side-toggle:hover { background: var(--c-surface-3); }

.extract-btn {
  margin-left: auto;
  padding: 2px 9px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-accent);
  background: var(--c-accent);
  color: #fff;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 100ms;
}
.extract-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.extract-btn:not(:disabled):hover { opacity: 0.85; }

/* Paste area */
.source-paste-area {
  padding: 8px 10px;
  border-bottom: 1px solid var(--c-surface-2);
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
}

.source-paste-input {
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-sm);
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  padding: 6px 8px;
  resize: vertical;
  outline: none;
  transition: border-color 120ms;
}
.source-paste-input:focus { border-color: var(--c-accent); }

.paste-actions { display: flex; gap: 6px; justify-content: flex-end; }

.paste-btn {
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.paste-btn--primary { background: var(--c-accent); color: #fff; border-color: var(--c-accent); }

/* Content */
.source-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  line-height: 1.9;
}

.source-empty {
  color: var(--c-text-2);
  font-size: 12px;
  text-align: center;
  padding-top: 48px;
  font-style: italic;
}

.source-block {
  margin-bottom: 14px;
  font-size: 13px;
  color: var(--c-text-0);
  line-height: 1.8;
}

/* Sentences */
.sent {
  cursor: pointer;
  border-radius: 2px;
  padding: 1px 1px;
  transition: background 100ms;
}
.sent:hover { background: var(--c-surface-2); }

.sent.arg-mapped {
  text-decoration: underline;
  text-decoration-color: color-mix(in srgb, var(--c-accent) 50%, transparent);
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}

.sent.arg-mapped-active {
  background: color-mix(in srgb, var(--c-accent) 14%, transparent);
  text-decoration: underline;
  text-decoration-color: var(--c-accent);
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
  border-radius: 3px;
  padding: 1px 3px;
}

/* Bind popup */
.arg-bind-popup {
  position: fixed;
  z-index: 9999;
  background: var(--c-surface-1);
  border: 1px solid var(--c-surface-3);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 10px 12px;
  min-width: 200px;
  max-width: 260px;
}

.bind-quote {
  font-size: 11px;
  color: var(--c-text-2);
  margin-bottom: 8px;
  font-style: italic;
  word-break: break-all;
}

.bind-actions { display: flex; flex-direction: column; gap: 5px; }

.bind-sep {
  font-size: 10px;
  color: var(--c-text-2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 2px;
}

.bind-new-btns { display: flex; flex-wrap: wrap; gap: 4px; }

.bind-btn {
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--c-surface-3);
  background: var(--c-surface-2);
  color: var(--c-text-0);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: background 100ms;
}
.bind-btn:hover { background: var(--c-surface-3); }
.bind-btn--primary { background: var(--c-accent); color: #fff; border-color: var(--c-accent); font-size: 12px; }
.bind-btn--cancel { color: var(--c-text-2); margin-top: 2px; }

.bind-btn.type-claim { color: var(--c-accent); border-color: var(--c-accent); }
.bind-btn.type-grounds { color: #10b981; border-color: #10b981; }
.bind-btn.type-warrant { color: #3b82f6; border-color: #3b82f6; }
.bind-btn.type-backing { color: #93c5fd; border-color: #93c5fd; }
.bind-btn.type-qualifier { color: #f59e0b; border-color: #f59e0b; }
.bind-btn.type-rebuttal { color: var(--c-danger); border-color: var(--c-danger); }
</style>
