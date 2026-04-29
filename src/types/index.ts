export interface ProgressEvent {
  step: number
  total: number
  message: string
}

export interface ParsedEvent {
  pages: number
  chars: number
  dual_column_pages: number
}

export interface CleanedEvent {
  chars: number
  has_references: boolean
}

export interface ChunkedEvent {
  total_chunks: number
  references_chars: number
}

export interface ChunkDoneEvent {
  index: number
  total: number
  original_preview: string
  translated_preview: string
  tokens: number
}

export interface CompleteEvent {
  task_id: string
  output_path: string
  content: string
  chunks: { original: string; translated: string }[]
}

export type TranslateStatus =
  | 'idle'
  | 'uploading'
  | 'parsing'
  | 'cleaning'
  | 'chunking'
  | 'translating'
  | 'formatting'
  | 'done'
  | 'error'

export interface TranslateState {
  status: TranslateStatus
  currentStep: number
  totalSteps: number
  stepMessage: string
  parsedInfo: ParsedEvent | null
  totalChunks: number
  completedChunks: number
  translations: ChunkDoneEvent[]
  finalContent: string
  chunks: { original: string; translated: string }[]
  errorMessage: string | null
  taskId: string | null
  /** Number of chunks that fell back to original text due to translation failure */
  fallbackChunks: number
  /** Whether translation was successfully ingested into RAG knowledge base */
  ragIngested: boolean
}

export interface AppConfig {
  parser: { engine: string; extract_tables: boolean }
  cleaner: { max_line_gap: number; fix_hyphenation: boolean; remove_headers_footers: boolean }
  chunker: { max_tokens: number; overlap_tokens: number; strategy: string }
  translator: {
    engine: 'ollama' | 'cloud'
    ollama_base_url: string
    model: string
    temperature: number
    num_predict: number
    system_prompt: string
    timeout: number
    cloud: CloudConfig
  }
  formatter: { output_format: string; file_format: string }
  network: { proxy: string }
}

export interface CloudConfig {
  provider: string
  api_key: string
  base_url: string
  model: string
  max_tokens: number
}

export interface ProviderPreset {
  name: string
  base_url: string
  models: string[]
  api_format: string
}

// ── Agent / RAG 类型 ────────────────────────────────────────────

export interface AgentEvent {
  type: 'thinking' | 'tool_call' | 'tool_result' | 'response' | 'error'
    | 'session_started' | 'task_started' | 'thought' | 'await_approval'
    | 'approval_received' | 'task_done' | 'warning' | 'done' | 'aborted'
  content: string
  event_id?: string
  metadata?: {
    // v1
    tool_name?: string
    arguments?: Record<string, unknown>
    duration_ms?: number
    error?: boolean
    event_id?: string
    // v2 session/task
    session_id?: string
    task_id?: string
    resumed?: boolean
    title?: string
    index?: number
    total?: number
    // v2 tool_call
    tool?: string
    args?: Record<string, unknown>
    risk?: string
    // v2 await_approval
    preview?: Record<string, unknown>
    // v2 done
    tasks_done?: number
    token_usage?: Record<string, number>
    // v2 warning
    code?: string
    // v2 task_done
    status?: string
  }
}

export interface AgentSessionInfo {
  id: string
  state: string
  global_step: number
  tasks_total: number
  tasks_done: number
  workspace_root?: string
  query?: string
  created_at?: string
  updated_at?: string
  source?: 'memory' | 'store'
}

export interface AgentChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  events: AgentEvent[]
  isStreaming: boolean
  timestamp: number
}

export interface RAGDocument {
  id: string
  title: string
  chunk_count: number
  metadata: Record<string, unknown>
}

// ── 编辑器 / Scholar Cursor 类型 ─────────────────────────────────

export interface EditorTab {
  id: string        // unique per open file (path as id)
  path: string | null  // null = untitled
  name: string
  content: string
  isModified: boolean
}

export interface FileEntry {
  name: string
  path: string
  isDir: boolean
  children?: FileEntry[]
}

export interface EditorSelection {
  startLine: number
  endLine: number
  startCol: number
  endCol: number
  text: string
}

export interface EditRequest {
  text: string
  instruction: string
}

export interface EditStreamEvent {
  type: 'progress' | 'delta' | 'complete' | 'error'
  content: string
  usage?: { prompt_tokens: number; completion_tokens: number }
}

export type AppMode = 'translate' | 'editor'
