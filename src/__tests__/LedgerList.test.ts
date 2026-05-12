/**
 * Phase 2 TDD — LedgerList component unit tests.
 *
 * Tests cover:
 * - Renders promises grouped by status (unpaid first, then mismatch, partial, paid, unknown)
 * - Shows status badge for each promise
 * - Clicking promise text triggers focusAnchor
 * - Shows "分析论证账本" button; clicking triggers buildOrRebuildLedger
 * - Empty state message when no ledger
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
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

import { _resetForTesting } from '../composables/useArgumentCompanion'
import LedgerList from '../components/argument/LedgerList.vue'

// ── helpers ─────────────────────────────────────────────────────────────────

function makePromise(id: string, status: string) {
  return {
    id,
    text: `Promise ${id} text`,
    kind: 'contribution',
    source_anchor_id: `a_${id}`,
    discharge_anchor_ids: [],
    status,
    severity: status === 'unpaid' || status === 'mismatch' ? 'error'
      : status === 'partial' ? 'warning' : 'info',
    note: status === 'mismatch' ? 'Numbers do not match' : null,
    created_by: 'ai',
    user_overridden: false,
  }
}

function makeLedger(promises: ReturnType<typeof makePromise>[]) {
  return {
    id: 'L_test',
    doc_id: 'doc1',
    doc_title: 'Test Paper',
    promises,
    anchors: promises.map(p => ({
      id: `a_${p.id}`,
      doc_id: 'doc1',
      char_start: 10,
      char_end: 30,
      quote: 'some text',
      context_before: '',
      context_after: '',
      section_path: null,
      status: 'anchored',
    })),
    doc_hash: null,
    last_built_at: Date.now() / 1000,
  }
}

// ── tests ───────────────────────────────────────────────────────────────────

describe('LedgerList', () => {
  beforeEach(() => {
    _resetForTesting()
  })

  it('shows empty state message when ledger is null', async () => {
    // LedgerList imported statically above
    const wrapper = mount(LedgerList, {
      props: { ledger: null, building: false },
    })

    expect(wrapper.text()).toContain('还没分析')
  })

  it('renders promises grouped by status in correct order', async () => {
    // LedgerList imported statically above
    const promises = [
      makePromise('p1', 'paid'),
      makePromise('p2', 'unpaid'),
      makePromise('p3', 'mismatch'),
      makePromise('p4', 'partial'),
    ]
    const ledger = makeLedger(promises)

    const wrapper = mount(LedgerList, {
      props: { ledger, building: false },
    })

    const text = wrapper.text()
    // All promises should appear
    expect(text).toContain('Promise p1 text')
    expect(text).toContain('Promise p2 text')
    expect(text).toContain('Promise p3 text')
    expect(text).toContain('Promise p4 text')

    // Status groups should appear in order: unpaid, mismatch, partial, paid
    // Use badge CSS class names which do appear as DOM attributes
    const html = wrapper.html()
    const unpaidPos = html.indexOf('badge-unpaid')
    const mismatchPos = html.indexOf('badge-mismatch')
    const partialPos = html.indexOf('badge-partial')
    const paidPos = html.indexOf('badge-paid')

    expect(unpaidPos).toBeGreaterThan(-1)
    expect(mismatchPos).toBeGreaterThan(-1)
    expect(partialPos).toBeGreaterThan(-1)
    expect(paidPos).toBeGreaterThan(-1)
    expect(unpaidPos).toBeLessThan(mismatchPos)
    expect(mismatchPos).toBeLessThan(partialPos)
    expect(partialPos).toBeLessThan(paidPos)
  })

  it('emits focusAnchor event when promise text is clicked', async () => {
    // LedgerList imported statically above
    const promises = [makePromise('p1', 'unpaid')]
    const ledger = makeLedger(promises)

    const wrapper = mount(LedgerList, {
      props: { ledger, building: false },
    })

    // Find and click the promise text button
    const promiseBtn = wrapper.find('[data-promise-focus]')
    await promiseBtn.trigger('click')

    expect(wrapper.emitted('focusAnchor')).toBeTruthy()
    expect(wrapper.emitted('focusAnchor')![0]).toEqual(['a_p1'])
  })

  it('emits analyze event when "分析论证账本" button is clicked', async () => {
    // LedgerList imported statically above

    const wrapper = mount(LedgerList, {
      props: { ledger: null, building: false },
    })

    const analyzeBtn = wrapper.find('[data-analyze-btn]')
    await analyzeBtn.trigger('click')

    expect(wrapper.emitted('analyze')).toBeTruthy()
  })

  it('disables analyze button when building=true', async () => {
    // LedgerList imported statically above

    const wrapper = mount(LedgerList, {
      props: { ledger: null, building: true },
    })

    const analyzeBtn = wrapper.find('[data-analyze-btn]')
    expect(analyzeBtn.attributes('disabled')).toBeDefined()
  })

  it('shows note text for mismatch promise', async () => {
    // LedgerList imported statically above
    const promises = [makePromise('p1', 'mismatch')]
    const ledger = makeLedger(promises)

    const wrapper = mount(LedgerList, {
      props: { ledger, building: false },
    })

    expect(wrapper.text()).toContain('Numbers do not match')
  })
})
