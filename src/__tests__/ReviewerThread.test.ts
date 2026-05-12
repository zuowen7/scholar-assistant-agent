/**
 * Phase 3 TDD — ReviewerThread component
 *
 * Tests: severity/category rendering, source badge, focusAnchor emit,
 * updatePointStatus emit, disabled rebuttal placeholder.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewerThread from '../components/argument/ReviewerThread.vue'
import type { ReviewPoint } from '../types'

function makePoint(overrides: Partial<ReviewPoint> = {}): ReviewPoint {
  return {
    id: 'rp_001',
    severity: 'major',
    category: 'baseline',
    title: 'Missing baselines',
    detail: 'The baselines are not competitive with recent work.',
    anchor_id: null,
    status: 'open',
    source: 'llm',
    reviewer_label: null,
    thread: [],
    ...overrides,
  }
}

describe('ReviewerThread', () => {
  it('renders point title', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint() },
    })
    expect(wrapper.text()).toContain('Missing baselines')
  })

  it('renders point detail', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint() },
    })
    expect(wrapper.text()).toContain('not competitive')
  })

  it('shows severity badge for major', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ severity: 'major' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/major|严重/)
  })

  it('shows severity badge for minor', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ severity: 'minor' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/minor|轻微/)
  })

  it('shows severity badge for fatal', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ severity: 'fatal' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/fatal|致命/)
  })

  it('shows source badge for llm', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ source: 'llm' }) },
    })
    const html = wrapper.html()
    expect(html).toContain('llm')
  })

  it('shows source badge for ledger_check', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ source: 'ledger_check' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/ledger|账本/)
  })

  it('shows source badge for scoped', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ source: 'scoped' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/scoped|质疑/)
  })

  it('emits focusAnchor when anchor_id is present and anchor button clicked', async () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ anchor_id: 'anc_001' }) },
    })
    const anchorBtn = wrapper.find('[data-anchor-btn]')
    expect(anchorBtn.exists()).toBe(true)
    await anchorBtn.trigger('click')
    expect(wrapper.emitted('focusAnchor')).toBeTruthy()
    expect(wrapper.emitted('focusAnchor')![0]).toEqual(['anc_001'])
  })

  it('does not show anchor button when anchor_id is null', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ anchor_id: null }) },
    })
    expect(wrapper.find('[data-anchor-btn]').exists()).toBe(false)
  })

  it('emits updatePointStatus when status dropdown changes', async () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ status: 'open' }) },
    })
    const statusBtn = wrapper.find('[data-status-btn]')
    expect(statusBtn.exists()).toBe(true)
    await statusBtn.trigger('click')
    expect(wrapper.emitted('updatePointStatus')).toBeTruthy()
  })

  it('shows rebuttal placeholder for open points', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ status: 'open' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/rebut|rebuttal|反驳/i)
  })

  it('shows category label', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ category: 'baseline' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/baseline|基线/i)
  })

  it('shows rebutted status visually', () => {
    const wrapper = mount(ReviewerThread, {
      props: { point: makePoint({ status: 'rebutted' }) },
    })
    const html = wrapper.html()
    expect(html).toMatch(/rebutted|已反驳/i)
  })

  it('shows thread turns when present', () => {
    const point = makePoint({
      thread: [
        { id: 't1', role: 'author', text: 'We added more baselines.', created_at: Date.now() },
        { id: 't2', role: 'reviewer', text: 'Still insufficient.', created_at: Date.now() },
      ],
    })
    const wrapper = mount(ReviewerThread, { props: { point } })
    expect(wrapper.text()).toContain('We added more baselines.')
    expect(wrapper.text()).toContain('Still insufficient.')
  })
})
