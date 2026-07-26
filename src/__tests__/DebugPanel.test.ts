import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
  createI18n: () => ({
    global: { locale: { value: 'zh-CN' }, t: (key: string) => key },
    install: vi.fn(),
  }),
}))

import DebugPanel from '../components/DebugPanel.vue'

afterEach(() => {
  document.body.querySelectorAll('.ui-popover-panel').forEach((node) => node.remove())
})

describe('DebugPanel', () => {
  it('opens above settings dialogs instead of behind their modal layer', async () => {
    const wrapper = mount(DebugPanel, { attachTo: document.body })

    await wrapper.get('.dp-trigger').trigger('click')
    await wrapper.vm.$nextTick()

    const panel = document.body.querySelector<HTMLElement>('.ui-popover-panel')
    expect(panel).not.toBeNull()
    expect(panel!.classList).toContain('ui-popover-panel--modal-safe')
    wrapper.unmount()
  })
})
