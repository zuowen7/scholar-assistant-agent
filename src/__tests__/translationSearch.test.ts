import { describe, expect, it } from 'vitest'
import { filterTranslationBlocks } from '../utils/translationSearch'

const blocks = [
  { original: 'Reliable evidence supports this claim.', translated: '可靠证据支持这一主张。' },
  { original: 'The method is reproducible.', translated: '该方法可以复现。' },
  { original: 'No translated content yet.', translated: '' },
]

describe('filterTranslationBlocks', () => {
  it('returns every block for an empty query without mutating the source array', () => {
    const result = filterTranslationBlocks(blocks, '   ')

    expect(result).toEqual(blocks)
    expect(result).not.toBe(blocks)
  })

  it('matches original and translated text case-insensitively', () => {
    expect(filterTranslationBlocks(blocks, 'RELIABLE')).toEqual([blocks[0]])
    expect(filterTranslationBlocks(blocks, '可以复现')).toEqual([blocks[1]])
  })

  it('returns an empty result when no real block contains the query', () => {
    expect(filterTranslationBlocks(blocks, '不存在的术语')).toEqual([])
  })
})
