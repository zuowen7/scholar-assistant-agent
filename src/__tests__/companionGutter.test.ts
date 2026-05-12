/**
 * Phase 2 TDD — companionGutter pure-function unit tests.
 *
 * Tests cover:
 * - Only unpaid/mismatch/partial promises produce glyph decorations
 * - paid promises produce no glyph
 * - lost anchors produce no glyph (can't compute line)
 * - open review points produce glyphs at their anchor line
 * - hover message contains note text
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('monaco-editor', () => ({
  Range: class Range {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  },
  editor: {},
}))

vi.mock('../utils/api', () => ({ API_BASE: 'http://127.0.0.1:18088' }))

import { computeCompanionDecorations } from '../composables/companionGutter'

// ── helpers ─────────────────────────────────────────────────────────────────

function makeAnchor(id: string, charStart: number | null, status = 'anchored') {
  return {
    id,
    doc_id: 'doc1',
    char_start: charStart,
    char_end: charStart !== null ? charStart + 20 : null,
    quote: 'some quote',
    context_before: '',
    context_after: '',
    section_path: null,
    status,
  }
}

function makePromise(
  id: string,
  status: string,
  sourceAnchorId: string,
  note?: string,
) {
  return {
    id,
    text: `Promise text for ${id}`,
    kind: 'contribution',
    source_anchor_id: sourceAnchorId,
    discharge_anchor_ids: [],
    status,
    severity: status === 'unpaid' || status === 'mismatch' ? 'error' : 'warning',
    note: note ?? null,
    created_by: 'ai',
    user_overridden: false,
  }
}

function makeReviewPoint(id: string, anchorId: string | null, status: string, severity: string) {
  return {
    id,
    severity,
    category: 'baseline',
    title: `Review point ${id}`,
    detail: 'Some detail text',
    anchor_id: anchorId,
    status,
    source: 'llm',
    reviewer_label: null,
    thread: [],
  }
}

/** Mock monaco model that returns line number based on char offset. */
function makeMockModel(lineMap: Record<number, number>) {
  return {
    getPositionAt: (offset: number) => ({
      lineNumber: lineMap[offset] ?? Math.floor(offset / 10) + 1,
      column: 1,
    }),
  }
}

/** Mock monaco namespace with Range class. */
const mockMonaco = {
  Range: class Range {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  },
}

// ── tests ───────────────────────────────────────────────────────────────────

describe('computeCompanionDecorations', () => {
  const model = makeMockModel({ 0: 1, 10: 2, 50: 5, 100: 10, 200: 20 })

  it('returns empty array when both ledger and review are null', () => {
    const result = computeCompanionDecorations(null, null, mockMonaco as never, model as never)
    expect(result).toEqual([])
  })

  it('emits glyph for unpaid promise', () => {
    const anchor = makeAnchor('a_001', 10)
    const promise = makePromise('p_001', 'unpaid', 'a_001', 'No evidence found')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(1)
    const deco = result[0]
    expect(deco.options.glyphMarginClassName).toContain('unpaid')
    expect(deco.options.glyphMarginHoverMessage?.value).toContain('No evidence found')
  })

  it('emits glyph for mismatch promise', () => {
    const anchor = makeAnchor('a_002', 50)
    const promise = makePromise('p_002', 'mismatch', 'a_002', 'Found N=1e5, expected N=1e6')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(1)
    expect(result[0].options.glyphMarginClassName).toContain('mismatch')
  })

  it('emits glyph for partial promise', () => {
    const anchor = makeAnchor('a_003', 100)
    const promise = makePromise('p_003', 'partial', 'a_003')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(1)
    expect(result[0].options.glyphMarginClassName).toContain('partial')
  })

  it('does NOT emit glyph for paid promise', () => {
    const anchor = makeAnchor('a_004', 100)
    const promise = makePromise('p_004', 'paid', 'a_004')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(0)
  })

  it('does NOT emit glyph for unknown promise', () => {
    const anchor = makeAnchor('a_005', 100)
    const promise = makePromise('p_005', 'unknown', 'a_005')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(0)
  })

  it('does NOT emit glyph when anchor status is lost', () => {
    const anchor = makeAnchor('a_006', null, 'lost')
    const promise = makePromise('p_006', 'unpaid', 'a_006', 'Lost anchor')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [promise],
      anchors: [anchor],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    expect(result).toHaveLength(0)
  })

  it('emits glyph for open review point with anchor', () => {
    const anchor = makeAnchor('a_rev_001', 200)
    const point = makeReviewPoint('rp_001', 'a_rev_001', 'open', 'major')
    const session = {
      id: 'R_001',
      doc_id: 'doc1',
      points: [point],
      anchors: [anchor],
      venue: 'NeurIPS',
      persona: 'reviewer2',
      checks: ['llm'],
      doc_hash: null,
      created_at: 0,
    }

    const result = computeCompanionDecorations(null, session as never, mockMonaco as never, model as never)

    expect(result).toHaveLength(1)
    expect(result[0].options.glyphMarginClassName).toContain('review')
    expect(result[0].options.glyphMarginHoverMessage?.value).toContain('Review point rp_001')
  })

  it('does NOT emit glyph for accepted/dismissed review point', () => {
    const anchor = makeAnchor('a_rev_002', 100)
    const accepted = makeReviewPoint('rp_002', 'a_rev_002', 'accepted', 'minor')
    const dismissed = makeReviewPoint('rp_003', 'a_rev_002', 'dismissed', 'minor')
    const session = {
      id: 'R_001',
      doc_id: 'doc1',
      points: [accepted, dismissed],
      anchors: [anchor],
      venue: null,
      persona: 'reviewer2',
      checks: ['llm'],
      doc_hash: null,
      created_at: 0,
    }

    const result = computeCompanionDecorations(null, session as never, mockMonaco as never, model as never)

    expect(result).toHaveLength(0)
  })

  it('merges multiple items on the same line into one decoration', () => {
    // Two promises anchored at the same position → same line → should merge
    const anchor1 = makeAnchor('a_merge_1', 10)
    const anchor2 = makeAnchor('a_merge_2', 10)
    const p1 = makePromise('p_m1', 'unpaid', 'a_merge_1', 'note 1')
    const p2 = makePromise('p_m2', 'mismatch', 'a_merge_2', 'note 2')
    const ledger = {
      id: 'L_001',
      doc_id: 'doc1',
      promises: [p1, p2],
      anchors: [anchor1, anchor2],
      doc_hash: null,
      last_built_at: 0,
    }

    const result = computeCompanionDecorations(ledger as never, null, mockMonaco as never, model as never)

    // Should be merged to 1 decoration, not 2
    expect(result).toHaveLength(1)
    // Merged hover should contain both notes
    const hover = result[0].options.glyphMarginHoverMessage?.value ?? ''
    expect(hover).toContain('note 1')
    expect(hover).toContain('note 2')
  })
})
