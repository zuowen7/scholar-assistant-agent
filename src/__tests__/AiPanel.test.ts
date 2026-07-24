import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const { readSseStream } = vi.hoisted(() => ({
  readSseStream: vi.fn(
    async (_reader: unknown, handler: (type: string, data: Record<string, unknown>) => void) => {
      handler('delta', { content: 'edited text' })
    },
  ),
}))

vi.mock('../utils/streamReader', () => ({ readSseStream }))
vi.mock('../composables/useSpeechRecognition', () => ({
  useSpeechRecognition: () => ({
    isSupported: false,
    status: { value: 'idle' },
    start: vi.fn(),
    stop: vi.fn(() => ''),
  }),
}))
vi.mock('../composables/useSpeechBusy', () => ({ setSpeechBusy: vi.fn() }))
vi.mock('vue-i18n', () => ({
  createI18n: () => ({
    global: { locale: { value: 'zh-CN' }, t: (key: string) => key },
    install: vi.fn(),
  }),
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (params?.file) return `${key}: ${params.file}`
      return key
    },
  }),
}))

import AiPanel from '../components/AiPanel.vue'

describe('AiPanel workflow routing', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    fetchMock.mockResolvedValue({
      ok: true,
      body: { getReader: () => ({}) },
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => `id-${Math.random()}`) })
    readSseStream.mockClear()
  })

  it('routes preset edits through the one-shot /api/edit SSE endpoint', async () => {
    const wrapper = mount(AiPanel, {
      props: {
        editorContext: 'Original paragraph',
        activeFile: 'paper.tex',
        workspaceFiles: [],
      },
    })

    await (wrapper.vm as unknown as { sendPreset: (name: string) => Promise<void> }).sendPreset(
      'polish',
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/api\/edit$/)
    const payload = JSON.parse(init.body)
    expect(payload).toMatchObject({ text: 'Original paragraph', task_type: 'polish' })
    expect(payload.instruction).toContain('aiPanel.prompts.polish')
  })

  it('keeps free-form tasks on Agent V2', async () => {
    const wrapper = mount(AiPanel, {
      props: { editorContext: 'Editor context', workspaceFiles: [] },
    })

    await wrapper.find('textarea').setValue('Inspect the whole project')
    await wrapper.find('.ac-send-btn').trigger('click')
    await flushPromises()

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/agent\/v2\/chat$/)
  })
})
