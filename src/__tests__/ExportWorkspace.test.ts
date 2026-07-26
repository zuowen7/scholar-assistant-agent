import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { activeTabId, tabs } from '../composables/useEditorState'
import { useFileTree } from '../composables/useFileTree'
import { _resetExportWorkspaceForTesting } from '../composables/useExportWorkspace'

const exportToWord = vi.fn()
const exportLatex = vi.fn()
const exportPdf = vi.fn()
const saveBlob = vi.fn()
const loadExportTemplates = vi.fn()

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))
vi.mock('../composables/useEditorIO', () => ({
  useEditorIO: () => ({
    exportToWord,
    exportLatex,
    exportPdf,
    saveBlob,
    loadExportTemplates,
  }),
}))
vi.mock('../composables/useAgentChat', () => ({
  useAgentChat: () => ({ sendMessage: vi.fn() }),
}))
vi.mock('../composables/useToast', () => ({
  useToast: () => ({ success: vi.fn() }),
}))

import ExportWorkspace from '../components/ExportWorkspace.vue'

describe('ExportWorkspace', () => {
  beforeEach(() => {
    _resetExportWorkspaceForTesting()
    tabs.value = [
      {
        id: 'main',
        path: 'D:/papers/demo/draft/main.md',
        name: 'main.md',
        content: '# Paper\n\n## Abstract\n\nReady.',
        isModified: false,
        docId: 'main',
      },
    ]
    activeTabId.value = 'main'
    useFileTree().rootDir.value = 'D:/papers/demo'
    loadExportTemplates.mockResolvedValue({
      templates: [{ id: 'generic_article', name: 'Generic Article' }],
      tectonic_available: true,
    })
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ records: [] }), { status: 200 }),
    )
  })

  it('renders the active document, preflight checks, formats, and history surface', async () => {
    const wrapper = mount(ExportWorkspace)
    await flushPromises()

    expect(wrapper.find('.export-workspace').exists()).toBe(true)
    expect(wrapper.text()).toContain('main.md')
    expect(wrapper.text()).toContain('exports.preflightTitle')
    expect(wrapper.text()).toContain('Word')
    expect(wrapper.text()).toContain('PDF')
    expect(wrapper.text()).toContain('LaTeX')
    expect(loadExportTemplates).toHaveBeenCalled()
  })
})
