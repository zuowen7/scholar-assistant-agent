/**
 * Tests for useWakeWord composable.
 *
 * Tests wake word detection using Web Speech API continuous mode.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── Mock SpeechRecognition ──────────────────────────────────────────────

let mockSRInstance: any = null
const mockStart = vi.fn()
const mockStop = vi.fn()

function MockSpeechRecognition(this: any) {
  this.continuous = false
  this.interimResults = false
  this.lang = ''
  this.maxAlternatives = 1
  this.onresult = null
  this.onerror = null
  this.onend = null
  this.start = mockStart
  this.stop = mockStop
  this.abort = vi.fn()
  mockSRInstance = this
}

beforeEach(() => {
  mockSRInstance = null
  mockStart.mockReset()
  mockStop.mockReset()

  // Install mock as a constructor function (not arrow function)
  ;(globalThis as any).SpeechRecognition = MockSpeechRecognition
  ;(globalThis as any).webkitSpeechRecognition = undefined
})

afterEach(() => {
  delete (globalThis as any).SpeechRecognition
  delete (globalThis as any).webkitSpeechRecognition
})

describe('useWakeWord', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function getFresh() {
    const mod = await import('../composables/useWakeWord')
    return mod.useWakeWord
  }

  it('startWakeWord creates SpeechRecognition and starts it', async () => {
    const useWakeWord = await getFresh()
    const { startWakeWord, active, stopWakeWord } = useWakeWord(vi.fn())
    await startWakeWord()
    expect(active.value).toBe(true)
    expect(mockSRInstance).not.toBeNull()
    expect(mockStart).toHaveBeenCalled()
    stopWakeWord()
  })

  it('wake word "小研" in result triggers callback', async () => {
    const callback = vi.fn()
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(callback)
    await startWakeWord()

    // Exact match
    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '小研 帮我翻译' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).toHaveBeenCalledTimes(1)
    stopWakeWord()
  })

  it('homophone "小严" also triggers callback', async () => {
    const callback = vi.fn()
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(callback)
    await startWakeWord()

    // Homophone — speech recognition hears "严" instead of "研"
    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '小严 帮我翻译' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).toHaveBeenCalledTimes(1)
    stopWakeWord()
  })

  it('homophone "小言" also triggers callback', async () => {
    const callback = vi.fn()
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(callback)
    await startWakeWord()

    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '你好小言帮我翻译' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).toHaveBeenCalledTimes(1)
    stopWakeWord()
  })

  it('non-matching speech does not trigger callback', async () => {
    const callback = vi.fn()
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(callback)
    await startWakeWord()

    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '今天天气不错' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).not.toHaveBeenCalled()
    stopWakeWord()
  })

  it('stopWakeWord stops recognition and sets active=false', async () => {
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord, active } = useWakeWord(vi.fn())
    await startWakeWord()
    expect(active.value).toBe(true)
    stopWakeWord()
    expect(active.value).toBe(false)
    expect(mockStop).toHaveBeenCalled()
  })

  it('auto-restarts on onend event', async () => {
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord, active } = useWakeWord(vi.fn())
    await startWakeWord()

    // Simulate recognition ending naturally
    mockStart.mockClear()
    mockSRInstance.onend()

    // Should schedule restart after 300ms
    vi.advanceTimersByTime(400)
    expect(mockStart).toHaveBeenCalledTimes(1)

    stopWakeWord()
  })

  it('no-speech error triggers restart', async () => {
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(vi.fn())
    await startWakeWord()

    mockStart.mockClear()
    mockSRInstance.onerror({ error: 'no-speech' })

    vi.advanceTimersByTime(400)
    expect(mockStart).toHaveBeenCalledTimes(1)

    stopWakeWord()
  })

  it('sets error when SpeechRecognition not available', async () => {
    delete (globalThis as any).SpeechRecognition
    delete (globalThis as any).webkitSpeechRecognition

    const useWakeWord = await getFresh()
    const { startWakeWord, error } = useWakeWord(vi.fn())
    await startWakeWord()
    expect(error.value).toBeTruthy()
  })

  it('reads custom wake word from localStorage', async () => {
    localStorage.setItem('voice-settings', JSON.stringify({ wakeWordPhrase: '你好助手' }))
    const callback = vi.fn()
    const useWakeWord = await getFresh()
    const { startWakeWord, stopWakeWord } = useWakeWord(callback)
    await startWakeWord()

    // Should NOT trigger on "小研"
    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '小研 帮我翻译' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).not.toHaveBeenCalled()

    // Should trigger on "你好助手"
    mockSRInstance.onresult({
      resultIndex: 0,
      results: [{
        0: { transcript: '你好助手 帮我翻译' },
        length: 1,
        isFinal: true,
      }],
    })
    expect(callback).toHaveBeenCalledTimes(1)

    stopWakeWord()
    localStorage.removeItem('voice-settings')
  })
})
