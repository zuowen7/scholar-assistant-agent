import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TranslationBlockHtml from '../components/TranslationBlockHtml.vue'

const mocks = vi.hoisted(() => ({
  renderBlock: vi.fn((text: string) => `<p>${text}</p>`),
  renderSentenceMarkedHtml: vi.fn((text: string, lang: string) => `<span>${lang}:${text}</span>`),
}))

vi.mock('../utils/markdown', () => ({ renderBlock: mocks.renderBlock }))
vi.mock('../utils/sentenceAlign', () => ({
  renderSentenceMarkedHtml: mocks.renderSentenceMarkedHtml,
}))

describe('TranslationBlockHtml', () => {
  it('caches block rendering until its text changes', async () => {
    const wrapper = mount(TranslationBlockHtml, {
      props: { text: 'source', blockType: 'paragraph' },
    })
    expect(wrapper.html()).toContain('<p>source</p>')
    expect(mocks.renderBlock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ text: 'source' })
    expect(mocks.renderBlock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ text: 'updated' })
    expect(wrapper.html()).toContain('<p>updated</p>')
    expect(mocks.renderBlock).toHaveBeenCalledTimes(2)
  })

  it('renders sentence markers with the requested language', () => {
    const wrapper = mount(TranslationBlockHtml, {
      props: { text: '译文', mode: 'sentence', lang: 'zh', blockId: 'b1', side: 'trans' },
    })
    expect(wrapper.html()).toContain('<span>zh:译文</span>')
    expect(mocks.renderSentenceMarkedHtml).toHaveBeenCalledWith('译文', 'zh', 'b1', 'trans')
  })
})
