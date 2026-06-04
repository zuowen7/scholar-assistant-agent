import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'zh-CN' },
  }),
}))

const mockRecentProjects = ref<any[]>([])

vi.mock('../composables/useProject', () => ({
  useProject: () => ({
    recentProjects: mockRecentProjects,
    currentProject: { value: null },
    projectLoading: { value: false },
    loadRecentProjects: vi.fn(),
  }),
}))

import { mount } from '@vue/test-utils'
import EditorWelcome from '../components/EditorWelcome.vue'

describe('EditorWelcome', () => {
  beforeEach(() => {
    mockRecentProjects.value = []
  })

  it('renders the welcome screen', () => {
    const wrapper = mount(EditorWelcome)
    expect(wrapper.find('.editor-welcome').exists()).toBe(true)
  })

  it('emits new-project when hero card is clicked', async () => {
    const wrapper = mount(EditorWelcome)
    await wrapper.find('[data-test="card-new-project"]').trigger('click')
    expect(wrapper.emitted('new-project')).toHaveLength(1)
  })

  it('emits open-folder when folder card is clicked', async () => {
    const wrapper = mount(EditorWelcome)
    await wrapper.find('[data-test="card-open-folder"]').trigger('click')
    expect(wrapper.emitted('open-folder')).toHaveLength(1)
  })

  it('hides recent projects when list is empty', () => {
    const wrapper = mount(EditorWelcome)
    expect(wrapper.find('[data-test="recent-projects"]').exists()).toBe(false)
  })

  it('shows recent projects when list has entries', () => {
    mockRecentProjects.value = [
      { path: '/tmp/A', name: 'Project A', template_id: 'research_paper', opened_at: '2026-01-01T00:00:00Z' },
    ]
    const wrapper = mount(EditorWelcome)
    expect(wrapper.find('[data-test="recent-projects"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="recent-item"]').length).toBe(1)
  })

  it('emits open-recent when a recent project is clicked', async () => {
    mockRecentProjects.value = [
      { path: '/tmp/A', name: 'Project A', template_id: 'research_paper', opened_at: '2026-01-01T00:00:00Z' },
    ]
    const wrapper = mount(EditorWelcome)
    await wrapper.find('[data-test="recent-item"]').trigger('click')
    expect(wrapper.emitted('open-recent')).toHaveLength(1)
    expect(wrapper.emitted('open-recent')![0]).toEqual(['/tmp/A'])
  })

  it('renders shortcut chips', () => {
    const wrapper = mount(EditorWelcome)
    expect(wrapper.findAll('.shortcut-chip').length).toBeGreaterThan(0)
  })
})
