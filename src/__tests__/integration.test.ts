/**
 * Voice command E2E integration test.
 *
 * Tests the full flow: trigger → state transitions → speech → silence → submit.
 * Mocks useSpeechRecognition at the composable level (its unit tests cover internals).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { nextTick, ref } from 'vue'

// ═══════════════════════════════════════════════════════════════════════
// Mocks
// ═══════════════════════════════════════════════════════════════════════

// Capture onResult/onEnd callbacks so tests can simulate speech
let capturedCallbacks: { onResult?: (text: string) => void; onEnd?: () => void } = {}

vi.mock('../composables/useSpeechRecognition', () => ({
  useSpeechRecognition: vi.fn((options?: { onResult?: (text: string) => void; onEnd?: () => void }) => {
    capturedCallbacks = options || {}
    return {
      status: ref('idle'),
      interimText: ref(''),
      error: ref(''),
      isSupported: true,
      start: vi.fn(),
      stop: vi.fn(() => ''),
      toggle: vi.fn(),
    }
  }),
}))

describe('Voice command E2E integration', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    capturedCallbacks = {}
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function getFresh() {
    const mod = await import('../composables/useVoiceCommand')
    return mod.useVoiceCommand()
  }

  // ═══════════════════════════════════════════════════════════════════
  // Test 1: Full happy path
  // ═══════════════════════════════════════════════════════════════════

  it('full flow: trigger → speech → 2s silence → submit', async () => {
    const vc = await getFresh()

    const triggerSpy = vi.fn()
    const submitSpy = vi.fn()
    window.addEventListener('voice-command-trigger', triggerSpy)
    window.addEventListener('voice-command-submit', ((e: CustomEvent) => {
      submitSpy(e.detail.text)
    }) as EventListener)

    // Step 1: Trigger
    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('activating')
    expect(triggerSpy).toHaveBeenCalledTimes(1)

    // Step 2: activating → listening (150ms)
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    // Step 3: Simulate speech result
    capturedCallbacks.onResult?.('把当前段落翻译成英文')
    expect(vc.transcript.value).toBe('把当前段落翻译成英文')

    // Step 4: Silence auto-submit (2s after last result)
    vi.advanceTimersByTime(2100)
    expect(vc.state.value).toBe('submitting')
    expect(submitSpy).toHaveBeenCalledWith('把当前段落翻译成英文')

    // Step 5: Processing
    vc.setProcessing()
    expect(vc.state.value).toBe('processing')

    // Step 6: Done
    vc.done()
    expect(vc.state.value).toBe('idle')

    window.removeEventListener('voice-command-trigger', triggerSpy)
    window.removeEventListener('voice-command-submit', submitSpy as any)
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 2: Speech onEnd triggers immediate submit (before silence)
  // ═══════════════════════════════════════════════════════════════════

  it('speech engine onEnd triggers immediate submit', async () => {
    const vc = await getFresh()

    const submitSpy = vi.fn()
    window.addEventListener('voice-command-submit', ((e: CustomEvent) => {
      submitSpy(e.detail.text)
    }) as EventListener)

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)

    capturedCallbacks.onResult?.('润色这段文字')
    // Don't wait for silence — onEnd fires first
    capturedCallbacks.onEnd?.()

    expect(vc.state.value).toBe('submitting')
    expect(submitSpy).toHaveBeenCalledWith('润色这段文字')

    window.removeEventListener('voice-command-submit', submitSpy as any)
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 3: Cancel mid-speech
  // ═══════════════════════════════════════════════════════════════════

  it('cancel during listening returns to idle', async () => {
    const vc = await getFresh()
    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    vc.cancel()
    expect(vc.state.value).toBe('idle')
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 4: 10s timeout with no speech
  // ═══════════════════════════════════════════════════════════════════

  it('10s timeout with no speech → auto cancel with error', async () => {
    const vc = await getFresh()
    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    vi.advanceTimersByTime(10_500)
    expect(vc.state.value).toBe('idle')
    expect(vc.error.value).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 5: Multiple results → silence → submit last transcript
  // ═══════════════════════════════════════════════════════════════════

  it('multiple results accumulate, last submitted', async () => {
    const vc = await getFresh()

    const submitSpy = vi.fn()
    window.addEventListener('voice-command-submit', ((e: CustomEvent) => {
      submitSpy(e.detail.text)
    }) as EventListener)

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)

    capturedCallbacks.onResult?.('帮我')
    vi.advanceTimersByTime(1000) // not enough for silence

    capturedCallbacks.onResult?.('帮我翻译这段英文')
    vi.advanceTimersByTime(2100) // silence triggers submit

    expect(vc.state.value).toBe('submitting')
    expect(submitSpy).toHaveBeenCalledWith('帮我翻译这段英文')

    window.removeEventListener('voice-command-submit', submitSpy as any)
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 6: Toggle — second trigger cancels
  // ═══════════════════════════════════════════════════════════════════

  it('second trigger cancels active session', async () => {
    const vc = await getFresh()
    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('idle')
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 7: Empty transcript → silence timer doesn't start, waits for timeout
  // ═══════════════════════════════════════════════════════════════════

  it('empty transcript → no submit, 10s timeout cancels', async () => {
    const vc = await getFresh()

    const submitSpy = vi.fn()
    window.addEventListener('voice-command-submit', submitSpy)

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)

    // Empty result → silence timer NOT started (text.trim() is falsy)
    capturedCallbacks.onResult?.('')
    vi.advanceTimersByTime(2100)
    expect(vc.state.value).toBe('listening') // still listening
    expect(submitSpy).not.toHaveBeenCalled()

    // Eventually 10s timeout fires
    vi.advanceTimersByTime(8500)
    expect(vc.state.value).toBe('idle')
    expect(vc.error.value).toBeTruthy()
  })

  // ═══════════════════════════════════════════════════════════════════
  // Test 8: Event payload carries correct text
  // ═══════════════════════════════════════════════════════════════════

  it('voice-command-submit event detail.text matches transcript', async () => {
    const vc = await getFresh()

    let capturedText = ''
    const handler = (e: Event) => {
      capturedText = (e as CustomEvent).detail.text
    }
    window.addEventListener('voice-command-submit', handler)

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)

    capturedCallbacks.onResult?.('这是一条测试指令')
    vi.advanceTimersByTime(2100)

    expect(capturedText).toBe('这是一条测试指令')

    window.removeEventListener('voice-command-submit', handler)
  })
})
