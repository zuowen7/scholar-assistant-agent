import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UiPill from '../components/ui/UiPill.vue'

describe('UiPill', () => {
  it('renders slot content', () => {
    const wrapper = mount(UiPill, {
      slots: { default: 'Online' },
    })
    expect(wrapper.text()).toBe('Online')
  })

  it('applies tone class', () => {
    const wrapper = mount(UiPill, {
      props: { tone: 'ok' },
      slots: { default: 'OK' },
    })
    expect(wrapper.classes()).toContain('ok')
  })

  it('default tone is neutral', () => {
    const wrapper = mount(UiPill, {
      slots: { default: 'Default' },
    })
    // No tone class added when unspecified
    expect(wrapper.classes()).not.toContain('ok')
    expect(wrapper.classes()).not.toContain('danger')
  })

  it('renders as button when clickable', () => {
    const wrapper = mount(UiPill, {
      props: { clickable: true },
      slots: { default: 'Click' },
    })
    expect(wrapper.find('button').exists()).toBe(true)
  })

  it('renders as span when not clickable', () => {
    const wrapper = mount(UiPill, {
      slots: { default: 'Static' },
    })
    expect(wrapper.find('span').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('emits click when clickable', async () => {
    const wrapper = mount(UiPill, {
      props: { clickable: true },
      slots: { default: 'Click me' },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('does not emit click when not clickable', async () => {
    const wrapper = mount(UiPill, {
      slots: { default: 'Static' },
    })
    await wrapper.find('span').trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(UiPill, {
      props: { clickable: true, disabled: true },
      slots: { default: 'Disabled' },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('shows dot indicator', () => {
    const wrapper = mount(UiPill, {
      slots: { default: 'Status' },
    })
    expect(wrapper.find('.pill-dot').exists()).toBe(true)
  })
})
