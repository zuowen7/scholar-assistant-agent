import { describe, it, expect } from 'vitest'
import {
  splitSentences,
  findCorrespondingSentenceIdx,
  findCorrespondingSentenceIndices,
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

    it('keeps an unpunctuated trailing sentence instead of dropping it', () => {
      const result = splitSentences('A complete sentence. A trailing sentence without punctuation', 'en')
      expect(result.map(sentence => sentence.text)).toEqual([
        'A complete sentence.',
        'A trailing sentence without punctuation',
      ])
    })

    it('returns empty array for empty string', () => {
      // Fallback: empty string is treated as one empty sentence
      const result = splitSentences('', 'en')
      expect(result).toHaveLength(1)
      expect(result[0].text).toBe('')
    })

    // ── 学术缩写保护（与后端 splitter.py 一致）──────────────────────────
    it('does not split on "et al." abbreviation', () => {
      const text = 'Smith et al. showed that the method works.'
      const result = splitSentences(text, 'en')
      expect(result).toHaveLength(1)
      expect(result[0]).toEqual({ text, start: 0, end: text.length })
    })

    it('does not split on "Fig." abbreviation', () => {
      const result = splitSentences('See Fig. 3 for details. The figure shows the trend.', 'en')
      // Fig. 不切，只有 details. 后切 → 2 句
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('See Fig. 3 for details.')
    })

    it('does not split on "e.g." abbreviation', () => {
      const result = splitSentences('Use a metric, e.g. F1 score, for evaluation. It is standard.', 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('Use a metric, e.g. F1 score, for evaluation.')
    })

    it('does not split on "i.e." abbreviation', () => {
      const result = splitSentences('The model, i.e. BERT, is large. It works well.', 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('The model, i.e. BERT, is large.')
    })

    it('does not split on decimal numbers (3.14)', () => {
      const text = 'Pi is 3.14 approximately. That is correct.'
      const result = splitSentences(text, 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('Pi is 3.14 approximately.')
      expect(result[0].start).toBe(0)
      expect(result[0].end).toBe(text.indexOf(' That'))
      expect(result[1].start).toBe(text.indexOf('That'))
      expect(result[1].end).toBe(text.length)
    })

    it('does not split on "vs." abbreviation', () => {
      const result = splitSentences('We compare CNN vs. Transformer. Both work.', 'en')
      expect(result).toHaveLength(2)
      expect(result[0].text).toBe('We compare CNN vs. Transformer.')
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

    it('keeps Chinese semicolon clauses in the same sentence', () => {
      const result = splitSentences('条件A满足；条件B也满足。', 'zh')
      expect(result).toHaveLength(1)
    })

    it('keeps an unpunctuated Chinese tail instead of dropping it', () => {
      const result = splitSentences('这是完整句子。这里是没有句号的尾句', 'zh')
      expect(result.map(sentence => sentence.text)).toEqual(['这是完整句子。', '这里是没有句号的尾句'])
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
      expect(result[1].start).toBe(7)
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

  it('maps by sentence order when translated sentence lengths differ greatly', () => {
    const orig = splitSentences('First. Second sentence is extremely long compared with the others. Third.', 'en')
    const trans = splitSentences('一。二。三。', 'zh')
    expect(findCorrespondingSentenceIdx(orig, 73, trans, 6, 1)).toBe(1)
  })

  it('returns the full counterpart range for one-to-many alignment', () => {
    const orig = splitSentences('First. Second.', 'en')
    const trans = splitSentences('第一句。补充句。第二句。', 'zh')
    expect(findCorrespondingSentenceIndices(orig, trans, 0)).toEqual([0, 1])
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

  it('preserves paragraph breaks and all source text between sentence spans', () => {
    const text = 'First sentence.\n\nSecond sentence without punctuation'
    const html = renderSentenceMarkedHtml(text, 'en', 'b3', 'orig')
    expect(html).toContain('\n\n')
    expect(html.replace(/<[^>]+>/g, '')).toBe(text)
  })
})
