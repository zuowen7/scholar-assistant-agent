import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAppMode } from '../composables/useAppMode'

// useAppMode is a module-level singleton — reset state between tests
describe('useAppMode', () => {
  beforeEach(() => {
    const { setMode, toggleAgentChat } = useAppMode()
    setMode('editor')
    toggleAgentChat(false)
    // Reset modeTransition without waiting for timer
    useAppMode().modeTransition.value = false
  })

  it('setMode updates appMode ref', () => {
    const { appMode, setMode } = useAppMode()
    expect(appMode.value).toBe('editor')
    setMode('translate')
    expect(appMode.value).toBe('translate')
  })

  it('setMode cycles through all modes', () => {
    const { appMode, setMode } = useAppMode()
    setMode('editor')
    expect(appMode.value).toBe('editor')
    setMode('translate')
    expect(appMode.value).toBe('translate')
    setMode('argument')
    expect(appMode.value).toBe('argument')
  })

  it('toggleAgentChat toggles boolean', () => {
    const { showAgentChat, toggleAgentChat } = useAppMode()
    expect(showAgentChat.value).toBe(false)
    toggleAgentChat()
    expect(showAgentChat.value).toBe(true)
    toggleAgentChat()
    expect(showAgentChat.value).toBe(false)
  })

  it('toggleAgentChat(true) forces open', () => {
    const { showAgentChat, toggleAgentChat } = useAppMode()
    expect(showAgentChat.value).toBe(false)
    toggleAgentChat(true)
    expect(showAgentChat.value).toBe(true)
    toggleAgentChat(true)
    expect(showAgentChat.value).toBe(true)
  })

  it('toggleAgentChat(false) forces close', () => {
    const { showAgentChat, toggleAgentChat } = useAppMode()
    toggleAgentChat(true)
    expect(showAgentChat.value).toBe(true)
    toggleAgentChat(false)
    expect(showAgentChat.value).toBe(false)
    toggleAgentChat(false)
    expect(showAgentChat.value).toBe(false)
  })

  it('modeTransition flashes true then resets after setMode', async () => {
    vi.useFakeTimers()
    const { modeTransition, setMode } = useAppMode()
    expect(modeTransition.value).toBe(false)
    setMode('translate')
    expect(modeTransition.value).toBe(true)
    vi.advanceTimersByTime(350)
    expect(modeTransition.value).toBe(false)
    vi.useRealTimers()
  })
})
