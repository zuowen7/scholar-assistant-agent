import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, number>) => {
      if (key === 'agent.thoughtProcess') return '思考过程'
      if (key === 'agent.thinkingCompact') return '思考中'
      if (key === 'agent.thoughtPhases') return `${params?.count} 个阶段`
      return key
    },
  }),
}))

import AgentThoughtGroup from '../components/AgentThoughtGroup.vue'
import { collapseThoughtEvents } from '../utils/agentThoughts'
import type { AgentEvent } from '../types'

describe('collapseThoughtEvents', () => {
  it('merges streaming fragments and separates distinct reasoning phases', () => {
    const events: AgentEvent[] = [
      { type: 'thought', content: '先读取', metadata: {} },
      { type: 'thought', content: '当前选区。', metadata: {} },
      { type: 'tool_call', content: 'read_file', metadata: { tool_name: 'read_file' } },
      { type: 'thinking', content: '再生成', metadata: {} },
      { type: 'thinking', content: '修改建议。', metadata: {} },
      { type: 'thought', content: '   ', metadata: {} },
    ]

    expect(collapseThoughtEvents(events)).toEqual(['先读取当前选区。', '再生成修改建议。'])
  })

  it('returns no visible phase for empty thought fragments', () => {
    expect(
      collapseThoughtEvents([
        { type: 'thought', content: '', metadata: {} },
        { type: 'thinking', content: '  ', metadata: {} },
      ]),
    ).toEqual([])
  })
})

describe('AgentThoughtGroup', () => {
  it('renders all reasoning as one compact group that is collapsed by default', () => {
    const wrapper = mount(AgentThoughtGroup, {
      props: {
        events: [
          { type: 'thought', content: '读取材料。', metadata: {} },
          { type: 'tool_call', content: 'read_file', metadata: { tool_name: 'read_file' } },
          { type: 'thought', content: '生成修改。', metadata: {} },
        ],
        streaming: false,
      },
    })

    expect(wrapper.findAll('details')).toHaveLength(1)
    expect(wrapper.find('details').attributes('open')).toBeUndefined()
    expect(wrapper.find('summary').text()).toContain('思考过程')
    expect(wrapper.find('summary').text()).toContain('2 个阶段')
    expect(wrapper.findAll('.thought-details p')).toHaveLength(2)
  })
})
