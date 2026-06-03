import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useVoiceRouter } from '../../composables/useVoiceRouter'
import { registerTier1Commands } from '../../composables/voiceCommands/tier1-navigation'
import { useAppMode } from '../../composables/useAppMode'

describe('Tier 1: Navigation commands', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
    const { setMode, toggleAgentChat } = useAppMode()
    setMode('editor')
    toggleAgentChat(false)
    registerTier1Commands(router.registerCommands)
  })

  const cases: [string, string, string][] = [
    // [input, expectedCommandId, label]
    ['翻译模式', 'nav:translate', '翻译模式'],
    ['打开翻译', 'nav:translate', '翻译模式'],
    ['去翻译', 'nav:translate', '翻译模式'],
    ['编辑模式', 'nav:editor', '编辑模式'],
    ['打开编辑器', 'nav:editor', '编辑模式'],
    ['回到编辑', 'nav:editor', '编辑模式'],
    ['论证模式', 'nav:argument', '论证模式'],
    ['打开论证', 'nav:argument', '论证模式'],
    ['打开助手', 'nav:agent-chat', '打开助手'],
    ['打开AI', 'nav:agent-chat', '打开助手'],
    ['显示助手', 'nav:agent-chat', '打开助手'],
    ['关闭助手', 'nav:close-agent', '关闭助手'],
    ['关闭AI', 'nav:close-agent', '关闭助手'],
    ['思维导图', 'nav:mindmap', '思维导图'],
    ['打开导图', 'nav:mindmap', '思维导图'],
    ['切换主题', 'nav:theme', '切换主题'],
    ['深色模式', 'nav:theme', '切换主题'],
    ['浅色模式', 'nav:theme', '切换主题'],
    // English
    ['switch to translate', 'nav:translate', '翻译模式'],
    ['open editor', 'nav:editor', '编辑模式'],
    ['argument mode', 'nav:argument', '论证模式'],
    ['open assistant', 'nav:agent-chat', '打开助手'],
    ['close assistant', 'nav:close-agent', '关闭助手'],
    ['mind map', 'nav:mindmap', '思维导图'],
    ['toggle theme', 'nav:theme', '切换主题'],
    ['dark mode', 'nav:theme', '切换主题'],
  ]

  for (const [input, expectedId, _label] of cases) {
    it(`"${input}" → ${expectedId}`, () => {
      const match = router.classifyIntent(input)
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe(expectedId)
    })
  }

  it('nav:translate dispatches setMode("translate")', async () => {
    const { appMode } = useAppMode()
    await router.routeCommand('翻译模式')
    expect(appMode.value).toBe('translate')
  })

  it('nav:editor dispatches setMode("editor")', async () => {
    const { appMode, setMode } = useAppMode()
    setMode('translate')
    await router.routeCommand('编辑模式')
    expect(appMode.value).toBe('editor')
  })

  it('nav:argument dispatches setMode("argument")', async () => {
    const { appMode } = useAppMode()
    await router.routeCommand('论证模式')
    expect(appMode.value).toBe('argument')
  })

  it('nav:agent-chat opens agent panel', async () => {
    const { showAgentChat } = useAppMode()
    await router.routeCommand('打开助手')
    expect(showAgentChat.value).toBe(true)
  })

  it('nav:close-agent closes agent panel', async () => {
    const { showAgentChat, toggleAgentChat } = useAppMode()
    toggleAgentChat(true)
    await router.routeCommand('关闭助手')
    expect(showAgentChat.value).toBe(false)
  })

  it('no false positive: "翻译一下这段话" is not nav:translate', () => {
    // With default threshold 0.25, "翻译" in "翻译一下这段话" scores 2/8+0.3=0.55
    // But "翻译模式" won't match at all, and "打开翻译" won't match
    // The pattern "翻译模式" doesn't appear in "翻译一下这段话"
    // "打开翻译" doesn't appear either
    // So this should be null
    const match = router.classifyIntent('翻译一下这段话')
    // The pattern "打开翻译" won't match; "翻译模式" won't match
    // But if there's a bare "翻译" pattern, it would. Let's check:
    // Current patterns for nav:translate: ['翻译模式', '打开翻译', '切换翻译', '去翻译']
    // None of these are substrings of "翻译一下这段话" ... wait:
    // "去翻译" - no. "打开翻译" - no. "切换翻译" - no. "翻译模式" - no.
    // So this should be null
    expect(match).toBeNull()
  })
})
