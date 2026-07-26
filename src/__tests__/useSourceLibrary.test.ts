import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useFileTree } from '../composables/useFileTree'
import { _resetSourceLibraryForTesting, useSourceLibrary } from '../composables/useSourceLibrary'
import {
  _handleSseEventForTesting,
  _resetForTesting as resetTranslation,
} from '../composables/useTranslate'

vi.mock('../utils/api', () => ({ API_BASE: 'http://127.0.0.1:18088' }))
vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn() }))

describe('useSourceLibrary', () => {
  beforeEach(() => {
    _resetSourceLibraryForTesting()
    resetTranslation()
    useFileTree().rootDir.value = 'D:/papers/project-a'
    vi.restoreAllMocks()
  })

  it('loads sources from the active project boundary', async () => {
    const source = {
      id: 'src_1',
      title: 'Paper',
      original_path: null,
      translated_path: null,
      translation_task_id: null,
      rag_status: 'unavailable',
      reading_status: 'unread',
      cited: false,
      metadata: {},
      created_at: '2026-07-26T00:00:00Z',
      updated_at: '2026-07-26T00:00:00Z',
    }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ sources: [source] }), { status: 200 }))

    const library = useSourceLibrary()
    await library.loadSources()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('project_path=D%3A%2Fpapers%2Fproject-a'),
    )
    expect(library.sources.value).toEqual([source])
  })

  it('attaches completed translation with its truthful RAG status', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
      if (String(url).endsWith('/rag-status')) {
        return new Response(JSON.stringify({ status: 'queued' }), { status: 200 })
      }
      const body = JSON.parse(String(init?.body))
      return new Response(
        JSON.stringify({
          id: 'src_1',
          ...body,
          original_path: body.original_path,
          translated_path: body.translated_path,
          translation_task_id: body.translation_task_id,
          created_at: '2026-07-26T00:00:00Z',
          updated_at: '2026-07-26T00:00:00Z',
        }),
        { status: 200 },
      )
    })
    _handleSseEventForTesting('translate.complete', {
      task_id: 'task-1',
      source_name: 'paper.pdf',
      source_path: 'D:/downloads/paper.pdf',
      output_path: 'D:/runtime/task-1.md',
      content: 'translated',
      rag_status: 'queued',
      blocks: [],
      chunks: [],
    })

    const saved = await useSourceLibrary().attachCurrentTranslation()

    expect(saved.title).toBe('paper.pdf')
    expect(saved.rag_status).toBe('queued')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:18088/api/project/sources',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
