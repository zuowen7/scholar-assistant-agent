import { ref, watch } from 'vue'
import type {
  AgentChatMessage,
  AgentEvent,
  AgentSessionInfo,
  AgentSkill,
  RAGDocument,
} from '../types'
import { API_BASE } from '../utils/api'
import { i18n } from '../i18n'
import { logger } from '../utils/logger'
import { readSseStream } from '../utils/streamReader'
import { currentWorkspaceGrant } from './useProject'

function workspaceGrantHeaders(): Record<string, string> | undefined {
  return currentWorkspaceGrant.value
    ? { 'X-Workspace-Grant': currentWorkspaceGrant.value }
    : undefined
}

/** Raw history message shape returned by the workflows messages endpoint. */
interface RawHistoryMessage {
  role?: string
  content?: string
  events?: AgentEvent[]
}

function formatPartialSummary(event: AgentEvent): string {
  const metadata = event.metadata || {}
  const counts = metadata.tool_counts || {}
  const stopCode = metadata.stop_code || 'tool_loop_stopped'
  const reasonKey = `agent.runtimeErrors.${stopCode}`
  const reason = i18n.global.t(reasonKey)
  return i18n.global.t('agent.partialSummary', {
    success: counts.success || 0,
    error: counts.error || 0,
    changed: metadata.changed_count || 0,
    reason,
  })
}

export interface AgentSelectionContext {
  filePath: string
  startLine: number
  startColumn: number
  endLine: number
  endColumn: number
  text: string
  /** Read-only context from the lines immediately before the selection. */
  beforeContext?: string
  /** Read-only context from the lines immediately after the selection. */
  afterContext?: string
}

export interface AgentTurnOptions {
  selection?: AgentSelectionContext
}

function normalizeAgentSelection(selection: AgentSelectionContext): AgentSelectionContext {
  if (
    selection.endColumn !== 1 ||
    selection.endLine <= selection.startLine ||
    !/(\r\n|\r|\n)$/.test(selection.text)
  ) {
    return selection
  }

  const terminalEol = selection.text.endsWith('\r\n')
    ? '\r\n'
    : selection.text.endsWith('\n')
      ? '\n'
      : '\r'
  const text = selection.text.slice(0, -terminalEol.length)
  const previousLineBreak = Math.max(text.lastIndexOf('\n'), text.lastIndexOf('\r'))
  const finalLine = text.slice(previousLineBreak + 1)
  return {
    ...selection,
    endLine: selection.endLine - 1,
    // JavaScript string length is measured in UTF-16 code units, matching Monaco.
    endColumn: finalLine.length + 1,
    text,
  }
}

const API_URL = API_BASE

// ── Module-level singleton state — survives page switches ──────────

const messages = ref<AgentChatMessage[]>([])
const sending = ref(false)
const ragDocuments = ref<RAGDocument[]>([])
const ragLoading = ref(false)
const agentSkills = ref<AgentSkill[]>([])
const skillsLoading = ref(false)
let abortController: AbortController | null = null

// v2 state
// conversationWorkflowId: persistent cross-message identity for the main
// conversation. Only updated by normal (non-selection) requests so that an
// ephemeral selection session never overwrites the ongoing chat context.
const conversationWorkflowId = ref<string | null>(null)
// activeRunSessionId: session ID of the currently running SSE stream.
// Used for approval, abort, and resume during a single run. Cleared when
// the run ends so it never leaks into the next request's workflow_id.
const activeRunSessionId = ref<string | null>(null)
// Per-session approval state: keyed by sessionId so concurrent/switching sessions
// cannot pollute each other's approval status (M11 fix).
const _approvalBySession = new Map<string, PendingApproval | null>()

// Per-workflow message isolation: messages are keyed by workflow/session ID.
const _messagesByWorkflow = new Map<string, AgentChatMessage[]>()
const WORKFLOW_MESSAGE_CACHE_LIMIT = 20

function cacheWorkflowMessages(workflowKey: string, workflowMessages: AgentChatMessage[]) {
  // Refresh insertion order so recently used workflows remain cached.
  _messagesByWorkflow.delete(workflowKey)
  _messagesByWorkflow.set(workflowKey, workflowMessages)
  while (_messagesByWorkflow.size > WORKFLOW_MESSAGE_CACHE_LIMIT) {
    const oldestWorkflowKey = _messagesByWorkflow.keys().next().value as string | undefined
    if (!oldestWorkflowKey) break
    _messagesByWorkflow.delete(oldestWorkflowKey)
    _approvalBySession.delete(oldestWorkflowKey)
  }
}

export function _getWorkflowCacheKeysForTesting(): string[] {
  return [..._messagesByWorkflow.keys()]
}

// Pipeline state (Phase 4)
export interface PendingCheckpoint {
  stage: string
  checkpoint_type: 'MANDATORY' | 'SLIM'
  title: string
  deliverables: string[]
  metrics: Record<string, number>
  options: string[]
  /** File path that was modified (for editor refresh) */
  file?: string
  /** New file content after modification (for Monaco inline update) */
  content?: string
  /** Content is only a preview; reload the full file from disk instead. */
  content_truncated?: boolean
}

const pipelineStage = ref('')
const pipelineCompleted = ref<string[]>([])
const pendingCheckpoint = ref<PendingCheckpoint | null>(null)

export interface PendingApproval {
  event_id: string
  /** Immutable owner captured from session_started; never route via mutable global state. */
  session_id: string
  tool_name: string
  args?: Record<string, unknown>
  risk?: string
  reason?: string
  preview?: Record<string, unknown>
  force_approval?: boolean
}

// One reactive approval source for every Agent surface and programmatic sender.
// The per-session map preserves isolation when switching workflows, while the
// shared ref guarantees that an approval raised by EditorLayout is visible in
// the global Agent dock.
const pendingApproval = ref<PendingApproval | null>(null)

watch(activeRunSessionId, (newSid) => {
  // Only restore — never clear — when the run ID changes. The finally block
  // intentionally clears activeRunSessionId after each run; that cleanup must
  // not wipe a pending approval that was raised during the stream.
  if (newSid) pendingApproval.value = _approvalBySession.get(newSid) ?? null
})

/** Reset all module-level singleton state — for use in tests only. */
export function _resetForTesting(): void {
  abortController?.abort()
  abortController = null
  messages.value = []
  sending.value = false
  ragDocuments.value = []
  ragLoading.value = false
  agentSkills.value = []
  skillsLoading.value = false
  conversationWorkflowId.value = null
  activeRunSessionId.value = null
  pendingApproval.value = null
  _approvalBySession.clear()
  _messagesByWorkflow.clear()
  pipelineStage.value = ''
  pipelineCompleted.value = []
  pendingCheckpoint.value = null
}

/** Agent chat composable (singleton). Manages ReAct loop SSE streaming, session lifecycle, per-session approval state, and RAG documents. */
export function useAgentChat() {
  function _setApproval(value: PendingApproval) {
    if (value.session_id) _approvalBySession.set(value.session_id, value)
    pendingApproval.value = value
  }

  function _clearApproval(eventId?: string) {
    // Approval events can overlap in a multi-tool turn. A late HTTP response or
    // approval_received event for tool A must never clear tool B's newer card.
    const current = pendingApproval.value
    if (eventId && current?.event_id !== eventId) return
    const ownerSessionId = current?.session_id || activeRunSessionId.value
    if (ownerSessionId) _approvalBySession.set(ownerSessionId, null)
    pendingApproval.value = null
  }

  // ── Shared SSE event handler ──────────────────────────────────────

  function createEventHandler(assistantMsgId: string) {
    return function handleEvent(eventType: string, data: Record<string, unknown>): void {
      const agentEvent: AgentEvent = {
        type: (data.type as AgentEvent['type']) ?? (eventType as AgentEvent['type']),
        content: (data.content as string) || '',
        event_id: data.event_id as string | undefined,
        metadata: data.metadata as AgentEvent['metadata'] | undefined,
      }

      const msg = messages.value.find((m) => m.id === assistantMsgId)
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
            msg.content =
              agentEvent.content ||
              (parts.length ? parts.join(' · ') : i18n.global.t('errors.translateComplete'))
          }
          msg.isStreaming = false
          msg.events = [...msg.events, agentEvent]
          break
        }
        case 'error':
          if (!msg.content) {
            const errorCode = agentEvent.metadata?.code
            const translationKey = errorCode ? `agent.runtimeErrors.${errorCode}` : ''
            msg.content =
              translationKey && i18n.global.te(translationKey)
                ? i18n.global.t(translationKey)
                : agentEvent.content || i18n.global.t('errors.unknownError')
          }
          msg.isStreaming = false
          msg.events = [...msg.events, agentEvent]
          break
        case 'warning':
          if (agentEvent.metadata?.reset_stream) {
            msg.content = ''
            msg.isStreaming = true
          }
          msg.events = [...msg.events, agentEvent]
          break
        case 'aborted':
          if (agentEvent.content === 'File edit rejected; no changes were applied') {
            msg.content = i18n.global.t(
              'agent.fileEditRejected',
              'File edit rejected; no changes were applied',
            )
          } else if (
            agentEvent.content === 'File edit approval timed out; no changes were applied'
          ) {
            msg.content = i18n.global.t(
              'agent.fileEditApprovalTimedOut',
              'Approval timed out; no changes were applied',
            )
          } else {
            msg.content =
              agentEvent.content || i18n.global.t('agent.sessionAborted', 'Session aborted')
          }
          msg.isStreaming = false
          _clearApproval()
          msg.events = [...msg.events, agentEvent]
          break
        case 'token':
          // Accumulate streaming tokens into msg.content for real-time display
          msg.content = (msg.content || '') + agentEvent.content
          break
        case 'thought':
        case 'thinking': {
          const last = msg.events[msg.events.length - 1]
          if (last && (last.type === 'thought' || last.type === 'thinking')) {
            msg.events = [
              ...msg.events.slice(0, -1),
              { ...last, content: last.content + agentEvent.content },
            ]
          } else {
            msg.events = [...msg.events, agentEvent]
          }
          break
        }
        case 'response':
          // Final response text replaces accumulated tokens (handles non-streaming too)
          msg.content = agentEvent.metadata?.partial
            ? formatPartialSummary(agentEvent)
            : agentEvent.content
          msg.isStreaming = false
          msg.events = [...msg.events, agentEvent]
          break
        case 'session_started':
          activeRunSessionId.value =
            (agentEvent.metadata?.session_id as string) ||
            agentEvent.content ||
            activeRunSessionId.value
          break
        case 'await_approval':
          _setApproval({
            event_id: agentEvent.event_id || '',
            session_id: activeRunSessionId.value || '',
            tool_name:
              (agentEvent.metadata?.tool_name as string) ||
              (agentEvent.metadata?.tool as string) ||
              '',
            args:
              (agentEvent.metadata?.args as Record<string, unknown>) ||
              (agentEvent.metadata?.arguments as Record<string, unknown>),
            risk: agentEvent.metadata?.risk as string | undefined,
            reason: agentEvent.metadata?.reason as string | undefined,
            preview: agentEvent.metadata?.preview as Record<string, unknown> | undefined,
            force_approval: (agentEvent.metadata?.force_approval as boolean) || false,
          })
          msg.events = [...msg.events, agentEvent]
          break
        case 'approval_received':
          _clearApproval(agentEvent.event_id)
          msg.events = [...msg.events, agentEvent]
          break
        case 'pipeline_stage':
          pipelineStage.value = (agentEvent.metadata?.to as string) || ''
          pipelineCompleted.value = (agentEvent.metadata?.completed as string[]) || []
          msg.events = [...msg.events, agentEvent]
          break
        case 'checkpoint': {
          pendingCheckpoint.value = {
            stage: (agentEvent.metadata?.stage as string) || '',
            checkpoint_type:
              (agentEvent.metadata?.checkpoint_type as 'MANDATORY' | 'SLIM') || 'SLIM',
            title: agentEvent.content || '',
            deliverables: (agentEvent.metadata?.deliverables as string[]) || [],
            metrics: (agentEvent.metadata?.metrics as Record<string, number>) || {},
            options: (agentEvent.metadata?.options as string[]) || ['continue'],
            file: agentEvent.metadata?.file as string | undefined,
            content: agentEvent.metadata?.content as string | undefined,
            content_truncated: agentEvent.metadata?.content_truncated as boolean | undefined,
          }
          msg.events = [...msg.events, agentEvent]
          // Emit every file checkpoint synchronously. A reactive watch can
          // coalesce consecutive checkpoints from one multi-file Agent turn.
          const checkpointFile = agentEvent.metadata?.file as string | undefined
          const deliverables = (agentEvent.metadata?.deliverables as string[]) || []
          const changedFiles = checkpointFile ? [checkpointFile, ...deliverables] : deliverables
          if (changedFiles.length)
            window.dispatchEvent(
              new CustomEvent('agent-files-changed', {
                detail: { files: [...new Set(changedFiles)] },
              }),
            )
          break
        }
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
    contextFile?: string,
    skills: string[] = [],
    options: AgentTurnOptions = {},
  ): Promise<void> {
    if (!text.trim() || sending.value) return

    _clearApproval()

    const userMessage: AgentChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text.trim(),
      events: [],
      isStreaming: false,
      timestamp: Date.now(),
    }
    messages.value.push(userMessage)

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

    const selection = options.selection ? normalizeAgentSelection(options.selection) : undefined
    // True when this run is an ephemeral selection edit — its session must not
    // overwrite the persistent conversation workflow ID.
    const isSelectionRun = !!selection
    // A selection edit is an atomic editor operation, not a continuation of
    // earlier chat. Keeping it isolated prevents an older <editor_context>
    // block from becoming the model's edit target.
    const history = selection
      ? []
      : messages.value
          .filter((m) => m.id !== assistantMsg.id && m.id !== userMessage.id && !m.isStreaming)
          .slice(-20)
          .map((m) => ({ role: m.role, content: m.content }))

    const handleEvent = createEventHandler(assistantMsg.id)

    const MAX_RETRIES = 2
    let sessionStarted = false

    let streamDone = false
    // Wrap the handler to track session start and detect stream completion
    const trackingHandler = (eventType: string, data: Record<string, unknown>) => {
      if (eventType === 'session_started') sessionStarted = true
      if (eventType === 'done' || eventType === 'error' || eventType === 'aborted')
        streamDone = true
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
          context_file: contextFile?.trim() || undefined,
          constraints: constraints?.trim() || undefined,
          workspace_root: workspaceRoot?.trim() || undefined,
          workspace_grant: currentWorkspaceGrant.value || undefined,
          workflow_id: selection ? undefined : conversationWorkflowId.value || undefined,
          skills: skills.slice(0, 8),
          selection: selection
            ? {
                file_path: selection.filePath,
                start_line: selection.startLine,
                start_column: selection.startColumn,
                end_line: selection.endLine,
                end_column: selection.endColumn,
                // Preserve whitespace exactly: it is part of the edit anchor.
                text: selection.text,
                before_context: selection.beforeContext?.trim() || undefined,
                after_context: selection.afterContext?.trim() || undefined,
              }
            : undefined,
        }),
        signal: abortController!.signal,
      })
      if (!resp.ok) {
        const err = await resp
          .json()
          .catch(() => ({ detail: i18n.global.t('errors.requestFailed') }))
        throw new Error(
          err.detail || i18n.global.t('errors.requestFailedHttp', { status: resp.status }),
        )
      }
      const reader = resp.body?.getReader()
      if (!reader) throw new Error(i18n.global.t('errors.streamFailed'))
      await readSseStream(reader, trackingHandler, abortController?.signal, () => streamDone)
      if (!streamDone && !abortController?.signal.aborted) {
        throw new TypeError(i18n.global.t('errors.agentStreamEnded'))
      }
    }

    try {
      let lastErr: unknown = null
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        if (attempt > 0) {
          // If session already started, use resume endpoint to avoid re-running the task
          const sid = activeRunSessionId.value
          if (sessionStarted && sid) {
            const msg = messages.value.find((m) => m.id === assistantMsg.id)
            if (msg) {
              msg.content = ''
              msg.isStreaming = true
              msg.events.push({
                type: 'warning',
                content: i18n.global.t('errors.recoveringSession', { attempt, max: MAX_RETRIES }),
              } as AgentEvent)
            }
            try {
              const resumeResp = await fetch(`${API_URL}/api/agent/v2/resume/${sid}`, {
                method: 'POST',
                headers: currentWorkspaceGrant.value
                  ? { 'X-Workspace-Grant': currentWorkspaceGrant.value }
                  : undefined,
                signal: abortController!.signal,
              })
              if (resumeResp.ok) {
                const reader = resumeResp.body?.getReader()
                if (reader) {
                  try {
                    await readSseStream(
                      reader,
                      trackingHandler,
                      abortController?.signal,
                      () => streamDone,
                    )
                    if (!streamDone && !abortController?.signal.aborted) {
                      throw new TypeError(i18n.global.t('errors.agentStreamEnded'))
                    }
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
            await new Promise((r) => setTimeout(r, attempt * 2000))
            continue
          }
          // Session not yet started: retry original request after delay
          const msg = messages.value.find((m) => m.id === assistantMsg.id)
          if (msg)
            msg.events.push({
              type: 'warning',
              content: i18n.global.t('errors.retryingNetwork', { attempt, max: MAX_RETRIES }),
            } as AgentEvent)
          await new Promise((r) => setTimeout(r, attempt * 2000))
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

      const msg = messages.value.find((m) => m.id === assistantMsg.id)
      if (msg?.isStreaming) {
        msg.isStreaming = false
        if (!msg.content) {
          const last = msg.events[msg.events.length - 1]
          msg.content =
            (last as AgentEvent | undefined)?.content || i18n.global.t('errors.translateComplete')
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const msg = messages.value.find((m) => m.id === assistantMsg.id)
      if (msg) {
        msg.content = `${i18n.global.t('errors.requestFailed')}: ${err instanceof Error ? err.message : String(err)}`
        msg.isStreaming = false
      }
    } finally {
      sending.value = false
      abortController = null
      if (!isSelectionRun && activeRunSessionId.value) {
        // Normal conversation: promote the run session to the persistent
        // workflow ID so subsequent messages continue the same conversation.
        conversationWorkflowId.value = activeRunSessionId.value
      }
      // Always clear the run ID — it is only meaningful while an SSE stream
      // is active. Leaving it set causes floating windows and abort calls to
      // target a stale session.
      activeRunSessionId.value = null
    }
  }

  function stopGenerating(): void {
    abortController?.abort()
  }

  function clearHistory(): void {
    startNewWorkflow()
  }

  // ── v2 Approval ──────────────────────────────────────────────────

  async function sendApproval(
    eventId: string,
    decision: 'allow_once' | 'allow_session' | 'deny',
    reason?: string,
    sessionId?: string,
  ): Promise<boolean> {
    const approvalOwner =
      pendingApproval.value?.event_id === eventId ? pendingApproval.value.session_id : null
    const sid = sessionId || approvalOwner || activeRunSessionId.value
    if (!sid || !eventId) {
      logger.warn('sendApproval skipped: approval routing identity is missing', {
        eventId,
        hasActiveSession: Boolean(activeRunSessionId.value),
      })
      return false
    }

    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/approve/${sid}/${eventId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(currentWorkspaceGrant.value
            ? { 'X-Workspace-Grant': currentWorkspaceGrant.value }
            : {}),
        },
        body: JSON.stringify({ decision, reason: reason || undefined }),
      })
      if (resp.ok) {
        _clearApproval(eventId)
        return true
      }
      const detail = await resp
        .json()
        .then((body) => body?.detail)
        .catch(() => undefined)
      logger.warn('sendApproval rejected by backend', {
        sessionId: sid,
        eventId,
        status: resp.status,
        detail,
      })
    } catch (e) {
      logger.warn('sendApproval failed', { error: e })
    }
    return false
  }

  async function abortSession(): Promise<boolean> {
    const sid = activeRunSessionId.value
    if (!sid) {
      // 没有 session_id 时直接中止当前 SSE
      stopGenerating()
      return true
    }

    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/abort/${sid}`, {
        method: 'POST',
        headers: currentWorkspaceGrant.value
          ? { 'X-Workspace-Grant': currentWorkspaceGrant.value }
          : undefined,
      })
      if (resp.ok) {
        _clearApproval()
        stopGenerating()
        return true
      }
    } catch (e) {
      logger.warn('abortSession failed', { error: e })
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
      if (
        existing &&
        ['COMPLETE', 'FAILED', 'ABORTED'].includes(String(existing.state).toUpperCase())
      ) {
        return // Session already completed, no need to resume
      }
    } catch {
      // If session list fetch fails, proceed with resume attempt
    }

    _clearApproval()
    conversationWorkflowId.value = targetSessionId
    activeRunSessionId.value = targetSessionId

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
        headers: currentWorkspaceGrant.value
          ? { 'X-Workspace-Grant': currentWorkspaceGrant.value }
          : undefined,
        signal: abortController.signal,
      })

      if (!resp.ok) {
        const err = await resp
          .json()
          .catch(() => ({ detail: i18n.global.t('errors.resumeFailed') }))
        throw new Error(
          err.detail || i18n.global.t('errors.requestFailedHttp', { status: resp.status }),
        )
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error(i18n.global.t('errors.streamFailed'))

      await readSseStream(reader, handleEvent, abortController?.signal)

      const msg = messages.value.find((m) => m.id === assistantMsg.id)
      if (msg?.isStreaming) {
        msg.isStreaming = false
        if (!msg.content) {
          const last = msg.events[msg.events.length - 1]
          msg.content = last?.content || i18n.global.t('errors.translateComplete')
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      const msg = messages.value.find((m) => m.id === assistantMsg.id)
      if (msg) {
        msg.content = `${i18n.global.t('errors.requestFailed')}: ${err instanceof Error ? err.message : String(err)}`
        msg.isStreaming = false
      }
    } finally {
      sending.value = false
      abortController = null
      activeRunSessionId.value = null
    }
  }

  // ── Session listing ──────────────────────────────────────────────

  async function fetchSessions(): Promise<AgentSessionInfo[]> {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/sessions`, {
        headers: workspaceGrantHeaders(),
      })
      if (resp.ok) return await resp.json()
    } catch (e) {
      logger.warn('fetchSessions failed', { error: e })
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
    } catch (e) {
      logger.warn('agentFetchDocs failed', { error: e })
    } finally {
      ragLoading.value = false
    }
  }

  async function deleteRAGDocument(docId: string): Promise<void> {
    const resp = await fetch(`${API_URL}/api/rag/documents/${docId}`, { method: 'DELETE' })
    if (resp.ok) {
      ragDocuments.value = ragDocuments.value.filter((d) => d.id !== docId)
    }
  }

  async function uploadRAGFile(file: File): Promise<{ ok: boolean; error?: string }> {
    const form = new FormData()
    form.append('file', file)
    try {
      const resp = await fetch(`${API_URL}/api/rag/upload`, { method: 'POST', body: form })
      if (!resp.ok) {
        const err = await resp
          .json()
          .catch(() => ({ detail: i18n.global.t('errors.uploadFailed') }))
        return {
          ok: false,
          error: err.detail || i18n.global.t('errors.uploadFailedHttp', { status: resp.status }),
        }
      }
      await fetchRAGDocuments()
      return { ok: true }
    } catch (e: unknown) {
      return {
        ok: false,
        error: e instanceof Error ? e.message : i18n.global.t('errors.networkError'),
      }
    }
  }

  // Per-workflow message loading (Phase 3)
  async function loadWorkflowMessages(wfId: string): Promise<boolean> {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/workflows/${wfId}/messages`, {
        headers: workspaceGrantHeaders(),
      })
      if (!resp.ok) return false
      const data = (await resp.json()) as { messages?: RawHistoryMessage[] }
      const loaded: AgentChatMessage[] = (data.messages || []).map((m, i) => {
        const events = Array.isArray(m.events) ? m.events : []
        const partial = events.find(
          (event) => event.type === 'response' && event.metadata?.partial === true,
        )
        return {
          id: `hist_${i}`,
          role: m.role === 'user' ? 'user' : 'assistant',
          content: partial ? formatPartialSummary(partial) : m.content || '',
          events,
          isStreaming: false,
          timestamp: Date.now() + i,
        }
      })
      cacheWorkflowMessages(wfId, loaded)
      _clearApproval()
      conversationWorkflowId.value = wfId
      messages.value = loaded
      pipelineStage.value = ''
      pipelineCompleted.value = []
      pendingCheckpoint.value = null
      return true
    } catch (e) {
      logger.error('loadWorkflowMessages failed:', e)
      return false
    }
  }

  function startNewWorkflow() {
    const previousWorkflowId = conversationWorkflowId.value
    if (previousWorkflowId && messages.value.length) {
      cacheWorkflowMessages(previousWorkflowId, [...messages.value])
    }
    conversationWorkflowId.value = null
    activeRunSessionId.value = null
    messages.value = []
    _clearApproval()
    pipelineStage.value = ''
    pipelineCompleted.value = []
    pendingCheckpoint.value = null
  }

  async function respondCheckpoint(_decision: string) {
    // Handled via SSE checkpoint event — decision flows through agent stream
    pendingCheckpoint.value = null
  }

  async function fetchTools() {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/tools`)
      if (!resp.ok) return {}
      const data = await resp.json()
      return data.tools || []
    } catch {
      return {}
    }
  }

  async function fetchAgentSkills(): Promise<AgentSkill[]> {
    skillsLoading.value = true
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/skills`)
      if (!resp.ok) return agentSkills.value
      const data = await resp.json()
      agentSkills.value = Array.isArray(data) ? data : []
      return agentSkills.value
    } catch (e) {
      logger.warn('fetchAgentSkills failed', { error: e })
      return agentSkills.value
    } finally {
      skillsLoading.value = false
    }
  }

  async function cleanupWorkflows() {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/workflows/cleanup`, {
        method: 'POST',
        headers: workspaceGrantHeaders(),
      })
      if (!resp.ok) throw new Error('cleanup failed')
      return await resp.json()
    } catch {
      return null
    }
  }

  async function deleteWorkflow(wfId: string) {
    try {
      const resp = await fetch(`${API_URL}/api/agent/v2/workflows/${wfId}`, {
        method: 'DELETE',
        headers: workspaceGrantHeaders(),
      })
      if (!resp.ok) return false
      _messagesByWorkflow.delete(wfId)
      _approvalBySession.delete(wfId)
      return true
    } catch {
      return false
    }
  }

  return {
    messages,
    sending,
    conversationWorkflowId,
    activeRunSessionId,
    pendingApproval,
    pipelineStage,
    pipelineCompleted,
    pendingCheckpoint,
    sendMessage,
    stopGenerating,
    clearHistory,
    sendApproval,
    abortSession,
    resumeSession,
    fetchSessions,
    startNewWorkflow,
    loadWorkflowMessages,
    respondCheckpoint,
    fetchTools,
    agentSkills,
    skillsLoading,
    fetchAgentSkills,
    cleanupWorkflows,
    deleteWorkflow,
    ragDocuments,
    ragLoading,
    fetchRAGDocuments,
    deleteRAGDocument,
    uploadRAGFile,
  }
}
