import type { VoiceCommandDef } from '../../types/voice'

export function registerTier5Commands(register: (defs: VoiceCommandDef[]) => void) {
  register([
    {
      id: 'mindmap:add-node',
      label: { zh: '添加节点', en: 'Add node' },
      patternsZh: ['添加节点', '新建节点', '加个节点'],
      patternsEn: ['add node', 'new node', 'add child'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'add-child' } }))
      },
    },
    {
      id: 'mindmap:delete-node',
      label: { zh: '删除节点', en: 'Delete node' },
      patternsZh: ['删除节点', '删除导图节点', '删掉节点'],
      patternsEn: ['delete node', 'remove node'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'delete-node' } }))
      },
    },
    {
      id: 'mindmap:ai-expand',
      label: { zh: 'AI扩展节点', en: 'AI expand node' },
      patternsZh: ['ai扩展', '扩展节点', 'ai扩展节点', '智能扩展'],
      patternsEn: ['ai expand', 'expand node', 'smart expand'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'ai-expand' } }))
      },
    },
    {
      id: 'mindmap:layout',
      label: { zh: '自动布局', en: 'Auto layout' },
      patternsZh: ['自动布局', '布局导图', '重新布局', '整理布局'],
      patternsEn: ['auto layout', 'layout', 'reorganize layout'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'layout' } }))
      },
    },
    {
      id: 'mindmap:save',
      label: { zh: '保存导图', en: 'Save mind map' },
      patternsZh: ['保存导图', '保存思维导图'],
      patternsEn: ['save mindmap', 'save mind map'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'save' } }))
      },
    },
    {
      id: 'mindmap:analyze',
      label: { zh: '分析导图', en: 'Analyze mind map' },
      patternsZh: ['分析导图', '导图分析', 'ai分析'],
      patternsEn: ['analyze map', 'analyze mind map', 'ai analyze'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'analyze' } }))
      },
    },
    {
      id: 'mindmap:zoom-in',
      label: { zh: '放大', en: 'Zoom in' },
      patternsZh: ['放大', '放大一点', '拉近'],
      patternsEn: ['zoom in', 'zoom closer'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'zoom-in' } }))
      },
    },
    {
      id: 'mindmap:zoom-out',
      label: { zh: '缩小', en: 'Zoom out' },
      patternsZh: ['缩小', '缩小一点', '拉远'],
      patternsEn: ['zoom out', 'zoom farther'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'zoom-out' } }))
      },
    },
    {
      id: 'mindmap:fit-view',
      label: { zh: '适应视图', en: 'Fit view' },
      patternsZh: ['适应视图', '适应屏幕', '全部显示'],
      patternsEn: ['fit view', 'fit screen', 'show all'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'fit-view' } }))
      },
    },
    {
      id: 'mindmap:reset-view',
      label: { zh: '重置视图', en: 'Reset view' },
      patternsZh: ['重置视图', '恢复视图'],
      patternsEn: ['reset view', 'restore view'],
      priority: 4,
      handler: async () => {
        window.dispatchEvent(new CustomEvent('voice-mindmap-command', { detail: { action: 'reset-view' } }))
      },
    },
  ])
}
