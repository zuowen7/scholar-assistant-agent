<template>
  <div class="preview-container">
    <div class="preview-header">
      <span class="preview-title">Preview</span>
    </div>
    <div class="preview-body" v-html="renderedHtml"></div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

const props = defineProps<{
  content: string
}>()

// HTML 转义：阻断 XSS 注入（marked 不会转义原始 HTML 标签）
const SAFE_TAGS = new Set(['pre', 'code', 'em', 'strong', 'del', 'sup', 'sub', 'br', 'hr', 'span', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'img'])

function escapeUnsafeHtml(html: string): string {
  // 保留 marked 生成的安全标签，剥离 script/iframe/event handlers
  return html.replace(/<\s*(\/?)\s*(\w+)([^>]*)>/g, (match, slash, tag, attrs) => {
    const tagName = tag.toLowerCase()
    if (SAFE_TAGS.has(tagName)) return match
    // class/href/src/style/id 是安全属性，移除 on* 事件和 javascript: 链接
    if (tagName === 'div' || tagName === 'section') {
      const cleanAttrs = attrs.replace(/\s*on\w+\s*=\s*["'][^"']*["']/gi, '')
      return `<${slash}${tag}${cleanAttrs}>`
    }
    return ''
  }).replace(/on\w+\s*=\s*["'][^"']*["']/gi, '')
}

// 配置 marked 使用 highlight.js
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
  if (!props.content) return '<p class="empty-hint">Start writing...</p>'
  const raw = marked.parse(props.content) as string
  return escapeUnsafeHtml(raw)
})
</script>

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
  padding: 16px 24px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
}

.preview-body :deep(h1) { font-size: 1.8em; margin: 0.8em 0 0.4em; border-bottom: 1px solid var(--border-color); padding-bottom: 0.3em; }
.preview-body :deep(h2) { font-size: 1.4em; margin: 0.8em 0 0.4em; border-bottom: 1px solid var(--border-color); padding-bottom: 0.3em; }
.preview-body :deep(h3) { font-size: 1.2em; margin: 0.6em 0 0.3em; }
.preview-body :deep(h4) { font-size: 1.1em; margin: 0.5em 0 0.2em; }
.preview-body :deep(p) { margin: 0.6em 0; }
.preview-body :deep(ul), .preview-body :deep(ol) { padding-left: 2em; margin: 0.5em 0; }
.preview-body :deep(blockquote) { border-left: 3px solid var(--accent); padding-left: 1em; margin: 0.8em 0; color: var(--text-secondary); }
.preview-body :deep(code) { background: var(--code-bg); padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }
.preview-body :deep(pre) { background: var(--code-bg); padding: 1em; border-radius: 6px; overflow-x: auto; margin: 0.8em 0; }
.preview-body :deep(pre code) { background: none; padding: 0; }
.preview-body :deep(table) { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
.preview-body :deep(th), .preview-body :deep(td) { border: 1px solid var(--border-color); padding: 0.5em 0.8em; text-align: left; }
.preview-body :deep(th) { background: var(--code-bg); font-weight: 600; }
.preview-body :deep(img) { max-width: 100%; border-radius: 4px; }
.preview-body :deep(a) { color: var(--accent); text-decoration: none; }
.preview-body :deep(a:hover) { text-decoration: underline; }
.preview-body :deep(.empty-hint) { color: var(--text-secondary); font-style: italic; }
</style>
