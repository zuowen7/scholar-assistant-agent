/**
 * Phase 2 TDD — useArgumentCompanion composable unit tests.
 *
 * Tests cover:
 * - buildOrRebuildLedger: consumes mock SSE → state.ledger.promises fills one by one
 * - relocate: anchor status updates after call
 * - focusAnchor: sets state.flashAnchor
 * - onEditorEdit: debounce sets ledgerStale=true
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

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
vi.mock('../composables/useEditorState', () => ({
  tabs: { value: [] },
  activeTabId: { value: null },
  activeTab: { value: null },
  content: { value: '' },
  contentVersion: { value: 0 },
}))
vi.mock('@tauri-apps/plugin-fs', () => ({
  writeTextFile: vi.fn().mockResolvedValue(undefined),
}))

import {
  useArgumentCompanion,
  _resetForTesting,
} from '../composables/useArgumentCompanion'
import type { RebuttalTurn, ReviewPoint, ReviewSession } from '../types'

// ── helpers ─────────────────────────────────────────────────────────────────

function makeAnchor(overrides: Record<string, unknown> = {}) {
  return {
    id: 'a_test001',
    doc_id: 'doc1',
    char_start: 10,
    char_end: 30,
    quote: 'test quote here',
    context_before: '',
    context_after: '',
    section_path: null,
    status: 'anchored',
    ...overrides,
  }
}

function makePromise(overrides: Record<string, unknown> = {}) {
  return {
    id: 'p_test001',
    text: 'We demonstrate our method scales to N=1e6',
    kind: 'contribution',
    source_anchor_id: 'a_test001',
    discharge_anchor_ids: [],
    status: 'unpaid',
    severity: 'error',
    note: 'Not found in body',
    created_by: 'ai',
    user_overridden: false,
    ...overrides,
  }
}

function makeLedger(overrides: Record<string, unknown> = {}) {
  return {
    id: 'L_test001',
    doc_id: 'doc1',
    doc_title: 'Test Paper',
    promises: [],
    anchors: [],
    doc_hash: null,
    last_built_at: Date.now() / 1000,
    ...overrides,
  }
}

/** Build a ReadableStream that emits SSE-formatted lines. */
function makeSseStream(events: { event: string; data: unknown }[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  const chunks: Uint8Array[] = events.map(e =>
    enc.encode(`event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`),
  )
  let i = 0
  return new ReadableStream({
    pull(ctrl) {
      if (i < chunks.length) {
        ctrl.enqueue(chunks[i++])
      } else {
        ctrl.close()
      }
    },
  })
}

// ── tests ───────────────────────────────────────────────────────────────────

describe('useArgumentCompanion', () => {
  beforeEach(() => {
    _resetForTesting()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── buildOrRebuildLedger ─────────────────────────────────────────────────

  describe('buildOrRebuildLedger', () => {
    it('fills state.ledger.promises one by one from SSE promise events', async () => {
      const p1 = makePromise({ id: 'p_001', text: 'Contribution 1' })
      const p2 = makePromise({ id: 'p_002', text: 'Contribution 2', status: 'paid', severity: 'info' })
      const completeData = {
        promise_count: 2,
        by_status: { unpaid: 1, paid: 1 },
        warnings: [],
      }
      const stream = makeSseStream([
        { event: 'promise', data: p1 },
        { event: 'promise', data: p2 },
        { event: 'complete', data: completeData },
      ])

      const mockFetch = vi.fn().mockResolvedValue({
        ok: true,
        body: stream,
      })
      vi.stubGlobal('fetch', mockFetch)

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')

      await companion.buildOrRebuildLedger('full text here')

      expect(companion.state.ledger).not.toBeNull()
      expect(companion.state.ledger!.promises).toHaveLength(2)
      expect(companion.state.ledger!.promises[0].id).toBe('p_001')
      expect(companion.state.ledger!.promises[1].id).toBe('p_002')
      expect(companion.state.building).toBe(false)
    })

    it('sets building=true during SSE and false after', async () => {
      let buildingDuringStream = false
      const stream = makeSseStream([
        { event: 'promise', data: makePromise() },
        { event: 'complete', data: { promise_count: 1, by_status: {}, warnings: [] } },
      ])

      const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: stream })
      vi.stubGlobal('fetch', mockFetch)

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')

      const buildPromise = companion.buildOrRebuildLedger('text')
      // building should be true immediately after call starts
      buildingDuringStream = companion.state.building
      await buildPromise

      expect(buildingDuringStream).toBe(true)
      expect(companion.state.building).toBe(false)
    })

    it('handles error SSE event gracefully without crashing', async () => {
      const stream = makeSseStream([
        { event: 'error', data: { message: 'LLM failed' } },
      ])
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')

      await expect(companion.buildOrRebuildLedger('text')).resolves.not.toThrow()
      expect(companion.state.building).toBe(false)
    })
  })

  // ── focusAnchor ──────────────────────────────────────────────────────────

  describe('focusAnchor', () => {
    it('sets flashAnchor when anchor is found in current ledger', () => {
      const anchor = makeAnchor({ id: 'a_001', char_start: 50, char_end: 70 })
      const ledger = makeLedger({ anchors: [anchor] })

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')
      companion.state.ledger = ledger as never

      companion.focusAnchor('a_001')

      expect(companion.state.flashAnchor).toEqual({ start: 50, end: 70 })
    })

    it('does nothing when anchor id not found', () => {
      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')
      companion.state.ledger = makeLedger() as never
      companion.state.flashAnchor = null

      companion.focusAnchor('a_nonexistent')

      expect(companion.state.flashAnchor).toBeNull()
    })

    it('does nothing when ledger is null', () => {
      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')
      companion.state.ledger = null
      companion.state.flashAnchor = null

      companion.focusAnchor('a_001')

      expect(companion.state.flashAnchor).toBeNull()
    })
  })

  // ── onEditorEdit + ledgerStale ───────────────────────────────────────────

  describe('onEditorEdit', () => {
    it('sets ledgerStale=true when ledger exists and doc hash differs', async () => {
      vi.useFakeTimers()
      const anchor = makeAnchor()
      const promise = makePromise()
      const ledger = makeLedger({
        promises: [promise],
        anchors: [anchor],
        doc_hash: 'old_hash_aabbcc',
      })

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')
      companion.state.ledger = ledger as never
      companion.state.ledgerStale = false

      companion.onEditorEdit('completely new text that changes the hash')

      // advance past debounce (1500ms)
      vi.advanceTimersByTime(1600)
      await Promise.resolve()

      expect(companion.state.ledgerStale).toBe(true)
      vi.useRealTimers()
    })

    it('does not set ledgerStale when no ledger exists', async () => {
      vi.useFakeTimers()

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')
      companion.state.ledger = null
      companion.state.ledgerStale = false

      companion.onEditorEdit('any text')

      vi.advanceTimersByTime(1600)
      await Promise.resolve()

      expect(companion.state.ledgerStale).toBe(false)
      vi.useRealTimers()
    })
  })

  // ── setDoc ───────────────────────────────────────────────────────────────

  describe('setDoc', () => {
    it('updates docId and resets ledger when switching to a new doc', () => {
      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper 1')
      companion.state.ledger = makeLedger() as never

      companion.setDoc('doc2', 'Paper 2')

      expect(companion.state.docId).toBe('doc2')
      // ledger resets for new doc
      expect(companion.state.ledger).toBeNull()
    })

    it('keeps ledger when switching back to same doc', () => {
      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper 1')
      const ledger = makeLedger()
      companion.state.ledger = ledger as never

      companion.setDoc('doc1', 'Paper 1')

      expect(companion.state.ledger).not.toBeNull()
    })
  })

  // ── runReview ─────────────────────────────────────────────────────────────

  describe('runReview', () => {
    it('fills state.review.points from SSE review_point events', async () => {
      const rp1 = {
        id: 'rp_001', severity: 'major', category: 'baseline',
        title: 'Missing baselines', detail: 'No comparison.',
        anchor_id: null, status: 'open', source: 'llm',
        reviewer_label: null, thread: [],
      }
      const rp2 = {
        id: 'rp_002', severity: 'minor', category: 'writing_clarity',
        title: 'Unclear prose', detail: 'Section 3 is unclear.',
        anchor_id: null, status: 'open', source: 'llm',
        reviewer_label: null, thread: [],
      }
      const stream = makeSseStream([
        { event: 'review_point', data: rp1 },
        { event: 'review_point', data: rp2 },
        { event: 'complete', data: { session_id: 'S_test', by_category: { baseline: 1 }, warnings: [] } },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Test Paper')

      await companion.runReview('paper text here')

      expect(companion.state.review).not.toBeNull()
      expect(companion.state.review!.points).toHaveLength(2)
      expect(companion.state.review!.points[0].id).toBe('rp_001')
      expect(companion.state.reviewing).toBe(false)
    })

    it('sets reviewing=true during stream and false after', async () => {
      const stream = makeSseStream([
        { event: 'review_point', data: {
          id: 'rp_x', severity: 'minor', category: 'other', title: 'T', detail: 'D',
          anchor_id: null, status: 'open', source: 'llm', reviewer_label: null, thread: [],
        }},
        { event: 'complete', data: { session_id: 'S_x', by_category: {}, warnings: [] } },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')

      const p = companion.runReview('text')
      const reviewingDuringStream = companion.state.reviewing
      await p

      expect(reviewingDuringStream).toBe(true)
      expect(companion.state.reviewing).toBe(false)
    })

    it('handles error event gracefully without crashing', async () => {
      const stream = makeSseStream([
        { event: 'error', data: { message: 'LLM unavailable' } },
      ])
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')

      await expect(companion.runReview('text')).resolves.not.toThrow()
      expect(companion.state.reviewing).toBe(false)
    })
  })

  // ── scopedReview ──────────────────────────────────────────────────────────

  describe('scopedReview', () => {
    it('sends focus text to /api/companion/review', async () => {
      const stream = makeSseStream([
        { event: 'review_point', data: {
          id: 'rp_sc', severity: 'major', category: 'soundness', title: 'Overreach',
          detail: 'This sentence is unsupported.', anchor_id: null, status: 'open',
          source: 'scoped', reviewer_label: null, thread: [],
        }},
        { event: 'complete', data: { session_id: 'S_sc', by_category: {}, warnings: [] } },
      ])

      const mockFetch = vi.fn().mockResolvedValue({ ok: true, body: stream })
      vi.stubGlobal('fetch', mockFetch)

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')

      await companion.scopedReview('This is the selected sentence.', 'full paper text')

      expect(mockFetch).toHaveBeenCalled()
      const reviewCall = mockFetch.mock.calls.find((c: unknown[]) => {
        try { return JSON.parse((c[1] as { body: string }).body).focus !== undefined } catch { return false }
      })
      expect(reviewCall).toBeDefined()
      if (!reviewCall) throw new Error('Expected scoped review fetch call')
      const callBody = JSON.parse(reviewCall[1].body)
      expect(callBody.focus).toBe('This is the selected sentence.')
    })

    it('adds scoped points to existing review or creates new review', async () => {
      const stream = makeSseStream([
        { event: 'review_point', data: {
          id: 'rp_sc2', severity: 'minor', category: 'other', title: 'T', detail: 'D',
          anchor_id: null, status: 'open', source: 'scoped', reviewer_label: null, thread: [],
        }},
        { event: 'complete', data: { session_id: 'S_sc2', by_category: {}, warnings: [] } },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')

      await companion.scopedReview('selected text', 'full paper')

      expect(companion.state.review).not.toBeNull()
      expect(companion.state.review!.points.length).toBeGreaterThanOrEqual(1)
    })
  })

  // ── rebut ─────────────────────────────────────────────────────────────────

  describe('rebut', () => {
    function makeReview() {
      const point: ReviewPoint = {
        id: 'rp_001', severity: 'major' as const, category: 'baseline' as const,
        title: 'Missing baselines', detail: 'No comparison.',
        anchor_id: null, status: 'open' as const, source: 'llm' as const,
        reviewer_label: null, thread: [] as RebuttalTurn[],
      }
      const review: ReviewSession = {
        id: 'S_001',
        doc_id: 'doc1',
        doc_title: 'Paper',
        venue: null,
        persona: 'reviewer2' as const,
        checks: ['llm'],
        points: [point],
        anchors: [],
        doc_hash: null,
        created_at: Date.now() / 1000,
      }
      return { review, point }
    }

    it('appends author turn then reviewer turn to point.thread', async () => {
      const { review, point } = makeReview()
      const stream = makeSseStream([
        { event: 'reviewer_reply', data: { text: 'Still not convinced.' } },
        { event: 'status', data: { status: 'open' } },
        { event: 'complete', data: {} },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')
      companion.state.review = review as never

      await companion.rebut('rp_001', 'We added baselines.', 'full paper')

      expect(point.thread).toHaveLength(2)
      expect(point.thread[0].role).toBe('author')
      expect(point.thread[0].text).toBe('We added baselines.')
      expect(point.thread[1].role).toBe('reviewer')
      expect(point.thread[1].text).toBe('Still not convinced.')
    })

    it('sets point.status to rebutted when status event says rebutted', async () => {
      const { review, point } = makeReview()
      const stream = makeSseStream([
        { event: 'reviewer_reply', data: { text: 'This point can be considered rebutted.' } },
        { event: 'status', data: { status: 'rebutted' } },
        { event: 'complete', data: {} },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')
      companion.state.review = review as never

      await companion.rebut('rp_001', 'We convinced you.', 'full text')

      expect(point.status).toBe('rebutted')
    })

    it('sets rebuttalSending to pointId during SSE and clears after', async () => {
      const { review } = makeReview()
      const stream = makeSseStream([
        { event: 'reviewer_reply', data: { text: 'Reply.' } },
        { event: 'status', data: { status: 'open' } },
        { event: 'complete', data: {} },
      ])

      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: stream }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')
      companion.state.review = review as never

      const p = companion.rebut('rp_001', 'msg', 'text')
      const lockDuring = companion.state.rebuttalSending
      await p

      expect(lockDuring).toBe('rp_001')
      expect(companion.state.rebuttalSending).toBe('')
    })

    it('does nothing if rebuttalSending is already set (lock)', async () => {
      const { review } = makeReview()

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')
      companion.state.review = review as never
      companion.state.rebuttalSending = 'other_point'

      // Stub fetch AFTER setDoc so we only capture rebut-related calls
      const mockFetch = vi.fn()
      vi.stubGlobal('fetch', mockFetch)

      await companion.rebut('rp_001', 'msg', 'text')

      // rebut must NOT have made a fetch call (lock prevents it)
      const rebutCalls = mockFetch.mock.calls.filter((c: unknown[]) =>
        (c[0] as string).includes('/rebut'),
      )
      expect(rebutCalls).toHaveLength(0)
    })

    it('clears rebuttalSending even when fetch fails', async () => {
      const { review } = makeReview()
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, body: null }))

      const companion = useArgumentCompanion()
      companion.setDoc('doc1', 'Paper')
      companion.state.review = review as never

      await companion.rebut('rp_001', 'msg', 'text')

      expect(companion.state.rebuttalSending).toBe('')
    })
  })
})
