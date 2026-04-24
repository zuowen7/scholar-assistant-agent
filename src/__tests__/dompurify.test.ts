import { describe, it, expect, beforeAll } from 'vitest'
import createDOMPurify from 'dompurify'
import { JSDOM } from 'jsdom'

let DOMPurify: ReturnType<typeof createDOMPurify>

beforeAll(() => {
  const dom = new JSDOM('')
  DOMPurify = createDOMPurify(dom.window)
})

describe('DOMPurify integration', () => {
  it('strips script tags', () => {
    const result = DOMPurify.sanitize('<script>alert("xss")</script><p>safe</p>')
    expect(result).not.toContain('<script>')
    expect(result).toContain('<p>safe</p>')
  })

  it('strips onclick handlers', () => {
    const result = DOMPurify.sanitize('<img src="x" onerror="alert(1)">')
    expect(result).not.toContain('onerror')
  })

  it('preserves safe HTML', () => {
    const result = DOMPurify.sanitize('<strong>bold</strong> <em>italic</em>')
    expect(result).toContain('<strong>bold</strong>')
    expect(result).toContain('<em>italic</em>')
  })

  it('strips iframe tags', () => {
    const result = DOMPurify.sanitize('<iframe src="evil.com"></iframe><p>ok</p>')
    expect(result).not.toContain('<iframe')
    expect(result).toContain('<p>ok</p>')
  })
})
