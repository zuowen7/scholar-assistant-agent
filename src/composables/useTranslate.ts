import { reactive, readonly } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { save } from '@tauri-apps/plugin-dialog'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import type {
  TranslateState,
  TranslateStatus,
  ProgressEvent,
  ParsedEvent,
  ChunkDoneEvent,
  AppConfig,
  CloudConfig,
  ProviderPreset,
} from '../types'

// Tauri 桌面端: 后端固定在 18088; Docker/Web: 同源，使用相对路径
const isTauri = '__TAURI_INTERNALS__' in window
const API_URL = API_BASE

// SSE 自动重连参数
const SSE_RECONNECT_MAX_ATTEMPTS = 3
const SSE_RECONNECT_DELAY_MS = 2000

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
    fallbackChunks: 0,
  }
}

const state = reactive<TranslateState>(createState())
let abortController: AbortController | null = null
let crashListener: UnlistenFn | null = null

function reset(): void {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  Object.assign(state, createState())
}

function cleanup(): void {
  reset()
  if (crashListener) {
    crashListener()
    crashListener = null
  }
}

function setStatus(s: TranslateStatus): void {
  state.status = s
}

function setError(msg: string): void {
  state.errorMessage = msg
  state.status = 'error'
}

function setStepMessage(msg: string): void {
  state.stepMessage = msg
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
    return await invoke<boolean>('check_backend_health')
  } catch {
    // 非 Tauri 环境回退到 fetch
    try {
      const resp = await fetch(`${API_URL}/api/health`, { signal: AbortSignal.timeout(3000) })
      return resp.ok
    } catch {
      return false
    }
  }
}

async function checkOllama(): Promise<boolean> {
  try {
    return await invoke<boolean>('check_ollama_health')
  } catch {
    // 非 Tauri 环境回退到 fetch
    try {
      const resp = await fetch(`${API_URL}/api/ollama/status`, { signal: AbortSignal.timeout(3000) })
      if (!resp.ok) return false
      const data = await resp.json()
      return data.reachable === true
    } catch {
      return false
    }
  }
}

async function startOllama(): Promise<string | null> {
  try {
    await invoke<string>('start_ollama')
    for (let i = 0; i < 30; i++) {
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

async function startStream(taskId: string, attempt: number = 0): Promise<void> {
  abortController?.abort()
  abortController = new AbortController()
  const resp = await fetch(`${API_URL}/api/translate/${taskId}/stream`, {
    signal: abortController.signal,
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '流式连接失败' }))
    throw new Error(err.detail || `连接失败 (${resp.status})`)
  }

  const reader = resp.body?.getReader()
  if (!reader) throw new Error('Unable to read response stream')

  try {
    await readSseStream(reader, handleSseEvent)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return
    }

    if (state.status !== 'done' && state.status !== 'idle' && attempt < SSE_RECONNECT_MAX_ATTEMPTS) {
      state.stepMessage = `连接中断，正在重试 (${attempt + 1}/${SSE_RECONNECT_MAX_ATTEMPTS})...`
      await new Promise(r => setTimeout(r, SSE_RECONNECT_DELAY_MS))
      // Re-check: user may have called reset() during the wait
      if (abortController === null) return

      const stillAlive = await checkHealth()
      if (stillAlive) {
        try {
          await startStream(taskId, attempt + 1)
          return
        } catch {
          // ignore reconnect failure
        }
      }
    }

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
      state.stepMessage = `Cleaning complete, ${data.chars?.toLocaleString() ?? 0} characters`
      break
    case 'chunked':
      state.totalChunks = (data.total_chunks as number) ?? 0
      state.stepMessage = `共 ${data.total_chunks} 个块`
      break
    case 'chunk_done': {
      const chunk = data as unknown as ChunkDoneEvent
      const existingIdx = state.translations.findIndex(t => t.index === chunk.index)
      if (existingIdx >= 0) {
        state.translations[existingIdx] = chunk
      } else {
        state.translations.push(chunk)
      }
      state.completedChunks = Math.max(state.completedChunks, chunk.index + 1)
      if ((data as Record<string, unknown>).fallback) {
        state.fallbackChunks += 1
        state.stepMessage = `Chunk ${chunk.index + 1}/${chunk.total} failed; original text was kept`
      } else {
        state.stepMessage = `Translated chunk ${chunk.index + 1}/${chunk.total}`
      }
      break
    }
    case 'chunk_error':
      console.warn(`Translation chunk ${(data as Record<string, unknown>).index}/${(data as Record<string, unknown>).total} failed:`, (data as Record<string, unknown>).error)
      break
    case 'complete':
      state.finalContent = (data.content as string) ?? ''
      state.chunks = (data.chunks as { original: string; translated: string }[]) ?? []
      setStatus('done')
      if (state.fallbackChunks > 0) {
        state.stepMessage = `翻译完成（警告：${state.fallbackChunks} 个块翻译失败，已保留原文）`
      } else {
        state.stepMessage = '翻译完成'
      }
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

const MAX_UPLOAD_SIZE = 200 * 1024 * 1024 // 200 MB, 与后端保持一致
async function translate(file: File): Promise<void> {
  reset()
  setStatus('uploading')
  state.stepMessage = '上传文件...'

  try {
    if (file.size > MAX_UPLOAD_SIZE) {
      throw new Error('文件过大，最大支持 200 MB')
    }

    const healthOk = await checkHealth()
    if (!healthOk) {
      throw new Error('Cannot connect to translation service. Please make sure the backend is running.')
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

async function uploadPdfByPath(filePath: string): Promise<string> {
  const resp = await fetch(`${API_URL}/api/translate/path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: filePath }),
  })

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || `上传失败 (${resp.status})`)
  }

  const data = await resp.json()
  state.taskId = data.task_id
  return data.task_id
}

async function translateFromPath(filePath: string): Promise<void> {
  reset()
  setStatus('uploading')
  state.stepMessage = '上传文件...'

  try {
    const healthOk = await checkHealth()
    if (!healthOk) {
      throw new Error('Cannot connect to translation service. Please make sure the backend is running.')
    }

    const supportedExts = ['.pdf','.docx','.doc','.txt','.md','.log','.html','.htm','.epub','.rtf','.tex','.csv','.pptx','.xlsx','.srt','.json','.xml']
    const ext = '.' + filePath.split('.').pop()?.toLowerCase()
    if (!supportedExts.includes(ext)) {
      throw new Error(`不支持的文件格式: ${ext}`)
    }

    const taskId = await uploadPdfByPath(filePath)
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
  const content = state.finalContent
  if (!content) return

  try {
    const filePath = await save({
      defaultPath: `translated_${state.taskId}.md`,
      filters: [{ name: 'Markdown', extensions: ['md'] }, { name: 'All Files', extensions: ['*'] }],
    })
    if (!filePath) return

    await invoke<string>('save_file', { path: filePath, content })
  } catch {
    // 非 Tauri 环境：浏览器下载
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `translated_${state.taskId}.md`
    a.click()
    URL.revokeObjectURL(url)
  }
}

async function restartBackend(): Promise<boolean> {
  try {
    await invoke<string>('restart_backend')
    // 等待后端就绪
    for (let i = 0; i < 20; i++) {
      await new Promise(r => setTimeout(r, 500))
      if (await checkHealth()) return true
    }
    return false
  } catch {
    return false
  }
}

function listenBackendCrash(): void {
  if (!isTauri) return
  listen<{ message: string; exit_status: string }>('backend-crashed', (event) => {
    if (state.status === 'idle' || state.status === 'error') {
      state.errorMessage = event.payload.message || 'Python backend exited unexpectedly'
      setStatus('error')
    }
  }).then(fn => { crashListener = fn }).catch(() => {})
}

export function useTranslate() {
  return {
    state: readonly(state),
    translate,
    translateFromPath,
    reset,
    cleanup,
    checkHealth,
    checkOllama,
    startOllama,
    downloadResult,
    overallProgress,
    restartBackend,
    listenBackendCrash,
    setStatus,
    setError,
    setStepMessage,
    // Cloud API
    checkCloudApi,
    getConfig,
    updateConfig,
    getProviderPresets,
  }
}

// --- Cloud API ---

async function checkCloudApi(): Promise<{ ok: boolean; error?: string }> {
  try {
    const resp = await fetch(`${API_URL}/api/cloud/status`, { signal: AbortSignal.timeout(15000) })
    if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}` }
    const data = await resp.json()
    return { ok: data.reachable === true, error: data.error }
  } catch {
    return { ok: false, error: '无法连接到后端' }
  }
}

async function getConfig(): Promise<AppConfig | null> {
  try {
    const resp = await fetch(`${API_URL}/api/config`, { signal: AbortSignal.timeout(5000) })
    if (!resp.ok) return null
    return await resp.json() as AppConfig
  } catch {
    return null
  }
}

async function updateConfig(config: { translator?: Record<string, unknown>; cloud?: CloudConfig; network?: Record<string, unknown> }): Promise<AppConfig | null> {
  try {
    const payload: Record<string, unknown> = {}
    if (config.translator) payload.translator = config.translator
    if (config.cloud) payload.cloud = config.cloud
    if (config.network) payload.network = config.network

    const resp = await fetch(`${API_URL}/api/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!resp.ok) return null
    return await resp.json() as AppConfig
  } catch {
    return null
  }
}

async function getProviderPresets(): Promise<Record<string, ProviderPreset>> {
  try {
    const resp = await fetch(`${API_URL}/api/cloud/providers`, { signal: AbortSignal.timeout(5000) })
    if (!resp.ok) return {}
    return await resp.json() as Record<string, ProviderPreset>
  } catch {
    return {}
  }
}
