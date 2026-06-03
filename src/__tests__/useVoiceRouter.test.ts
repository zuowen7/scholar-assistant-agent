import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { VoiceCommandDef } from '../types/voice'

// Import will fail until useVoiceRouter.ts is created — that's RED phase
import { useVoiceRouter } from '../composables/useVoiceRouter'

function makeCmd(overrides: Partial<VoiceCommandDef> & { id: string }): VoiceCommandDef {
  return {
    label: { zh: overrides.id, en: overrides.id },
    patternsZh: [],
    patternsEn: [],
    handler: vi.fn(async () => {}),
    ...overrides,
  }
}

describe('useVoiceRouter', () => {
  let router: ReturnType<typeof useVoiceRouter>

  beforeEach(() => {
    router = useVoiceRouter()
    router.clearCommands()
  })

  // ── classifyIntent ─────────────────────────────────────────────

  describe('classifyIntent', () => {
    it('matches Chinese keyword pattern', () => {
      router.registerCommands([
        makeCmd({ id: 'nav:translate', patternsZh: ['翻译模式', '打开翻译'] }),
      ])
      const match = router.classifyIntent('打开翻译')
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe('nav:translate')
    })

    it('matches English keyword pattern', () => {
      router.registerCommands([
        makeCmd({ id: 'nav:editor', patternsEn: ['editor mode', 'open editor'] }),
      ])
      const match = router.classifyIntent('switch to editor mode')
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe('nav:editor')
    })

    it('matches mixed Chinese patterns for polish', () => {
      router.registerCommands([
        makeCmd({ id: 'editor:polish', patternsZh: ['润色', '优化文字'] }),
      ])
      const match = router.classifyIntent('帮我润色这段文字')
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe('editor:polish')
    })

    it('returns null for non-command text', () => {
      router.registerCommands([
        makeCmd({ id: 'nav:translate', patternsZh: ['翻译模式', '打开翻译'] }),
        makeCmd({ id: 'editor:polish', patternsZh: ['润色'] }),
      ])
      expect(router.classifyIntent('随便聊聊天气')).toBeNull()
      expect(router.classifyIntent('量子计算的最新进展是什么')).toBeNull()
    })

    it('returns null for empty input', () => {
      router.registerCommands([
        makeCmd({ id: 'nav:translate', patternsZh: ['翻译模式'] }),
      ])
      expect(router.classifyIntent('')).toBeNull()
      expect(router.classifyIntent('   ')).toBeNull()
    })

    it('extracts params from RegExp named groups', () => {
      router.registerCommands([
        makeCmd({
          id: 'editor:translate',
          patternsZh: [/翻译成(?<target>英文|中文)/],
        }),
      ])
      const match = router.classifyIntent('翻译成英文')
      expect(match).not.toBeNull()
      expect(match!.params.target).toBe('英文')
    })

    it('picks highest-scoring match across commands', () => {
      router.registerCommands([
        makeCmd({ id: 'a', patternsZh: ['打开'], priority: 0 }),
        makeCmd({ id: 'b', patternsZh: ['打开翻译'], priority: 0 }),
      ])
      const match = router.classifyIntent('打开翻译')
      expect(match!.commandId).toBe('b')
    })

    it('respects priority for equal scores', () => {
      router.registerCommands([
        makeCmd({ id: 'low', patternsZh: ['翻译'], priority: 1 }),
        makeCmd({ id: 'high', patternsZh: ['翻译'], priority: 10 }),
      ])
      const match = router.classifyIntent('翻译')
      expect(match!.commandId).toBe('high')
    })

    it('rejects matches below threshold', () => {
      router.registerCommands([
        makeCmd({
          id: 'strict',
          patternsZh: ['翻译模式'],
          threshold: 0.9, // very high threshold
        }),
      ])
      // "帮我翻译模式" — the keyword is a small fraction
      const match = router.classifyIntent('请帮我切换到翻译模式好吗')
      expect(match).toBeNull()
    })

    it('case insensitive matching', () => {
      router.registerCommands([
        makeCmd({ id: 'x', patternsEn: ['Export PDF'] }),
      ])
      const match = router.classifyIntent('export pdf')
      expect(match).not.toBeNull()
      expect(match!.commandId).toBe('x')
    })

    it('no false positive: translate verb vs translate mode', () => {
      router.registerCommands([
        makeCmd({
          id: 'nav:translate',
          patternsZh: ['翻译模式', '打开翻译'],
          threshold: 0.35,
        }),
      ])
      // "翻译一下这段话" — 翻译 is a verb here, not a mode switch
      const match = router.classifyIntent('翻译一下这段话')
      // This should be null or low-confidence depending on threshold
      expect(match).toBeNull()
    })
  })

  // ── routeCommand ───────────────────────────────────────────────

  describe('routeCommand', () => {
    it('dispatches handler when command matched', async () => {
      const handler = vi.fn(async () => {})
      router.registerCommands([
        makeCmd({ id: 'nav:translate', patternsZh: ['打开翻译'], handler }),
      ])
      const result = await router.routeCommand('打开翻译')
      expect(result.type).toBe('command')
      expect(result.commandId).toBe('nav:translate')
      expect(result.success).toBe(true)
      expect(handler).toHaveBeenCalledOnce()
    })

    it('returns chat fallback when no command matches', async () => {
      router.registerCommands([
        makeCmd({ id: 'nav:translate', patternsZh: ['打开翻译'] }),
      ])
      const result = await router.routeCommand('随便聊聊')
      expect(result.type).toBe('chat')
      expect(result.text).toBe('随便聊聊')
      expect(result.success).toBe(true)
    })

    it('captures handler error in result.error', async () => {
      router.registerCommands([
        makeCmd({
          id: 'fail:cmd',
          patternsZh: ['触发错误'],
          handler: async () => { throw new Error('boom') },
        }),
      ])
      const result = await router.routeCommand('触发错误')
      expect(result.type).toBe('command')
      expect(result.success).toBe(false)
      expect(result.error).toBe('boom')
    })

    it('updates lastCommandResult ref', async () => {
      router.registerCommands([
        makeCmd({ id: 'nav:editor', patternsZh: ['编辑模式'] }),
      ])
      await router.routeCommand('编辑模式')
      expect(router.lastCommandResult.value).not.toBeNull()
      expect(router.lastCommandResult.value!.type).toBe('command')
      expect(router.lastCommandResult.value!.commandId).toBe('nav:editor')
    })

    it('passes raw text to handler', async () => {
      const handler = vi.fn(async () => {})
      router.registerCommands([
        makeCmd({ id: 'x', patternsZh: ['测试'], handler }),
      ])
      await router.routeCommand('测试一下')
      expect(handler).toHaveBeenCalledWith({}, '测试一下')
    })

    it('passes extracted params to handler', async () => {
      const handler = vi.fn(async () => {})
      router.registerCommands([
        makeCmd({
          id: 'export',
          patternsZh: [/导出(?<format>PDF|Word|LaTeX)/],
          handler,
        }),
      ])
      await router.routeCommand('导出PDF')
      expect(handler).toHaveBeenCalledWith({ format: 'PDF' }, '导出PDF')
    })
  })

  // ── registerCommands ───────────────────────────────────────────

  describe('registerCommands', () => {
    it('sorts commands by priority descending', () => {
      router.registerCommands([
        makeCmd({ id: 'low', patternsZh: ['test'], priority: 1 }),
        makeCmd({ id: 'high', patternsZh: ['test'], priority: 10 }),
        makeCmd({ id: 'mid', patternsZh: ['test'], priority: 5 }),
      ])
      // Match "test" — highest priority should win
      const match = router.classifyIntent('test')
      expect(match!.commandId).toBe('high')
    })
  })
})
