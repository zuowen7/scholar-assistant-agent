/**
 * Phase 5 TDD — CompanionPanel "导入真实审稿意见" UI.
 *
 * Tests that the import section exists and emits the correct event.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

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

vi.mock('monaco-editor', () => ({
  Range: class Range {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  },
  editor: {},
}))
vi.mock('../utils/api', () => ({ API_BASE: 'http://127.0.0.1:18088' }))
vi.mock('../composables/useEditorState', () => ({
  tabs: { value: [] },
  activeTabId: { value: null },
  activeTab: { value: null },
  content: { value: '' },
  contentVersion: { value: 0 },
}))
vi.mock('@tauri-apps/plugin-fs', () => ({
  writeTextFile: vi.fn().mockResolvedValue(undefined),
}))

import { _resetForTesting, useArgumentCompanion } from '../composables/useArgumentCompanion'
import CompanionPanel from '../components/argument/CompanionPanel.vue'

describe('CompanionPanel Phase 5 — import real reviews', () => {
  beforeEach(() => {
    _resetForTesting()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({}),
      body: null,
    }))
  })

  it('shows import reviews section in Reviewer 2 tab', async () => {
    const wrapper = mount(CompanionPanel, {
      props: { content: 'paper text' },
    })
    // Switch to Reviewer 2 tab
    const reviewerTab = wrapper.findAll('button').find(b => b.text().includes('Reviewer'))
    if (reviewerTab) await reviewerTab.trigger('click')

    const html = wrapper.html()
    expect(html).toMatch(/导入|import|真实.*审稿|real.*review/i)
  })

  it('has a textarea for pasting real reviews', async () => {
    const wrapper = mount(CompanionPanel, {
      props: { content: 'paper text' },
    })
    const reviewerTab = wrapper.findAll('button').find(b => b.text().includes('Reviewer'))
    if (reviewerTab) await reviewerTab.trigger('click')

    const textarea = wrapper.find('[data-import-textarea]')
    expect(textarea.exists()).toBe(true)
  })

  it('has a submit button for importing reviews', async () => {
    const wrapper = mount(CompanionPanel, {
      props: { content: 'paper text' },
    })
    const reviewerTab = wrapper.findAll('button').find(b => b.text().includes('Reviewer'))
    if (reviewerTab) await reviewerTab.trigger('click')

    const btn = wrapper.find('[data-import-btn]')
    expect(btn.exists()).toBe(true)
  })

  it('import button triggers importReviews when clicked with text', async () => {
    // Set docId so importReviews doesn't short-circuit
    const companion = useArgumentCompanion()
    companion.setDoc('doc1', 'Test Paper')
    // Re-stub fetch after setDoc (which calls getLedger + listReviews)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({}),
      body: null,
    }))

    const wrapper = mount(CompanionPanel, {
      props: { content: 'paper text' },
    })
    const reviewerTab = wrapper.findAll('button').find(b => b.text().includes('Reviewer'))
    if (reviewerTab) await reviewerTab.trigger('click')

    const textarea = wrapper.find('[data-import-textarea]')
    if (!textarea.exists()) return

    await textarea.setValue('Reviewer 1: weak baselines')
    const btn = wrapper.find('[data-import-btn]')
    if (!btn.exists()) return
    await btn.trigger('click')

    // Give the async function a tick to start
    await new Promise(r => setTimeout(r, 0))

    // Should have called fetch with the import endpoint
    const mockFetch = vi.mocked(globalThis.fetch)
    const importCalls = mockFetch.mock.calls.filter((c: unknown[]) =>
      (c[0] as string).includes('/import'),
    )
    expect(importCalls.length).toBeGreaterThan(0)
  })
})
