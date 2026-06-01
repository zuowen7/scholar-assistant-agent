/**
 * Tests for useSpeechRecognition composable.
 *
 * Uses a mock SpeechRecognition constructor to verify:
 * - isSupported detection
 * - start/stop/toggle lifecycle
 * - interim/final result accumulation
 * - error handling
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── Mock SpeechRecognition ────────────────────────────────────────────────

class MockSpeechRecognition {
  continuous = false
  interimResults = false
  lang = ''
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  onresult: ((e: SpeechRecognitionEvent) => void) | null = null
  private _accumulated: any[] = []

  start = vi.fn(() => { this._accumulated = []; this.onstart?.() })
  stop = vi.fn(() => { this.onend?.() })
  abort = vi.fn()

  /** Simulate a speech result event (accumulates like real Chrome) */
  simulateResult(results: Array<{ transcript: string; isFinal: boolean }>) {
    const newEntries = results.map(r => ({
      0: { transcript: r.transcript },
      isFinal: r.isFinal,
      length: 1,
    }))
    const prevLen = this._accumulated.length
    this._accumulated.push(...newEntries)
    const event = {
      results: this._accumulated,
      resultIndex: prevLen,
    } as unknown as SpeechRecognitionEvent
    this.onresult?.(event)
  }

  /** Simulate an error */
  simulateError(error: string) {
    this.onerror?.({ error })
  }

  /** Simulate natural end */
  simulateEnd() {
    this.onend?.()
  }
}

let mockInstance: MockSpeechRecognition

function installMock() {
  mockInstance = new MockSpeechRecognition()
  const instance = mockInstance
  // Use a class so `new` works correctly
  ;(globalThis as any).SpeechRecognition = class { constructor() { return instance } }
  ;(globalThis as any).webkitSpeechRecognition = undefined
}

function removeMock() {
  delete (globalThis as any).SpeechRecognition
  delete (globalThis as any).webkitSpeechRecognition
}

// Reset module between tests so singleton state is fresh
describe('useSpeechRecognition', () => {
  beforeEach(() => {
    removeMock()
    installMock()
    // Re-import to reset module state
    vi.resetModules()
  })

  afterEach(() => {
    removeMock()
  })

  // Helper to get a fresh instance after module reset
  async function getFresh() {
    const mod = await import('../composables/useSpeechRecognition')
    return mod.useSpeechRecognition()
  }

  // ── isSupported ──────────────────────────────────────────────────────────

  it('detects support when SpeechRecognition exists', async () => {
    const sr = await getFresh()
    expect(sr.isSupported).toBe(true)
  })

  it('detects unsupported when neither API exists', async () => {
    removeMock()
    const sr = await getFresh()
    expect(sr.isSupported).toBe(false)
  })

  it('detects support via webkitSpeechRecognition fallback', async () => {
    delete (globalThis as any).SpeechRecognition
    ;(globalThis as any).webkitSpeechRecognition = vi.fn(() => mockInstance)
    const sr = await getFresh()
    expect(sr.isSupported).toBe(true)
  })

  // ── start ────────────────────────────────────────────────────────────────

  it('starts listening and sets status', async () => {
    const sr = await getFresh()
    expect(sr.status.value).toBe('idle')
    sr.start()
    expect(sr.status.value).toBe('listening')
    expect(mockInstance.continuous).toBe(true)
    expect(mockInstance.interimResults).toBe(true)
    expect(mockInstance.lang).toBe('zh-CN')
  })

  it('sets custom language', async () => {
    const sr = await getFresh()
    sr.start('en-US')
    expect(mockInstance.lang).toBe('en-US')
  })

  it('ignores start when already listening', async () => {
    const sr = await getFresh()
    sr.start()
    expect(mockInstance.start).toHaveBeenCalledTimes(1)
    sr.start() // should be ignored
    expect(mockInstance.start).toHaveBeenCalledTimes(1)
  })

  it('sets error when not supported', async () => {
    removeMock()
    const sr = await getFresh()
    sr.start()
    expect(sr.error.value).toBe('Speech recognition not supported')
  })

  // ── stop ─────────────────────────────────────────────────────────────────

  it('stops and returns accumulated text', async () => {
    const sr = await getFresh()
    sr.start()

    // Interim result: browser sends partial transcript (same utterance, refined)
    mockInstance.simulateResult([
      { transcript: '你好', isFinal: false },
    ])
    expect(sr.interimText.value).toBe('你好')

    // Final result: same utterance becomes final with full transcript
    mockInstance.simulateResult([
      { transcript: '你好世界', isFinal: true },
    ])
    expect(sr.interimText.value).toBe('你好世界')

    const text = sr.stop()
    expect(text).toBe('你好世界')
    expect(sr.status.value).toBe('idle')
    expect(sr.interimText.value).toBe('')
  })

  it('calls recognition.stop() on stop', async () => {
    const sr = await getFresh()
    sr.start()
    sr.stop()
    expect(mockInstance.stop).toHaveBeenCalled()
  })

  // ── toggle ───────────────────────────────────────────────────────────────

  it('toggle starts when idle', async () => {
    const sr = await getFresh()
    expect(sr.status.value).toBe('idle')
    sr.toggle()
    expect(sr.status.value).toBe('listening')
  })

  it('toggle stops when listening', async () => {
    const sr = await getFresh()
    sr.toggle()
    expect(sr.status.value).toBe('listening')
    sr.toggle()
    expect(sr.status.value).toBe('idle')
  })

  // ── error handling ───────────────────────────────────────────────────────

  it('handles network error', async () => {
    const sr = await getFresh()
    sr.start()
    mockInstance.simulateError('network')
    expect(sr.error.value).toBe('network')
    expect(sr.status.value).toBe('idle')
  })

  it('ignores no-speech and aborted errors', async () => {
    const sr = await getFresh()
    sr.start()
    mockInstance.simulateError('no-speech')
    expect(sr.error.value).toBe('')
    mockInstance.simulateError('aborted')
    expect(sr.error.value).toBe('')
  })

  it('resets to idle on natural end', async () => {
    const sr = await getFresh()
    sr.start()
    mockInstance.simulateEnd()
    expect(sr.status.value).toBe('idle')
  })

  // ── Chrome re-inclusion dedup ────────────────────────────────────────────

  it('strips prefix re-inclusion when Chrome re-recognizes earlier audio', async () => {
    // This simulates the exact bug pattern:
    // 1. User says "太阳系一共有八大行星，他们分别是"
    // 2. User continues: "水星、金星、..."
    // 3. Chrome produces a THIRD result that re-includes the first utterance
    const sr = await getFresh()
    sr.start()

    // First utterance
    mockInstance.simulateResult([
      { transcript: '太阳系一共有八大行星，他们分别是', isFinal: true },
    ])
    expect(sr.interimText.value).toContain('太阳系')

    // Second utterance (distinct)
    mockInstance.simulateResult([
      { transcript: '水星、金星、地球', isFinal: true },
    ])
    expect(sr.interimText.value).toContain('水星')

    // Third utterance: Chrome re-includes the first + adds new content
    mockInstance.simulateResult([
      { transcript: '太阳系一共有八大行星，他们分别是，所带的是地球', isFinal: true },
    ])

    const text = sr.interimText.value
    // "太阳系一共有八大行星" should appear at most twice
    // (once from first utterance, NOT again from the third)
    const matches = text.match(/太阳系/g) || []
    expect(matches.length).toBeLessThanOrEqual(2)
    // The new content from the third utterance should be preserved
    expect(text).toContain('地球')
  })

  it('handles homophone difference in re-included content', async () => {
    // First utterance uses "它们", re-inclusion uses "他们"
    const sr = await getFresh()
    sr.start()

    mockInstance.simulateResult([
      { transcript: '太阳系一共有八大行星，它们分别是', isFinal: true },
    ])

    mockInstance.simulateResult([
      { transcript: '水星金星地球', isFinal: true },
    ])

    // Re-inclusion with different homophone (他们 vs 它们)
    mockInstance.simulateResult([
      { transcript: '太阳系一共有八大行星，他们分别是，我们所在的是地球', isFinal: true },
    ])

    const text = sr.interimText.value
    const matches = text.match(/太阳系/g) || []
    expect(matches.length).toBeLessThanOrEqual(2)
    expect(text).toContain('地球')
  })

  it('superset replaces accumulated text', async () => {
    const sr = await getFresh()
    sr.start()

    mockInstance.simulateResult([
      { transcript: '你好', isFinal: true },
    ])
    expect(sr.interimText.value).toBe('你好')

    // Chrome re-recognizes as a superset (same content + more)
    mockInstance.simulateResult([
      { transcript: '你好世界', isFinal: true },
    ])
    expect(sr.interimText.value).toBe('你好世界')
  })

  it('resetAccumulated clears text without stopping recognition', async () => {
    const sr = await getFresh()
    sr.start()

    mockInstance.simulateResult([
      { transcript: '你好世界', isFinal: true },
    ])
    expect(sr.interimText.value).toBe('你好世界')

    sr.resetAccumulated()
    expect(sr.interimText.value).toBe('')
    // Still listening — not stopped
    expect(sr.status.value).toBe('listening')

    // New result after reset starts fresh
    mockInstance.simulateResult([
      { transcript: '新的内容', isFinal: true },
    ])
    expect(sr.interimText.value).toBe('新的内容')
  })
})
