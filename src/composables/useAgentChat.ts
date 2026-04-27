import { ref } from 'vue'
import type { AgentChatMessage, AgentEvent, RAGDocument } from '../types'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'

const API_URL = API_BASE

// Module-level singleton state — survives page switches
const messages = ref<AgentChatMessage[]>([])
const sending = ref(false)
const ragDocuments = ref<RAGDocument[]>([])
const ragLoading = ref(false)
let abortController: AbortController | null = null

export function useAgentChat() {

  // ── SSE 流式对话 ──────────────────────────────────────────────

  async function sendMessage(
    text: string,
    contextText?: string,
    constraints?: string,
  ): Promise<void> {
    if (!text.trim() || sending.value) return

    // 添加用户消息
    messages.value.push({
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      events: [],
      isStreaming: false,
      timestamp: Date.now(),
    })

    // 创建 assistant 消息占位
    const assistantMsg: AgentChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      events: [],
      isStreaming: true,
      timestamp: Date.now(),
    }
    messages.value.push(assistantMsg)

    sending.value = true
    abortController?.abort()
    abortController = new AbortController()

    // 构造历史（最近 10 轮，不含当前 assistant 占位）
    const history = messages.value
      .filter(m => m.id !== assistantMsg.id && !m.isStreaming)
      .slice(-20)
      .map(m => ({ role: m.role, content: m.content }))

    // handleEvent 闭包状态
    function handleEvent(eventType: string, data: Record<string, unknown>): void {
      const agentEvent: AgentEvent = {
        type: data.type as AgentEvent['type'],
        content: (data.content as string) || '',
        metadata: data.metadata as AgentEvent['metadata'] | undefined,
      }

      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (!msg) return

      if (eventType === 'response') {
        msg.content = agentEvent.content
        msg.isStreaming = false
      } else if (eventType === 'error') {
        msg.content = agentEvent.content
        msg.isStreaming = false
      } else {
        msg.events = [...msg.events, agentEvent]
      }
    }

    try {
      const resp = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          history,
          context_text: contextText?.trim() || undefined,
          constraints: constraints?.trim() || undefined,
        }),
        signal: abortController.signal,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '请求失败' }))
        throw new Error(err.detail || `请求失败 (${resp.status})`)
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')

      await readSseStream(reader, handleEvent)

      // 如果流结束但 assistant 还在 streaming（没有收到 response 事件），标记结束
      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (msg?.isStreaming) {
        msg.isStreaming = false
        if (!msg.content && msg.events.length > 0) {
          // 用最后一个事件的内容作为回答
          const last = msg.events[msg.events.length - 1]
          msg.content = last.content
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (msg) {
        msg.content = `请求失败: ${err instanceof Error ? err.message : String(err)}`
        msg.isStreaming = false
      }
    } finally {
      sending.value = false
      abortController = null
    }
  }

  function stopGenerating(): void {
    abortController?.abort()
  }

  function clearHistory(): void {
    messages.value = []
  }

  // ── RAG 文档管理 ─────────────────────────────────────────────

  async function fetchRAGDocuments(): Promise<void> {
    ragLoading.value = true
    try {
      const resp = await fetch(`${API_URL}/api/rag/documents`)
      if (resp.ok) {
        ragDocuments.value = await resp.json()
      }
    } catch (e) { console.warn('agentFetchDocs failed:', e) }
    finally {
      ragLoading.value = false
    }
  }

  async function deleteRAGDocument(docId: string): Promise<void> {
    const resp = await fetch(`${API_URL}/api/rag/documents/${docId}`, { method: 'DELETE' })
    if (resp.ok) {
      ragDocuments.value = ragDocuments.value.filter(d => d.id !== docId)
    }
  }

  return {
    messages,
    sending,
    ragDocuments,
    ragLoading,
    sendMessage,
    stopGenerating,
    clearHistory,
    fetchRAGDocuments,
    deleteRAGDocument,
  }
}
