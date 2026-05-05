import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UiTooltip from '../components/ui/UiTooltip.vue'

describe('UiTooltip', () => {
  it('renders slot content', () => {
    const wrapper = mount(UiTooltip, {
      props: { text: 'Helpful hint' },
      slots: { default: '<button>Hover me</button>' },
    })
    expect(wrapper.text()).toContain('Hover me')
  })

  it('renders tooltip text', () => {
    const wrapper = mount(UiTooltip, {
      props: { text: 'This is a tooltip' },
      slots: { default: '<span>Target</span>' },
    })
    expect(wrapper.find('.ui-tooltip').text()).toBe('This is a tooltip')
  })

  it('sets role="tooltip" on tooltip element', () => {
    const wrapper = mount(UiTooltip, {
      props: { text: 'Accessible tip' },
      slots: { default: '<span>Target</span>' },
    })
    expect(wrapper.find('[role="tooltip"]').exists()).toBe(true)
  })
})
