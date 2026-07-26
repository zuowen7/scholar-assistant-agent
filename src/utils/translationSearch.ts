import type { BlockData } from '../types'

export function filterTranslationBlocks<T extends Pick<BlockData, 'original' | 'translated'>>(
  blocks: readonly T[],
  rawQuery: string,
): T[] {
  const query = rawQuery.trim().toLocaleLowerCase()
  if (!query) return [...blocks]

  return blocks.filter((block) => {
    const searchableText = `${block.original}\n${block.translated || ''}`.toLocaleLowerCase()
    return searchableText.includes(query)
  })
}
