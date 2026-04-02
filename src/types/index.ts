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
}

export interface AppConfig {
  parser: { engine: string; extract_tables: boolean }
  cleaner: { max_line_gap: number; fix_hyphenation: boolean; remove_headers_footers: boolean }
  chunker: { max_tokens: number; overlap_tokens: number; strategy: string }
  translator: {
    ollama_base_url: string
    model: string
    temperature: number
    num_predict: number
    system_prompt: string
    timeout: number
  }
  formatter: { output_format: string; file_format: string }
}
