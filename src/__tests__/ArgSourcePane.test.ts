/**
 * Phase 3 TDD — span↔node mapping unit tests (useArgumentMap Phase 3 extensions).
 *
 * Tests:
 * - focusNode / focusSpan → highlightNodeIds updates
 * - setPastedSource / loadSourceFromTranslation / loadSourceFromEditor → source state
 * - _resetForTesting clears all Phase 3 state
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../utils/api', () => ({ API_BASE: 'http://127.0.0.1:18088' }))

vi.mock('../composables/useTranslate', () => ({
  useTranslate: () => ({
    state: {
      blocks: [
        { id: 'b1', type: 'paragraph', translatable: true, original: 'Original text.', translated: '翻译文本。', status: 'ok' },
        { id: 'b2', type: 'paragraph', translatable: true, original: 'Another block.', translated: '另一段文字。', status: 'ok' },
      ],
    },
  }),
}))

vi.mock('../composables/useEditor', () => ({
  useEditor: () => ({
    activeTab: {
      value: {
        id: 'tab1',
        name: 'test.md',
        content: '# Hello\nThis is the editor content.',
        isModified: false,
        path: '/test.md',
      },
    },
  }),
}))

import {
  useArgumentMap,
  _resetForTesting,
  focusNode,
  focusSpan,
  setPastedSource,
  loadSourceFromTranslation,
  loadSourceFromEditor,
} from '../composables/useArgumentMap'
import type { ArgGraph, SpanMapping } from '../composables/useArgumentMap'

function makeSpan(partial: Partial<SpanMapping> = {}): SpanMapping {
  return {
    id: 'sp_1',
    node_id: 'n_1',
    source_type: 'selection',
    side: 'trans',
    quote: 'Test quote',
    ...partial,
  }
}

function makeGraph(spans: SpanMapping[] = []): ArgGraph {
  return {
    id: 'g1',
    title: 'Test Graph',
    nodes: [],
    edges: [],
    spans,
    issues: [],
    created_at: 0,
    updated_at: 0,
  }
}

// ── focusNode ──────────────────────────────────────────────────────────────────

describe('focusNode', () => {
  beforeEach(() => _resetForTesting())

  it('sets highlightNodeIds to [nodeId]', () => {
    const { state } = useArgumentMap()
    focusNode('n_abc')
    expect(state.highlightNodeIds).toEqual(['n_abc'])
  })

  it('empty string clears highlightNodeIds', () => {
    const { state } = useArgumentMap()
    focusNode('n_abc')
    focusNode('')
    expect(state.highlightNodeIds).toEqual([])
  })

  it('overwrites previous highlight', () => {
    const { state } = useArgumentMap()
    focusNode('n_1')
    focusNode('n_2')
    expect(state.highlightNodeIds).toEqual(['n_2'])
    expect(state.highlightNodeIds).not.toContain('n_1')
  })
})

// ── focusSpan ──────────────────────────────────────────────────────────────────

describe('focusSpan', () => {
  beforeEach(() => _resetForTesting())

  it('sets highlightNodeIds from span.node_id', () => {
    const { state } = useArgumentMap()
    state.graph = makeGraph([makeSpan({ id: 'sp_1', node_id: 'n_target' })])
    focusSpan('sp_1')
    expect(state.highlightNodeIds).toContain('n_target')
  })

  it('does nothing when span not found', () => {
    const { state } = useArgumentMap()
    state.graph = makeGraph([])
    state.highlightNodeIds = ['n_existing']
    focusSpan('sp_unknown')
    expect(state.highlightNodeIds).toEqual(['n_existing'])
  })

  it('works when graph has multiple spans', () => {
    const { state } = useArgumentMap()
    state.graph = makeGraph([
      makeSpan({ id: 'sp_1', node_id: 'n_A' }),
      makeSpan({ id: 'sp_2', node_id: 'n_B' }),
    ])
    focusSpan('sp_2')
    expect(state.highlightNodeIds).toContain('n_B')
    expect(state.highlightNodeIds).not.toContain('n_A')
  })
})

// ── setPastedSource ────────────────────────────────────────────────────────────

describe('setPastedSource', () => {
  beforeEach(() => _resetForTesting())

  it('sets mode=paste and text', () => {
    const { state } = useArgumentMap()
    setPastedSource('Hello world.')
    expect(state.source.mode).toBe('paste')
    expect(state.source.text).toBe('Hello world.')
  })

  it('clears blocks array', () => {
    const { state } = useArgumentMap()
    setPastedSource('text')
    expect(state.source.blocks).toHaveLength(0)
  })

  it('sets custom label', () => {
    const { state } = useArgumentMap()
    setPastedSource('text', '自定义来源')
    expect(state.source.label).toBe('自定义来源')
  })

  it('uses default label when not provided', () => {
    const { state } = useArgumentMap()
    setPastedSource('text')
    expect(state.source.label).toBeTruthy()
  })
})

// ── loadSourceFromTranslation ──────────────────────────────────────────────────

describe('loadSourceFromTranslation', () => {
  beforeEach(() => _resetForTesting())

  it('sets mode=translation', () => {
    const { state } = useArgumentMap()
    loadSourceFromTranslation()
    expect(state.source.mode).toBe('translation')
  })

  it('populates blocks from useTranslate state', () => {
    const { state } = useArgumentMap()
    loadSourceFromTranslation()
    expect(state.source.blocks.length).toBeGreaterThan(0)
    expect(state.source.blocks[0].id).toBe('b1')
    expect(state.source.blocks[1].id).toBe('b2')
  })

  it('sets side=trans', () => {
    const { state } = useArgumentMap()
    loadSourceFromTranslation()
    expect(state.source.side).toBe('trans')
  })

  it('builds text from translated content', () => {
    const { state } = useArgumentMap()
    loadSourceFromTranslation()
    expect(state.source.text).toContain('翻译文本')
  })
})

// ── loadSourceFromEditor ───────────────────────────────────────────────────────

describe('loadSourceFromEditor', () => {
  beforeEach(() => _resetForTesting())

  it('sets mode=editor', () => {
    const { state } = useArgumentMap()
    loadSourceFromEditor()
    expect(state.source.mode).toBe('editor')
  })

  it('sets text from active tab content', () => {
    const { state } = useArgumentMap()
    loadSourceFromEditor()
    expect(state.source.text).toContain('Hello')
  })

  it('sets label from tab name', () => {
    const { state } = useArgumentMap()
    loadSourceFromEditor()
    expect(state.source.label).toBe('test.md')
  })

  it('clears blocks array', () => {
    const { state } = useArgumentMap()
    loadSourceFromEditor()
    expect(state.source.blocks).toHaveLength(0)
  })
})

// ── _resetForTesting clears Phase 3 state ────────────────────────────────────

describe('_resetForTesting clears Phase 3 state', () => {
  it('resets highlightNodeIds, hoveredSpanId, and source', () => {
    const { state } = useArgumentMap()
    focusNode('n_1')
    setPastedSource('some text', 'my label')
    state.hoveredSpanId = 'sp_xyz'
    _resetForTesting()
    expect(state.highlightNodeIds).toEqual([])
    expect(state.hoveredSpanId).toBe('')
    expect(state.source.text).toBe('')
    expect(state.source.mode).toBe('paste')
    expect(state.source.blocks).toHaveLength(0)
  })
})
