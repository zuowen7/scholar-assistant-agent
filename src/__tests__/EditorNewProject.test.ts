import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'zh-CN' },
  }),
}))

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn().mockResolvedValue('/tmp/selected-dir'),
}))

vi.mock('../composables/useProject', () => ({
  useProject: () => ({
    createProject: vi.fn().mockResolvedValue({
      project_path: '/tmp/TestProject',
      metadata: { version: 1, name: 'TestProject', status: 'ready', template_id: 'research_paper' },
      warnings: [],
    }),
    currentProject: { value: null },
    recentProjects: { value: [] },
    projectLoading: { value: false },
  }),
}))

// Mock fetch for template loading in onMounted
const mockFetch = vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve([
    { id: 'research_paper', name: 'Research Paper', folders: ['draft', 'revised', 'final', 'references', 'data', 'notes', 'scripts', 'ai'] },
    { id: 'review_paper', name: 'Literature Review', folders: ['draft', 'revised', 'final', 'references', 'notes', 'ai'] },
    { id: 'thesis', name: 'Thesis', folders: ['chapters', 'draft', 'revised', 'final', 'references', 'data', 'notes', 'scripts', 'ai', 'figures'] },
    { id: 'blank', name: 'Blank', folders: ['draft', 'references', 'notes'] },
  ]),
})
globalThis.fetch = mockFetch

import { mount } from '@vue/test-utils'
import EditorNewProject from '../components/EditorNewProject.vue'

describe('EditorNewProject', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the dialog when visible', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    expect(wrapper.find('.project-start-dialog').exists()).toBe(true)
  })

  it('hides the dialog when not visible', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: false } })
    expect(wrapper.find('.project-start-dialog').exists()).toBe(false)
  })

  it('emits close when backdrop is clicked', async () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    await wrapper.find('.project-start-backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('emits close when X button is clicked', async () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    await wrapper.find('.project-start-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('renders project name input', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    const input = wrapper.find('input[data-test="project-name"]')
    expect(input.exists()).toBe(true)
  })

  it('disables create button when name is empty', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    const btn = wrapper.find('button[data-test="create-btn"]')
    expect(btn.exists()).toBe(true)
    // Button should be disabled initially (no name entered)
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('renders template selector options', async () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    // Wait for onMounted async fetch to complete
    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()
    const templates = wrapper.findAll('[data-test="template-option"]')
    expect(templates.length).toBe(4)
  })

  it('renders location input and browse button', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    expect(wrapper.find('input[data-test="project-location"]').exists()).toBe(true)
    expect(wrapper.find('button[data-test="browse-btn"]').exists()).toBe(true)
  })

  it('renders git init checkbox', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    expect(wrapper.find('input[data-test="git-checkbox"]').exists()).toBe(true)
  })
})
