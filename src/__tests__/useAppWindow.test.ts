import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { close, getCurrentWindow, minimize, toggleMaximize } = vi.hoisted(() => ({
  close: vi.fn().mockResolvedValue(undefined),
  getCurrentWindow: vi.fn(),
  minimize: vi.fn().mockResolvedValue(undefined),
  toggleMaximize: vi.fn().mockResolvedValue(undefined),
}))

getCurrentWindow.mockReturnValue({ close, minimize, toggleMaximize })

vi.mock('@tauri-apps/api/window', () => ({ getCurrentWindow }))

import { useAppWindow } from '../composables/useAppWindow'

describe('useAppWindow', () => {
  const originalTauriInternals = (globalThis as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__

  beforeEach(() => {
    delete (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
    window.history.replaceState({}, '', '/')
    vi.clearAllMocks()
  })

  afterEach(() => {
    window.history.replaceState({}, '', '/')
    if (originalTauriInternals === undefined) {
      delete (globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__
    } else {
      ;(globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ =
        originalTauriInternals
    }
  })

  it('keeps the browser development entry mountable without Tauri internals', async () => {
    const controls = useAppWindow()

    expect(getCurrentWindow).not.toHaveBeenCalled()
    await expect(controls.handleMinimize()).resolves.toBeUndefined()
    await expect(controls.handleToggleMaximize()).resolves.toBeUndefined()
    await expect(controls.handleClose()).resolves.toBeUndefined()
    expect(minimize).not.toHaveBeenCalled()
    expect(toggleMaximize).not.toHaveBeenCalled()
    expect(close).not.toHaveBeenCalled()
  })

  it('delegates window controls to Tauri when native internals are available', async () => {
    ;(globalThis as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {}
    const controls = useAppWindow()

    await controls.handleMinimize()
    await controls.handleToggleMaximize()
    await controls.handleClose()

    expect(getCurrentWindow).toHaveBeenCalledTimes(1)
    expect(minimize).toHaveBeenCalledTimes(1)
    expect(toggleMaximize).toHaveBeenCalledTimes(1)
    expect(close).toHaveBeenCalledTimes(1)
  })

  it('detects and cleans the agent-only URL without requiring Tauri', async () => {
    window.history.replaceState({}, '', '/?agent-only=1')

    const controls = useAppWindow()

    expect(controls.isAgentOnly.value).toBe(true)
    expect(window.location.search).toBe('')
    await expect(controls.onAgentWindowClose()).resolves.toBeUndefined()
    expect(close).not.toHaveBeenCalled()
  })
})
