import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import AppSidebar from '../components/shell/AppSidebar.vue'

describe('AppSidebar Agent entry', () => {
  it('offers Agent as a primary workspace action instead of a footer-only icon', async () => {
    const wrapper = mount(AppSidebar, {
      props: { activeModule: 'write', recentFiles: [], provider: 'local', model: 'qwen' },
    })

    expect(wrapper.find('.sidebar-footer [data-testid="workspace-agent"]').exists()).toBe(false)
    await wrapper.get('.primary-nav [data-testid="workspace-agent"]').trigger('click')
    expect(wrapper.emitted('agent')).toHaveLength(1)
  })

  it('marks the active workspace for assistive technology', () => {
    const wrapper = mount(AppSidebar, {
      props: { activeModule: 'mindmap', recentFiles: [], provider: 'local', model: 'qwen' },
    })

    const current = wrapper.get('[aria-current="page"]')
    expect(current.text()).toContain('shell.think')
    expect(wrapper.get('.settings-button').attributes('aria-label')).toBe('topbar.settings')
  })
})
