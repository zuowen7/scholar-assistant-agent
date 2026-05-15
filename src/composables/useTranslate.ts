import { reactive, readonly, markRaw } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { save } from '@tauri-apps/plugin-dialog'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'
import { persistTranslation, loadLastTranslation, clearPersistedTranslation } from './useTranslatePersist'
import { toastFromError } from './useToast'
import { validateTranslateUpload, extractApiErrorMessage } from '../utils/validation'
import type {
  TranslateState,
  TranslateStatus,
  ProgressEvent,
  ParsedEvent,
  ChunkDoneEvent,
  BlockData,
  ChunkedEvent,
  QAWarning,
  BlockTranslatedEvent,
  AppConfig,
  CloudConfig,
  ProviderPreset,
} from '../types'

// Tauri 桌面端: 后端固定在 18088; Docker/Web: 同源，使用相对路径
const isTauri = '__TAURI_INTERNALS__' in window
const API_URL = API_BASE

// SSE 自动重连参数（指数退避：2s → 4s → 8s，总超时 30s）
const SSE_RECONNECT_MAX_ATTEMPTS = 3
const SSE_RECONNECT_BASE_DELAY_MS = 2000
const SSE_RECONNECT_TOTAL_TIMEOUT_MS = 30000

function createState(): TranslateState {
  return {
    status: 'idle',
    currentStep: 0,
    totalSteps: 5,
    stepMessage: '',
    parsedInfo: null,
    totalChunks: 0,
    completedChunks: 0,
    totalBlocks: 0,
    completedBlocks: 0,
    translations: [],
    finalContent: '',
    blocks: [],
    chunks: [],
    errorMessage: null,
    taskId: null,
    fallbackChunks: 0,
    misalignedChunks: 0,
    ragIngested: false,
    qaWarnings: [],
    sectionMap: {},
  }
}

const state = reactive<TranslateState>(createState())
let abortController: AbortController | null = null
let crashListener: UnlistenFn | null = null
let _currentStreamId = 0
let _isReconnecting = false

function reset(): void {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  _currentStreamId++
  _isReconnecting = false
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

  // Within step 4 (translating), subdivide by blocks (or chunks fallback)
  if (state.currentStep === 4) {
    if (state.totalBlocks > 0) {
      pct += (state.completedBlocks / state.totalBlocks) * 16
    } else if (state.totalChunks > 0) {
      pct += (state.completedChunks / state.totalChunks) * 16
    }
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
    const body = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(extractApiErrorMessage(body) || `上传失败 (${resp.status})`)
  }

  const data = validateTranslateUpload(await resp.json())
  state.taskId = data.task_id
  return data.task_id
}

async function startStream(taskId: string, attempt: number = 0): Promise<void> {
  abortController?.abort()
  abortController = new AbortController()
  const myStreamId = ++_currentStreamId

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
    await readSseStream(reader, (event, data) => {
      // Discard events from stale streams
      if (myStreamId !== _currentStreamId) return
      handleSseEvent(event, data)
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return
    }
    // Stale stream — silently discard
    if (myStreamId !== _currentStreamId) return

    if (state.status !== 'done' && state.status !== 'idle' && attempt < SSE_RECONNECT_MAX_ATTEMPTS) {
      if (_isReconnecting) return
      _isReconnecting = true
      try {
        const delay = Math.min(SSE_RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt), SSE_RECONNECT_TOTAL_TIMEOUT_MS)
        state.stepMessage = `连接中断，正在重试 (${attempt + 1}/${SSE_RECONNECT_MAX_ATTEMPTS})… ${Math.round(delay / 1000)}s 后重连`
        await new Promise(r => setTimeout(r, delay))
        if (abortController === null || myStreamId !== _currentStreamId) return

        const stillAlive = await checkHealth()
        if (stillAlive) {
          _isReconnecting = false
          await startStream(taskId, attempt + 1)
          return
        }
      } finally {
        _isReconnecting = false
      }
    }

    if (state.status !== 'done') {
      throw err
    }
  }
}

function handleSseEvent(event: string, data: Record<string, unknown>): void {
  switch (event) {
    case 'translate.progress': {
      const p = data as unknown as ProgressEvent
      state.currentStep = p.step
      state.totalSteps = p.total
      state.stepMessage = p.message
      setStatus(stepToStatus(p.step))
      break
    }
    case 'translate.parsed':
      state.parsedInfo = data as unknown as ParsedEvent
      break
    case 'translate.cleaned':
      state.stepMessage = `Cleaning complete, ${data.chars?.toLocaleString() ?? 0} characters`
      break
    case 'translate.chunked': {
      const ev = data as unknown as ChunkedEvent
      state.totalChunks = ev.total_chunks ?? 0
      state.totalBlocks = ev.total_blocks ?? 0
      // 用原文初始化 blocks 骨架；markRaw 防止 Vue 深度追踪大数组内部属性
      state.blocks = (ev.blocks ?? []).map(b => markRaw({
        id: b.id,
        type: b.type,
        level: b.level,
        translatable: b.translatable,
        original: b.original,
        translated: '',
      }))
      state.stepMessage = `共 ${state.totalChunks} 块、${state.totalBlocks} 段`
      break
    }
    case 'translate.block_translated': {
      const ev = data as unknown as BlockTranslatedEvent
      const idx = state.blocks.findIndex(b => b.id === ev.block_id)
      if (idx >= 0) {
        const wasEmpty = !state.blocks[idx].translated
        const updated = markRaw({
          ...state.blocks[idx],
          translated: ev.translated,
          translatable: ev.translatable,
          type: ev.type,
          status: ev.status,
        })
        // Replace whole array to trigger shallowRef/reactive update cleanly
        const newBlocks = [...state.blocks]
        newBlocks[idx] = updated
        state.blocks = newBlocks
        if (wasEmpty) state.completedBlocks += 1
      }
      break
    }
    case 'translate.chunk_done': {
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
      } else if ((data as Record<string, unknown>).aligned === false) {
        state.misalignedChunks += 1
        state.stepMessage = `Chunk ${chunk.index + 1}/${chunk.total} translated (alignment fallback)`
      } else {
        state.stepMessage = `Translated chunk ${chunk.index + 1}/${chunk.total}`
      }
      // P0: Track section type per chunk
      const secType = (data as Record<string, unknown>).section_type as string | undefined
      if (secType && secType !== 'unknown') {
        state.sectionMap[chunk.index] = secType
      }
      break
    }
    case 'translate.qa_warnings': {
      // P0: Post-translation QA warnings
      const qa = data as unknown as QAWarning
      state.qaWarnings.push(qa)
      break
    }
    case 'translate.chunk_error':
      console.warn(`Translation chunk ${(data as Record<string, unknown>).index}/${(data as Record<string, unknown>).total} failed:`, (data as Record<string, unknown>).error)
      break
    case 'translate.complete':
      state.finalContent = (data.content as string) ?? ''
      // complete 事件用最终的 blocks 覆盖（修正流式过程中可能的不一致）
      if (data.blocks) {
        state.blocks = data.blocks as BlockData[]
      }
      state.chunks = (data.chunks as { original: string; translated: string }[]) ?? []
      state.ragIngested = (data.rag_ingested as boolean) ?? false
      setStatus('done')
      if (state.fallbackChunks > 0 || state.misalignedChunks > 0) {
        const parts: string[] = []
        if (state.fallbackChunks > 0) parts.push(`${state.fallbackChunks} 块失败`)
        if (state.misalignedChunks > 0) parts.push(`${state.misalignedChunks} 块对齐失败`)
        state.stepMessage = `翻译完成（警告：${parts.join('、')}）`
      } else {
        state.stepMessage = '翻译完成'
      }
      persistTranslation({
        id: state.taskId || `result-${Date.now()}`,
        finalContent: state.finalContent,
        blocks: state.blocks,
        chunks: state.chunks,
        parsedInfo: state.parsedInfo,
        stepMessage: state.stepMessage,
        fallbackChunks: state.fallbackChunks,
        misalignedChunks: state.misalignedChunks,
      })
      break
    case 'translate.error':
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
      toastFromError(err)
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
      toastFromError(err)
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
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = `translated_${state.taskId}.md`
    a.click()
    URL.revokeObjectURL(blobUrl)
  }
}

async function exportBilingualDocx(): Promise<void> {
  if (!state.taskId) return
  state.errorMessage = ''

  try {
    const resp = await fetch(`${API_URL}/api/export/bilingual_docx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.taskId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '导出失败' }))
      const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)
      throw new Error(detail || `导出失败 (${resp.status})`)
    }

    const blob = await resp.blob()
    const defaultName = `${state.taskId}_bilingual.docx`
    const { saveBlob } = await import('./useEditorIO')
    const result = await saveBlob(blob, defaultName)
    if (result === 'Cancelled') return
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    state.errorMessage = msg
  }
}

async function exportTranslationOnlyDocx(): Promise<void> {
  if (!state.taskId) return
  state.errorMessage = ''

  try {
    const resp = await fetch(`${API_URL}/api/export/translation_only_docx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.taskId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '导出失败' }))
      const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)
      throw new Error(detail || `导出失败 (${resp.status})`)
    }

    const blob = await resp.blob()
    const defaultName = `${state.taskId}_translation_only.docx`
    const { saveBlob } = await import('./useEditorIO')
    const result = await saveBlob(blob, defaultName)
    if (result === 'Cancelled') return
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    state.errorMessage = msg
  }
}

async function exportTranslationOnlyMarkdown(): Promise<void> {
  if (!state.taskId) return

  // 构建纯译文markdown
  const parts: string[] = []
  for (const b of state.blocks) {
    if (b.status === 'failed') continue
    if (!b.translatable) {
      parts.push(b.original)
    } else if (b.translated) {
      parts.push(b.type === 'heading' ? `${'#'.repeat(Math.min(Math.max(b.level || 2, 1), 6))} ${b.translated.replace(/^#+\s+/, '').trim()}` : b.translated)
    }
  }
  const content = parts.join('\n\n')

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
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = `translated_${state.taskId}.md`
    a.click()
    URL.revokeObjectURL(blobUrl)
  }
}

// ── P2: PPTX 导出 ──────────────────────────────────────────────────────

async function exportPPTX(): Promise<void> {
  if (!state.taskId) return
  state.errorMessage = ''

  try {
    const resp = await fetch(`${API_URL}/api/export/pptx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.taskId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'PPTX 导出失败' }))
      const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)
      throw new Error(detail || `PPTX 导出失败 (${resp.status})`)
    }

    const blob = await resp.blob()
    const defaultName = `${state.taskId}_presentation.pptx`
    const { saveBlob } = await import('./useEditorIO')
    await saveBlob(blob, defaultName)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    state.errorMessage = msg
  }
}

// ── P3: Data Availability 导出 ──────────────────────────────────────────

async function exportDataAvailability(): Promise<void> {
  if (!state.taskId) return
  state.errorMessage = ''

  try {
    const resp = await fetch(`${API_URL}/api/export/data_availability`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: state.taskId }),
    })

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Data Availability 生成失败' }))
      const detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail)
      throw new Error(detail || `生成失败 (${resp.status})`)
    }

    const data = await resp.json()
    // 复制到剪贴板 + 保存为文件
    const content = data.section || JSON.stringify(data, null, 2)
    const { saveBlob } = await import('./useEditorIO')
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    await saveBlob(blob, `${state.taskId}_data_availability.md`)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '未知错误'
    state.errorMessage = msg
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
    recoverTranslation,
    discardPersisted,
    // Cloud API
    checkCloudApi,
    getConfig,
    updateConfig,
    getProviderPresets,
    exportBilingualDocx,
    exportTranslationOnlyDocx,
    exportTranslationOnlyMarkdown,
    // P2-P3: New export formats
    exportPPTX,
    exportDataAvailability,
  }
}

/** Reset all singleton state — for use in tests only. */
export function _resetForTesting(): void {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  if (crashListener) {
    crashListener()
    crashListener = null
  }
  Object.assign(state, createState())
}

async function recoverTranslation(): Promise<boolean> {
  const saved = await loadLastTranslation()
  if (!saved) return false
  Object.assign(state, {
    status: 'done',
    currentStep: 5,
    totalSteps: 5,
    stepMessage: saved.stepMessage || '翻译完成（已恢复）',
    finalContent: saved.finalContent,
    blocks: saved.blocks,
    chunks: saved.chunks,
    parsedInfo: saved.parsedInfo,
    fallbackChunks: saved.fallbackChunks ?? 0,
    misalignedChunks: saved.misalignedChunks ?? 0,
    taskId: saved.id,
  })
  return true
}

async function discardPersisted(): Promise<void> {
  const saved = await loadLastTranslation()
  if (saved) await clearPersistedTranslation(saved.id)
  reset()
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
