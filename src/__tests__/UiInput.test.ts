import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UiInput from '../components/ui/UiInput.vue'

describe('UiInput', () => {
  it('v-model works: typing emits update', async () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: '' },
    })
    const input = wrapper.find('input')
    await input.setValue('new text')
    const emitted = wrapper.emitted('update:modelValue') as string[][]
    expect(emitted[0][0]).toBe('new text')
  })

  it('reflects modelValue prop', () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: 'hello' },
    })
    expect(wrapper.find('input').element.value).toBe('hello')
  })

  it('emits empty string on clear button click', async () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: 'text to clear', clearable: true },
    })
    await wrapper.find('.ui-input-clear').trigger('click')
    const emitted = wrapper.emitted('update:modelValue') as string[][]
    expect(emitted[0][0]).toBe('')
  })

  it('hides clear button when value is empty', () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: '', clearable: true },
    })
    expect(wrapper.find('.ui-input-clear').exists()).toBe(false)
  })

  it('hides clear button when not clearable', () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: 'text', clearable: false },
    })
    expect(wrapper.find('.ui-input-clear').exists()).toBe(false)
  })

  it('sets placeholder attribute', () => {
    const wrapper = mount(UiInput, {
      props: { placeholder: 'Enter name...' },
    })
    expect(wrapper.find('input').attributes('placeholder')).toBe('Enter name...')
  })

  it('sets type attribute', () => {
    const wrapper = mount(UiInput, {
      props: { type: 'password' },
    })
    expect(wrapper.find('input').attributes('type')).toBe('password')
  })

  it('applies disabled class and attribute', () => {
    const wrapper = mount(UiInput, {
      props: { disabled: true },
    })
    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
    expect(wrapper.classes()).toContain('disabled')
  })

  it('applies error class and aria-invalid', () => {
    const wrapper = mount(UiInput, {
      props: { error: true },
    })
    expect(wrapper.classes()).toContain('has-error')
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('true')
  })

  it('does not have error by default', () => {
    const wrapper = mount(UiInput)
    expect(wrapper.classes()).not.toContain('has-error')
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('false')
  })

  it('renders prefix and suffix slots', () => {
    const wrapper = mount(UiInput, {
      props: { modelValue: '' },
      slots: {
        prefix: '<span class="pfx">🔍</span>',
        suffix: '<span class="sfx">.com</span>',
      },
    })
    expect(wrapper.find('.ui-input-prefix').exists()).toBe(true)
    expect(wrapper.find('.ui-input-suffix').exists()).toBe(true)
  })

  it('prefix/suffix do not render when slots not provided', () => {
    const wrapper = mount(UiInput)
    expect(wrapper.find('.ui-input-prefix').exists()).toBe(false)
    expect(wrapper.find('.ui-input-suffix').exists()).toBe(false)
  })
})
