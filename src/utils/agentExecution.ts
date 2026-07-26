import type { AgentEvent } from '../types'

export type AgentExecutionStatus = 'running' | 'success' | 'error'

export interface AgentExecutionStep {
  id: string
  toolName: string
  args: Record<string, unknown>
  result: string
  status: AgentExecutionStatus
}

function eventToolName(event: AgentEvent): string {
  return String(event.metadata?.tool_name || event.metadata?.tool || event.content || 'tool')
}

function eventArgs(event: AgentEvent): Record<string, unknown> {
  const args = event.metadata?.args || event.metadata?.arguments
  if (args && typeof args === 'object') return args
  const input = event.metadata?.input
  if (typeof input !== 'string' || !input.trim()) return {}
  try {
    const parsed = JSON.parse(input)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

export function buildExecutionSteps(events: AgentEvent[]): AgentExecutionStep[] {
  const steps: AgentExecutionStep[] = []
  const byId = new Map<string, AgentExecutionStep>()

  for (const [index, event] of events.entries()) {
    if (event.type === 'tool_call') {
      const id = event.event_id || `tool-${index}`
      const step: AgentExecutionStep = {
        id,
        toolName: eventToolName(event),
        args: eventArgs(event),
        result: '',
        status: 'running',
      }
      steps.push(step)
      byId.set(id, step)
      continue
    }

    if (event.type !== 'tool_result') continue
    const toolName = eventToolName(event)
    const step =
      (event.event_id ? byId.get(event.event_id) : undefined) ||
      [...steps]
        .reverse()
        .find((candidate) => candidate.status === 'running' && candidate.toolName === toolName)
    if (!step) continue
    step.result = event.content
    step.status = event.metadata?.error || event.metadata?.is_error ? 'error' : 'success'
  }

  return steps
}

export function executionSummary(steps: AgentExecutionStep[]) {
  return {
    total: steps.length,
    completed: steps.filter((step) => step.status === 'success').length,
    failed: steps.filter((step) => step.status === 'error').length,
    running: steps.filter((step) => step.status === 'running').length,
  }
}
