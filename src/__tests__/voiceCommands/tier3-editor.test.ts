import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVoiceRouter } from '../../composables/useVoiceRouter'
import { registerTier3Commands } from '../../composables/voiceCommands/tier3-editor'

describe('Tier 3: Editor commands', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
    registerTier3Commands(router.registerCommands)
  })

  const cases: [string, string][] = [
    ['导出Word', 'editor:export-word'],
    ['导出word', 'editor:export-word'],
    ['导出文档', 'editor:export-word'],
    ['导出PDF', 'editor:export-pdf'],
    ['导出pdf', 'editor:export-pdf'],
    ['导出LaTeX', 'editor:export-latex'],
    ['导出latex', 'editor:export-latex'],
    ['润色', 'editor:polish'],
    ['润色一下', 'editor:polish'],
    ['帮我润色', 'editor:polish'],
    ['优化文字', 'editor:polish'],
    ['扩写', 'editor:expand'],
    ['扩展', 'editor:expand'],
    ['展开', 'editor:expand'],
    ['补充内容', 'editor:expand'],
    ['审阅', 'editor:review'],
    ['审查', 'editor:review'],
    ['检查文本', 'editor:review'],
    ['翻译成英文', 'editor:translate-en'],
    ['翻译成英语', 'editor:translate-en'],
    ['翻译成中文', 'editor:translate-zh'],
    ['译成中文', 'editor:translate-zh'],
    ['合规检查', 'editor:compliance'],
    ['处理引用', 'editor:citations'],
    ['整理引用', 'editor:citations'],
    // English
    ['export word', 'editor:export-word'],
    ['export pdf', 'editor:export-pdf'],
    ['export latex', 'editor:export-latex'],
    ['polish', 'editor:polish'],
    ['polish text', 'editor:polish'],
    ['expand', 'editor:expand'],
    ['expand text', 'editor:expand'],
    ['review', 'editor:review'],
    ['review text', 'editor:review'],
    ['translate to english', 'editor:translate-en'],
    ['translate to chinese', 'editor:translate-zh'],
    ['compliance check', 'editor:compliance'],
    ['process citations', 'editor:citations'],
  ]

  for (const [input, expectedId] of cases) {
    it(`"${input}" → ${expectedId}`, () => {
      const match = router.classifyIntent(input)
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe(expectedId)
    })
  }

  it('editor:export-pdf dispatches voice-export event with format', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('导出PDF')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-export')
    expect(call).toBeDefined()
    const evt = call![0] as CustomEvent
    expect(evt.detail).toEqual({ format: 'pdf' })
    spy.mockRestore()
  })

  it('editor:polish dispatches voice-ai-preset event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('润色')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-ai-preset')
    expect(call).toBeDefined()
    const evt = call![0] as CustomEvent
    expect(evt.detail).toEqual({ action: 'polish' })
    spy.mockRestore()
  })

  it('editor:compliance dispatches voice-compliance event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('合规检查')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-compliance' }))
    spy.mockRestore()
  })

  it('editor:citations dispatches voice-citations event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('处理引用')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-citations' }))
    spy.mockRestore()
  })
})
