import { describe, it, expect, vi } from 'vitest'
import { readSseStream } from '../utils/streamReader'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeReader(chunks: string[]): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder()
  let idx = 0
  const reader = {
    async read(): Promise<{ done: boolean; value: Uint8Array | undefined }> {
      if (idx >= chunks.length) return { done: true, value: undefined }
      return { done: false, value: encoder.encode(chunks[idx++]) }
    },
    cancel: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
  return reader
}

function makeAbortingReader(chunks: string[], abortAfter: number): ReadableStreamDefaultReader<Uint8Array> {
  const encoder = new TextEncoder()
  let idx = 0
  const reader = {
    async read(): Promise<{ done: boolean; value: Uint8Array | undefined }> {
      if (idx >= chunks.length) return { done: true, value: undefined }
      if (idx >= abortAfter) throw new DOMException('AbortError', 'AbortError')
      return { done: false, value: encoder.encode(chunks[idx++]) }
    },
    cancel: vi.fn().mockResolvedValue(undefined),
  } as unknown as ReadableStreamDefaultReader<Uint8Array>
  return reader
}

// ---------------------------------------------------------------------------
// Basic event parsing
// ---------------------------------------------------------------------------

describe('readSseStream – event parsing', () => {

  it('parses a single event+data pair', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      'event: progress\ndata: {"step":1}\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events).toHaveLength(1)
    expect(events[0][0]).toBe('progress')
    expect(events[0][1]).toEqual({ step: 1 })
  })

  it('parses multiple events in one chunk', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      'event: a\ndata: {"x":1}\n\nevent: b\ndata: {"x":2}\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events).toHaveLength(2)
    expect(events[0][0]).toBe('a')
    expect(events[1][0]).toBe('b')
  })

  it('handles events split across multiple chunks', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      'event: progress\n',
      'data: {"step":2}\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events).toHaveLength(1)
    expect(events[0][1]).toEqual({ step: 2 })
  })

  it('defaults event type to "data" when no event line', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      'data: {"msg":"hello"}\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events[0][0]).toBe('data')
  })

  it('skips comment lines starting with colon', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      ': keepalive\nevent: done\ndata: {"ok":true}\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events).toHaveLength(1)
    expect(events[0][0]).toBe('done')
  })

  it('silently drops malformed JSON in data field', async () => {
    const events: Array<[string, Record<string, unknown>]> = []
    const reader = makeReader([
      'event: test\ndata: NOT_JSON\n\n',
    ])
    await readSseStream(reader, (type, data) => events.push([type, data]))

    expect(events).toHaveLength(0)
  })

})

// ---------------------------------------------------------------------------
// Resource cleanup
// ---------------------------------------------------------------------------

describe('readSseStream – cleanup', () => {

  it('calls reader.cancel() after normal completion', async () => {
    const reader = makeReader(['event: done\ndata: {}\n\n'])
    await readSseStream(reader, () => {})

    expect(reader.cancel).toHaveBeenCalledOnce()
  })

  it('calls reader.cancel() even when read() throws (abort scenario)', async () => {
    const reader = makeAbortingReader(
      ['event: a\ndata: {}\n\n', 'event: b\ndata: {}\n\n'],
      1,
    )
    try {
      await readSseStream(reader, () => {})
    } catch {
      // AbortError is expected — we just want to verify cancel() was still called
    }
    expect(reader.cancel).toHaveBeenCalledOnce()
  })

})
