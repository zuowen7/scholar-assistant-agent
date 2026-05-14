import { ref, watch } from 'vue'
import type { AgentChatMessage, AgentEvent, AgentSessionInfo, RAGDocument } from '../types'
import { API_BASE } from '../utils/api'
import { readSseStream } from '../utils/streamReader'

const API_URL = API_BASE

// ── Module-level singleton state — survives page switches ──────────

const messages = ref<AgentChatMessage[]>([])
const sending = ref(false)
const ragDocuments = ref<RAGDocument[]>([])
const ragLoading = ref(false)
let abortController: AbortController | null = null

// v2 state
const sessionId = ref<string | null>(null)
// Per-session approval state: keyed by sessionId so concurrent/switching sessions
// cannot pollute each other's approval status (M11 fix).
const _approvalBySession = new Map<string, PendingApproval | null>()

export interface PendingApproval {
  event_id: string
  tool_name: string
  args?: Record<string, unknown>
  risk?: string
  preview?: Record<string, unknown>
}

export function useAgentChat() {

  // ── Per-session pendingApproval (M11 fix) ────────────────────────
  // A reactive ref that always reflects the approval state of the *current* session.
  // All reads/writes go through the helpers below so switching sessions never
  // leaks an approval from a previous session.
  const pendingApproval = ref<PendingApproval | null>(null)

  function _setApproval(value: PendingApproval | null) {
    const sid = sessionId.value
    if (sid) _approvalBySession.set(sid, value)
    pendingApproval.value = value
  }

  function _clearApproval() {
    _setApproval(null)
  }

  // When sessionId changes (e.g. user switches to a different session via resumeSession
  // or a new session starts), sync pendingApproval to whatever was stored for that session.
  watch(sessionId, (newSid) => {
    pendingApproval.value = (newSid ? (_approvalBySession.get(newSid) ?? null) : null)
  })

  // ── Shared SSE event handler ──────────────────────────────────────

  function createEventHandler(assistantMsgId: string) {
    return function handleEvent(eventType: string, data: Record<string, unknown>): void {
      const agentEvent: AgentEvent = {
        type: (data.type as AgentEvent['type']) || eventType,
        content: (data.content as string) || '',
        event_id: data.event_id as string | undefined,
        metadata: data.metadata as AgentEvent['metadata'] | undefined,
      }

      const msg = messages.value.find(m => m.id === assistantMsgId)
      if (!msg) return

      switch (eventType) {
        case 'done': {
          const tasksDone = agentEvent.metadata?.tasks_done
          const usage = agentEvent.metadata?.token_usage
          const parts: string[] = []
          if (agentEvent.content) parts.push(agentEvent.content)
          if (tasksDone != null) parts.push(`${tasksDone} tasks`)
          if (usage) {
            const u = usage as Record<string, number>
            const total = u.total_tokens || (u.prompt_tokens || 0) + (u.completion_tokens || 0)
            if (total) parts.push(`${total} tokens`)
          }
          if (!msg.content) {
            msg.content = agentEvent.content || (parts.length ? parts.join(' · ') : '完成')
          }
          msg.isStreaming = false
          msg.events = [...msg.events, agentEvent]
          break
        }
        case 'error':
          if (!msg.content) msg.content = agentEvent.content || '发生错误'
          msg.isStreaming = false
          msg.events = [...msg.events, agentEvent]
          break
        case 'aborted':
          msg.content = agentEvent.content || '会话已中止'
          msg.isStreaming = false
          _clearApproval()
          msg.events = [...msg.events, agentEvent]
          break
        case 'response':
          msg.content = agentEvent.content
          msg.isStreaming = false
          break
        case 'session_started':
          sessionId.value = (agentEvent.metadata?.session_id as string) || sessionId.value
          break
        case 'await_approval':
          _setApproval({
            event_id: agentEvent.event_id || '',
            tool_name: (agentEvent.metadata?.tool_name as string) || (agentEvent.metadata?.tool as string) || '',
            args: agentEvent.metadata?.args as Record<string, unknown>
              || agentEvent.metadata?.arguments as Record<string, unknown>,
            risk: agentEvent.metadata?.risk as string | undefined,
            preview: agentEvent.metadata?.preview as Record<string, unknown> | undefined,
          })
          msg.events = [...msg.events, agentEvent]
          break
        case 'approval_received':
          _clearApproval()
          msg.events = [...msg.events, agentEvent]
          break
        default:
          msg.events = [...msg.events, agentEvent]
          break
      }
    }
  }

  // ── SSE streaming ────────────────────────────────────────────────

  async function sendMessage(
    text: string,
    contextText?: string,
    constraints?: string,
    workspaceRoot?: string,
  ): Promise<void> {
    if (!text.trim() || sending.value) return

    _clearApproval()

    messages.value.push({
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      events: [],
      isStreaming: false,
      timestamp: Date.now(),
    })

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

    const history = messages.value
      .filter(m => m.id !== assistantMsg.id && !m.isStreaming)
      .slice(-20)
      .map(m => ({ role: m.role, content: m.content }))

    const handleEvent = createEventHandler(assistantMsg.id)

    const MAX_RETRIES = 2
    let sessionStarted = false

    // Wrap the handler to track whether session has started (for reconnect decisions)
    const trackingHandler = (eventType: string, data: Record<string, unknown>) => {
      if (eventType === 'session_started') sessionStarted = true
      handleEvent(eventType, data)
    }

    const doFetch = async () => {
      const resp = await fetch(`${API_URL}/api/agent/v2/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text.trim(),
          history,
          context_text: contextText?.trim() || undefined,
          constraints: constraints?.trim() || undefined,
          workspace_root: workspaceRoot?.trim() || undefined,
        }),
        signal: abortController!.signal,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '请求失败' }))
        throw new Error(err.detail || `请求失败 (${resp.status})`)
      }
      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')
      await readSseStream(reader, trackingHandler)
    }

    try {
      let lastErr: unknown = null
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (attempt > 0) {
          // If session already started, use resume endpoint to avoid re-running the task
          const sid = sessionId.value
          if (sessionStarted && sid) {
            const msg = messages.value.find(m => m.id === assistantMsg.id)
            if (msg) msg.events.push({ type: 'warning', content: `网络中断，正在恢复会话... (${attempt}/${MAX_RETRIES})` } as AgentEvent)
            try {
              const resumeResp = await fetch(`${API_URL}/api/agent/v2/resume/${sid}`, {
                method: 'POST',
                signal: abortController!.signal,
              })
              if (resumeResp.ok) {
                const reader = resumeResp.body?.getReader()
                if (reader) {
                  try {
                    await readSseStream(reader, trackingHandler, abortController?.signal)
                    lastErr = null
                    break
                  } catch (streamErr) {
                    if (streamErr instanceof DOMException && streamErr.name === 'AbortError') return
                    lastErr = streamErr
                  }
                }
              }
            } catch (_re) {
              if (_re instanceof DOMException && _re.name === 'AbortError') return
            }
            await new Promise(r => setTimeout(r, attempt * 2000))
            continue
          }
          // Session not yet started: retry original request after delay
          const msg = messages.value.find(m => m.id === assistantMsg.id)
          if (msg) msg.events.push({ type: 'warning', content: `网络错误，正在重试... (${attempt}/${MAX_RETRIES})` } as AgentEvent)
          await new Promise(r => setTimeout(r, attempt * 2000))
        }
        try {
          await doFetch()
          lastErr = null
          break
        } catch (e) {
          if (e instanceof DOMException && e.name === 'AbortError') return
          // Only retry on network-level errors (TypeError = fetch failed), not HTTP errors
          if (attempt < MAX_RETRIES && e instanceof TypeError) {
            lastErr = e
            continue
          }
          throw e
        }
      }
      if (lastErr) throw lastErr

      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (msg?.isStreaming) {
        msg.isStreaming = false
        if (!msg.content) {
          const last = msg.events[msg.events.length - 1]
          msg.content = (last as AgentEvent | undefined)?.content || '完成'
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
      _clearApproval()
    }
  }

  function stopGenerating(): void {
    abortController?.abort()
  }

  function clearHistory(): void {
    messages.value = []
    sessionId.value = null
    _clearApproval()
  }

  // ── v2 Approval ──────────────────────────────────────────────────

  async function sendApproval(
    eventId: string,
    decision: 'allow_once' | 'allow_session' | 'deny',
    reason?: string,
  ): Promise<boolean> {
    const sid = sessionId.value
    if (!sid || !eventId) return false

    try {
      const resp = await fetch(
        `${API_URL}/api/agent/v2/approve/${sid}/${eventId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decision, reason: reason || undefined }),
        },
      )
      if (resp.ok) {
        _clearApproval()
        return true
      }
    } catch (e) {
      console.warn('sendApproval failed:', e)
    }
    return false
  }

  async function abortSession(): Promise<boolean> {
    const sid = sessionId.value
    if (!sid) {
      // 没有 session_id 时直接中止当前 SSE
      stopGenerating()
      return true
    }

    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/abort/${sid}`, { method: 'POST' })
      if (resp.ok) {
        _clearApproval()
        stopGenerating()
        return true
      }
    } catch (e) {
      console.warn('abortSession failed:', e)
    }
    // 即使后端 abort 失败，也中止前端流
    stopGenerating()
    return false
  }

  // ── v2 Resume ────────────────────────────────────────────────────

  async function resumeSession(targetSessionId: string): Promise<void> {
    if (sending.value) return

    // Idempotency check: verify session is not already done before resuming
    try {
      const sessions = await fetchSessions()
      const existing = sessions.find((s: AgentSessionInfo) => s.id === targetSessionId)
      if (existing && (existing.state === 'DONE' || existing.state === 'ABORTED')) {
        return // Session already completed, no need to resume
      }
    } catch {
      // If session list fetch fails, proceed with resume attempt
    }

    _clearApproval()
    sessionId.value = targetSessionId

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

    const handleEvent = createEventHandler(assistantMsg.id)

    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/resume/${targetSessionId}`, {
        method: 'POST',
        signal: abortController.signal,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '恢复失败' }))
        throw new Error(err.detail || `恢复失败 (${resp.status})`)
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')

      await readSseStream(reader, handleEvent)

      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (msg?.isStreaming) {
        msg.isStreaming = false
        if (!msg.content) {
          const last = msg.events[msg.events.length - 1]
          msg.content = last?.content || '完成'
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const msg = messages.value.find(m => m.id === assistantMsg.id)
      if (msg) {
        msg.content = `恢复失败: ${err instanceof Error ? err.message : String(err)}`
        msg.isStreaming = false
      }
    } finally {
      sending.value = false
      abortController = null
    }
  }

  // ── Session listing ──────────────────────────────────────────────

  async function fetchSessions(): Promise<AgentSessionInfo[]> {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/sessions`)
      if (resp.ok) return await resp.json()
    } catch (e) {
      console.warn('fetchSessions failed:', e)
    }
    return []
  }

  // ── RAG ──────────────────────────────────────────────────────────

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

  async function uploadRAGFile(file: File): Promise<{ ok: boolean; error?: string }> {
    const form = new FormData()
    form.append('file', file)
    try {
      const resp = await fetch(`${API_URL}/api/rag/upload`, { method: 'POST', body: form })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: '上传失败' }))
        return { ok: false, error: err.detail || `上传失败 (${resp.status})` }
      }
      await fetchRAGDocuments()
      return { ok: true }
    } catch (e: unknown) {
      return { ok: false, error: e instanceof Error ? e.message : '网络错误' }
    }
  }

  return {
    messages,
    sending,
    sessionId,
    pendingApproval,
    sendMessage,
    stopGenerating,
    clearHistory,
    sendApproval,
    abortSession,
    resumeSession,
    fetchSessions,
    ragDocuments,
    ragLoading,
    fetchRAGDocuments,
    deleteRAGDocument,
    uploadRAGFile,
  }
}
