import { ref } from 'vue'
import type { VoiceCommandDef, VoiceCommandMatch, VoiceCommandResult } from '../types/voice'

const lastCommandResult = ref<VoiceCommandResult | null>(null)

const commandRegistry: VoiceCommandDef[] = []

function matchCommand(cmd: VoiceCommandDef, text: string): VoiceCommandMatch | null {
  const textLower = text.toLowerCase()
  const allPatterns = [...cmd.patternsZh, ...cmd.patternsEn]
  let bestScore = 0
  let extractedParams: Record<string, string> = {}

  for (const pattern of allPatterns) {
    if (typeof pattern === 'string') {
      const patLower = pattern.toLowerCase()
      if (textLower.includes(patLower)) {
        const score = Math.min(patLower.length / text.length + 0.3, 1.0)
        if (score > bestScore) {
          bestScore = score
        }
      }
    } else {
      const flags = pattern.flags.includes('i') ? pattern : new RegExp(pattern.source, pattern.flags + 'i')
      const m = text.match(flags)
      if (m) {
        const score = Math.min(m[0].length / text.length + 0.3, 1.0)
        if (score > bestScore) {
          bestScore = score
          extractedParams = (m as { groups?: Record<string, string> }).groups ?? {}
        }
      }
    }
  }

  if (bestScore < (cmd.threshold ?? 0.25)) return null

  return {
    commandId: cmd.id,
    label: cmd.label,
    score: bestScore,
    params: extractedParams,
  }
}

export function useVoiceRouter() {
  function registerCommands(defs: VoiceCommandDef[]) {
    commandRegistry.push(...defs)
    commandRegistry.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
  }

  function clearCommands() {
    commandRegistry.length = 0
  }

  function classifyIntent(text: string): VoiceCommandMatch | null {
    const trimmed = text.trim()
    if (!trimmed) return null

    let bestMatch: VoiceCommandMatch | null = null
    let bestScore = 0

    for (const cmd of commandRegistry) {
      const match = matchCommand(cmd, trimmed)
      if (match && match.score > bestScore) {
        bestScore = match.score
        bestMatch = match
      } else if (match && match.score === bestScore) {
        // Tie-break: prefer higher priority
        const currentPriority = commandRegistry.find(c => c.id === bestMatch!.commandId)?.priority ?? 0
        const newPriority = cmd.priority ?? 0
        if (newPriority > currentPriority) {
          bestMatch = match
        }
      }
    }

    return bestMatch
  }

  async function routeCommand(text: string): Promise<VoiceCommandResult> {
    const match = classifyIntent(text)

    if (match) {
      const cmd = commandRegistry.find(c => c.id === match.commandId)
      if (cmd?.handler) {
        const result: VoiceCommandResult = {
          type: 'command',
          commandId: match.commandId,
          label: match.label,
          success: false,
        }
        try {
          await cmd.handler(match.params, text)
          result.success = true
        } catch (err) {
          result.error = err instanceof Error ? err.message : String(err)
        }
        lastCommandResult.value = result
        return result
      }
    }

    const result: VoiceCommandResult = {
      type: 'chat',
      text,
      success: true,
    }
    lastCommandResult.value = result
    return result
  }

  return {
    lastCommandResult,
    registerCommands,
    clearCommands,
    classifyIntent,
    routeCommand,
  }
}
