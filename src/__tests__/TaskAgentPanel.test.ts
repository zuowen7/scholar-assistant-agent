import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

const startNewWorkflow = vi.fn()
const sendMessage = vi.fn()
const messages = ref([
  { id: 'u1', role: 'user', content: 'Check this section', events: [], isStreaming: false, timestamp: 1 },
  {
    id: 'a1', role: 'assistant', content: 'I found one issue.', isStreaming: false, timestamp: 2,
    events: [
      { type: 'tool_call', content: '', metadata: { tool_name: 'read_file' } },
      { type: 'tool_result', content: 'ok', metadata: { tool_name: 'read_file' } },
    ],
  },
] as any[])

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => params ? `${key}:${Object.values(params).join(',')}` : key }),
  createI18n: () => ({ global: { locale: { value: 'zh-CN' }, t: (key: string) => key }, install: vi.fn() }),
}))
vi.mock('../composables/useAgentChat', () => ({
  useAgentChat: () => ({
    messages,
    sending: ref(false),
    pendingApproval: ref(null),
    sendMessage,
    sendApproval: vi.fn(),
    startNewWorkflow,
  }),
}))
vi.mock('../composables/useFileTree', () => ({
  useFileTree: () => ({ rootDir: ref('D:/papers/project'), refresh: vi.fn() }),
}))
vi.mock('../composables/useEditor', () => ({
  useEditor: () => ({ reloadOpenTabs: vi.fn() }),
}))

import TaskAgentPanel from '../components/TaskAgentPanel.vue'

describe('TaskAgentPanel workspace flow', () => {
  beforeEach(() => vi.clearAllMocks())

  it('keeps file context, conversation, and tool activity in the writing dock', () => {
    const wrapper = mount(TaskAgentPanel, {
      props: { context: 'whole document', selection: 'selected paragraph', activeFile: 'D:/papers/project/draft.md' },
    })

    expect(wrapper.get('[data-testid="agent-context-ledger"]').text()).toContain('draft.md')
    expect(wrapper.get('[data-testid="agent-context-ledger"]').text()).toContain('taskAgent.selectionScope')
    expect(wrapper.get('[data-testid="agent-conversation"]').text()).toContain('Check this section')
    expect(wrapper.get('[data-testid="agent-conversation"]').text()).toContain('I found one issue.')
    expect(wrapper.get('[data-testid="agent-conversation"]').text()).toContain('taskAgent.tools.readFile')
  })

  it('starts a fresh Agent workflow from the dock header', async () => {
    const wrapper = mount(TaskAgentPanel, { props: { context: '', activeFile: 'draft.md' } })
    await wrapper.get('[data-testid="agent-new-task"]').trigger('click')
    expect(startNewWorkflow).toHaveBeenCalledTimes(1)
  })
})
