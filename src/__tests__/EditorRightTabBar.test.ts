import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import EditorRightTabBar from '../components/EditorRightTabBar.vue'

describe('EditorRightTabBar', () => {
  it('exposes labeled Agent, preview, and argument tabs', async () => {
    const wrapper = mount(EditorRightTabBar, {
      props: { modelValue: 'preview', agentOpen: false },
    })

    expect(wrapper.get('[data-testid="right-tab-agent"]').text()).toContain('editor.rightAgent')
    await wrapper.get('[data-testid="right-tab-agent"]').trigger('click')
    await wrapper.get('[data-testid="right-tab-preview"]').trigger('click')
    await wrapper.get('[data-testid="right-tab-argument"]').trigger('click')

    expect(wrapper.emitted('openAgent')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')).toEqual([['preview'], ['argument']])
  })

  it('emits null when the dock is closed', async () => {
    const wrapper = mount(EditorRightTabBar, { props: { modelValue: 'preview' } })
    await wrapper.get('[data-testid="right-tab-close"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[null]])
  })
})
