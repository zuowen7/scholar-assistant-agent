import type { VoiceCommandDef } from '../../types/voice'

export function registerTier3Commands(register: (defs: VoiceCommandDef[]) => void) {
  register([
    {
      id: 'editor:export-word',
      label: { zh: '导出Word', en: 'Export Word' },
      patternsZh: ['导出word', '导出文档', '导出docx'],
      patternsEn: ['export word', 'export docx', 'export document'],
      priority: 6,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-export', { detail: { format: 'word' } }))
      },
    },
    {
      id: 'editor:export-pdf',
      label: { zh: '导出PDF', en: 'Export PDF' },
      patternsZh: ['导出pdf', '导出文件'],
      patternsEn: ['export pdf', 'export to pdf'],
      priority: 6,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-export', { detail: { format: 'pdf' } }))
      },
    },
    {
      id: 'editor:export-latex',
      label: { zh: '导出LaTeX', en: 'Export LaTeX' },
      patternsZh: ['导出latex', '导出tex'],
      patternsEn: ['export latex', 'export tex'],
      priority: 6,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-export', { detail: { format: 'latex' } }))
      },
    },
    {
      id: 'editor:polish',
      label: { zh: '润色文本', en: 'Polish text' },
      patternsZh: ['润色', '润色一下', '帮我润色', '优化文字', '修改文字'],
      patternsEn: ['polish', 'polish text', 'refine text'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-ai-preset', { detail: { action: 'polish' } }))
      },
    },
    {
      id: 'editor:expand',
      label: { zh: '扩写文本', en: 'Expand text' },
      patternsZh: ['扩写', '扩展', '展开', '扩展一下', '补充内容', '帮我扩展'],
      patternsEn: ['expand', 'expand text', 'elaborate'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-ai-preset', { detail: { action: 'expand' } }))
      },
    },
    {
      id: 'editor:review',
      label: { zh: '审阅文本', en: 'Review text' },
      patternsZh: ['审阅', '审查', '帮我审阅', '检查文本'],
      patternsEn: ['review', 'review text', 'critique text'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-ai-preset', { detail: { action: 'review' } }))
      },
    },
    {
      id: 'editor:translate-en',
      label: { zh: '翻译成英文', en: 'Translate to English' },
      patternsZh: ['翻译成英文', '翻译成英语', '译成英文', '翻成英文', '英文翻译'],
      patternsEn: ['translate to english', 'translate into english'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-ai-preset', { detail: { action: 'en' } }))
      },
    },
    {
      id: 'editor:translate-zh',
      label: { zh: '翻译成中文', en: 'Translate to Chinese' },
      patternsZh: ['翻译成中文', '译成中文', '翻成中文', '中文翻译'],
      patternsEn: ['translate to chinese', 'translate into chinese'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-ai-preset', { detail: { action: 'zh' } }))
      },
    },
    {
      id: 'editor:compliance',
      label: { zh: '合规检查', en: 'Compliance check' },
      patternsZh: ['合规检查', '合规', '检查合规', '合规性'],
      patternsEn: ['compliance check', 'compliance', 'check compliance'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-compliance'))
      },
    },
    {
      id: 'editor:citations',
      label: { zh: '处理引用', en: 'Process citations' },
      patternsZh: ['处理引用', '格式化引用', '引用处理', '整理引用'],
      patternsEn: ['process citations', 'format citations', 'handle citations'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-citations'))
      },
    },
  ])
}
