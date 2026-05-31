import { describe, it, expect } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (typeof params === 'object' && params !== null) {
        let result = key
        for (const [k, v] of Object.entries(params)) {
          result = result.replace(`{${k}}`, String(v))
        }
        return result
      }
      return key
    },
    locale: { value: 'zh-CN' },
  }),
  createI18n: () => ({
    global: { locale: { value: 'zh-CN' }, t: (k: string) => k },
  }),
}))
import { mount } from '@vue/test-utils'
import UiButton from '../components/ui/UiButton.vue'

describe('UiButton', () => {
  it('renders slot content', () => {
    const wrapper = mount(UiButton, {
      slots: { default: 'Click Me' },
    })
    expect(wrapper.text()).toBe('Click Me')
  })

  it('renders with correct default variant class', () => {
    const wrapper = mount(UiButton, { slots: { default: 'OK' } })
    expect(wrapper.classes()).toContain('secondary')
  })

  it('applies variant class', () => {
    const wrapper = mount(UiButton, {
      props: { variant: 'primary' },
      slots: { default: 'Primary' },
    })
    expect(wrapper.classes()).toContain('primary')
  })

  it('applies size class', () => {
    const wrapper = mount(UiButton, {
      props: { size: 'lg' },
      slots: { default: 'Large' },
    })
    expect(wrapper.classes()).toContain('lg')
  })

  it('applies danger variant', () => {
    const wrapper = mount(UiButton, {
      props: { variant: 'danger' },
      slots: { default: 'Delete' },
    })
    expect(wrapper.classes()).toContain('danger')
  })

  it('emits click event when clicked', async () => {
    const wrapper = mount(UiButton, {
      slots: { default: 'Click' },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(UiButton, {
      props: { disabled: true },
      slots: { default: 'Cannot click' },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('does not emit click when loading', async () => {
    const wrapper = mount(UiButton, {
      props: { loading: true },
      slots: { default: 'Loading' },
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeUndefined()
  })

  it('shows loading dots when loading', () => {
    const wrapper = mount(UiButton, {
      props: { loading: true },
      slots: { default: 'Loading' },
    })
    expect(wrapper.find('.btn-loader-dots').exists()).toBe(true)
  })

  it('does not show loading dots when not loading', () => {
    const wrapper = mount(UiButton, {
      slots: { default: 'Normal' },
    })
    expect(wrapper.find('.btn-loader-dots').exists()).toBe(false)
  })

  it('applies icon-only class when iconOnly is true', () => {
    const wrapper = mount(UiButton, {
      props: { iconOnly: true },
      slots: { default: '×' },
    })
    expect(wrapper.classes()).toContain('icon-only')
  })

  it('sets button type attribute', () => {
    const wrapper = mount(UiButton, {
      props: { type: 'submit' },
      slots: { default: 'Submit' },
    })
    expect(wrapper.attributes('type')).toBe('submit')
  })

  it('renders left icon slot', () => {
    const wrapper = mount(UiButton, {
      slots: {
        default: 'Save',
        'icon-left': '<span class="test-icon">📁</span>',
      },
    })
    expect(wrapper.find('.btn-icon').exists()).toBe(true)
  })

  it('does not render icon container when no icon slot', () => {
    const wrapper = mount(UiButton, {
      slots: { default: 'Plain' },
    })
    expect(wrapper.find('.btn-icon').exists()).toBe(false)
  })
})
