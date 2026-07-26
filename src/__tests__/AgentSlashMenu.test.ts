import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AgentSlashMenu from '../components/AgentSlashMenu.vue'
import type { AgentSlashCommand } from '../composables/useAgentSlashCommands'

const items: AgentSlashCommand[] = [
  {
    id: 'preset-review',
    command: '/review',
    kind: 'preset',
    label: '投稿前审阅',
    description: '检查论证与证据',
    prompt: 'Review',
  },
  {
    id: 'skill-nature-reviewer',
    command: '/nature-reviewer',
    kind: 'skill',
    label: 'Nature 模拟审稿',
    description: '严格审稿流程',
    prompt: 'Nature review',
    skillName: 'nature_reviewer',
    selected: true,
  },
]

function mountMenu(overrides: Partial<InstanceType<typeof AgentSlashMenu>['$props']> = {}) {
  return mount(AgentSlashMenu, {
    props: {
      items,
      activeIndex: 0,
      menuLabel: '命令与能力',
      loadingLabel: '正在加载',
      emptyLabel: '没有匹配项',
      presetLabel: '预设指令',
      skillLabel: 'Agent Skills',
      selectedLabel: '已启用',
      ...overrides,
    },
  })
}

describe('AgentSlashMenu', () => {
  it('separates preset instructions from dynamic skills and exposes selection state', () => {
    const wrapper = mountMenu()

    expect(wrapper.text()).toContain('预设指令')
    expect(wrapper.text()).toContain('Agent Skills')
    expect(wrapper.text()).toContain('/review')
    expect(wrapper.text()).toContain('/nature-reviewer')
    expect(wrapper.text()).toContain('已启用')
    expect(wrapper.find('[role="option"]').attributes('aria-selected')).toBe('true')
  })

  it('selects on pointer down without taking focus from the composer', async () => {
    const wrapper = mountMenu()
    await wrapper.findAll('[role="option"]')[1].trigger('pointerdown')

    expect(wrapper.emitted('select')?.[0]).toEqual([items[1]])
  })

  it('shows a directional empty state', () => {
    const wrapper = mountMenu({ items: [] })
    expect(wrapper.text()).toContain('没有匹配项')
  })
})
