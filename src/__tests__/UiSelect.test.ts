import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UiSelect from '../components/ui/UiSelect.vue'

describe('UiSelect', () => {
  it('renders with modelValue', () => {
    const wrapper = mount(UiSelect, {
      props: { modelValue: 'option-2' },
      slots: {
        default: `
          <option value="option-1">One</option>
          <option value="option-2">Two</option>
        `,
      },
    })
    const select = wrapper.find('select')
    expect(select.element.value).toBe('option-2')
  })

  it('emits update:modelValue on change', async () => {
    const wrapper = mount(UiSelect, {
      props: { modelValue: 'option-1' },
      slots: {
        default: `
          <option value="option-1">One</option>
          <option value="option-2">Two</option>
        `,
      },
    })
    await wrapper.find('select').setValue('option-2')
    const emitted = wrapper.emitted('update:modelValue') as string[][]
    expect(emitted[0][0]).toBe('option-2')
  })

  it('applies disabled state', () => {
    const wrapper = mount(UiSelect, {
      props: { disabled: true },
    })
    expect(wrapper.find('select').attributes('disabled')).toBeDefined()
  })

  it('renders option children', () => {
    const wrapper = mount(UiSelect, {
      props: { modelValue: '' },
      slots: {
        default: '<option value="a">A</option><option value="b">B</option>',
      },
    })
    const options = wrapper.findAll('option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toBe('A')
    expect(options[1].text()).toBe('B')
  })
})
