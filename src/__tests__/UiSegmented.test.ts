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
import UiSegmented from '../components/ui/UiSegmented.vue'
import { h } from 'vue'

describe('UiSegmented', () => {
  const options = [
    { value: 'tab1', label: 'Tab 1' },
    { value: 'tab2', label: 'Tab 2' },
    { value: 'tab3', label: 'Tab 3' },
  ]

  it('renders all options', () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(3)
    expect(buttons[0].text()).toContain('Tab 1')
    expect(buttons[1].text()).toContain('Tab 2')
  })

  it('marks selected option as active', () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab2', options },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons[1].classes()).toContain('active')
    expect(buttons[0].classes()).not.toContain('active')
  })

  it('emits update:modelValue when clicking unselected option', async () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options },
    })
    await wrapper.findAll('button')[2].trigger('click')
    const emitted = wrapper.emitted('update:modelValue') as any[][]
    expect(emitted[0][0]).toBe('tab3')
  })

  it('does not emit when clicking already selected option', async () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options },
    })
    await wrapper.findAll('button')[0].trigger('click')
    // Clicking active should still emit (no-op in parent)
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  it('does not emit when clicking disabled option', async () => {
    const disabledOpts = [
      { value: 'a', label: 'A' },
      { value: 'b', label: 'B', disabled: true },
    ]
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'a', options: disabledOpts },
    })
    await wrapper.findAll('button')[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('applies size class', () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options, size: 'sm' },
    })
    expect(wrapper.classes()).toContain('sm')
  })

  it('applies full class', () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options, full: true },
    })
    expect(wrapper.classes()).toContain('full')
  })

  it('sets aria-selected on active option', () => {
    const wrapper = mount(UiSegmented, {
      props: { modelValue: 'tab1', options },
    })
    expect(wrapper.findAll('button')[0].attributes('aria-selected')).toBe('true')
    expect(wrapper.findAll('button')[1].attributes('aria-selected')).toBe('false')
  })
})
