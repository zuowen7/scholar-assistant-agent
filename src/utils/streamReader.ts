export async function readSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (eventType: string, data: Record<string, unknown>) => void,
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

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

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
  } catch (err) {
    reader.cancel().catch(() => {})
    throw err
  }
}
