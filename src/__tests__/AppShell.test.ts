import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const { startDragging, toggleMaximize } = vi.hoisted(() => ({
  startDragging: vi.fn(),
  toggleMaximize: vi.fn(),
}))

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({
    startDragging,
    toggleMaximize,
    minimize: vi.fn(),
    close: vi.fn(),
  }),
}))
vi.mock('@tauri-apps/api/webview', () => ({
  getCurrentWebview: () => ({ setZoom: vi.fn() }),
}))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import AppShell from '../components/shell/AppShell.vue'

const props = {
  activeModule: 'write' as const,
  recentFiles: [],
  provider: 'local',
  model: 'qwen',
}

describe('AppShell window chrome', () => {
  beforeEach(() => {
    startDragging.mockClear()
    toggleMaximize.mockClear()
  })

  it('starts native dragging from the active shell drag rail', async () => {
    const wrapper = mount(AppShell, { props, slots: { default: '<div>workspace</div>' } })

    await wrapper.get('[data-testid="window-drag-rail"]').trigger('mousedown', { button: 0 })

    expect(startDragging).toHaveBeenCalledTimes(1)
  })

  it('ignores non-primary mouse buttons and supports title-bar double click', async () => {
    const wrapper = mount(AppShell, { props })
    const rail = wrapper.get('[data-testid="window-drag-rail"]')

    await rail.trigger('mousedown', { button: 2 })
    expect(startDragging).not.toHaveBeenCalled()

    await rail.trigger('dblclick')
    expect(toggleMaximize).toHaveBeenCalledTimes(1)
  })
})
