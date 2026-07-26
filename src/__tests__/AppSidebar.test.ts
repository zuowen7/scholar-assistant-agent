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
})
