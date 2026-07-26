import type { AgentEvent } from '../types'

function isThoughtEvent(event: AgentEvent): boolean {
  return event.type === 'thought' || event.type === 'thinking'
}

/** Collapse token-level thought events into readable reasoning phases. */
export function collapseThoughtEvents(events: AgentEvent[]): string[] {
  const phases: string[] = []
  let current = ''
  let collecting = false

  const flush = () => {
    const content = current.trim()
    if (content) phases.push(content)
    current = ''
    collecting = false
  }

  for (const event of events) {
    if (isThoughtEvent(event)) {
      current += event.content
      collecting = true
    } else if (collecting) {
      flush()
    }
  }
  if (collecting) flush()
  return phases
}
