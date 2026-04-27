import { describe, it, expect } from 'vitest'
import type {
  TranslateStatus,
  TranslateState,
  EditorTab,
  EditorSelection,
  AgentEvent,
  AgentChatMessage,
  RAGDocument,
  FileEntry,
  AppMode,
  EditStreamEvent,
} from '../types'

// ---------------------------------------------------------------------------
// TranslateStatus — verify the allowed string values
// ---------------------------------------------------------------------------
describe('TranslateStatus type values', () => {
  const validStatuses: TranslateStatus[] = [
    'idle',
    'uploading',
    'parsing',
    'cleaning',
    'chunking',
    'translating',
    'formatting',
    'done',
    'error',
  ]

  it('contains exactly 9 statuses', () => {
    expect(validStatuses).toHaveLength(9)
  })

  it('includes all pipeline stages in order', () => {
    expect(validStatuses.slice(1, 8)).toEqual([
      'uploading',
      'parsing',
      'cleaning',
      'chunking',
      'translating',
      'formatting',
      'done',
    ])
  })

  it('starts with idle and ends with error', () => {
    expect(validStatuses[0]).toBe('idle')
    expect(validStatuses[validStatuses.length - 1]).toBe('error')
  })
})

// ---------------------------------------------------------------------------
// TranslateState — default state shape
// ---------------------------------------------------------------------------
describe('TranslateState default shape', () => {
  const defaultState: TranslateState = {
    status: 'idle',
    currentStep: 0,
    totalSteps: 0,
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

  it('has status idle by default', () => {
    expect(defaultState.status).toBe('idle')
  })

  it('has zero progress values', () => {
    expect(defaultState.currentStep).toBe(0)
    expect(defaultState.totalSteps).toBe(0)
    expect(defaultState.totalChunks).toBe(0)
    expect(defaultState.completedChunks).toBe(0)
  })

  it('has empty content fields', () => {
    expect(defaultState.stepMessage).toBe('')
    expect(defaultState.finalContent).toBe('')
    expect(defaultState.translations).toEqual([])
    expect(defaultState.chunks).toEqual([])
  })

  it('has nullable fields as null', () => {
    expect(defaultState.parsedInfo).toBeNull()
    expect(defaultState.errorMessage).toBeNull()
    expect(defaultState.taskId).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// EditorTab — required fields
// ---------------------------------------------------------------------------
describe('EditorTab interface', () => {
  it('has all required fields for a file tab', () => {
    const tab: EditorTab = {
      id: '/path/to/file.md',
      path: '/path/to/file.md',
      name: 'file.md',
      content: '# Hello',
      isModified: false,
    }

    expect(tab.id).toBeTypeOf('string')
    expect(tab.path).toBeTypeOf('string')
    expect(tab.name).toBeTypeOf('string')
    expect(tab.content).toBeTypeOf('string')
    expect(tab.isModified).toBeTypeOf('boolean')
  })

  it('allows path to be null for untitled tabs', () => {
    const untitled: EditorTab = {
      id: 'untitled-1',
      path: null,
      name: 'Untitled',
      content: '',
      isModified: false,
    }

    expect(untitled.path).toBeNull()
  })

  it('id and path may differ for untitled tabs', () => {
    const tab: EditorTab = {
      id: 'untitled-999',
      path: null,
      name: 'Untitled',
      content: 'some text',
      isModified: true,
    }

    expect(tab.id).not.toBe(tab.path)
    expect(tab.isModified).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// EditorSelection — shape
// ---------------------------------------------------------------------------
describe('EditorSelection interface', () => {
  it('has all numeric position fields and text', () => {
    const sel: EditorSelection = {
      startLine: 1,
      endLine: 5,
      startCol: 0,
      endCol: 10,
      text: 'selected text',
    }

    expect(sel.startLine).toBeTypeOf('number')
    expect(sel.endLine).toBeTypeOf('number')
    expect(sel.startCol).toBeTypeOf('number')
    expect(sel.endCol).toBeTypeOf('number')
    expect(sel.text).toBeTypeOf('string')
  })

  it('can represent an empty selection', () => {
    const sel: EditorSelection = {
      startLine: 0,
      endLine: 0,
      startCol: 0,
      endCol: 0,
      text: '',
    }

    expect(sel.text).toBe('')
  })
})

// ---------------------------------------------------------------------------
// AgentEvent — discriminated union by type field
// ---------------------------------------------------------------------------
describe('AgentEvent discriminated union', () => {
  it('supports thinking event', () => {
    const evt: AgentEvent = {
      type: 'thinking',
      content: 'Analyzing the document structure...',
    }

    expect(evt.type).toBe('thinking')
    expect(evt.content).toBeTruthy()
    expect(evt.metadata).toBeUndefined()
  })

  it('supports tool_call event with metadata', () => {
    const evt: AgentEvent = {
      type: 'tool_call',
      content: 'search_documents',
      metadata: {
        tool_name: 'search_documents',
        arguments: { query: 'transformer attention', top_k: 5 },
      },
    }

    expect(evt.type).toBe('tool_call')
    expect(evt.metadata?.tool_name).toBe('search_documents')
    expect(evt.metadata?.arguments).toBeDefined()
  })

  it('supports tool_result event with duration', () => {
    const evt: AgentEvent = {
      type: 'tool_result',
      content: 'Found 3 relevant documents.',
      metadata: {
        tool_name: 'search_documents',
        duration_ms: 120,
        error: false,
      },
    }

    expect(evt.type).toBe('tool_result')
    expect(evt.metadata?.duration_ms).toBe(120)
    expect(evt.metadata?.error).toBe(false)
  })

  it('supports response event', () => {
    const evt: AgentEvent = {
      type: 'response',
      content: 'Here is a summary of the document.',
    }

    expect(evt.type).toBe('response')
  })

  it('supports error event', () => {
    const evt: AgentEvent = {
      type: 'error',
      content: 'Connection refused',
      metadata: { error: true },
    }

    expect(evt.type).toBe('error')
    expect(evt.metadata?.error).toBe(true)
  })

  it('all valid type values are accepted', () => {
    const types: AgentEvent['type'][] = [
      'thinking',
      'tool_call',
      'tool_result',
      'response',
      'error',
    ]

    expect(types).toHaveLength(5)
    types.forEach(t => expect(t).toBeTypeOf('string'))
  })
})

// ---------------------------------------------------------------------------
// AgentChatMessage — structure
// ---------------------------------------------------------------------------
describe('AgentChatMessage interface', () => {
  it('has required fields', () => {
    const msg: AgentChatMessage = {
      id: 'msg-1',
      role: 'user',
      content: 'Translate this text',
      events: [],
      isStreaming: false,
      timestamp: Date.now(),
    }

    expect(msg.role).toBe('user')
    expect(msg.events).toEqual([])
    expect(msg.isStreaming).toBe(false)
    expect(msg.timestamp).toBeTypeOf('number')
  })

  it('supports assistant role with streaming events', () => {
    const msg: AgentChatMessage = {
      id: 'msg-2',
      role: 'assistant',
      content: '',
      events: [
        { type: 'thinking', content: 'Processing...' },
        { type: 'tool_call', content: 'translate_text', metadata: { tool_name: 'translate_text' } },
      ],
      isStreaming: true,
      timestamp: Date.now(),
    }

    expect(msg.role).toBe('assistant')
    expect(msg.events).toHaveLength(2)
    expect(msg.isStreaming).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// RAGDocument — structure
// ---------------------------------------------------------------------------
describe('RAGDocument interface', () => {
  it('has required fields', () => {
    const doc: RAGDocument = {
      id: 'doc-abc',
      title: 'Attention Is All You Need',
      chunk_count: 12,
      metadata: { source: 'upload', pages: 8 },
    }

    expect(doc.id).toBeTypeOf('string')
    expect(doc.title).toBeTypeOf('string')
    expect(doc.chunk_count).toBeTypeOf('number')
    expect(doc.metadata).toBeTypeOf('object')
  })
})

// ---------------------------------------------------------------------------
// FileEntry — tree structure
// ---------------------------------------------------------------------------
describe('FileEntry interface', () => {
  it('represents a file', () => {
    const file: FileEntry = {
      name: 'notes.md',
      path: '/home/user/notes.md',
      isDir: false,
    }

    expect(file.isDir).toBe(false)
    expect(file.children).toBeUndefined()
  })

  it('represents a directory with children', () => {
    const dir: FileEntry = {
      name: 'docs',
      path: '/home/user/docs',
      isDir: true,
      children: [
        { name: 'a.md', path: '/home/user/docs/a.md', isDir: false },
        { name: 'b.md', path: '/home/user/docs/b.md', isDir: false },
      ],
    }

    expect(dir.isDir).toBe(true)
    expect(dir.children).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// AppMode — union type
// ---------------------------------------------------------------------------
describe('AppMode type', () => {
  it('accepts translate', () => {
    const mode: AppMode = 'translate'
    expect(mode).toBe('translate')
  })

  it('accepts editor', () => {
    const mode: AppMode = 'editor'
    expect(mode).toBe('editor')
  })
})

// ---------------------------------------------------------------------------
// EditStreamEvent — discriminated union
// ---------------------------------------------------------------------------
describe('EditStreamEvent interface', () => {
  it('supports all event types', () => {
    const progress: EditStreamEvent = { type: 'progress', content: 'Starting...' }
    const delta: EditStreamEvent = { type: 'delta', content: 'Hello world' }
    const complete: EditStreamEvent = { type: 'complete', content: 'Done', usage: { prompt_tokens: 10, completion_tokens: 20 } }
    const error: EditStreamEvent = { type: 'error', content: 'Failed' }

    expect(progress.type).toBe('progress')
    expect(delta.type).toBe('delta')
    expect(complete.type).toBe('complete')
    expect(complete.usage?.completion_tokens).toBe(20)
    expect(error.type).toBe('error')
  })
})
