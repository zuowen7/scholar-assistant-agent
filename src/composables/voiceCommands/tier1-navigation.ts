import type { VoiceCommandDef } from '../../types/voice'
import { useAppMode } from '../useAppMode'

export function registerTier1Commands(register: (defs: VoiceCommandDef[]) => void) {
  register([
    {
      id: 'nav:translate',
      label: { zh: '翻译模式', en: 'Translation mode' },
      patternsZh: ['翻译模式', '打开翻译', '切换翻译', '去翻译'],
      patternsEn: ['translate mode', 'switch to translate', 'open translate', 'go to translate'],
      priority: 10,
      handler: async () => {
        useAppMode().setMode('translate')
      },
    },
    {
      id: 'nav:editor',
      label: { zh: '编辑模式', en: 'Editor mode' },
      patternsZh: ['编辑模式', '打开编辑器', '切换编辑', '去编辑器', '回到编辑'],
      patternsEn: ['editor mode', 'switch to editor', 'open editor', 'go to editor'],
      priority: 10,
      handler: async () => {
        useAppMode().setMode('editor')
      },
    },
    {
      id: 'nav:argument',
      label: { zh: '论证模式', en: 'Argument mode' },
      patternsZh: ['论证模式', '打开论证', '切换论证', '去论证'],
      patternsEn: ['argument mode', 'switch to argument', 'open argument'],
      priority: 10,
      handler: async () => {
        useAppMode().setMode('argument')
      },
    },
    {
      id: 'nav:agent-chat',
      label: { zh: '打开助手', en: 'Open assistant' },
      patternsZh: ['打开助手', '打开AI', '打开agent', '打开面板', '显示助手', '显示面板'],
      patternsEn: ['open assistant', 'open agent', 'show assistant', 'show panel', 'open chat'],
      priority: 9,
      handler: async () => {
        useAppMode().toggleAgentChat(true)
      },
    },
    {
      id: 'nav:close-agent',
      label: { zh: '关闭助手', en: 'Close assistant' },
      patternsZh: ['关闭助手', '关闭AI', '关闭agent', '关闭面板', '隐藏助手'],
      patternsEn: ['close assistant', 'close agent', 'close panel', 'hide assistant'],
      priority: 9,
      handler: async () => {
        useAppMode().toggleAgentChat(false)
      },
    },
    {
      id: 'nav:mindmap',
      label: { zh: '思维导图', en: 'Mind map' },
      patternsZh: ['思维导图', '打开导图', '打开脑图', '切换导图'],
      patternsEn: ['mind map', 'open mindmap', 'switch to mindmap'],
      priority: 9,
      handler: async () => {
        useAppMode().setMode('editor')
        window.dispatchEvent(new CustomEvent('voice-set-mindmap'))
      },
    },
    {
      id: 'nav:theme',
      label: { zh: '切换主题', en: 'Toggle theme' },
      patternsZh: ['切换主题', '换主题', '深色模式', '浅色模式', '暗色模式', '亮色模式', '夜间模式', '日间模式'],
      patternsEn: ['toggle theme', 'switch theme', 'dark mode', 'light mode', 'night mode'],
      priority: 8,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-toggle-theme'))
      },
    },
  ])
}
