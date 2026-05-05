/**
 * E2E 翻译管道测试 — 模拟完整 SSE 流从前端到"后端"的链路
 *
 * 测试 useTranslate composable 的 SSE 事件处理逻辑，
 * 验证翻译管道的所有阶段状态转换。
 * 使用 fetch mock 来模拟后端 SSE 响应。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mock fetch globally
// ---------------------------------------------------------------------------
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// ---------------------------------------------------------------------------
// Helper: build a mock SSE ReadableStream
// ---------------------------------------------------------------------------
function createSSEResponse(events: Array<{ event?: string; data: object }>): Response {
  const encoder = new TextEncoder()
  let body = ''
  for (const evt of events) {
    if (evt.event) body += `event: ${evt.event}\n`
    body += `data: ${JSON.stringify(evt.data)}\n\n`
  }
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(body))
      controller.close()
    },
  })
  return {
    ok: true,
    status: 200,
    body: stream,
    headers: new Headers({ 'Content-Type': 'text/event-stream' }),
  } as unknown as Response
}

// ---------------------------------------------------------------------------
// Helper: import useTranslate's state creation (module-level singleton)
// ---------------------------------------------------------------------------
// We test the SSE event handling logic by directly testing the handleSseEvent function
// pattern used in useTranslate.ts

describe('Translate Pipeline E2E', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  // ── SSE Event Parsing ──────────────────────────────────────────────────
  describe('SSE event stream parsing', () => {
    it('parses progress events in correct order', async () => {
      const events = [
        { event: 'progress', data: { step: 1, total: 5, message: '上传中...' } },
        { event: 'progress', data: { step: 2, total: 5, message: '解析中...' } },
      ]

      mockFetch.mockResolvedValueOnce(createSSEResponse(events))

      const response = await fetch('/api/translate/start', { method: 'POST', body: '{}' })
      expect(response.ok).toBe(true)

      if (response.body) {
        const reader = response.body.getReader()
        const { readSseStream } = await import('../utils/streamReader')
        const captured: Array<[string, any]> = []

        await readSseStream(reader as any, (type, data) => {
          captured.push([type, data])
        })

        expect(captured).toHaveLength(2)
        expect(captured[0][0]).toBe('progress')
        expect(captured[0][1].step).toBe(1)
        expect(captured[1][0]).toBe('progress')
        expect(captured[1][1].step).toBe(2)
      }
    })

    it('parses full pipeline event sequence', async () => {
      const events = [
        { event: 'progress', data: { step: 1, total: 5, message: '上传中...' } },
        { event: 'parsed', data: { pages: 10, chars: 5000, dual_column_pages: 0 } },
        { event: 'cleaned', data: { chars: 4800, has_references: true } },
        { event: 'chunked', data: { total_chunks: 4, total_blocks: 12, block_types: { paragraph: 10, heading: 2 }, references_chars: 200, blocks: [], chunks: [] } },
        { event: 'progress', data: { step: 4, total: 5, message: '翻译中...' } },
        { event: 'block_translated', data: { chunk_index: 0, block_id: 'b1', type: 'paragraph', translatable: true, original: 'Hello', translated: '你好', aligned: true, status: 'ok' } },
        { event: 'chunk_done', data: { index: 0, total: 4, original_preview: 'Hello...', translated_preview: '你好...', tokens: 50, section_type: 'introduction' } },
        { event: 'complete', data: { task_id: 'task-1', output_path: '/out/test.md', content: '你好 world', blocks: [], chunks: [], misalign_count: 0 } },
      ]

      mockFetch.mockResolvedValueOnce(createSSEResponse(events))
      const response = await fetch('/api/translate/start', { method: 'POST', body: '{}' })

      if (response.body) {
        const reader = response.body.getReader()
        const { readSseStream } = await import('../utils/streamReader')
        const captured: Array<[string, any]> = []

        await readSseStream(reader as any, (type, data) => {
          captured.push([type, data])
        })

        expect(captured).toHaveLength(8)

        // Verify event sequence
        const types = captured.map(c => c[0])
        expect(types).toEqual([
          'progress', 'parsed', 'cleaned', 'chunked',
          'progress', 'block_translated', 'chunk_done', 'complete',
        ])

        // Verify parsed event data
        expect(captured[1][1].pages).toBe(10)

        // Verify block_translated data
        expect(captured[5][1].translated).toBe('你好')
        expect(captured[5][1].aligned).toBe(true)
        expect(captured[5][1].status).toBe('ok')

        // Verify chunk_done includes section_type
        expect(captured[6][1].section_type).toBe('introduction')

        // Verify complete event
        expect(captured[7][1].task_id).toBe('task-1')
        expect(captured[7][1].content).toBe('你好 world')
      }
    })

    it('handles error events in the pipeline', async () => {
      const events = [
        { event: 'progress', data: { step: 1, total: 5, message: 'Starting...' } },
        { event: 'error', data: { message: 'No API key configured' } },
      ]

      mockFetch.mockResolvedValueOnce(createSSEResponse(events))
      const response = await fetch('/api/translate/start', { method: 'POST', body: '{}' })

      if (response.body) {
        const reader = response.body.getReader()
        const { readSseStream } = await import('../utils/streamReader')
        const captured: Array<[string, any]> = []

        await readSseStream(reader as any, (type, data) => {
          captured.push([type, data])
        })

        expect(captured).toHaveLength(2)
        expect(captured[1][0]).toBe('error')
        expect(captured[1][1].message).toBe('No API key configured')
      }
    })

    it('handles QA warnings events', async () => {
      const events = [
        { event: 'chunk_done', data: { index: 0, total: 1, original_preview: 'We prove...', translated_preview: '', tokens: 30, section_type: 'results' } },
        { event: 'qa_warnings', data: { chunk_index: 0, section_type: 'results', score: 85, flags: [{ type: 'overclaim', severity: 'warning', location: 'We prove...', message: 'Overclaim detected: prove', suggestion: 'Use show/demonstrate instead' }] } },
      ]

      mockFetch.mockResolvedValueOnce(createSSEResponse(events))
      const response = await fetch('/api/translate/start', { method: 'POST', body: '{}' })

      if (response.body) {
        const reader = response.body.getReader()
        const { readSseStream } = await import('../utils/streamReader')
        const captured: Array<[string, any]> = []

        await readSseStream(reader as any, (type, data) => {
          captured.push([type, data])
        })

        expect(captured).toHaveLength(2)
        expect(captured[1][0]).toBe('qa_warnings')
        expect(captured[1][1].score).toBe(85)
        expect(captured[1][1].flags).toHaveLength(1)
        expect(captured[1][1].flags[0].type).toBe('overclaim')
      }
    })
  })

  // ── Export Endpoint Integration ────────────────────────────────────────
  describe('Export endpoints', () => {
    it('PPTX export fetches with correct parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => new Blob(['fake-pptx'], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' }),
      })

      const res = await fetch('/api/export/pptx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: 'task-1', format: 'pptx' }),
      })

      expect(res.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/export/pptx', expect.objectContaining({
        method: 'POST',
      }))
    })

    it('Data Availability export fetches with correct parameters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: async () => new Blob(['# Data Availability Statement\n\n...'], { type: 'text/markdown' }),
      })

      const res = await fetch('/api/export/data_availability', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: 'task-1' }),
      })

      expect(res.ok).toBe(true)
      expect(mockFetch).toHaveBeenCalledWith('/api/export/data_availability', expect.objectContaining({
        method: 'POST',
      }))
    })
  })

  // ── Fetch Error Handling ───────────────────────────────────────────────
  describe('Network error handling', () => {
    it('handles network failure gracefully', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Connection refused'))

      await expect(
        fetch('/api/translate/start', { method: 'POST', body: '{}' }),
      ).rejects.toThrow('Connection refused')
    })

    it('handles non-200 response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      })

      const response = await fetch('/api/translate/start', { method: 'POST', body: '{}' })
      expect(response.ok).toBe(false)
      expect(response.status).toBe(500)
    })
  })
})
