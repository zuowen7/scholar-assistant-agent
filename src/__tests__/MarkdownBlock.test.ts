import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import MarkdownBlock from '../components/MarkdownBlock.vue'

const { renderMarkdown } = vi.hoisted(() => ({
  renderMarkdown: vi.fn((source: string) => `<p>${source}</p>`),
}))

vi.mock('../utils/markdown', () => ({ renderMarkdown }))

describe('MarkdownBlock', () => {
  it('re-renders only when its own source changes', async () => {
    const wrapper = mount(MarkdownBlock, { props: { source: 'first' } })

    expect(wrapper.html()).toContain('<p>first</p>')
    expect(renderMarkdown).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ source: 'first' })
    expect(renderMarkdown).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ source: 'second' })
    expect(wrapper.html()).toContain('<p>second</p>')
    expect(renderMarkdown).toHaveBeenCalledTimes(2)
  })

  it('coalesces streaming token bursts and flushes the final response', async () => {
    vi.useFakeTimers()
    renderMarkdown.mockClear()
    const wrapper = mount(MarkdownBlock, { props: { source: 'a', streaming: true } })

    await wrapper.setProps({ source: 'ab' })
    await wrapper.setProps({ source: 'abc' })
    expect(renderMarkdown).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(40)
    expect(wrapper.html()).toContain('<p>abc</p>')
    expect(renderMarkdown).toHaveBeenCalledTimes(2)

    await wrapper.setProps({ source: 'final', streaming: false })
    expect(wrapper.html()).toContain('<p>final</p>')
    expect(renderMarkdown).toHaveBeenCalledTimes(3)
    vi.useRealTimers()
  })
})
