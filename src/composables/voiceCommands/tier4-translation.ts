import type { VoiceCommandDef } from '../../types/voice'
import { useAppMode } from '../useAppMode'

export function registerTier4Commands(register: (defs: VoiceCommandDef[]) => void) {
  register([
    {
      id: 'translate:new',
      label: { zh: '开始翻译', en: 'New translation' },
      patternsZh: ['开始翻译', '翻译文件', '新翻译', '上传翻译', '上传文件翻译'],
      patternsEn: ['start translation', 'translate file', 'new translation', 'upload translation'],
      priority: 6,
      handler: async () => {
        useAppMode().setMode('translate')
        window.dispatchEvent(new CustomEvent('voice-translate-new'))
      },
    },
    {
      id: 'translate:retry',
      label: { zh: '重试失败块', en: 'Retry failed blocks' },
      patternsZh: ['重试翻译', '重试失败', '重试失败块', '重新翻译失败'],
      patternsEn: ['retry translation', 'retry failed', 'retry failed blocks'],
      priority: 5,
      handler: async () => {
        useAppMode().setMode('translate')
        window.dispatchEvent(new CustomEvent('voice-translate-retry'))
      },
    },
    {
      id: 'translate:export-bilingual-docx',
      label: { zh: '导出双语Word', en: 'Export bilingual Word' },
      patternsZh: ['导出双语word', '导出双语文档', '导出双语docx'],
      patternsEn: ['export bilingual', 'export bilingual word', 'export bilingual docx'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-translate-export', { detail: { format: 'bilingual-docx' } }))
      },
    },
    {
      id: 'translate:export-translation-docx',
      label: { zh: '导出译文Word', en: 'Export translation Word' },
      patternsZh: ['导出译文word', '导出译文文档', '导出译文docx'],
      patternsEn: ['export translation word', 'export translation docx'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-translate-export', { detail: { format: 'translation-docx' } }))
      },
    },
    {
      id: 'translate:export-bilingual-md',
      label: { zh: '导出双语Markdown', en: 'Export bilingual Markdown' },
      patternsZh: ['导出双语markdown', '导出双语md'],
      patternsEn: ['export bilingual markdown', 'export bilingual md'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-translate-export', { detail: { format: 'bilingual-md' } }))
      },
    },
    {
      id: 'translate:export-translation-md',
      label: { zh: '导出译文Markdown', en: 'Export translation Markdown' },
      patternsZh: ['导出译文markdown', '导出译文md'],
      patternsEn: ['export translation markdown', 'export translation md'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-translate-export', { detail: { format: 'translation-md' } }))
      },
    },
    {
      id: 'translate:export-pptx',
      label: { zh: '导出PPTX', en: 'Export PPTX' },
      patternsZh: ['导出pptx', '导出ppt', '导出幻灯片'],
      patternsEn: ['export pptx', 'export ppt', 'export slides'],
      priority: 5,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-translate-export', { detail: { format: 'pptx' } }))
      },
    },
  ])
}
