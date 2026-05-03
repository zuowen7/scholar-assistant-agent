/**
 * Markdown 渲染工具——封装 marked + KaTeX + DOMPurify
 *
 * 替代 TranslateView 里手写的正则 markdown，正确处理：
 * - 代码块（``` ... ```）
 * - LaTeX 公式（$...$ inline / $$...$$ display）
 * - 表格 | --- |
 * - 标题层级
 * - 列表（有序/无序）
 * - 引用块
 *
 * 所有输出经 DOMPurify 净化，防止 XSS。
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import katex from 'katex'

// 配置 marked：GFM 风格、换行换段、安全转义
marked.use({
  gfm: true,
  breaks: false,
})

// 占位符：用 ASCII 控制字符避免与正文冲突
const MATH_DISPLAY_PLACEHOLDER = (i: number) => `\x00MATHD${i}\x00`
const MATH_INLINE_PLACEHOLDER = (i: number) => `\x00MATHI${i}\x00`

interface MathSlot {
  index: number
  display: boolean
  rendered: string
}

function extractAndRenderMath(src: string): { protectedText: string; slots: MathSlot[] } {
  const slots: MathSlot[] = []
  let counter = 0

  // 先取 display 公式 $$...$$（贪婪但非跨段）
  let working = src.replace(/\$\$([\s\S]+?)\$\$/g, (_, inner) => {
    const idx = counter++
    let html = ''
    try {
      html = katex.renderToString(inner.trim(), { displayMode: true, throwOnError: false })
    } catch {
      html = `<pre class="math-error">$$${escapeHtml(inner)}$$</pre>`
    }
    slots.push({ index: idx, display: true, rendered: html })
    return MATH_DISPLAY_PLACEHOLDER(idx)
  })

  // \[ ... \] 也作为 display
  working = working.replace(/\\\[([\s\S]+?)\\\]/g, (_, inner) => {
    const idx = counter++
    let html = ''
    try {
      html = katex.renderToString(inner.trim(), { displayMode: true, throwOnError: false })
    } catch {
      html = `<pre class="math-error">\\[${escapeHtml(inner)}\\]</pre>`
    }
    slots.push({ index: idx, display: true, rendered: html })
    return MATH_DISPLAY_PLACEHOLDER(idx)
  })

  // inline $...$（避开货币符号：要求不被数字紧紧包围）
  working = working.replace(/(?<![\\$])\$([^$\n]+?)\$(?!\d)/g, (_, inner) => {
    const idx = counter++
    let html = ''
    try {
      html = katex.renderToString(inner.trim(), { displayMode: false, throwOnError: false })
    } catch {
      html = `<code class="math-error">$${escapeHtml(inner)}$</code>`
    }
    slots.push({ index: idx, display: false, rendered: html })
    return MATH_INLINE_PLACEHOLDER(idx)
  })

  return { protectedText: working, slots }
}

function restoreMath(html: string, slots: MathSlot[]): string {
  let out = html
  for (const slot of slots) {
    const ph = slot.display
      ? MATH_DISPLAY_PLACEHOLDER(slot.index)
      : MATH_INLINE_PLACEHOLDER(slot.index)
    out = out.split(ph).join(slot.rendered)
  }
  return out
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * 把 markdown 字符串渲染为安全 HTML，含 KaTeX 公式
 */
export function renderMarkdown(src: string): string {
  if (!src) return ''
  const { protectedText, slots } = extractAndRenderMath(src)
  // marked.parse 同步模式
  const html = marked.parse(protectedText, { async: false }) as string
  const withMath = restoreMath(html, slots)
  return DOMPurify.sanitize(withMath, {
    ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'annotation', 'semantics'],
    ADD_ATTR: ['class', 'style', 'aria-hidden', 'data-mtype'],
  })
}

/**
 * 把单个块（已知 type）渲染为 HTML
 * 用于按块呈现时，根据类型选择渲染方式
 */
export function renderBlock(text: string, type: string): string {
  if (!text) return ''
  // 不可翻译块（公式/代码/表格）也走完整 markdown 渲染（KaTeX 会处理 $$...$$）
  return renderMarkdown(text)
}
