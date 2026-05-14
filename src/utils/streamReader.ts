export async function readSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (eventType: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''
  let dataBuffer = ''

  function flush(): void {
    if (!dataBuffer) return
    try {
      onEvent(currentEvent || 'data', JSON.parse(dataBuffer))
    } catch {
      // skip malformed JSON
    }
    currentEvent = ''
    dataBuffer = ''
  }

  const onAbort = () => { reader.cancel().catch(() => {}) }
  if (signal) {
    if (signal.aborted) { reader.cancel().catch(() => {}); return }
    signal.addEventListener('abort', onAbort, { once: true })
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (signal?.aborted) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith(':')) continue
        if (line.startsWith('event:')) {
          flush()
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          if (raw) dataBuffer += (dataBuffer ? '\n' : '') + raw
        } else if (line === '') {
          flush()
        }
      }
    }
    flush()
  } finally {
    if (signal) signal.removeEventListener('abort', onAbort)
    reader.cancel().catch(() => {})
  }
}
