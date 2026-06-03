import type { VoiceCommandDef } from '../../types/voice'

export function registerTier2Commands(register: (defs: VoiceCommandDef[]) => void) {
  register([
    {
      id: 'file:open-folder',
      label: { zh: '打开文件夹', en: 'Open folder' },
      patternsZh: ['打开文件夹', '打开目录', '打开项目', '打开工作区'],
      patternsEn: ['open folder', 'open directory', 'open project', 'open workspace'],
      priority: 7,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-open-folder'))
      },
    },
    {
      id: 'file:new',
      label: { zh: '新建文件', en: 'New file' },
      patternsZh: ['新建文件', '新建文档', '创建文件', '新建一个', '新建空白'],
      patternsEn: ['new file', 'new document', 'create file', 'create document'],
      priority: 7,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-new-file'))
      },
    },
    {
      id: 'file:save',
      label: { zh: '保存文件', en: 'Save file' },
      patternsZh: ['保存', '保存文件', '存盘'],
      patternsEn: ['save', 'save file'],
      priority: 7,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-save'))
      },
    },
  ])
}
