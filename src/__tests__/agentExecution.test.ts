import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, number | string>) => {
      if (key === 'agent.execution.title') return '执行过程'
      if (key === 'agent.execution.completed') return `已完成 · ${params?.count} 步`
      if (key === 'agent.execution.failed')
        return `共 ${params?.count} 步 · ${params?.failed} 步失败`
      if (key === 'agent.execution.readFile') return `读取 ${params?.target}`
      if (key === 'agent.execution.editFile') return `修改 ${params?.target}`
      return key
    },
  }),
}))

import AgentExecutionGroup from '../components/AgentExecutionGroup.vue'
import type { AgentEvent } from '../types'
import { buildExecutionSteps, executionSummary, hasPendingApproval } from '../utils/agentExecution'

describe('agent execution presentation', () => {
  const events: AgentEvent[] = [
    {
      type: 'tool_call',
      content: 'read_file',
      event_id: 'read-1',
      metadata: { tool_name: 'read_file', args: { file_path: 'draft/main.md' } },
    },
    {
      type: 'tool_result',
      content: '# manuscript',
      event_id: 'read-1',
      metadata: { tool_name: 'read_file' },
    },
    {
      type: 'tool_call',
      content: 'str_replace',
      event_id: 'edit-1',
      metadata: { tool_name: 'str_replace', args: { file_path: 'draft/main.md' } },
    },
    {
      type: 'tool_result',
      content: 'selection mismatch',
      event_id: 'edit-1',
      metadata: { tool_name: 'str_replace', error: true },
    },
  ]

  it('pairs calls and results into compact steps', () => {
    const steps = buildExecutionSteps(events)

    expect(steps).toHaveLength(2)
    expect(steps[0]).toMatchObject({
      id: 'read-1',
      toolName: 'read_file',
      status: 'success',
    })
    expect(steps[1]).toMatchObject({
      id: 'edit-1',
      toolName: 'str_replace',
      status: 'error',
      result: 'selection mismatch',
    })
  })

  it('summarizes counts without exposing raw tool payloads', () => {
    expect(executionSummary(buildExecutionSteps(events))).toEqual({
      total: 2,
      completed: 1,
      failed: 1,
      running: 0,
    })
  })

  it('keeps successful execution collapsed and opens failures for attention', async () => {
    const wrapper = mount(AgentExecutionGroup, {
      props: { events: events.slice(0, 2), streaming: false },
    })

    expect(wrapper.find('.execution-group').attributes('open')).toBeUndefined()
    expect(wrapper.find('.execution-group > summary').text()).toContain('已完成 · 1 步')

    await wrapper.setProps({ events })

    expect(wrapper.find('.execution-group').attributes('open')).toBeDefined()
    expect(wrapper.find('.execution-group > summary').text()).toContain('1 步失败')
  })

  it('carries the fuller result_detail for the expanded view', () => {
    const longResult = 'x'.repeat(500)
    const resultEvents: AgentEvent[] = [
      {
        type: 'tool_call',
        content: 'read_file',
        event_id: 'r1',
        metadata: { tool_name: 'read_file' },
      },
      {
        type: 'tool_result',
        content: longResult.slice(0, 200),
        event_id: 'r1',
        metadata: { tool_name: 'read_file', result_detail: longResult },
      },
    ]
    const steps = buildExecutionSteps(resultEvents)
    expect(steps[0].result).toBe(longResult.slice(0, 200))
    expect(steps[0].resultDetail).toBe(longResult)
  })

  it('only treats unmatched approvals as pending attention', () => {
    const settled: AgentEvent[] = [
      {
        type: 'await_approval',
        content: '',
        event_id: 'ap-1',
        metadata: { tool_name: 'write_file' },
      },
      { type: 'approval_received', content: '', event_id: 'ap-1' },
    ]
    const pending: AgentEvent[] = [
      {
        type: 'await_approval',
        content: '',
        event_id: 'ap-2',
        metadata: { tool_name: 'write_file' },
      },
    ]
    expect(hasPendingApproval(settled)).toBe(false)
    expect(hasPendingApproval(pending)).toBe(true)
    expect(hasPendingApproval([...settled, ...pending])).toBe(true)
  })
})
