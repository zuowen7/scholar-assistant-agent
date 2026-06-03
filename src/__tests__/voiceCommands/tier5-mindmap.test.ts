import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVoiceRouter } from '../../composables/useVoiceRouter'
import { registerTier5Commands } from '../../composables/voiceCommands/tier5-mindmap'

describe('Tier 5: MindMap commands', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
    registerTier5Commands(router.registerCommands)
  })

  const cases: [string, string][] = [
    ['添加节点', 'mindmap:add-node'],
    ['新建节点', 'mindmap:add-node'],
    ['删除节点', 'mindmap:delete-node'],
    ['删除导图节点', 'mindmap:delete-node'],
    ['AI扩展', 'mindmap:ai-expand'],
    ['扩展节点', 'mindmap:ai-expand'],
    ['AI扩展节点', 'mindmap:ai-expand'],
    ['自动布局', 'mindmap:layout'],
    ['布局导图', 'mindmap:layout'],
    ['重新布局', 'mindmap:layout'],
    ['保存导图', 'mindmap:save'],
    ['保存思维导图', 'mindmap:save'],
    ['分析导图', 'mindmap:analyze'],
    ['导图分析', 'mindmap:analyze'],
    ['放大', 'mindmap:zoom-in'],
    ['缩小', 'mindmap:zoom-out'],
    ['适应视图', 'mindmap:fit-view'],
    ['重置视图', 'mindmap:reset-view'],
    // English
    ['add node', 'mindmap:add-node'],
    ['delete node', 'mindmap:delete-node'],
    ['ai expand', 'mindmap:ai-expand'],
    ['auto layout', 'mindmap:layout'],
    ['save mindmap', 'mindmap:save'],
    ['analyze map', 'mindmap:analyze'],
    ['zoom in', 'mindmap:zoom-in'],
    ['zoom out', 'mindmap:zoom-out'],
    ['fit view', 'mindmap:fit-view'],
  ]

  for (const [input, expectedId] of cases) {
    it(`"${input}" → ${expectedId}`, () => {
      const match = router.classifyIntent(input)
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe(expectedId)
    })
  }

  it('mindmap:add-node dispatches voice-mindmap-command event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('添加节点')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-mindmap-command')
    expect(call).toBeDefined()
    expect((call![0] as CustomEvent).detail).toEqual({ action: 'add-child' })
    spy.mockRestore()
  })

  it('mindmap:delete-node dispatches voice-mindmap-command event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('删除节点')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-mindmap-command')
    expect(call).toBeDefined()
    expect((call![0] as CustomEvent).detail).toEqual({ action: 'delete-node' })
    spy.mockRestore()
  })

  it('mindmap:zoom-in dispatches voice-mindmap-command event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('放大')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-mindmap-command')
    expect(call).toBeDefined()
    expect((call![0] as CustomEvent).detail).toEqual({ action: 'zoom-in' })
    spy.mockRestore()
  })
})
