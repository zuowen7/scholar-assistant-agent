import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVoiceRouter } from '../../composables/useVoiceRouter'
import { registerTier2Commands } from '../../composables/voiceCommands/tier2-file'

describe('Tier 2: File commands', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
    registerTier2Commands(router.registerCommands)
  })

  const cases: [string, string][] = [
    ['保存', 'file:save'],
    ['保存文件', 'file:save'],
    ['存盘', 'file:save'],
    ['新建文件', 'file:new'],
    ['新建文档', 'file:new'],
    ['创建文件', 'file:new'],
    ['打开文件夹', 'file:open-folder'],
    ['打开目录', 'file:open-folder'],
    ['打开项目', 'file:open-folder'],
    // English
    ['save file', 'file:save'],
    ['save', 'file:save'],
    ['new file', 'file:new'],
    ['new document', 'file:new'],
    ['open folder', 'file:open-folder'],
    ['open project', 'file:open-folder'],
  ]

  for (const [input, expectedId] of cases) {
    it(`"${input}" → ${expectedId}`, () => {
      const match = router.classifyIntent(input)
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe(expectedId)
    })
  }

  it('file:save dispatches CustomEvent', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('保存')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-save' }))
    spy.mockRestore()
  })

  it('file:open-folder dispatches CustomEvent', async () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    await router.routeCommand('打开文件夹')
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'voice-open-folder' }))
    spy.mockRestore()
  })
})
