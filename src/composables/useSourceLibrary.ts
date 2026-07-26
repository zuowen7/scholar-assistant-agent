import { computed, ref } from 'vue'
import { API_BASE } from '../utils/api'
import { useFileTree } from './useFileTree'
import { useTranslate } from './useTranslate'

export type SourceRagStatus = 'unavailable' | 'queued' | 'ready' | 'failed'
export type SourceReadingStatus = 'unread' | 'reading' | 'read'

export interface ProjectSource {
  id: string
  title: string
  original_path: string | null
  translated_path: string | null
  translation_task_id: string | null
  rag_status: SourceRagStatus
  reading_status: SourceReadingStatus
  cited: boolean
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

const sources = ref<ProjectSource[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')

function projectPath(): string {
  const root = useFileTree().rootDir.value
  if (!root) throw new Error('请先打开论文项目')
  return root
}

async function parseError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => ({}))) as { detail?: string }
  return payload.detail || `请求失败 (${response.status})`
}

async function loadSources(): Promise<void> {
  const root = projectPath()
  loading.value = true
  error.value = ''
  try {
    const response = await fetch(
      `${API_BASE}/api/project/sources?project_path=${encodeURIComponent(root)}`,
    )
    if (!response.ok) throw new Error(await parseError(response))
    const payload = (await response.json()) as { sources?: ProjectSource[] }
    sources.value = Array.isArray(payload.sources) ? payload.sources : []
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法读取项目文献'
    throw cause
  } finally {
    loading.value = false
  }
}

async function upsertSource(
  source: Omit<ProjectSource, 'id' | 'created_at' | 'updated_at'> & { id?: string },
): Promise<ProjectSource> {
  saving.value = true
  error.value = ''
  try {
    const response = await fetch(`${API_BASE}/api/project/sources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath(),
        source_id: source.id,
        title: source.title,
        original_path: source.original_path,
        translated_path: source.translated_path,
        translation_task_id: source.translation_task_id,
        rag_status: source.rag_status,
        reading_status: source.reading_status,
        cited: source.cited,
        metadata: source.metadata,
      }),
    })
    if (!response.ok) throw new Error(await parseError(response))
    const saved = (await response.json()) as ProjectSource
    const index = sources.value.findIndex((item) => item.id === saved.id)
    if (index >= 0) sources.value[index] = saved
    else sources.value.unshift(saved)
    return saved
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法保存项目文献'
    throw cause
  } finally {
    saving.value = false
  }
}

async function attachCurrentTranslation(): Promise<ProjectSource> {
  const { state } = useTranslate()
  if (state.status !== 'done' || !state.taskId) throw new Error('当前没有已完成的翻译')
  return upsertSource({
    title: state.sourceName || `翻译任务 ${state.taskId}`,
    original_path: state.sourcePath,
    translated_path: state.outputPath,
    translation_task_id: state.taskId,
    rag_status: state.ragStatus,
    reading_status: 'unread',
    cited: false,
    metadata: {
      pages: state.parsedInfo?.pages ?? null,
      chars: state.parsedInfo?.chars ?? null,
      bilingual: true,
    },
  })
}

async function addLocalReference(file: File): Promise<ProjectSource> {
  return upsertSource({
    title: file.name,
    original_path: null,
    translated_path: null,
    translation_task_id: null,
    rag_status: 'unavailable',
    reading_status: 'unread',
    cited: false,
    metadata: { size: file.size, type: file.type || null },
  })
}

async function addPathReference(path: string): Promise<ProjectSource> {
  const title = path.split(/[\\/]/).pop() || path
  return upsertSource({
    title,
    original_path: path,
    translated_path: null,
    translation_task_id: null,
    rag_status: 'unavailable',
    reading_status: 'unread',
    cited: false,
    metadata: {},
  })
}

async function updateSource(
  source: ProjectSource,
  patch: Partial<Pick<ProjectSource, 'reading_status' | 'cited' | 'rag_status'>>,
): Promise<ProjectSource> {
  return upsertSource({ ...source, ...patch })
}

export function useSourceLibrary() {
  return {
    sources,
    loading,
    saving,
    error,
    translatedCount: computed(
      () => sources.value.filter((source) => source.translation_task_id).length,
    ),
    citedCount: computed(() => sources.value.filter((source) => source.cited).length),
    loadSources,
    upsertSource,
    attachCurrentTranslation,
    addLocalReference,
    addPathReference,
    updateSource,
  }
}

export function _resetSourceLibraryForTesting() {
  sources.value = []
  loading.value = false
  saving.value = false
  error.value = ''
}
