/**
 * Tests for useGlobalHotkey composable.
 *
 * TDD tests for system-wide hotkey registration via tauri-plugin-global-shortcut.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── Mocks ──────────────────────────────────────────────────────────────

const mockRegister = vi.fn().mockResolvedValue(undefined)
const mockUnregister = vi.fn().mockResolvedValue(undefined)

vi.mock('@tauri-apps/plugin-global-shortcut', () => ({
  register: mockRegister,
  unregister: mockUnregister,
}))

describe('useGlobalHotkey', () => {
  const originalTauriInternals = (globalThis as any).__TAURI_INTERNALS__

  beforeEach(() => {
    vi.resetModules()
    mockRegister.mockReset().mockResolvedValue(undefined)
    mockUnregister.mockReset().mockResolvedValue(undefined)
  })

  afterEach(() => {
    if (originalTauriInternals !== undefined) {
      ;(globalThis as any).__TAURI_INTERNALS__ = originalTauriInternals
    } else {
      delete (globalThis as any).__TAURI_INTERNALS__
    }
  })

  async function getFresh() {
    const mod = await import('../composables/useGlobalHotkey')
    return mod.useGlobalHotkey
  }

  // ── Tauri environment ────────────────────────────────────────────────

  it('registers hotkey on creation in Tauri environment', async () => {
    ;(globalThis as any).__TAURI_INTERNALS__ = {}
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup } = useGlobalHotkey('Alt+Space', callback)

    // Dynamic import resolves via mock, need to flush microtasks
    await vi.dynamicImportSettled()

    expect(mockRegister).toHaveBeenCalledWith('Alt+Space', expect.any(Function))
    await cleanup()
  })

  it('fires callback when hotkey is pressed', async () => {
    ;(globalThis as any).__TAURI_INTERNALS__ = {}
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup } = useGlobalHotkey('Alt+Space', callback)

    await vi.dynamicImportSettled()

    const handler = mockRegister.mock.calls[0]?.[1]
    expect(handler).toBeDefined()
    handler({ state: 'Pressed', shortcuts: ['Alt+Space'] })
    expect(callback).toHaveBeenCalledTimes(1)

    await cleanup()
  })

  it('does not fire callback on key release', async () => {
    ;(globalThis as any).__TAURI_INTERNALS__ = {}
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup } = useGlobalHotkey('Alt+Space', callback)

    await vi.dynamicImportSettled()

    const handler = mockRegister.mock.calls[0]?.[1]
    handler({ state: 'Released', shortcuts: ['Alt+Space'] })
    expect(callback).not.toHaveBeenCalled()

    await cleanup()
  })

  // ── Non-Tauri (browser) environment ──────────────────────────────────

  it('does not register in browser environment', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup, isRegistered } = useGlobalHotkey('Alt+Space', callback)

    await vi.dynamicImportSettled()

    expect(mockRegister).not.toHaveBeenCalled()
    expect(isRegistered.value).toBe(false)
    await cleanup()
  })

  // ── changeHotkey ─────────────────────────────────────────────────────

  it('changeHotkey unregisters old and registers new', async () => {
    ;(globalThis as any).__TAURI_INTERNALS__ = {}
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { changeHotkey, currentKey, cleanup } = useGlobalHotkey('Alt+Space', callback)

    await vi.dynamicImportSettled()
    expect(mockRegister).toHaveBeenCalledWith('Alt+Space', expect.any(Function))

    await changeHotkey('Ctrl+Shift+V')
    expect(mockUnregister).toHaveBeenCalledWith('Alt+Space')
    expect(mockRegister).toHaveBeenCalledWith('Ctrl+Shift+V', expect.any(Function))
    expect(currentKey.value).toBe('Ctrl+Shift+V')

    await cleanup()
  })

  // ── cleanup ──────────────────────────────────────────────────────────

  it('cleanup unregisters the current hotkey', async () => {
    ;(globalThis as any).__TAURI_INTERNALS__ = {}
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup } = useGlobalHotkey('Alt+Space', callback)

    await vi.dynamicImportSettled()
    await cleanup()

    expect(mockUnregister).toHaveBeenCalledWith('Alt+Space')
  })

  it('cleanup does nothing in browser environment', async () => {
    delete (globalThis as any).__TAURI_INTERNALS__
    const callback = vi.fn()
    const useGlobalHotkey = await getFresh()
    const { cleanup } = useGlobalHotkey('Alt+Space', callback)

    await cleanup()
    expect(mockUnregister).not.toHaveBeenCalled()
  })
})
