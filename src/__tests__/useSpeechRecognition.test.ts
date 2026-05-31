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

  start = vi.fn(() => { this.onstart?.() })
  stop = vi.fn(() => { this.onend?.() })
  abort = vi.fn()

  /** Simulate a speech result event */
  simulateResult(results: Array<{ transcript: string; isFinal: boolean }>) {
    const event = {
      results: results.map(r => [
        { transcript: r.transcript },
        // Stub SpeechRecognitionAlternative
      ]).map((alternatives, i) => ({
        0: alternatives[0],
        isFinal: results[i].isFinal,
        length: 1,
      })),
      resultIndex: 0,
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
    expect(mockInstance.continuous).toBe(false)
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

    // Simulate interim results
    mockInstance.simulateResult([
      { transcript: '你好', isFinal: false },
    ])
    expect(sr.interimText.value).toBe('你好')

    // Simulate final result
    mockInstance.simulateResult([
      { transcript: '你好', isFinal: true },
      { transcript: '世界', isFinal: false },
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
})
