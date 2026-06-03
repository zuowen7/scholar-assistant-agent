import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVoiceRouter } from '../../composables/useVoiceRouter'
import { registerTier4Commands } from '../../composables/voiceCommands/tier4-translation'

describe('Tier 4: Translation commands', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
    registerTier4Commands(router.registerCommands)
  })

  const cases: [string, string][] = [
    ['开始翻译', 'translate:new'],
    ['翻译文件', 'translate:new'],
    ['新翻译', 'translate:new'],
    ['上传翻译', 'translate:new'],
    ['重试翻译', 'translate:retry'],
    ['重试失败', 'translate:retry'],
    ['导出双语Word', 'translate:export-bilingual-docx'],
    ['导出双语文档', 'translate:export-bilingual-docx'],
    ['导出译文文档', 'translate:export-translation-docx'],
    ['导出译文Word', 'translate:export-translation-docx'],
    ['导出PPTX', 'translate:export-pptx'],
    ['导出PPT', 'translate:export-pptx'],
    ['导出双语Markdown', 'translate:export-bilingual-md'],
    ['导出译文Markdown', 'translate:export-translation-md'],
    // English
    ['start translation', 'translate:new'],
    ['translate file', 'translate:new'],
    ['retry translation', 'translate:retry'],
    ['export bilingual', 'translate:export-bilingual-docx'],
    ['export pptx', 'translate:export-pptx'],
  ]

  for (const [input, expectedId] of cases) {
    it(`"${input}" → ${expectedId}`, () => {
      const match = router.classifyIntent(input)
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe(expectedId)
    })
  }

  it('translate:new dispatches voice-translate-new event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('开始翻译')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-translate-new' }))
    spy.mockRestore()
  })

  it('translate:retry dispatches voice-translate-retry event', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('重试翻译')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-translate-retry' }))
    spy.mockRestore()
  })

  it('translate:export-bilingual-docx dispatches voice-translate-export event with format', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('导出双语Word')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-translate-export')
    expect(call).toBeDefined()
    expect((call![0] as CustomEvent).detail).toEqual({ format: 'bilingual-docx' })
    spy.mockRestore()
  })

  it('translate:export-pptx dispatches voice-translate-export event with format', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('导出PPTX')
    const call = spy.mock.calls.find(c => (c[0] as CustomEvent).type === 'voice-translate-export')
    expect(call).toBeDefined()
    expect((call![0] as CustomEvent).detail).toEqual({ format: 'pptx' })
    spy.mockRestore()
  })
})
