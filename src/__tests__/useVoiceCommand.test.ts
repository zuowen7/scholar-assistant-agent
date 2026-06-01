/**
 * Tests for useVoiceCommand composable.
 *
 * TDD tests for the voice command orchestrator state machine.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// ── Mock useSpeechRecognition ──────────────────────────────────────────

let mockSpeechOptions: { onResult?: (text: string) => void; onEnd?: () => void } = {}
const mockStart = vi.fn()
const mockStop = vi.fn(() => '')
const mockIsSupported = ref(true)

vi.mock('../composables/useSpeechRecognition', () => ({
  useSpeechRecognition: vi.fn((options?: { onResult?: (text: string) => void; onEnd?: () => void }) => {
    mockSpeechOptions = options || {}
    return {
      status: ref('idle'),
      interimText: ref(''),
      error: ref(''),
      isSupported: mockIsSupported.value,
      start: mockStart,
      stop: mockStop,
      toggle: vi.fn(),
    }
  }),
}))

describe('useVoiceCommand', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    mockStart.mockReset()
    mockStop.mockReset().mockReturnValue('')
    mockIsSupported.value = true
    mockSpeechOptions = {}
  })

  afterEach(() => {
    vi.useRealTimers()
    delete (globalThis as any).__TAURI_INTERNALS__
  })

  async function getFresh() {
    const mod = await import('../composables/useVoiceCommand')
    return mod.useVoiceCommand()
  }

  // ── Initial state ────────────────────────────────────────────────────

  it('initial state is idle', async () => {
    const vc = await getFresh()
    expect(vc.state.value).toBe('idle')
    expect(vc.transcript.value).toBe('')
    expect(vc.response.value).toBe('')
    expect(vc.error.value).toBe('')
  })

  // ── triggerVoiceCommand ──────────────────────────────────────────────

  it('transitions idle → activating → listening', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__ // browser mode, skip window management
    const vc = await getFresh()

    const triggerEvents: string[] = []
    window.addEventListener('voice-command-trigger', () => triggerEvents.push('triggered'))

    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('activating')
    expect(triggerEvents).toHaveLength(1)

    // Advance past the 150ms delay
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')
    expect(mockStart).toHaveBeenCalled()
  })

  it('dispatches voice-command-trigger event', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    const eventSpy = vi.fn()
    window.addEventListener('voice-command-trigger', eventSpy)
    vc.triggerVoiceCommand()
    expect(eventSpy).toHaveBeenCalledTimes(1)
  })

  // ── Speech recognition integration ───────────────────────────────────

  it('onResult updates transcript', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    // Simulate speech result
    mockSpeechOptions.onResult?.('把这段翻译成英文')
    expect(vc.transcript.value).toBe('把这段翻译成英文')
  })

  it('onEnd with text transitions to submitting and dispatches submit event', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    const submitSpy = vi.fn()
    window.addEventListener('voice-command-submit', ((e: CustomEvent) => {
      submitSpy(e.detail.text)
    }) as EventListener)

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)

    mockSpeechOptions.onResult?.('翻译这段')
    mockSpeechOptions.onEnd?.()

    expect(vc.state.value).toBe('submitting')
    expect(submitSpy).toHaveBeenCalledWith('翻译这段')
  })

  it('onEnd without text does not transition to submitting', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    // onEnd with empty transcript — stays listening (10s timeout handles cancel)
    mockSpeechOptions.onEnd?.()
    expect(vc.state.value).toBe('listening')
  })

  // ── Cancel ───────────────────────────────────────────────────────────

  it('cancel returns to idle from listening', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    vc.cancel()
    expect(vc.state.value).toBe('idle')
    expect(mockStop).toHaveBeenCalled()
  })

  it('cancel from activating', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('activating')

    vc.cancel()
    expect(vc.state.value).toBe('idle')
  })

  // ── Toggle ───────────────────────────────────────────────────────────

  it('triggerVoiceCommand while listening cancels (toggle)', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    // Trigger again → should cancel
    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('idle')
  })

  // ── Timeout ──────────────────────────────────────────────────────────

  it('auto-cancel after 10s with no speech', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    expect(vc.state.value).toBe('listening')

    // Advance past 10s timeout
    vi.advanceTimersByTime(10_500)
    expect(vc.state.value).toBe('idle')
    expect(vc.error.value).toBeTruthy()
  })

  // ── Error handling ───────────────────────────────────────────────────

  it('speech not supported sets error and stays idle', async () => {
    mockIsSupported.value = false
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    expect(vc.state.value).toBe('idle')
    expect(vc.error.value).toBeTruthy()
  })

  // ── Processing state ─────────────────────────────────────────────────

  it('setProcessing transitions to processing', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    // Manually transition to submitting first
    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    mockSpeechOptions.onResult?.('test')
    mockSpeechOptions.onEnd?.()
    expect(vc.state.value).toBe('submitting')

    // Simulate App.vue calling setProcessing after handling submit event
    vc.setProcessing()
    expect(vc.state.value).toBe('processing')
  })

  it('done returns to idle', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const vc = await getFresh()

    vc.triggerVoiceCommand()
    await vi.advanceTimersByTimeAsync(200)
    mockSpeechOptions.onResult?.('test')
    mockSpeechOptions.onEnd?.()
    vc.setProcessing()
    expect(vc.state.value).toBe('processing')

    vc.done()
    expect(vc.state.value).toBe('idle')
  })
})
