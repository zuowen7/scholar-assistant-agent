import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import UiDropdown from '../components/ui/UiDropdown.vue'
import type { DropdownItem } from '../components/ui/UiDropdown.vue'

describe('UiDropdown', () => {
  const items: DropdownItem[] = [
    { text: 'Edit', onClick: () => {} },
    { text: 'Copy', shortcut: 'Ctrl+C', onClick: () => {} },
    { divider: true },
    { text: 'Delete', danger: true, onClick: () => {} },
  ]

  it('renders trigger slot', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button class="trigger-btn">Actions</button>' },
    })
    expect(wrapper.find('.trigger-btn').exists()).toBe(true)
  })

  it('renders items with correct labels', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button>Menu</button>' },
    })
    // All items should be rendered inside the dropdown panel
    const allText = wrapper.html()
    expect(allText).toContain('Edit')
    expect(allText).toContain('Copy')
    expect(allText).toContain('Delete')
  })

  it('renders divider', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button>Menu</button>' },
    })
    expect(wrapper.find('.dd-divider').exists()).toBe(true)
  })

  it('renders section label', () => {
    const itemsWithLabel: DropdownItem[] = [
      { label: 'EXPORT' },
      { text: 'Markdown', onClick: () => {} },
    ]
    const wrapper = mount(UiDropdown, {
      props: { items: itemsWithLabel },
      slots: { trigger: '<button>Menu</button>' },
    })
    expect(wrapper.find('.dd-section-label').exists()).toBe(true)
  })

  it('renders shortcut text', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button>Menu</button>' },
    })
    expect(wrapper.find('.dd-shortcut').exists()).toBe(true)
    expect(wrapper.find('.dd-shortcut').text()).toBe('Ctrl+C')
  })

  it('applies danger class to danger items', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button>Menu</button>' },
    })
    const dangerItem = wrapper.findAll('.dd-item').find(el => el.classes().includes('danger'))
    expect(dangerItem).toBeTruthy()
    expect(dangerItem!.text()).toContain('Delete')
  })

  it('applies disabled class and attribute', () => {
    const disabledItems: DropdownItem[] = [
      { text: 'Disabled', disabled: true, onClick: () => {} },
    ]
    const wrapper = mount(UiDropdown, {
      props: { items: disabledItems },
      slots: { trigger: '<button>Menu</button>' },
    })
    const btn = wrapper.find('.dd-item')
    expect(btn.classes()).toContain('disabled')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})
