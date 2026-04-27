/**
 * Tests for the markdown rendering pipeline used in App.vue.
 *
 * The renderMarkdown function does:
 *   1. HTML-escape the raw input (XSS prevention)
 *   2. Convert markdown constructs to HTML
 *   3. Sanitize the result with DOMPurify
 *
 * We replicate that logic here so the test is self-contained and does not
 * depend on the Vue component runtime.
 */
import { describe, it, expect, beforeAll } from 'vitest'
import createDOMPurify from 'dompurify'
import { JSDOM } from 'jsdom'

let DOMPurify: ReturnType<typeof createDOMPurify>

beforeAll(() => {
  const dom = new JSDOM('')
  DOMPurify = createDOMPurify(dom.window)
})

// ---------------------------------------------------------------------------
// Re-implement the escape + render logic from App.vue (lines 1086-1138)
// ---------------------------------------------------------------------------

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderMarkdown(md: string): string {
  // Step 1: HTML escape everything
  md = escapeHtml(md)

  const extracted: string[] = []

  function extract(re: RegExp, processor: (m: RegExpMatchArray) => string): void {
    md = md.replace(re, (...args) => {
      const ph = `\x00EX${extracted.length}\x00`
      extracted.push(processor(args as unknown as RegExpMatchArray))
      return ph
    })
  }

  // Step 2: Markdown → HTML (same order as App.vue)

  // Blockquotes (already escaped to &gt;)
  extract(/^(?:&gt;)+\s*(.+(?:(?:\n|^)(?:&gt;)+\s*.+)*)/gm, (m) => {
    const lines = m[1].replace(/^(?:&gt;)+\s?/gm, '').split('\n')
    const content = lines
      .map(l => l.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'))
      .join('<br/>')
    return `<blockquote>${content}</blockquote>`
  })

  md = md.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  md = md.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  md = md.replace(/^# (.+)$/gm, '<h1>$1</h1>')
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  md = md.replace(/^---$/gm, '<hr/>')

  // Restore extracted blocks
  md = md.replace(/\x00EX(\d+)\x00/g, (_: string, idx: string) => extracted[parseInt(idx)])

  // Paragraph wrapping
  md = md.replace(/\n{2,}/g, '</p><p>')
  md = md.replace(/\n/g, '<br/>')
  md = `<p>${md}</p>`

  // Clean up empty/unnecessary wrappers
  md = md.replace(/<p>\s*(<h[1-3]>)/g, '$1')
  md = md.replace(/(<\/h[1-3]>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*(<blockquote>)/g, '$1')
  md = md.replace(/(<\/blockquote>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*(<hr\/>)/g, '$1')
  md = md.replace(/(<hr\/>)\s*<\/p>/g, '$1')
  md = md.replace(/<p>\s*<\/p>/g, '')

  // Step 3: Sanitize with DOMPurify
  return DOMPurify.sanitize(md)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('renderMarkdown', () => {
  // ── Headers ──────────────────────────────────────────────────────────
  describe('headers', () => {
    it('renders h1', () => {
      const result = renderMarkdown('# Title')
      expect(result).toContain('<h1>Title</h1>')
    })

    it('renders h2', () => {
      const result = renderMarkdown('## Section')
      expect(result).toContain('<h2>Section</h2>')
    })

    it('renders h3', () => {
      const result = renderMarkdown('### Subsection')
      expect(result).toContain('<h3>Subsection</h3>')
    })

    it('does not confuse # inside text with a header', () => {
      const result = renderMarkdown('use # channel 5')
      // The # is not at the start of a line, so no header
      expect(result).not.toContain('<h1>')
      expect(result).toContain('#')
    })
  })

  // ── Bold ─────────────────────────────────────────────────────────────
  describe('bold and italic', () => {
    it('renders **bold** as <strong>', () => {
      const result = renderMarkdown('This is **important** text')
      expect(result).toContain('<strong>important</strong>')
    })

    it('handles multiple bold sections', () => {
      const result = renderMarkdown('**a** and **b**')
      expect(result).toContain('<strong>a</strong>')
      expect(result).toContain('<strong>b</strong>')
    })
  })

  // ── Blockquotes ──────────────────────────────────────────────────────
  describe('blockquotes', () => {
    it('renders > quoted text as blockquote', () => {
      const result = renderMarkdown('> This is a quote')
      expect(result).toContain('<blockquote>')
      expect(result).toContain('This is a quote')
      expect(result).toContain('</blockquote>')
    })

    it('renders multi-line blockquotes', () => {
      const result = renderMarkdown('> Line one\n> Line two')
      expect(result).toContain('<blockquote>')
      expect(result).toContain('Line one')
      expect(result).toContain('Line two')
    })

    it('supports bold inside blockquotes', () => {
      const result = renderMarkdown('> This is **bold** in a quote')
      expect(result).toContain('<blockquote>')
      expect(result).toContain('<strong>bold</strong>')
    })
  })

  // ── Horizontal rules ─────────────────────────────────────────────────
  describe('horizontal rules', () => {
    it('renders --- as <hr>', () => {
      const result = renderMarkdown('above\n\n---\n\nbelow')
      // DOMPurify normalizes self-closing <hr/> to <hr>
      expect(result).toContain('<hr>')
    })
  })

  // ── Paragraphs and line breaks ───────────────────────────────────────
  describe('paragraphs and line breaks', () => {
    it('wraps content in <p> tags', () => {
      const result = renderMarkdown('Hello world')
      expect(result).toContain('<p>')
      expect(result).toContain('Hello world')
    })

    it('converts double newlines to paragraph breaks', () => {
      const result = renderMarkdown('First para\n\nSecond para')
      expect(result).toContain('</p><p>')
    })

    it('converts single newlines to <br>', () => {
      const result = renderMarkdown('Line 1\nLine 2')
      // DOMPurify normalizes self-closing <br/> to <br>
      expect(result).toContain('<br>')
    })
  })

  // ── Empty / edge case input ──────────────────────────────────────────
  describe('empty and edge case input', () => {
    it('returns sanitized output for empty string', () => {
      const result = renderMarkdown('')
      // Should be valid sanitized HTML (empty or empty paragraph)
      expect(result).toBeTypeOf('string')
      expect(result).not.toContain('<script>')
    })

    it('handles whitespace-only input', () => {
      const result = renderMarkdown('   \n\n   ')
      expect(result).toBeTypeOf('string')
    })
  })

  // ── Special characters ───────────────────────────────────────────────
  describe('special characters', () => {
    it('escapes ampersands', () => {
      const result = renderMarkdown('Tom & Jerry')
      expect(result).toContain('&amp;')
      expect(result).not.toContain('Tom & Jerry')
    })

    it('escapes angle brackets', () => {
      const result = renderMarkdown('5 < 10 > 3')
      expect(result).toContain('&lt;')
      expect(result).toContain('&gt;')
      expect(result).not.toContain('5 < 10')
    })

    it('escapes double quotes into the output safely', () => {
      const result = renderMarkdown('She said "hello"')
      // After escapeHtml + DOMPurify, quotes appear as literal characters
      // (DOMPurify decodes &quot; in safe text context). The key is that
      // no HTML attribute injection is possible.
      expect(result).toContain('hello')
      expect(result).not.toContain('<script')
    })

    it('escapes single quotes into the output safely', () => {
      const result = renderMarkdown("it's fine")
      // DOMPurify decodes &#39; in safe text context
      expect(result).toContain('fine')
      expect(result).not.toContain('<script')
    })
  })

  // ── XSS security ─────────────────────────────────────────────────────
  describe('XSS prevention', () => {
    it('escapes <script> tags so they are not executed', () => {
      const result = renderMarkdown('<script>alert("xss")</script>hello')
      // escapeHtml turns <script> into &lt;script&gt;, so no actual script tag exists
      expect(result).not.toContain('<script>')
      expect(result).toContain('&lt;script&gt;')
      expect(result).toContain('hello')
    })

    it('escapes <iframe> tags so they are not rendered', () => {
      const result = renderMarkdown('<iframe src="evil.com"></iframe>safe')
      // After escaping, there are no real HTML tags, only escaped text
      expect(result).not.toContain('<iframe')
      expect(result).toContain('safe')
    })

    it('escapes onclick attributes so they cannot fire', () => {
      const result = renderMarkdown('<div onclick="alert(1)">click</div>')
      // The div and onclick are escaped to text — not executable
      expect(result).not.toContain('<div')
      expect(result).toContain('&lt;div')
    })

    it('escapes onerror attributes on images', () => {
      const result = renderMarkdown('<img src="x" onerror="alert(1)">')
      // The img tag is fully escaped — not an actual element
      expect(result).not.toContain('<img')
      expect(result).toContain('&lt;img')
    })

    it('escapes javascript: URLs in anchor tags', () => {
      const result = renderMarkdown('<a href="javascript:alert(1)">link</a>')
      // The a tag is fully escaped — not a real link
      expect(result).not.toContain('<a ')
      expect(result).toContain('&lt;a')
    })

    it('escapes <style> tags so they cannot apply', () => {
      const result = renderMarkdown('<style>body{display:none}</style>visible')
      expect(result).not.toContain('<style>')
      expect(result).toContain('visible')
    })

    it('handles nested script injection', () => {
      const result = renderMarkdown('<<script>script>alert(1)</script>')
      expect(result).not.toContain('<script>')
    })

    it('escapes SVG-based XSS payloads', () => {
      const result = renderMarkdown('<svg onload="alert(1)"><circle/></svg>')
      // SVG is escaped — no real SVG element
      expect(result).not.toContain('<svg')
      expect(result).toContain('&lt;svg')
    })
  })
})
