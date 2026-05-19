/**
 * useArgumentCompanion — singleton composable for Argument Companion v3.
 *
 * Manages: Ledger state, ReviewSession state, editor bridge (flashAnchor),
 * and all API calls (build ledger, run review, rebuttal).
 */
import { reactive } from 'vue'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import type { Ledger, ReviewSession, ReviewSummary, Anchor, Promise as ArgPromise } from '../types'
import { useToast } from './useToast'

// ── SHA-1-lite hash (16 hex chars) for doc staleness detection ────────────

function simpleHash(text: string): string {
  let h = 0
  for (let i = 0; i < text.length; i++) {
    h = Math.imul(31, h) + text.charCodeAt(i) | 0
  }
  return (h >>> 0).toString(16).padStart(8, '0')
}

// ── Module-level singleton state ──────────────────────────────────────────

interface CompanionState {
  docId: string
  docTitle: string
  ledger: Ledger | null
  building: boolean
  ledgerStale: boolean
  review: ReviewSession | null
  reviewList: ReviewSummary[]
  reviewing: boolean
  rebuttalSending: string  // point_id or ''
  flashAnchor: { start: number; end: number } | null
}

const state = reactive<CompanionState>({
  docId: '',
  docTitle: '',
  ledger: null,
  building: false,
  ledgerStale: false,
  review: null,
  reviewList: [],
  reviewing: false,
  rebuttalSending: '',
  flashAnchor: null,
})

const { pushError, pushWarning } = useToast()

let _debounceTimer: ReturnType<typeof setTimeout> | null = null

// ── Internal helpers ──────────────────────────────────────────────────────

function findAnchor(anchors: Anchor[], id: string): Anchor | undefined {
  return anchors.find(a => a.id === id)
}

// ── API calls ─────────────────────────────────────────────────────────────

async function buildOrRebuildLedger(text: string): Promise<void> {
  console.log('[companion] buildOrRebuildLedger called, docId:', state.docId, 'textLen:', text?.length ?? 0)
  if (!state.docId) {
    state.docId = `untitled-${crypto.randomUUID()}`
    state.docTitle = 'Untitled'
  }
  if (!text.trim()) {
    console.warn('[companion] buildOrRebuildLedger skipped: empty text')
    return
  }
  if (text.length > 5_000_000) {
    pushError('文本过长（超过 5 MB），请缩短后重试。')
    return
  }
  state.building = true
  console.log('[companion] setting building=true, about to fetch...')
  try {
    const resp = await fetch(`${API_BASE}/api/companion/ledger/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_id: state.docId, doc_title: state.docTitle, text }),
    })
    console.log('[companion] fetch returned:', resp.status, 'hasBody:', !!resp.body)
    if (!resp.ok || !resp.body) {
      console.warn('[companion] build ledger failed:', resp.status)
      pushError(`构建论证账本失败（${resp.status}）`)
      state.building = false
      return
    }

    // Initialize ledger shell
    const docHash = simpleHash(text)
    const ledger: Ledger = {
      id: '',
      doc_id: state.docId,
      doc_title: state.docTitle,
      promises: [],
      anchors: [],
      doc_hash: docHash,
      last_built_at: Date.now() / 1000,
    }

    let eventCount = 0
    await readSseStream(resp.body.getReader(), (eventType, data) => {
      eventCount++
      if (eventType === 'error') {
        const msg = (data as Record<string, unknown>)['message'] as string || '未知错误'
        console.warn('[companion] build ledger error:', msg)
        pushError(`构建论证账本失败：${msg}`)
        state.building = false
        return
      }
      if (eventType === 'promise') {
        const p = data as unknown as ArgPromise
        ledger.promises.push(p)
        if ((data as Record<string, unknown>)['anchor']) {
          ledger.anchors.push((data as Record<string, unknown>)['anchor'] as Anchor)
        }
      } else if (eventType === 'anchor') {
        ledger.anchors.push(data as unknown as Anchor)
      } else if (eventType === 'complete') {
        const d = data as Record<string, unknown>
        if (d['ledger_id']) ledger.id = d['ledger_id'] as string
      }
    })
    console.log('[companion] readSseStream done, events received:', eventCount, 'promises:', ledger.promises.length)

    if (ledger.promises.length === 0 && eventCount > 0) {
      console.warn('[companion] LLM returned 0 promises — LLM may be unavailable or text too short')
      pushWarning('AI 未提取到任何承诺，请确认 LLM 配置正确或文本内容足够。')
    }
    state.ledger = ledger
    state.ledgerStale = false
  } finally {
    state.building = false
  }
}

async function getLedger(): Promise<void> {
  if (!state.docId) return
  try {
    const resp = await fetch(`${API_BASE}/api/companion/ledger/${encodeURIComponent(state.docId)}`)
    if (!resp.ok) {
      state.ledger = null
      return
    }
    state.ledger = await resp.json() as Ledger
  } catch {
    state.ledger = null
  }
}

async function upsertPromise(promise: Partial<ArgPromise>): Promise<void> {
  if (!state.docId || !state.ledger) return
  try {
    const resp = await fetch(
      `${API_BASE}/api/companion/ledger/${encodeURIComponent(state.docId)}/promise`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(promise),
      },
    )
    if (!resp.ok) { pushError(`保存承诺失败（${resp.status}）`); return }
    const updated = await resp.json() as ArgPromise
    const idx = state.ledger.promises.findIndex(p => p.id === updated.id)
    if (idx >= 0) state.ledger.promises[idx] = updated
    else state.ledger.promises.push(updated)
  } catch (e) { pushError('保存承诺失败，请重试。'); console.warn('[companion] upsertPromise error:', e) }
}

async function deletePromise(pid: string): Promise<void> {
  if (!state.docId || !state.ledger) return
  try {
    await fetch(
      `${API_BASE}/api/companion/ledger/${encodeURIComponent(state.docId)}/promise/${pid}`,
      { method: 'DELETE' },
    )
    state.ledger.promises = state.ledger.promises.filter(p => p.id !== pid)
  } catch (e) { pushError('删除承诺失败，请重试。'); console.warn('[companion] deletePromise error:', e) }
}

async function relocate(text: string): Promise<void> {
  if (!state.docId || !state.ledger) return
  try {
    const resp = await fetch(
      `${API_BASE}/api/companion/ledger/${encodeURIComponent(state.docId)}/relocate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      },
    )
    if (!resp.ok) return
    const updated = await resp.json() as Ledger
    state.ledger = updated
  } catch (e) { pushError('锚点重定位失败，请重试。'); console.warn('[companion] relocate error:', e) }
}

async function listReviews(): Promise<void> {
  if (!state.docId) return
  try {
    const resp = await fetch(`${API_BASE}/api/companion/reviews?doc_id=${encodeURIComponent(state.docId)}`)
    if (!resp.ok) return
    state.reviewList = await resp.json() as ReviewSummary[]
  } catch (e) { pushError('加载评审列表失败。'); console.warn('[companion] listReviews error:', e) }
}

async function runReview(
  text: string,
  venue: string | null = null,
  persona = 'reviewer2',
  mode: 'serial' | 'parallel' = 'serial',
): Promise<void> {
  if (!state.docId) {
    state.docId = `untitled-${crypto.randomUUID()}`
    state.docTitle = 'Untitled'
  }
  state.reviewing = true
  try {
    const resp = await fetch(`${API_BASE}/api/companion/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: state.docId,
        doc_title: state.docTitle,
        text,
        venue,
        persona,
        mode,
      }),
    })
    if (!resp.ok || !resp.body) { state.reviewing = false; return }

    let session: ReviewSession = {
      id: '',
      doc_id: state.docId,
      doc_title: state.docTitle,
      venue,
      persona: persona as ReviewSession['persona'],
      checks: ['llm'],
      points: [],
      anchors: [],
      doc_hash: simpleHash(text),
      created_at: Date.now() / 1000,
    }

    await readSseStream(resp.body.getReader(), (eventType, data) => {
      if (eventType === 'review_point') {
        session.points.push(data as unknown as import('../types').ReviewPoint)
      } else if (eventType === 'anchor') {
        session.anchors.push(data as unknown as Anchor)
      } else if (eventType === 'complete') {
        const d = data as Record<string, unknown>
        if (d['session_id']) session.id = d['session_id'] as string
      }
    })

    if (!session.id) {
      pushError('评审会话未初始化（未收到 complete 事件），请重试。')
      return
    }
    state.review = session
    await listReviews()
  } finally {
    state.reviewing = false
  }
}

async function scopedReview(focus: string | { quote: string; char_start: number; char_end: number }, text: string): Promise<void> {
  if (!state.docId) return
  state.reviewing = true
  try {
    const sessionId = state.review?.id ?? undefined
    const resp = await fetch(`${API_BASE}/api/companion/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: state.docId,
        doc_title: state.docTitle,
        text,
        focus,
        session_id: sessionId,
      }),
    })
    if (!resp.ok || !resp.body) { state.reviewing = false; return }

    if (!state.review) {
      state.review = {
        id: '',
        doc_id: state.docId,
        doc_title: state.docTitle,
        venue: null,
        persona: 'reviewer2',
        checks: ['llm'],
        points: [],
        anchors: [],
        doc_hash: simpleHash(text),
        created_at: Date.now() / 1000,
      }
    }

    await readSseStream(resp.body.getReader(), (eventType, data) => {
      if (eventType === 'review_point') {
        state.review!.points.push(data as unknown as import('../types').ReviewPoint)
      } else if (eventType === 'anchor') {
        state.review!.anchors.push(data as unknown as Anchor)
      } else if (eventType === 'complete') {
        const d = data as Record<string, unknown>
        if (d['session_id'] && !state.review!.id) {
          state.review!.id = d['session_id'] as string
        }
      }
    })
  } finally {
    state.reviewing = false
  }
}

async function updatePointStatus(pointId: string, status: import('../types').PointStatus): Promise<void> {
  if (!state.review) return
  try {
    await fetch(
      `${API_BASE}/api/companion/review/${state.review.id}/point/${pointId}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      },
    )
    const point = state.review.points.find(p => p.id === pointId)
    if (point) point.status = status
  } catch (e) { pushError('更新评审意见状态失败。'); console.warn('[companion] updatePointStatus error:', e) }
}

async function rebut(pointId: string, message: string, text: string): Promise<void> {
  if (!state.review || state.rebuttalSending) return
  state.rebuttalSending = pointId
  try {
    const resp = await fetch(
      `${API_BASE}/api/companion/review/${state.review.id}/point/${pointId}/rebut`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, text }),
      },
    )
    if (!resp.ok || !resp.body) { state.rebuttalSending = ''; return }

    const point = state.review.points.find(p => p.id === pointId)

    await readSseStream(resp.body.getReader(), (eventType, data) => {
      if (eventType === 'reviewer_reply' && point) {
        point.thread.push({
          id: `rt_${crypto.randomUUID()}`,
          role: 'reviewer',
          text: (data as Record<string, unknown>)['text'] as string ?? '',
          created_at: Date.now() / 1000,
        })
      } else if (eventType === 'status' && point) {
        const s = (data as Record<string, unknown>)['status'] as string
        if (s === 'rebutted') point.status = 'rebutted'
      }
    })

    // Prepend author message to thread
    if (point) {
      point.thread.unshift({
        id: `rt_author_${Date.now()}`,
        role: 'author',
        text: message,
        created_at: Date.now() / 1000,
      })
    }
  } finally {
    state.rebuttalSending = ''
  }
}

async function importReviews(reviewsRaw: string, text: string): Promise<void> {
  if (!state.docId) return
  state.reviewing = true
  try {
    const resp = await fetch(`${API_BASE}/api/companion/review/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: state.docId,
        doc_title: state.docTitle,
        text,
        reviews_raw: reviewsRaw,
      }),
    })
    if (!resp.ok || !resp.body) { state.reviewing = false; return }

    if (!state.review) {
      state.review = {
        id: '',
        doc_id: state.docId,
        doc_title: state.docTitle,
        venue: null,
        persona: 'real' as const,
        checks: ['imported'],
        points: [],
        anchors: [],
        doc_hash: simpleHash(text),
        created_at: Date.now() / 1000,
      }
    }

    await readSseStream(resp.body.getReader(), (eventType, data) => {
      if (eventType === 'review_point') {
        state.review!.points.push(data as unknown as import('../types').ReviewPoint)
      } else if (eventType === 'complete') {
        const d = data as Record<string, unknown>
        if (d['session_id'] && !state.review!.id) {
          state.review!.id = d['session_id'] as string
        }
      }
    })

    await listReviews()
  } finally {
    state.reviewing = false
  }
}

// ── Editor bridge ─────────────────────────────────────────────────────────

function focusAnchor(anchorId: string): void {
  const allAnchors: Anchor[] = [
    ...(state.ledger?.anchors ?? []),
    ...(state.review?.anchors ?? []),
  ]
  const anchor = findAnchor(allAnchors, anchorId)
  if (!anchor || anchor.char_start === null || anchor.char_end === null) return
  state.flashAnchor = { start: anchor.char_start, end: anchor.char_end }
}

function focusFromGutter(kind: 'promise' | 'point', id: string): void {
  // Notify CompanionPanel to scroll to the item (via focusAnchor too)
  if (kind === 'promise' && state.ledger) {
    const p = state.ledger.promises.find(x => x.id === id)
    if (p) focusAnchor(p.source_anchor_id)
  } else if (kind === 'point' && state.review) {
    const pt = state.review.points.find(x => x.id === id)
    if (pt?.anchor_id) focusAnchor(pt.anchor_id)
  }
}

function onEditorEdit(text: string): void {
  if (_debounceTimer !== null) clearTimeout(_debounceTimer)
  _debounceTimer = setTimeout(() => {
    if (!state.ledger) return
    const currentHash = simpleHash(text)
    if (state.ledger.doc_hash !== currentHash) {
      state.ledgerStale = true
    }
  }, 1500)
}

// ── Lifecycle ─────────────────────────────────────────────────────────────

function setDoc(docId: string, docTitle: string): void {
  if (docId === state.docId) return
  state.docId = docId
  state.docTitle = docTitle
  state.ledger = null
  state.ledgerStale = false
  state.review = null
  state.reviewList = []
  // Fetch existing ledger/reviews in background
  getLedger()
  listReviews()
}

// ── Testing escape hatch ──────────────────────────────────────────────────

export function _resetForTesting(): void {
  state.docId = ''
  state.docTitle = ''
  state.ledger = null
  state.building = false
  state.ledgerStale = false
  state.review = null
  state.reviewList = []
  state.reviewing = false
  state.rebuttalSending = ''
  state.flashAnchor = null
  if (_debounceTimer !== null) { clearTimeout(_debounceTimer); _debounceTimer = null }
}

// ── Public API ────────────────────────────────────────────────────────────

export function useArgumentCompanion() {
  return {
    state,
    setDoc,
    buildOrRebuildLedger,
    getLedger,
    upsertPromise,
    deletePromise,
    relocate,
    runReview,
    scopedReview,
    listReviews,
    updatePointStatus,
    rebut,
    importReviews,
    focusAnchor,
    focusFromGutter,
    onEditorEdit,
  }
}
