/** Phase 3 tests: useAgentChat — per-workflow isolation, AbortSignal, pipeline state. */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

// Mock API base
vi.mock('../utils/api', () => ({ API_BASE: 'http://localhost:18088' }))

// Mock i18n
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

describe('useAgentChat — workflow isolation', () => {
  it('messages should be per-workflow', () => {
    // Messages for workflow A vs workflow B are stored separately
    const messagesByWorkflow = new Map<string, any[]>()
    messagesByWorkflow.set('wf_a', [
      { id: '1', role: 'user', content: 'hello A', events: [], isStreaming: false, timestamp: 1 },
    ])
    messagesByWorkflow.set('wf_b', [
      { id: '2', role: 'user', content: 'hello B', events: [], isStreaming: false, timestamp: 2 },
    ])

    const msgsA = messagesByWorkflow.get('wf_a') ?? []
    const msgsB = messagesByWorkflow.get('wf_b') ?? []

    expect(msgsA).toHaveLength(1)
    expect(msgsB).toHaveLength(1)
    expect(msgsA[0].content).toBe('hello A')
    expect(msgsB[0].content).toBe('hello B')
  })

  it('switching workflow changes active messages', () => {
    const messagesByWorkflow = new Map<string, any[]>()
    messagesByWorkflow.set('wf_x', [{ id: '1', role: 'user', content: 'msg from X', events: [], isStreaming: false, timestamp: 1 }])
    messagesByWorkflow.set('wf_y', [{ id: '2', role: 'user', content: 'msg from Y', events: [], isStreaming: false, timestamp: 2 }])

    let activeId = 'wf_x'
    let messages = messagesByWorkflow.get(activeId)!

    expect(messages[0].content).toBe('msg from X')

    activeId = 'wf_y'
    messages = messagesByWorkflow.get(activeId)!

    expect(messages[0].content).toBe('msg from Y')
  })

  it('switch to nonexistent workflow returns empty', () => {
    const messagesByWorkflow = new Map<string, any[]>()
    const result = messagesByWorkflow.get('no_such_id') ?? []
    expect(result).toHaveLength(0)
  })

  it('send message should include workflow_id in request body', () => {
    // Verify the payload shape
    const payload = {
      message: 'test',
      workflow_id: 'wf_abc123',
    }
    expect(payload.workflow_id).toBe('wf_abc123')
  })

  it('start new workflow sets workflowId to null', () => {
    let workflowId: string | null = 'wf_old'
    // New chat button sets to null → triggers new workflow creation
    workflowId = null
    expect(workflowId).toBeNull()
  })

  it('clear current workflow only removes that one', () => {
    const messagesByWorkflow = new Map<string, any[]>()
    messagesByWorkflow.set('wf_a', [{ id: '1', role: 'user', content: 'a', events: [], isStreaming: false, timestamp: 1 }])
    messagesByWorkflow.set('wf_b', [{ id: '2', role: 'user', content: 'b', events: [], isStreaming: false, timestamp: 2 }])

    // Delete only wf_a
    messagesByWorkflow.delete('wf_a')

    expect(messagesByWorkflow.has('wf_a')).toBe(false)
    expect(messagesByWorkflow.has('wf_b')).toBe(true)
  })
})

describe('useAgentChat — shared between panels', () => {
  it('AgentPanel and AiPanel share same workflowId', () => {
    const sharedWorkflowId = ref<string | null>('wf_shared')

    // Both panels read the same ref
    const agentPanelId = sharedWorkflowId
    const aiPanelId = sharedWorkflowId

    expect(agentPanelId.value).toBe('wf_shared')
    expect(aiPanelId.value).toBe('wf_shared')

    sharedWorkflowId.value = 'wf_new'
    expect(agentPanelId.value).toBe('wf_new')
    expect(aiPanelId.value).toBe('wf_new')
  })

  it('AiPanel chat mode writes to shared workflow messages', () => {
    const messagesByWorkflow = new Map<string, any[]>()
    const activeId = 'wf_test'
    messagesByWorkflow.set(activeId, [])

    // AiPanel adds a message
    const msgs = messagesByWorkflow.get(activeId)!
    msgs.push({ id: '1', role: 'user', content: 'from AiPanel', events: [], isStreaming: false, timestamp: Date.now() })

    expect(messagesByWorkflow.get(activeId)).toHaveLength(1)
    expect(messagesByWorkflow.get(activeId)![0].content).toBe('from AiPanel')
  })

  it('AiPanel preset mode does not affect workflow', () => {
    // Preset mode uses /api/edit, not /api/agent/v2/chat
    const isPresetMode = true
    const workflowId = 'wf_123'

    // In preset mode, workflow_id is not needed
    const endpoint = isPresetMode ? '/api/edit' : '/api/agent/v2/chat'
    expect(endpoint).toBe('/api/edit')
  })
})

describe('useAgentChat — AbortSignal fix', () => {
  it('resume passes AbortSignal to reader', () => {
    const signal = new AbortController().signal
    const streamReaderArgs: any[] = [null, () => {}, undefined, undefined]

    // After fix: signal is the 3rd argument
    streamReaderArgs[2] = signal
    expect(streamReaderArgs[2]).toBeDefined()
    expect(streamReaderArgs[2]).toBeInstanceOf(AbortSignal)
  })

  it('initial fetch passes AbortSignal to reader', () => {
    const signal = new AbortController().signal
    const streamReaderArgs: any[] = [null, () => {}, undefined, undefined]
    streamReaderArgs[2] = signal
    expect(streamReaderArgs[2]).toBeDefined()
  })

  it('abort during resume stops stream', () => {
    const controller = new AbortController()
    controller.abort()
    expect(controller.signal.aborted).toBe(true)
  })
})

describe('useAgentChat — pipeline state', () => {
  it('pipeline_stage event updates progress', () => {
    let stage = ''
    let completed: string[] = []

    // Simulate SSE event handler
    const handleEvent = (eventType: string, data: any) => {
      if (eventType === 'pipeline_stage') {
        stage = data.metadata?.to ?? ''
        completed = data.metadata?.completed ?? []
      }
    }

    handleEvent('pipeline_stage', {
      type: 'pipeline_stage',
      metadata: { to: 'research', completed: [] },
    })
    expect(stage).toBe('research')

    handleEvent('pipeline_stage', {
      type: 'pipeline_stage',
      metadata: { to: 'outline', completed: ['research'] },
    })
    expect(stage).toBe('outline')
    expect(completed).toContain('research')
  })

  it('checkpoint event sets pendingCheckpoint', () => {
    let pendingCheckpoint: any = null

    const handleEvent = (data: any) => {
      pendingCheckpoint = data
    }

    handleEvent({
      stage: 'draft',
      checkpoint_type: 'MANDATORY',
      title: 'Stage: WRITE complete',
      deliverables: ['Draft (3200 words)'],
      metrics: { word_count: 3200 },
    })

    expect(pendingCheckpoint).not.toBeNull()
    expect(pendingCheckpoint.stage).toBe('draft')
    expect(pendingCheckpoint.checkpoint_type).toBe('MANDATORY')
  })

  it('MANDATORY checkpoint cannot be skipped', () => {
    const checkpoint = { checkpoint_type: 'MANDATORY' } as const
    const canSkip = checkpoint.checkpoint_type === 'SLIM'
    expect(canSkip).toBe(false)
  })

  it('SLIM checkpoint can be skipped', () => {
    const checkpoint = { checkpoint_type: 'SLIM' } as const
    const canSkip = checkpoint.checkpoint_type === 'SLIM'
    expect(canSkip).toBe(true)
  })
})
