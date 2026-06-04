import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'zh-CN' },
  }),
}))

const mockRecentProjects = ref<any[]>([])
const mockLoadRecentProjects = vi.fn()

vi.mock('../composables/useProject', () => ({
  useProject: () => ({
    recentProjects: mockRecentProjects,
    currentProject: { value: null },
    projectLoading: { value: false },
    loadRecentProjects: mockLoadRecentProjects,
  }),
}))

vi.mock('../utils/api', () => ({
  API_BASE: '',
}))

import { mount } from '@vue/test-utils'
import EditorWelcome from '../components/EditorWelcome.vue'

describe('EditorWelcome', () => {
  beforeEach(() => {
    mockRecentProjects.value = []
    mockLoadRecentProjects.mockReset()
  })

  it('renders the welcome screen', () => {
    const wrapper = mount(EditorWelcome)
    expect(wrapper.find('.editor-welcome').exists()).toBe(true)
  })

  it('calls loadRecentProjects on mount', () => {
    mount(EditorWelcome)
    expect(mockLoadRecentProjects).toHaveBeenCalledTimes(1)
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

  it('displays max 5 recent projects', () => {
    mockRecentProjects.value = Array.from({ length: 8 }, (_, i) => ({
      path: `/tmp/Project${i}`, name: `Project ${i}`, template_id: 'research_paper', opened_at: '2026-01-01T00:00:00Z',
    }))
    const wrapper = mount(EditorWelcome)
    expect(wrapper.findAll('[data-test="recent-item"]').length).toBe(5)
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

  it('formats path to last 2 segments', () => {
    mockRecentProjects.value = [
      { path: '/home/user/papers/MyPaper', name: 'MyPaper', template_id: 'research_paper', opened_at: '2026-01-01T00:00:00Z' },
    ]
    const wrapper = mount(EditorWelcome)
    const pathEl = wrapper.find('.recent-path')
    expect(pathEl.text()).toBe('papers/MyPaper')
  })

  it('renders shortcut chips', () => {
    const wrapper = mount(EditorWelcome)
    expect(wrapper.findAll('.shortcut-chip').length).toBeGreaterThan(0)
  })
})
