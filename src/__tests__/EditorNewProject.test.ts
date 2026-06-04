import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockCreateProject = vi.fn().mockResolvedValue({
  project_path: '/tmp/TestProject',
  metadata: { version: 1, name: 'TestProject', status: 'ready', template_id: 'research_paper' },
  warnings: [],
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'zh-CN' },
  }),
}))

vi.mock('../utils/api', () => ({
  API_BASE: '',
}))

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn().mockResolvedValue('/tmp/selected-dir'),
}))

vi.mock('../composables/useProject', () => ({
  useProject: () => ({
    createProject: mockCreateProject,
    currentProject: { value: null },
    recentProjects: { value: [] },
    projectLoading: { value: false },
  }),
}))

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

async function mountWithTemplates() {
  const wrapper = mount(EditorNewProject, { props: { visible: true } })
  await vi.dynamicImportSettled()
  await wrapper.vm.$nextTick()
  return wrapper
}

describe('EditorNewProject', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateProject.mockResolvedValue({
      project_path: '/tmp/TestProject',
      metadata: { version: 1, name: 'TestProject', status: 'ready', template_id: 'research_paper' },
      warnings: [],
    })
  })

  // ── Rendering ─────────────────────────────────────────────────────

  it('renders the dialog when visible', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: true } })
    expect(wrapper.find('.project-start-dialog').exists()).toBe(true)
  })

  it('hides the dialog when not visible', () => {
    const wrapper = mount(EditorNewProject, { props: { visible: false } })
    expect(wrapper.find('.project-start-dialog').exists()).toBe(false)
  })

  it('emits close when backdrop is clicked', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('.project-start-backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('emits close when X button is clicked', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('.project-start-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('renders project name input', async () => {
    const wrapper = await mountWithTemplates()
    expect(wrapper.find('input[data-test="project-name"]').exists()).toBe(true)
  })

  it('renders 4 template options', async () => {
    const wrapper = await mountWithTemplates()
    expect(wrapper.findAll('[data-test="template-option"]').length).toBe(4)
  })

  it('renders location input and browse button', async () => {
    const wrapper = await mountWithTemplates()
    expect(wrapper.find('input[data-test="project-location"]').exists()).toBe(true)
    expect(wrapper.find('button[data-test="browse-btn"]').exists()).toBe(true)
  })

  it('renders git init checkbox', async () => {
    const wrapper = await mountWithTemplates()
    expect(wrapper.find('input[data-test="git-checkbox"]').exists()).toBe(true)
  })

  // ── Button state ──────────────────────────────────────────────────

  it('disables create button when name is empty', async () => {
    const wrapper = await mountWithTemplates()
    const btn = wrapper.find('button[data-test="create-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('disables create button when location is empty', async () => {
    const wrapper = await mountWithTemplates()
    const nameInput = wrapper.find('input[data-test="project-name"]')
    await nameInput.setValue('MyProject')
    // location is still empty
    const btn = wrapper.find('button[data-test="create-btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it('enables create button when name and location are filled', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('input[data-test="project-name"]').setValue('MyProject')
    await wrapper.find('input[data-test="project-location"]').setValue('/tmp/projects')
    const btn = wrapper.find('button[data-test="create-btn"]')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  // ── Template selection ────────────────────────────────────────────

  it('highlights selected template', async () => {
    const wrapper = await mountWithTemplates()
    const templates = wrapper.findAll('[data-test="template-option"]')
    // Click second template
    await templates[1].trigger('click')
    expect(templates[1].classes()).toContain('active')
    // First should no longer be active
    expect(templates[0].classes()).not.toContain('active')
  })

  // ── Browse button ─────────────────────────────────────────────────

  it('sets location when browse returns a path', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('button[data-test="browse-btn"]').trigger('click')
    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()
    const locInput = wrapper.find('input[data-test="project-location"]')
    expect((locInput.element as HTMLInputElement).value).toBe('/tmp/selected-dir')
  })

  // ── Create flow ───────────────────────────────────────────────────

  it('calls createProject and emits project-created on success', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('input[data-test="project-name"]').setValue('MyProject')
    await wrapper.find('input[data-test="project-location"]').setValue('/tmp/projects')
    await wrapper.find('button[data-test="create-btn"]').trigger('click')
    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()

    expect(mockCreateProject).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'MyProject',
        location: '/tmp/projects',
      }),
    )
    expect(wrapper.emitted('project-created')).toHaveLength(1)
    expect(wrapper.emitted('project-created')![0]).toEqual(['/tmp/TestProject'])
  })

  it('shows error message when createProject rejects', async () => {
    mockCreateProject.mockRejectedValueOnce(new Error('Server error'))
    const wrapper = await mountWithTemplates()
    await wrapper.find('input[data-test="project-name"]').setValue('MyProject')
    await wrapper.find('input[data-test="project-location"]').setValue('/tmp/projects')
    await wrapper.find('button[data-test="create-btn"]').trigger('click')
    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.error-msg').exists()).toBe(true)
    expect(wrapper.find('.error-msg').text()).toContain('Server error')
    // Should NOT emit project-created
    expect(wrapper.emitted('project-created')).toBeUndefined()
  })

  // ── Form reset ────────────────────────────────────────────────────

  it('resets form after successful creation', async () => {
    const wrapper = await mountWithTemplates()
    await wrapper.find('input[data-test="project-name"]').setValue('MyProject')
    await wrapper.find('input[data-test="project-location"]').setValue('/tmp/projects')
    await wrapper.find('button[data-test="create-btn"]').trigger('click')
    await vi.dynamicImportSettled()
    await wrapper.vm.$nextTick()

    // Form should be reset
    expect((wrapper.find('input[data-test="project-name"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('input[data-test="project-location"]').element as HTMLInputElement).value).toBe('')
  })
})
