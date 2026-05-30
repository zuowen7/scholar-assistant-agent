import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgentApprovalInline from '../components/AgentApprovalInline.vue'

describe('AgentApprovalInline', () => {
  const basePending = {
    event_id: 'evt_1',
    tool_name: 'write_file',
    args: { file_path: 'draft.md' },
    risk: 'destructive',
    reason: 'SmartPause: write_file may overwrite existing file',
  }

  it('shows session approval for ordinary approvals', () => {
    const wrapper = mount(AgentApprovalInline, {
      props: { pending: basePending },
    })
    expect(wrapper.text()).toContain('本次会话')
  })

  it('hides session approval for force approvals', () => {
    const wrapper = mount(AgentApprovalInline, {
      props: {
        pending: {
          ...basePending,
          force_approval: true,
        },
      },
    })

    expect(wrapper.text()).not.toContain('本次会话')
    expect(wrapper.text()).toContain('每次都需确认')
  })
})
