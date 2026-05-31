import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'agent.allowOnce': '仅此一次',
        'agent.allowSession': '本次会话',
        'agent.confirmEach': '每次都需确认',
        'general.no': '否',
        'general.yes': '是',
      }
      return map[key] || key
    },
    locale: { value: 'zh-CN' },
  }),
  createI18n: () => ({}),
}))

import AgentApprovalInline from '../components/AgentApprovalInline.vue'

describe('AgentApprovalInline', () => {
  const basePending = {
    event_id: 'evt_1',
    tool_name: 'write_file',
    args: { file_path: 'draft.md' },
    risk: 'destructive',
    reason: 'SmartPause: write_file may overwrite existing file',
  }

  it('shows session approval button for ordinary approvals', () => {
    const wrapper = mount(AgentApprovalInline, {
      props: { pending: basePending },
    })
    expect(wrapper.text()).toContain('本次会话')
  })

  it('shows force-approval hint for force approvals', () => {
    const wrapper = mount(AgentApprovalInline, {
      props: {
        pending: { ...basePending, force_approval: true },
      },
    })
    expect(wrapper.text()).not.toContain('本次会话')
    expect(wrapper.text()).toContain('每次都需确认')
  })
})
