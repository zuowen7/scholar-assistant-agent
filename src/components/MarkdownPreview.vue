<template>
  <div class="preview-container">
    <div class="preview-header">
      <span class="preview-title">{{ t('editor.preview') }}</span>
    </div>
    <div class="preview-body" :key="renderKey" v-html="renderedHtml"></div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import { marked } from 'marked'
import hljs from 'highlight.js'
import katex from 'katex'
import DOMPurify from 'dompurify'

const props = defineProps<{
  content: string
  version?: number
}>()

// Debounced content for rendering (avoid re-rendering on every keystroke)
const debouncedContent = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

watch(() => [props.content, props.version], (v) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => { debouncedContent.value = v[0] as string }, 80)
}, { immediate: true })

onUnmounted(() => {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
})

// Extract math blocks before Markdown parsing, replace with placeholders
function extractMath(text: string): { text: string; blocks: string[] } {
  const blocks: string[] = []

  // Display math: $$...$$ (must come before inline)
  let result = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => {
    const idx = blocks.length
    blocks.push(renderKatex(math, true))
    return `\x00MATH${idx}\x00`
  })

  // Inline math: $...$
  result = result.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    const idx = blocks.length
    blocks.push(renderKatex(math, false))
    return `\x00MATH${idx}\x00`
  })

  return { text: result, blocks }
}

function renderKatex(latex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(latex.trim(), {
      displayMode,
      throwOnError: false,
      strict: false,
    })
  } catch {
    return `<code class="math-error">${escapeHtmlText(latex)}</code>`
  }
}

function escapeHtmlText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Restore math blocks after Markdown rendering
function restoreMath(html: string, blocks: string[]): string {
  return html.replace(/\x00MATH(\d+)\x00/g, (_, idx) => blocks[parseInt(idx)])
}

// Configure marked
marked.setOptions({
  gfm: true,
  breaks: true,
})

const renderer = new marked.Renderer()
renderer.code = ({ text, lang }: { text: string; lang?: string }) => {
  const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
  const highlighted = hljs.highlight(text, { language }).value
  return `<pre><code class="hljs language-${language}">${highlighted}</code></pre>`
}

marked.use({ renderer })

const renderedHtml = computed(() => {
  const src = debouncedContent.value
  if (!src) return '<p class="empty-hint">开始写作...</p>'

  const { text: mathExtracted, blocks } = extractMath(src)
  const raw = marked.parse(mathExtracted) as string

  // Protect KaTeX output from XSS cleanup
  const katexBlocks: string[] = []
  let protectedHtml = raw.replace(/\x00MATH(\d+)\x00/g, (_, idx) => {
    const ph = `\x00KX${katexBlocks.length}\x00`
    katexBlocks.push(blocks[parseInt(idx)])
    return ph
  })

  protectedHtml = DOMPurify.sanitize(protectedHtml, {
    ADD_TAGS: ['math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'munder', 'mover', 'munderover', 'mtext', 'mspace', 'mstyle', 'mpadded', 'mphantom', 'mfenced', 'menclose', 'msqrt', 'mroot', 'mtable', 'mtr', 'mtd', 'annotation', 'mglyph', 'ms', 'msgroup', 'msline', 'mscarry', 'mscarries', 'mscolumn', 'msrow', 'mstack', 'mlongdiv', 'msgap', 'mlabeledtr', 'maction', 'merror'],
    ADD_ATTR: ['display', 'mathvariant', 'linethickness', 'notation', 'lspace', 'rspace', 'width', 'height', 'depth', 'voffset', 'align', 'columnalign', 'rowspacing', 'columnspacing', 'class', 'xmlns'],
  })

  // Restore KaTeX blocks, then sanitize once more to catch any XSS in KaTeX output
  protectedHtml = protectedHtml.replace(/\x00KX(\d+)\x00/g, (_, idx) => katexBlocks[parseInt(idx)] ?? '')
  return DOMPurify.sanitize(protectedHtml, {
    ADD_TAGS: ['math', 'semantics', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac',
               'munder', 'mover', 'munderover', 'mtext', 'mspace', 'mstyle', 'mpadded',
               'mphantom', 'mfenced', 'menclose', 'msqrt', 'mroot', 'mtable', 'mtr', 'mtd',
               'annotation', 'mglyph', 'ms', 'merror', 'mlabeledtr', 'maction',
               'span', 'svg', 'path', 'line', 'rect', 'circle', 'use', 'defs', 'g'],
    ADD_ATTR: ['display', 'mathvariant', 'linethickness', 'notation', 'lspace', 'rspace',
               'width', 'height', 'depth', 'voffset', 'align', 'columnalign', 'rowspacing',
               'columnspacing', 'class', 'xmlns', 'viewBox', 'preserveAspectRatio',
               'aria-hidden', 'focusable', 'd', 'stroke', 'fill', 'stroke-width',
               'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r'],
  })
})
</script>

<style>
@import 'katex/dist/katex.min.css';
</style>

<style scoped>
.preview-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--editor-bg);
  border-left: 1px solid var(--border-color);
}

.preview-header {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.preview-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px var(--page-gutter);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
}
.preview-body :deep(> *) {
  max-width: var(--page-width);
  margin-left: auto;
  margin-right: auto;
}

.preview-body :deep(h1) {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: 1.8em; font-weight: 600;
  margin: 1em 0 0.5em;
  border-bottom: 1px solid var(--border-color); padding-bottom: 0.3em;
  letter-spacing: var(--tracking-display);
}
.preview-body :deep(h2) {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: 1.4em; font-weight: 600;
  margin: 0.9em 0 0.4em;
  border-bottom: 1px solid var(--border-color); padding-bottom: 0.3em;
  letter-spacing: var(--tracking-tight);
}
.preview-body :deep(h3) {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: 1.2em; font-weight: 600;
  margin: 0.7em 0 0.3em;
}
.preview-body :deep(h4) {
  font-family: var(--font-serif-zh), var(--font-serif);
  font-size: 1.1em; font-weight: 600;
  margin: 0.5em 0 0.2em;
}
.preview-body :deep(p) { margin: 0.6em 0; }
.preview-body :deep(ul), .preview-body :deep(ol) { padding-left: 2em; margin: 0.5em 0; }
.preview-body :deep(blockquote) { border-left: 3px solid var(--c-accent); padding-left: 1em; margin: 0.8em 0; color: var(--text-secondary); }
.preview-body :deep(code) { background: var(--code-bg); padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
.preview-body :deep(pre) { background: var(--code-bg); padding: 1em; border-radius: 6px; overflow-x: auto; margin: 0.8em 0; }
.preview-body :deep(pre code) { background: none; padding: 0; }
.preview-body :deep(table) { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
.preview-body :deep(th), .preview-body :deep(td) { border: 1px solid var(--border-color); padding: 0.5em 0.8em; text-align: left; }
.preview-body :deep(th) { background: var(--code-bg); font-weight: 600; }
.preview-body :deep(img) { max-width: 100%; border-radius: 4px; }
.preview-body :deep(a) { color: var(--c-accent); text-decoration: none; }
.preview-body :deep(a:hover) { text-decoration: underline; }
.preview-body :deep(.empty-hint) { color: var(--text-secondary); font-style: italic; }
.preview-body :deep(.math-error) { color: var(--c-danger); background: var(--c-danger-bg); padding: 2px 6px; border-radius: 3px; }

/* KaTeX display math centering */
.preview-body :deep(.katex-display) {
  margin: 1em 0;
  overflow-x: auto;
  overflow-y: hidden;
}
</style>
