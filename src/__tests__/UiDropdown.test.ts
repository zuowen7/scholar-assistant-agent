import { afterEach, describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import UiDropdown from '../components/ui/UiDropdown.vue'
import type { DropdownItem } from '../components/ui/UiDropdown.vue'

describe('UiDropdown', () => {
  const items: DropdownItem[] = [
    { text: 'Edit', onClick: () => {} },
    { text: 'Copy', shortcut: 'Ctrl+C', onClick: () => {} },
    { divider: true },
    { text: 'Delete', danger: true, onClick: () => {} },
  ]

  afterEach(() => {
    document.body.innerHTML = ''
  })

  async function mountOpen(itemsToRender: DropdownItem[]) {
    const wrapper = mount(UiDropdown, {
      attachTo: document.body,
      props: { items: itemsToRender },
      slots: { trigger: '<button>Menu</button>' },
    })
    await wrapper.find('.ui-popover-trigger').trigger('click')
    await nextTick()
    return wrapper
  }

  it('renders trigger slot', () => {
    const wrapper = mount(UiDropdown, {
      props: { items },
      slots: { trigger: '<button class="trigger-btn">Actions</button>' },
    })
    expect(wrapper.find('.trigger-btn').exists()).toBe(true)
  })

  it('renders items with correct labels', async () => {
    await mountOpen(items)
    // All items should be rendered inside the dropdown panel
    const allText = document.body.innerHTML
    expect(allText).toContain('Edit')
    expect(allText).toContain('Copy')
    expect(allText).toContain('Delete')
  })

  it('renders divider', async () => {
    await mountOpen(items)
    expect(document.body.querySelector('.dd-divider')).toBeTruthy()
  })

  it('renders section label', async () => {
    const itemsWithLabel: DropdownItem[] = [
      { label: 'EXPORT' },
      { text: 'Markdown', onClick: () => {} },
    ]
    await mountOpen(itemsWithLabel)
    expect(document.body.querySelector('.dd-section-label')).toBeTruthy()
  })

  it('renders shortcut text', async () => {
    await mountOpen(items)
    const shortcut = document.body.querySelector('.dd-shortcut')
    expect(shortcut).toBeTruthy()
    expect(shortcut?.textContent).toBe('Ctrl+C')
  })

  it('applies danger class to danger items', async () => {
    await mountOpen(items)
    const dangerItem = document.body.querySelector('.dd-item.danger')
    expect(dangerItem).toBeTruthy()
    expect(dangerItem?.textContent).toContain('Delete')
  })

  it('applies disabled class and attribute', async () => {
    const disabledItems: DropdownItem[] = [
      { text: 'Disabled', disabled: true, onClick: () => {} },
    ]
    await mountOpen(disabledItems)
    const btn = document.body.querySelector('.dd-item')
    expect(btn?.classList.contains('disabled')).toBe(true)
    expect(btn?.hasAttribute('disabled')).toBe(true)
  })
})
