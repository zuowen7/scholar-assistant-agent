import { describe, expect, it } from 'vitest'
import {
  filterAgentSlashCommands,
  parseAgentSlashInvocation,
  skillSlashCommand,
  type AgentSlashCommand,
} from '../composables/useAgentSlashCommands'
import type { AgentSkill } from '../types'

const commands: AgentSlashCommand[] = [
  {
    id: 'preset-review',
    command: '/review',
    kind: 'preset',
    label: '投稿前审阅',
    description: '检查方法和证据',
    prompt: 'Review the paper.',
  },
  {
    id: 'skill-paper-review',
    command: '/paper-review',
    kind: 'skill',
    label: 'Systematic paper review',
    description: 'Review methodology',
    prompt: 'Use the review skill.',
    skillName: 'paper_review',
  },
  {
    id: 'preset-polish',
    command: '/polish',
    kind: 'preset',
    label: '学术润色',
    description: '改进表达',
    prompt: 'Polish the selection.',
  },
]

describe('agent slash commands', () => {
  it('turns dynamic Agent V2 skill names into stable slash commands', () => {
    const skill: AgentSkill = {
      name: 'nature_reviewer',
      description: 'Review',
      layer: 'agents',
      category: 'nature',
      active: false,
      default_active: false,
    }

    expect(skillSlashCommand(skill)).toBe('/nature-reviewer')
  })

  it('prioritizes command prefixes and also searches localized labels', () => {
    expect(filterAgentSlashCommands(commands, 'rev').map((item) => item.command)).toEqual([
      '/review',
      '/paper-review',
    ])
    expect(filterAgentSlashCommands(commands, '润色').map((item) => item.command)).toEqual([
      '/polish',
    ])
  })

  it('parses direct invocations with optional arguments and normalizes underscores', () => {
    expect(parseAgentSlashInvocation('/paper_review 方法章节')).toEqual({
      command: '/paper-review',
      argument: '方法章节',
    })
    expect(parseAgentSlashInvocation('plain task')).toBeNull()
  })
})
