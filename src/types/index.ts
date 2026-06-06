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

export interface BlockData {
  id: string
  type: 'paragraph' | 'heading' | 'formula' | 'code' | 'table' | 'list' | 'figure_caption'
  level?: number
  translatable: boolean
  original: string
  translated: string
  status?: 'ok' | 'failed' | 'partial'
}

export interface ChunkedEvent {
  total_chunks: number
  total_blocks: number
  block_types: Record<string, number>
  references_chars: number
  blocks: Array<{
    id: string
    type: BlockData['type']
    level: number
    translatable: boolean
    original: string
  }>
  chunks: Array<{
    index: number
    block_ids: string[]
    char_count: number
    estimated_tokens: number
  }>
}

export interface BlockTranslatedEvent {
  chunk_index: number
  block_id: string
  type: BlockData['type']
  translatable: boolean
  original: string
  translated: string
  aligned?: boolean
  source?: string
  status?: 'ok' | 'failed' | 'partial'
}

export interface ChunkDoneEvent {
  index: number
  total: number
  original_preview: string
  translated_preview: string
  tokens: number
  fallback?: boolean
  aligned?: boolean
}

export interface CompleteEvent {
  task_id: string
  output_path: string
  content: string
  blocks: BlockData[]
  chunks: { original: string; translated: string }[]
  misalign_count?: number
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
  totalBlocks: number
  completedBlocks: number
  translations: ChunkDoneEvent[]
  finalContent: string
  /** 结构化块——文档原文骨架，翻译完成后 translated 字段被填充 */
  blocks: BlockData[]
  /** 向后兼容：旧的 chunks 字符串对（弃用中，由 blocks 派生） */
  chunks: { original: string; translated: string }[]
  errorMessage: string | null
  taskId: string | null
  /** Number of chunks that fell back to original text due to translation failure */
  fallbackChunks: number
  /** Number of chunks where LLM output paragraph count != input block count */
  misalignedChunks: number
  /** Whether translation was successfully ingested into RAG knowledge base */
  ragIngested: boolean
  /** QA warnings from post-translation checks (P0) */
  qaWarnings: QAWarning[]
  /** Section type tracking per chunk (P0) */
  sectionMap: Record<number, string>
}

export interface QAWarning {
  chunkIndex: number
  sectionType: string
  score: number
  flags: QAFlagItem[]
}

export interface QAFlagItem {
  type: string
  severity: string
  location: string
  message: string
  suggestion: string
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
    | 'pipeline_stage' | 'checkpoint'
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
    reason?: string
    force_approval?: boolean
    preview?: Record<string, unknown>
    // v2 done
    tasks_done?: number
    token_usage?: Record<string, number>
    // v2 warning
    code?: string
    // v2 task_done
    status?: string
    // pipeline_stage
    to?: string
    completed?: string[]
    // checkpoint
    stage?: string
    checkpoint_type?: string
    deliverables?: string[]
    metrics?: Record<string, number>
    options?: string[]
    file?: string
    content?: string
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

// ── 论证陪练 v3 类型 ──────────────────────────────────────────────

export interface Anchor {
  id: string
  doc_id: string
  char_start: number | null
  char_end: number | null
  quote: string
  context_before: string
  context_after: string
  section_path: string | null
  status: 'anchored' | 'drifted' | 'lost'
}

export type NodeKind = 'contribution' | 'claim' | 'hypothesis' | 'gap_statement' | 'scope'
export type PromiseStatus = 'paid' | 'partial' | 'unpaid' | 'mismatch' | 'unknown'

export interface Promise {
  id: string
  text: string
  kind: NodeKind
  source_anchor_id: string
  discharge_anchor_ids: string[]
  status: PromiseStatus
  severity: 'info' | 'warning' | 'error'
  note: string | null
  created_by: 'user' | 'ai'
  user_overridden: boolean
}

export interface Ledger {
  id: string
  doc_id: string
  doc_title: string
  promises: Promise[]
  anchors: Anchor[]
  doc_hash: string | null
  last_built_at: number
}

export type PointSeverity = 'minor' | 'major' | 'fatal'
export type PointCategory =
  | 'motivation' | 'novelty' | 'baseline' | 'ablation' | 'soundness'
  | 'claim_overreach' | 'missing_related_work' | 'reproducibility'
  | 'experiment_design' | 'writing_clarity'
  | 'inconsistency' | 'gap_mismatch' | 'weak_positioning' | 'term_drift' | 'other'
export type PointStatus = 'open' | 'rebutted' | 'accepted' | 'dismissed'
export type PointSource = 'llm' | 'ledger_check' | 'coherence_check' | 'rw_check' | 'scoped' | 'imported'

export interface RebuttalTurn {
  id: string
  role: 'author' | 'reviewer'
  text: string
  created_at: number
}

export interface ReviewPoint {
  id: string
  severity: PointSeverity
  category: PointCategory
  title: string
  detail: string
  anchor_id: string | null
  status: PointStatus
  source: PointSource
  reviewer_label: string | null
  perspective: 'method' | 'experiment' | 'writing' | 'devils_advocate' | 'aggregated' | null
  thread: RebuttalTurn[]
}

export interface ReviewSession {
  id: string
  doc_id: string
  doc_title: string
  venue: string | null
  persona: 'reviewer2' | 'ac' | 'domain_expert' | 'friendly' | 'real'
  checks: string[]
  points: ReviewPoint[]
  anchors: Anchor[]
  doc_hash: string | null
  created_at: number
  synthesis?: Record<string, unknown>
}

export interface ReviewSummary {
  session_id: string
  venue: string | null
  persona: string
  point_count: number
  open_count: number
  rebutted_count: number
  created_at: number
}

// ── 编辑器 / Scholar Cursor 类型 ─────────────────────────────────

export interface EditorTab {
  id: string        // unique per open file (path as id)
  path: string | null  // null = untitled
  name: string
  content: string
  isModified: boolean
  docId: string     // stable id for argument companion keying
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

export type AppMode = 'translate' | 'editor' | 'argument'

// ── Project Management ──────────────────────────────────────────────

export interface ProjectMetadata {
  version: number
  name: string
  author: string
  created_at: string
  updated_at: string
  template_id: string
  status: 'creating' | 'ready'
  tags: string[]
  vcs: { initialized: boolean }
  env: { type: string | null; path: string | null }
}

export interface RecentProject {
  path: string
  name: string
  template_id: string
  opened_at: string
}

export interface ProjectTemplate {
  id: string
  name: string
  folders: string[]
}
