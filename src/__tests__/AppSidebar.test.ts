import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import AppSidebar from '../components/shell/AppSidebar.vue'

describe('AppSidebar Agent entry', () => {
  it('keeps Agent outside the project section navigation', async () => {
    const wrapper = mount(AppSidebar, {
      props: {
        activeModule: 'draft',
        workspaceActive: true,
        provider: 'local',
        model: 'qwen',
      },
    })

    expect(wrapper.find('.primary-nav [data-testid="workspace-agent"]').exists()).toBe(false)
    await wrapper.get('.sidebar-footer [data-testid="workspace-agent"]').trigger('click')
    expect(wrapper.emitted('agent')).toHaveLength(1)
  })
})
