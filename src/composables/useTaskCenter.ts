import { computed } from 'vue'
import { useAgentChat } from './useAgentChat'
import { useArgumentCompanion } from './useArgumentCompanion'
import { useTranslate } from './useTranslate'
import { useExportWorkspace } from './useExportWorkspace'

export interface WorkspaceTask {
  id: string
  kind: 'translation' | 'rag' | 'review' | 'agent' | 'export'
  label: string
  status: 'running' | 'queued' | 'failed'
  progress: number | null
}

export function useTaskCenter() {
  const translation = useTranslate()
  const agent = useAgentChat()
  const companion = useArgumentCompanion()
  const exportWorkspace = useExportWorkspace()

  const tasks = computed<WorkspaceTask[]>(() => {
    const items: WorkspaceTask[] = []
    if (!['idle', 'done', 'error'].includes(translation.state.status)) {
      items.push({
        id: `translation-${translation.state.taskId || 'pending'}`,
        kind: 'translation',
        label: translation.state.sourceName || 'PDF 翻译',
        status: 'running',
        progress: translation.overallProgress(),
      })
    }
    if (translation.state.ragStatus === 'queued') {
      items.push({
        id: `rag-${translation.state.taskId || 'pending'}`,
        kind: 'rag',
        label: `${translation.state.sourceName || '翻译结果'} · RAG 入库`,
        status: 'queued',
        progress: null,
      })
    } else if (translation.state.ragStatus === 'failed') {
      items.push({
        id: `rag-${translation.state.taskId || 'failed'}`,
        kind: 'rag',
        label: `${translation.state.sourceName || '翻译结果'} · RAG 入库失败`,
        status: 'failed',
        progress: null,
      })
    }
    if (companion.state.reviewing) {
      items.push({
        id: `review-${companion.state.docId || 'current'}`,
        kind: 'review',
        label: `正在审阅 ${companion.state.docTitle || '当前文稿'}`,
        status: 'running',
        progress: null,
      })
    }
    if (agent.sending.value) {
      items.push({
        id: `agent-${agent.sessionId.value || 'current'}`,
        kind: 'agent',
        label: agent.pipelineStage.value || 'Agent 正在执行任务',
        status: 'running',
        progress: null,
      })
    }
    if (exportWorkspace.loading.value) {
      items.push({
        id: 'export-current',
        kind: 'export',
        label: '正在生成导出文件',
        status: 'running',
        progress: null,
      })
    }
    return items
  })

  return { tasks }
}
