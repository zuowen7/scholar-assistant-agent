import { describe, it, expect } from 'vitest'
import {
  splitSentences,
  findCorrespondingSentenceIdx,
  renderSentenceMarkedHtml,
} from '../utils/sentenceAlign'

// ---------------------------------------------------------------------------
// splitSentences
// ---------------------------------------------------------------------------
describe('splitSentences', () => {
  describe('English text', () => {
    it('splits on period followed by space and capital letter', () => {
      const result = splitSentences('First sentence. Second sentence.', 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('First sentence.')
      expect(result[1].text).toBe('Second sentence.')
    })

    it('splits on question mark', () => {
      const result = splitSentences('What time is it? The meeting starts at noon.', 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('What time is it?')
    })

    it('splits on exclamation mark', () => {
      const result = splitSentences('Run! Save yourself!', 'en')
      expect(result).toHaveLength(2)
    })

    it('handles closing quotes after punctuation', () => {
      const result = splitSentences('He said "hello." She replied "hi."', 'en')
      expect(result).toHaveLength(2)
    })

    it('returns single sentence when no punctuation present', () => {
      const result = splitSentences('just a phrase without ending', 'en')
      expect(result).toHaveLength(1)
      expect(result[0].text).toBe('just a phrase without ending')
    })

    it('returns empty array for empty string', () => {
      // Fallback: empty string is treated as one empty sentence
      const result = splitSentences('', 'en')
      expect(result).toHaveLength(1)
      expect(result[0].text).toBe('')
    })
  })

  describe('Chinese text', () => {
    it('splits on Chinese period 。', () => {
      const result = splitSentences('这是第一句话。这是第二句话。', 'zh')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('这是第一句话。')
      expect(result[1].text).toBe('这是第二句话。')
    })

    it('splits on Chinese exclamation ！', () => {
      const result = splitSentences('注意！这里很重要！', 'zh')
      expect(result).toHaveLength(2)
    })

    it('splits on Chinese question ？', () => {
      const result = splitSentences('你确定吗？我们核实一下。', 'zh')
      expect(result).toHaveLength(2)
    })

    it('splits on Chinese semicolon ；', () => {
      const result = splitSentences('条件A满足；条件B也满足。', 'zh')
      expect(result).toHaveLength(2)
    })

    it('returns single sentence for undelimited text', () => {
      const result = splitSentences('这一段没有任何标点符号', 'zh')
      expect(result).toHaveLength(1)
    })
  })

  describe('sentence position tracking', () => {
    it('records correct start and end positions', () => {
      const text = 'Alpha. Beta.'
      const result = splitSentences(text, 'en')
      expect(result[0].start).toBe(0)
      expect(result[0].end).toBe(6)
      expect(result[1].start).toBe(6)
      expect(result[1].end).toBe(12)
    })
  })
})

// ---------------------------------------------------------------------------
// findCorrespondingSentenceIdx
// ---------------------------------------------------------------------------
describe('findCorrespondingSentenceIdx', () => {
  it('maps first sentence of equal-length texts', () => {
    const orig = splitSentences('A. B. C.', 'en')
    const trans = splitSentences('X. Y. Z.', 'en')
    const idx = findCorrespondingSentenceIdx(orig, 8, trans, 8, 0)
    expect(idx).toBe(0)
  })

  it('maps last sentence of equal-length texts', () => {
    const orig = splitSentences('A. B. C.', 'en')
    const trans = splitSentences('X. Y. Z.', 'en')
    const idx = findCorrespondingSentenceIdx(orig, 8, trans, 8, 2)
    expect(idx).toBe(2)
  })

  it('maps middle sentence proportionally', () => {
    const orig = splitSentences('Short. Very long sentence here. Short.', 'en')
    const trans = splitSentences('Short. Also very long translation here. Short.', 'en')
    const idx = findCorrespondingSentenceIdx(orig, 39, trans, 41, 1)
    expect(idx).toBeGreaterThanOrEqual(0)
    expect(idx).toBeLessThan(3)
  })

  it('returns -1 for out-of-range index', () => {
    const orig = splitSentences('A. B.', 'en')
    const trans = splitSentences('X. Y.', 'en')
    expect(findCorrespondingSentenceIdx(orig, 5, trans, 5, -1)).toBe(-1)
    expect(findCorrespondingSentenceIdx(orig, 5, trans, 5, 5)).toBe(-1)
  })

  it('returns -1 when translation has no sentences', () => {
    const orig = splitSentences('A. B.', 'en')
    expect(findCorrespondingSentenceIdx(orig, 5, [], 0, 0)).toBe(-1)
  })
})

// ---------------------------------------------------------------------------
// renderSentenceMarkedHtml
// ---------------------------------------------------------------------------
describe('renderSentenceMarkedHtml', () => {
  it('returns escaped plain text for single-sentence input', () => {
    const html = renderSentenceMarkedHtml('No punctuation', 'en', 'block-1', 'orig')
    expect(html).toBe('No punctuation')
  })

  it('wraps sentences in span tags with data attributes', () => {
    const html = renderSentenceMarkedHtml('First. Second.', 'en', 'block-1', 'orig')
    expect(html).toContain('data-sent-idx="0"')
    expect(html).toContain('data-sent-idx="1"')
    expect(html).toContain('data-block-id="block-1"')
    expect(html).toContain('data-side="orig"')
  })

  it('escapes HTML in text content', () => {
    const html = renderSentenceMarkedHtml('<script>alert(1)</script>. Safe.', 'en', 'b1', 'trans')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })

  it('sets data-side correctly for translation side', () => {
    const html = renderSentenceMarkedHtml('Hola. Mundo.', 'en', 'b2', 'trans')
    expect(html).toContain('data-side="trans"')
  })
})
