import { describe, it, expect } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: { value: 'zh-CN' } }),
  createI18n: () => ({ global: { locale: { value: 'zh-CN' }, t: (k: string) => k } }),
}))

import { mount } from '@vue/test-utils'
import UiEmpty from '../components/ui/UiEmpty.vue'

describe('UiEmpty', () => {
  it('renders title and subtitle', () => {
    const wrapper = mount(UiEmpty, {
      props: {
        title: 'No items found',
        subtitle: 'Try adding some content first',
      },
    })

    expect(wrapper.text()).toContain('No items found')
    expect(wrapper.text()).toContain('Try adding some content first')
  })

  it('renders only title when no subtitle', () => {
    const wrapper = mount(UiEmpty, {
      props: { title: 'Empty state' },
    })

    expect(wrapper.text()).toContain('Empty state')
    const subtitle = wrapper.find('.ui-empty-subtitle')
    expect(subtitle.exists()).toBe(false)
  })

  it('renders action button when actionLabel provided', () => {
    const wrapper = mount(UiEmpty, {
      props: {
        title: 'No projects',
        actionLabel: 'Create project',
      },
    })

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('Create project')
  })

  it('does not render action button without actionLabel', () => {
    const wrapper = mount(UiEmpty, {
      props: { title: 'Nothing here' },
    })

    const btn = wrapper.find('button')
    expect(btn.exists()).toBe(false)
  })

  it('emits action when button is clicked', async () => {
    const wrapper = mount(UiEmpty, {
      props: {
        title: 'Empty',
        actionLabel: 'Add item',
      },
    })

    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted()).toHaveProperty('action')
    expect(wrapper.emitted().action).toHaveLength(1)
  })

  it('renders icon element when icon prop provided', () => {
    const wrapper = mount(UiEmpty, {
      props: { title: 'No data', icon: 'FolderIcon' },
      global: { stubs: { FolderIcon: true } },
    })

    const iconContainer = wrapper.find('.ui-empty-icon')
    expect(iconContainer.exists()).toBe(true)
  })

  it('renders custom icon slot', () => {
    const wrapper = mount(UiEmpty, {
      props: { title: 'Empty' },
      slots: { icon: '<span class="custom-icon">X</span>' },
    })

    expect(wrapper.find('.custom-icon').exists()).toBe(true)
  })

  it('renders custom actions slot', () => {
    const wrapper = mount(UiEmpty, {
      props: { title: 'Empty' },
      slots: { actions: '<button class="custom-action">Custom</button>' },
    })

    expect(wrapper.find('.custom-action').exists()).toBe(true)
  })
})
