import { describe, it, expect, vi, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { useTypewriter } from '../composables/useTypewriter'

describe('useTypewriter', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('finish() jumps to the end immediately', async () => {
    const tw = useTypewriter(5)
    tw.feed('A very long text that would take many frames')
    await nextTick()
    tw.finish()
    expect(tw.display.value).toBe('A very long text that would take many frames')
    expect(tw.typing.value).toBe(false)
  })

  it('reset() clears display and stops typing', async () => {
    const tw = useTypewriter(200)
    tw.feed('Some content')
    await nextTick()
    tw.finish()
    tw.reset()
    expect(tw.display.value).toBe('')
    expect(tw.typing.value).toBe(false)
  })

  it('feed with shorter text replaces immediately', async () => {
    const tw = useTypewriter(5)
    tw.feed('Longer initial text here')
    await nextTick()
    tw.finish()
    tw.feed('Short')
    await nextTick()
    // When feed receives shorter content, it resets and shows immediately
    expect(tw.display.value).toBe('Short')
  })

  it('typing is true after feeding slow-speed text', async () => {
    const tw = useTypewriter(2)
    expect(tw.typing.value).toBe(false)
    tw.feed('Some text')
    await nextTick()
    // At speed=2, feed triggers watch which starts typing
    expect(tw.typing.value).toBe(true)
    tw.finish()
    expect(tw.typing.value).toBe(false)
  })
})
