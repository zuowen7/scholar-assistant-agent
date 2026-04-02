import { reactive, readonly } from 'vue'
import type {
  TranslateState,
  TranslateStatus,
  ProgressEvent,
  ParsedEvent,
  ChunkDoneEvent,
} from '../types'

const API_URL = 'http://localhost:18088'

function createState(): TranslateState {
  return {
    status: 'idle',
    currentStep: 0,
    totalSteps: 5,
    stepMessage: '',
    parsedInfo: null,
    totalChunks: 0,
    completedChunks: 0,
    translations: [],
    finalContent: '',
    chunks: [],
    errorMessage: null,
    taskId: null,
  }
}

const state = reactive<TranslateState>(createState())

function reset(): void {
  Object.assign(state, createState())
}

function setStatus(s: TranslateStatus): void {
  state.status = s
}

function overallProgress(): number {
  if (state.status === 'done') return 100
  if (state.status === 'idle' || state.status === 'error') return 0
  if (state.status === 'uploading') return 2

  // Step 1-5 each contribute ~18%, plus 10% for upload
  const stepBase = [0, 10, 28, 46, 64, 82]
  let pct = stepBase[state.currentStep] ?? 0

  // Within step 4 (translating), subdivide by chunks
  if (state.currentStep === 4 && state.totalChunks > 0) {
    const chunkPct = (state.completedChunks / state.totalChunks) * 16
    pct += chunkPct
  } else if (state.currentStep > 0) {
    pct += 14 // each non-translate step is ~14%
  }

  return Math.min(Math.round(pct), 98)
}

async function checkHealth(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_URL}/api/health`, { signal: AbortSignal.timeout(3000) })
    return resp.ok
  } catch {
    return false
  }
}

async function checkOllama(): Promise<boolean> {
  try {
    const resp = await fetch(`${API_URL}/api/ollama/status`, { signal: AbortSignal.timeout(3000) })
    if (!resp.ok) return false
    const data = await resp.json()
    return data.reachable === true
  } catch {
    return false
  }
}

async function startOllama(): Promise<string | null> {
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const result = await invoke<string>('start_ollama')
    // Wait for Ollama to become reachable
    for (let i = 0; i < 10; i++) {
      await new Promise(r => setTimeout(r, 1000))
      if (await checkOllama()) return null
    }
    return 'Ollama 启动超时，请手动运行 ollama serve'
  } catch (err) {
    return err instanceof Error ? err.message : String(err)
  }
}

async function uploadPdf(file: File): Promise<string> {
  const formData = new FormData()
  formData.append('file', file)

  const resp = await fetch(`${API_URL}/api/translate`, {
    method: 'POST',
    body: formData,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || `上传失败 (${resp.status})`)
  }

  const data = await resp.json()
  state.taskId = data.task_id
  return data.task_id
}

async function startStream(taskId: string): Promise<void> {
  const resp = await fetch(`${API_URL}/api/translate/${taskId}/stream`)

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '流式连接失败' }))
    throw new Error(err.detail || `连接失败 (${resp.status})`)
  }

  const reader = resp.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')

  const decoder = new TextDecoder()
  let buffer = ''
  let currentEvent = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          if (!raw) continue
          try {
            const data = JSON.parse(raw)
            handleSseEvent(currentEvent, data)
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  } catch (err) {
    // Stream ended or was interrupted — if already done, ignore
    if (state.status !== 'done') {
      throw err
    }
  }
}

function handleSseEvent(event: string, data: Record<string, unknown>): void {
  switch (event) {
    case 'progress': {
      const p = data as unknown as ProgressEvent
      state.currentStep = p.step
      state.totalSteps = p.total
      state.stepMessage = p.message
      setStatus(stepToStatus(p.step))
      break
    }
    case 'parsed':
      state.parsedInfo = data as unknown as ParsedEvent
      break
    case 'cleaned':
      state.stepMessage = `清洗完成，${data.chars?.toLocaleString() ?? 0} 字符`
      break
    case 'chunked':
      state.totalChunks = (data.total_chunks as number) ?? 0
      state.stepMessage = `共 ${data.total_chunks} 个块`
      break
    case 'chunk_done': {
      const chunk = data as unknown as ChunkDoneEvent
      state.completedChunks = chunk.index + 1
      state.translations.push(chunk)
      state.stepMessage = `翻译块 ${chunk.index + 1}/${chunk.total}`
      break
    }
    case 'complete':
      state.finalContent = (data.content as string) ?? ''
      state.chunks = (data.chunks as { original: string; translated: string }[]) ?? []
      setStatus('done')
      state.stepMessage = '翻译完成'
      break
    case 'error':
      if (state.status !== 'done') {
        state.errorMessage = (data.message as string) ?? '未知错误'
        setStatus('error')
      }
      break
  }
}

function stepToStatus(step: number): TranslateStatus {
  const map: Record<number, TranslateStatus> = {
    1: 'parsing',
    2: 'cleaning',
    3: 'chunking',
    4: 'translating',
    5: 'formatting',
  }
  return map[step] || 'idle'
}

async function translate(file: File): Promise<void> {
  reset()
  setStatus('uploading')
  state.stepMessage = '上传 PDF...'

  try {
    const healthOk = await checkHealth()
    if (!healthOk) {
      throw new Error('无法连接翻译服务，请确认后端已启动')
    }

    const taskId = await uploadPdf(file)
    await startStream(taskId)
  } catch (err: unknown) {
    if (state.status !== 'done') {
      const msg = err instanceof Error ? err.message : '未知错误'
      state.errorMessage = msg
      setStatus('error')
    }
  }
}

async function downloadResult(): Promise<void> {
  if (!state.taskId) return
  const url = `${API_URL}/api/download/${state.taskId}`
  window.open(url, '_blank')
}

export function useTranslate() {
  return {
    state: readonly(state),
    translate,
    reset,
    checkHealth,
    checkOllama,
    startOllama,
    downloadResult,
    overallProgress,
  }
}
