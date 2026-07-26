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

export interface SourceContent {
  source_id: string
  title: string
  text: string
  pages: number
  chars: number
}

export interface SourceQueryHit {
  doc_id: string
  chunk_id: string
  source: string
  text: string
  distance: number | null
  metadata: Record<string, unknown>
}

const sources = ref<ProjectSource[]>([])
const loading = ref(false)
const saving = ref(false)
const indexingSourceId = ref('')
const deletingSourceId = ref('')
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
  return importSource(file)
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
  patch: Partial<
    Pick<
      ProjectSource,
      | 'title'
      | 'translated_path'
      | 'translation_task_id'
      | 'reading_status'
      | 'cited'
      | 'rag_status'
      | 'metadata'
    >
  >,
): Promise<ProjectSource> {
  return upsertSource({ ...source, ...patch })
}

async function importSource(file: File, existingSource?: ProjectSource): Promise<ProjectSource> {
  saving.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('project_path', projectPath())
    if (existingSource) form.append('source_id', existingSource.id)
    form.append('file', file)
    const response = await fetch(`${API_BASE}/api/project/sources/import`, {
      method: 'POST',
      body: form,
    })
    if (!response.ok) throw new Error(await parseError(response))
    const saved = (await response.json()) as ProjectSource
    const index = sources.value.findIndex((item) => item.id === saved.id)
    if (index >= 0) sources.value[index] = saved
    else sources.value.unshift(saved)
    return saved
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法导入文献'
    throw cause
  } finally {
    saving.value = false
  }
}

async function readSource(
  source: ProjectSource,
  version: 'original' | 'translated' = 'original',
): Promise<SourceContent> {
  const response = await fetch(
    `${API_BASE}/api/project/sources/${encodeURIComponent(source.id)}/content?project_path=${encodeURIComponent(projectPath())}&version=${version}`,
  )
  if (!response.ok) throw new Error(await parseError(response))
  if (source.reading_status === 'unread') {
    void updateSource(source, { reading_status: 'reading' }).catch(() => undefined)
  }
  return (await response.json()) as SourceContent
}

async function attachTranslationToSource(source: ProjectSource): Promise<ProjectSource> {
  const { state } = useTranslate()
  if (state.status !== 'done' || !state.taskId || !state.outputPath) {
    throw new Error('当前文献翻译尚未完成')
  }
  const response = await fetch(
    `${API_BASE}/api/project/sources/${encodeURIComponent(source.id)}/translation`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_path: projectPath(),
        output_path: state.outputPath,
        task_id: state.taskId,
        // Translation auto-ingestion has no project/source filter metadata.
        // Mark this attachment unavailable until indexSource creates the project-scoped index.
        rag_status: 'unavailable',
      }),
    },
  )
  if (!response.ok) throw new Error(await parseError(response))
  const saved = (await response.json()) as ProjectSource
  const index = sources.value.findIndex((item) => item.id === saved.id)
  if (index >= 0) sources.value[index] = saved
  return saved
}

async function indexSource(source: ProjectSource): Promise<ProjectSource> {
  indexingSourceId.value = source.id
  error.value = ''
  let queuedSource = source
  try {
    queuedSource = await updateSource(source, { rag_status: 'queued' })
    const content = await readSource(queuedSource)
    const docId = `project:${source.id}`
    const response = await fetch(`${API_BASE}/api/rag/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: docId,
        title: source.title,
        text: content.text,
        project_root: projectPath(),
        source_id: source.id,
      }),
    })
    if (!response.ok) throw new Error(await parseError(response))
    const payload = (await response.json()) as { chunk_count?: number }
    return await updateSource(queuedSource, {
      rag_status: 'ready',
      metadata: {
        ...queuedSource.metadata,
        rag_doc_id: docId,
        chunk_count: payload.chunk_count ?? 0,
        indexed_at: new Date().toISOString(),
      },
    })
  } catch (cause) {
    await updateSource(queuedSource, { rag_status: 'failed' }).catch(() => undefined)
    error.value = cause instanceof Error ? cause.message : 'RAG 入库失败'
    throw cause
  } finally {
    indexingSourceId.value = ''
  }
}

async function querySources(query: string, sourceIds?: string[]): Promise<SourceQueryHit[]> {
  const response = await fetch(`${API_BASE}/api/rag/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      top_k: 8,
      project_root: projectPath(),
      source_ids: sourceIds?.length ? sourceIds : undefined,
    }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  const payload = (await response.json()) as { hits?: SourceQueryHit[] }
  return Array.isArray(payload.hits) ? payload.hits : []
}

async function deleteSource(source: ProjectSource): Promise<void> {
  deletingSourceId.value = source.id
  error.value = ''
  try {
    const ragDocId =
      typeof source.metadata.rag_doc_id === 'string'
        ? source.metadata.rag_doc_id
        : `project:${source.id}`
    if (source.rag_status === 'ready' || source.rag_status === 'failed') {
      await fetch(`${API_BASE}/api/rag/documents/${encodeURIComponent(ragDocId)}`, {
        method: 'DELETE',
      }).catch(() => undefined)
    }
    const response = await fetch(
      `${API_BASE}/api/project/sources/${encodeURIComponent(source.id)}?project_path=${encodeURIComponent(projectPath())}&delete_file=true`,
      { method: 'DELETE' },
    )
    if (!response.ok) throw new Error(await parseError(response))
    sources.value = sources.value.filter((item) => item.id !== source.id)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法删除文献'
    throw cause
  } finally {
    deletingSourceId.value = ''
  }
}

async function importZoteroItem(item: {
  key: string
  title?: string
  authors?: string[]
  year?: string
  journal?: string
  citation_key?: string
  markdown_citation?: string
}): Promise<ProjectSource> {
  return upsertSource({
    title: item.title?.trim() || item.citation_key || item.key,
    original_path: null,
    translated_path: null,
    translation_task_id: null,
    rag_status: 'unavailable',
    reading_status: 'unread',
    cited: false,
    metadata: {
      zotero_key: item.key,
      citation_key: item.citation_key ?? null,
      authors: item.authors ?? [],
      year: item.year ?? null,
      journal: item.journal ?? null,
      markdown_citation: item.markdown_citation ?? null,
    },
  })
}

export function useSourceLibrary() {
  return {
    sources,
    loading,
    saving,
    indexingSourceId,
    deletingSourceId,
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
    importSource,
    importZoteroItem,
    readSource,
    attachTranslationToSource,
    indexSource,
    querySources,
    deleteSource,
    updateSource,
  }
}

export function _resetSourceLibraryForTesting() {
  sources.value = []
  loading.value = false
  saving.value = false
  indexingSourceId.value = ''
  deletingSourceId.value = ''
  error.value = ''
}
