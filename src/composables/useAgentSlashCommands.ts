import type { AgentSkill } from '../types'

export type AgentSlashCommandKind = 'preset' | 'skill'

export interface AgentSlashCommand {
  id: string
  command: string
  kind: AgentSlashCommandKind
  label: string
  description: string
  prompt: string
  skillName?: string
  selected?: boolean
}

export interface AgentSlashInvocation {
  command: string
  argument: string
}

export function skillSlashCommand(skill: AgentSkill): string {
  return `/${skill.name.trim().toLocaleLowerCase().replaceAll('_', '-')}`
}

export function parseAgentSlashInvocation(value: string): AgentSlashInvocation | null {
  const match = value.trim().match(/^\/([a-z0-9][a-z0-9_-]*)(?:\s+([\s\S]*))?$/i)
  if (!match) return null
  return {
    command: `/${match[1].toLocaleLowerCase().replaceAll('_', '-')}`,
    argument: match[2]?.trim() || '',
  }
}

export function filterAgentSlashCommands(
  items: AgentSlashCommand[],
  query: string,
  limit = 10,
): AgentSlashCommand[] {
  const needle = query.trim().toLocaleLowerCase().replace(/^\/+/, '')
  if (!needle) return items.slice(0, limit)

  return items
    .map((item, index) => {
      const command = item.command.slice(1).toLocaleLowerCase()
      const label = item.label.toLocaleLowerCase()
      const description = item.description.toLocaleLowerCase()
      const exact = command === needle
      const prefix = command.startsWith(needle)
      const labelPrefix = label.startsWith(needle)
      const contains =
        command.includes(needle) || label.includes(needle) || description.includes(needle)
      return {
        item,
        index,
        score: exact ? 0 : prefix ? 1 : labelPrefix ? 2 : contains ? 3 : Number.POSITIVE_INFINITY,
      }
    })
    .filter((entry) => Number.isFinite(entry.score))
    .sort((a, b) => {
      const kindOrder = (a.item.kind === 'preset' ? 0 : 1) - (b.item.kind === 'preset' ? 0 : 1)
      return kindOrder || a.score - b.score || a.index - b.index
    })
    .slice(0, limit)
    .map((entry) => entry.item)
}
