<template>
  <div
    class="agent-panel"
    :class="{ open: open && !isFloating, standalone: isStandalone, floating: isFloating }"
    :style="isFloating ? { left: floatX + 'px', top: floatY + 'px' } : {}"
  >
    <div
      class="agent-header"
      :class="{ draggable: isStandalone || isFloating }"
      @mousedown="_headerMouseDown"
    >
      <div class="agent-tabs">
        <button class="agent-tab u-interactive" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">{{ t('agent.tabChat') }}</button>
        <button class="agent-tab u-interactive" :class="{ active: tab === 'docs' }" @click="tab = 'docs'">{{ t('agent.tabDocs') }}</button>
        <button class="agent-tab u-interactive" :class="{ active: tab === 'templates' }" @click="tab = 'templates'">{{ t('agent.tabTemplates') }}</button>
        <button class="agent-tab u-interactive" :class="{ active: tab === 'sessions' }" @click="tab = 'sessions'; refreshSessions()">{{ t('agent.tabSessions') }}</button>
      </div>
      <div class="agent-header-actions">
        <!-- Standalone window: dock back to main -->
        <button v-if="isStandalone" class="agent-hdr-btn" :title="t('agent.dockBack')" @click="onDockBack">
          <PinOff :size="13" :stroke-width="1.8" />
        </button>
        <!-- Main window: float / dock toggle -->
        <button v-if="!isStandalone" class="agent-hdr-btn" :title="isFloating ? t('agent.dockSide') : t('agent.popFloat')" @click="toggleFloat">
          <PinOff v-if="isFloating" :size="13" :stroke-width="1.8" />
          <Pin v-else :size="13" :stroke-width="1.8" />
        </button>
        <button v-if="!isStandalone && !isFloating" class="agent-close-btn" @click="$emit('update:open', false)" :aria-label="t('agent.close')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Sessions Tab -->
    <div v-show="tab === 'sessions'" class="agent-sessions">
      <AgentSessionList ref="sessionListRef" @resume="handleSessionResume" />
    </div>

    <!-- Chat Tab -->
    <div v-show="tab === 'chat'" class="agent-chat">
      <div v-if="sending && !pendingApproval" class="agent-thinking-bar"></div>
      <div class="agent-messages" ref="messagesRef" @scroll="_onMessagesScroll">
        <div v-if="currentStatus && sending && !pendingApproval" class="agent-status-bar">
          <span class="status-dots"><i></i><i></i><i></i></span>
          <span class="agent-status-text">{{ currentStatus }}</span>
        </div>
        <div v-if="messages.length === 0 && !sending" class="agent-empty">
          <p>{{ t('agent.placeholder') }}</p>
          <p class="hint" v-if="workspaceName">{{ t('agent.workspaceLabel') }}{{ workspaceName }}</p>
          <p class="hint warn" v-else>{{ t('agent.noWorkspaceLabel') }}</p>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="agent-msg" :class="msg.role">
          <template v-for="(evt, i) in msg.events" :key="i">
            <div v-if="evt.type === 'task_started'" class="agent-event task-lifecycle">
              <span class="evt-lifecycle-icon">&#x25B6;</span>
              <span class="evt-label">{{ t('agent.labelTask') }}</span>
              <span class="evt-task-title">{{ evt.metadata?.title || evt.content }}</span>
              <span v-if="evt.metadata?.index != null" class="evt-task-progress">{{ evt.metadata.index }}/{{ evt.metadata.total }}</span>
            </div>
            <div v-else-if="evt.type === 'task_done'" class="agent-event task-lifecycle done">
              <span class="evt-lifecycle-icon">&#x2714;</span>
              <span class="evt-label">{{ t('agent.labelTaskDone') }}</span>
              <span class="evt-task-id">{{ evt.metadata?.task_id }}</span>
            </div>
            <div v-else-if="evt.type === 'thought' || evt.type === 'thinking'" class="agent-event thinking">
              <span class="evt-thinking-dot"></span>
              <span class="evt-label">{{ evt.type === 'thought' ? t('agent.labelThought') : t('agent.labelReasoning') }}</span>
              <span class="evt-content-text">{{ evt.content }}</span>
            </div>
            <div v-else-if="evt.type === 'tool_call'" class="agent-event tool-call">
              <div class="evt-tool-header">
                <span class="evt-tool-icon">&#x26A1;</span>
                <span class="evt-label">{{ t('agent.labelToolCall') }}</span>
                <span class="evt-tool-name">{{ evt.metadata?.tool_name || evt.metadata?.tool || evt.content }}</span>
                <span v-if="evt.metadata?.risk" class="evt-risk-badge" :class="'risk-' + evt.metadata.risk">{{ evt.metadata.risk }}</span>
              </div>
              <div class="evt-tool-desc">{{ getToolDescription(evt.metadata?.tool_name || evt.metadata?.tool) }}</div>
              <div v-if="(evt.metadata?.arguments || evt.metadata?.args) && Object.keys((evt.metadata?.arguments || evt.metadata?.args) as any).length" class="evt-tool-args">
                <span class="evt-args-label">{{ t('agent.labelParams') }}</span>
                <code class="evt-args-code">{{ formatToolArgs((evt.metadata?.arguments || evt.metadata?.args) as any) }}</code>
              </div>
            </div>
            <div v-else-if="evt.type === 'tool_result'" class="agent-event tool-result" :class="{ 'evt-error': evt.metadata?.error }">
              <div class="evt-result-header">
                <span v-if="evt.metadata?.error" class="evt-tool-icon error">&#x2717;</span>
                <span v-else class="evt-tool-icon success">&#x2713;</span>
                <span class="evt-label">{{ evt.metadata?.error ? t('agent.labelExecFailed') : t('agent.labelExecDone') }}</span>
                <span class="evt-result-tool">{{ evt.metadata?.tool_name || evt.metadata?.tool }}</span>
                <span v-if="evt.metadata?.duration_ms" class="evt-duration">{{ evt.metadata.duration_ms }}ms</span>
              </div>
              <div class="evt-result-preview">{{ truncateResult(evt.content) }}</div>
            </div>
            <div v-else-if="evt.type === 'warning'" class="agent-event warning">
              <span class="evt-warning-icon">&#x26A0;</span>
              <span class="evt-content-text">{{ evt.content }}</span>
            </div>
          </template>
          <div v-if="msg.content" class="agent-bubble">{{ msg.content }}</div>
          <div v-if="msg.isStreaming" class="agent-streaming">
            <span class="dot-wave"><i></i><i></i><i></i></span>
          </div>
        </div>
      </div>
      <!-- Approval bar: hidden when file-edit approval is routed to inline diff in editor -->
      <AgentApprovalInline
        v-if="pendingApproval && !showInlineDiff"
        :pending="pendingApproval"
        @decide="handleApprovalDecision"
      />
      <div class="agent-input-area">
        <div class="agent-workspace-bar" :class="{ active: !!workspaceName, inactive: !workspaceName }">
          <span class="ws-dot"></span>
          <span class="ws-name" v-if="workspaceName">{{ workspaceName }}</span>
          <span class="ws-name muted" v-else>{{ t('agent.noProject') }}</span>
        </div>
        <div v-if="contextText" class="agent-context-note">
          {{ t('agent.contextEditor', { type: editorSelection.text ? t('agent.contextSelection') : t('agent.contextDocument'), count: contextText.length }) }}
        </div>
        <!-- File attachments -->
        <div class="agent-attachments" v-if="files.length">
          <div class="agent-file" v-for="f in files" :key="f.name">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span>{{ f.name }}</span>
            <button class="agent-file-remove" :title="t('agent.removeAttachment')" @click="removeFile(f.name)">×</button>
          </div>
        </div>
        <div class="agent-input-row">
          <button class="agent-attach-btn" @click="attachFile" :title="t('agent.addAttachment')" :disabled="sending">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
          </button>
          <input
            ref="agentInputEl"
            v-model="input"
            @keydown.enter="sendMessage"
            :disabled="sending"
            :placeholder="t('agent.inputPlaceholder')"
            class="agent-input"
          />
          <button
            v-if="agentSpeech.isSupported"
            class="agent-attach-btn"
            :class="{ 'voice-active': agentSpeech.status.value === 'listening' }"
            :title="agentSpeech.status.value === 'listening' ? t('agent.voiceStop') : t('agent.voiceStart')"
            :disabled="sending"
            @click="toggleAgentSpeech"
          >
            <Mic :size="14" :stroke-width="2" />
          </button>
          <button
            class="agent-send-btn"
            :class="{ stopping: sending }"
            @click="sending ? abortSession() : sendMessage()"
            :disabled="!sending && !input.trim()"
            :title="sending ? t('agent.stopGenerate') : t('agent.send')"
          >
            <svg v-if="sending" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <rect x="3" y="3" width="18" height="18" rx="3"/>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Docs Tab -->
    <div v-show="tab === 'docs'" class="agent-docs">
      <div class="docs-toolbar">
        <span class="docs-title">{{ t('agent.docsTitle') }}</span>
        <span class="docs-subtitle">{{ t('agent.docsSubtitle') }}</span>
        <div class="docs-toolbar-actions">
          <button class="btn primary u-interactive" :disabled="ragUploading" @click="ragFileInput?.click()">
            <UiSpinner v-if="ragUploading" size="sm" />
            <span>{{ ragUploading ? t('agent.uploading') : t('agent.uploadFile') }}</span>
          </button>
          <button class="btn ghost u-interactive" :class="{ refreshing: ragLoading }" @click="fetchDocs" :disabled="ragLoading">{{ t('agent.refresh') }}</button>
        </div>
        <input ref="ragFileInput" type="file" style="display:none"
          accept=".pdf,.docx,.doc,.txt,.md,.log,.html,.htm,.epub,.rtf,.tex,.csv,.pptx,.xlsx,.srt,.json,.xml"
          @change="handleRagUpload" />
      </div>
      <Transition name="v-slide-up">
        <div v-if="ragUploadError" class="docs-error">{{ ragUploadError }}</div>
      </Transition>
      <div v-if="ragLoading && ragDocuments.length === 0" class="docs-list">
        <div v-for="i in 4" :key="i" class="doc-card skel" :style="{ '--stagger-i': i - 1 }">
          <div class="doc-info" style="flex:1">
            <UiSkeleton shape="line" height="13" width="70%" />
            <UiSkeleton shape="line" height="10" width="30%" />
          </div>
        </div>
      </div>
      <div v-else-if="ragDocuments.length === 0" class="docs-empty anim-fade-in-up">
        <span class="empty-glyph">▤</span>
        <p>{{ t('agent.noDocs') }}</p>
      </div>
      <TransitionGroup v-else name="v-list-stagger" tag="div" class="docs-list">
        <div v-for="(doc, idx) in ragDocuments" :key="doc.id" class="doc-card u-interactive" :style="{ '--stagger-i': idx }">
          <div class="doc-info">
            <span class="doc-title">{{ doc.title || doc.id }}</span>
            <span class="doc-meta">{{ doc.chunk_count }} {{ t('agent.chunks') }}</span>
          </div>
          <button class="doc-del-btn u-interactive" @click="deleteDoc(doc.id)" :title="t('agent.delete')">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>

    <!-- Templates Tab -->
    <div v-show="tab === 'templates'" class="agent-templates">
      <div class="docs-toolbar">
        <span class="docs-title">{{ t('agent.templatesTitle') }}</span>
        <button class="btn ghost u-interactive" :class="{ refreshing: templatesLoading }" @click="loadPaperTemplates" :disabled="templatesLoading">{{ t('agent.refreshTemplates') }}</button>
      </div>
      <div v-if="templatesLoading && templates.length === 0" class="template-grid">
        <UiSkeleton v-for="i in 4" :key="i" shape="card" height="58" :style="{ '--stagger-i': i - 1 }" class="tpl-skel" />
      </div>
      <div v-else-if="templates.length === 0" class="docs-empty anim-fade-in-up">
        <span class="empty-glyph">◳</span>
        <p>{{ t('agent.noTemplates') }}</p>
        <button class="btn ghost u-interactive" style="margin-top:8px" @click="ingestPaperAssets">{{ t('agent.indexTemplates') }}</button>
      </div>
      <TransitionGroup v-else name="v-list-stagger" tag="div" class="template-grid">
        <div v-for="(t, idx) in templates" :key="t.id" class="template-card u-interactive" :style="{ '--stagger-i': idx }" @click="previewingTemplate = t">
          <span class="template-icon">{{ t.icon }}</span>
          <div class="template-info">
            <span class="template-name">{{ t.name }}</span>
            <span class="template-venue">{{ t.venue }}</span>
          </div>
        </div>
      </TransitionGroup>
      <Transition name="v-scale-in">
        <div v-if="previewingTemplate" class="template-preview">
          <div class="template-preview-header">
            <span>{{ previewingTemplate.icon }} {{ previewingTemplate.name }}</span>
            <button class="btn ghost u-interactive" @click="previewingTemplate = null">&times;</button>
          </div>
          <div class="template-preview-desc">{{ previewingTemplate.description }}</div>
          <button class="btn primary u-interactive" style="margin-top:8px;width:100%" @click="createFromTemplate(previewingTemplate)">{{ t('agent.createFromThisTemplate') }}</button>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

import { useAgentChat } from '../composables/useAgentChat'
import { useEditor } from '../composables/useEditor'
import { useEditorState } from '../composables/useEditorState'
import { useFileTree } from '../composables/useFileTree'
import AgentApprovalInline from './AgentApprovalInline.vue'
import AgentSessionList from './AgentSessionList.vue'
import { Pin, PinOff, Mic } from './ui/icons'
import { API_BASE } from '../utils/api'
import type { AgentSessionInfo } from '../types'
import { useSpeechRecognition } from '../composables/useSpeechRecognition'
import { setSpeechBusy } from '../composables/useSpeechBusy'
import UiSpinner from './ui/UiSpinner.vue'
import UiSkeleton from './ui/UiSkeleton.vue'

let voiceBaseInput = ''
const agentSpeech = useSpeechRecognition({
  onResult: (text) => { input.value = voiceBaseInput + (voiceBaseInput ? ' ' : '') + text },
  onEnd: () => { voiceBaseInput = '' },
})

function toggleAgentSpeech() {
  if (agentSpeech.status.value === 'listening') {
    voiceBaseInput = ''
    agentSpeech.stop()
    setSpeechBusy(false)
    agentInputEl.value?.focus()
  } else {
    voiceBaseInput = input.value
    setSpeechBusy(true)
    agentSpeech.start()
  }
}

// Tauri is available when window.__TAURI_INTERNALS__ exists
const _isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

const props = defineProps<{
  open: boolean
  standalone?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'switch-to-editor'): void
}>()

// ── Floating panel: native OS window (Tauri) or in-app overlay (web) ─────────

const isStandalone = computed(() => props.standalone === true)

// In-app float fallback (web mode only)
const isFloating = ref(false)
const floatX = ref(0)
const floatY = ref(0)
let _dragActive = false
let _dragOffX = 0
let _dragOffY = 0

// Tauri native OS window ref
let _agentWindow: import('@tauri-apps/api/webviewWindow').WebviewWindow | null = null

async function openAgentWindow() {
  const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')

  // Close any existing agent window first
  try { const old = await WebviewWindow.getByLabel('agent'); if (old) await old.close() } catch {}

  // Pass agent-only flag and optional session via URL params — sessionStorage is
  // window-isolated in Tauri so URL params are the only reliable cross-window channel.
  const params = new URLSearchParams({ 'agent-only': '1' })
  const { sessionId } = useAgentChat()
  if (sessionId.value) params.set('session', sessionId.value)
  const url = `${window.location.origin}/?${params}`

  _agentWindow = new WebviewWindow('agent', {
    url,
    title: t('agent.title'),
    width: 400,
    height: 560,
    minWidth: 320,
    minHeight: 400,
    resizable: true,
    decorations: false,
    shadow: true,
    center: true,
    visible: true,
    skipTaskbar: false,
    alwaysOnTop: true,
  })

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('window timeout')), 5000)
    _agentWindow!.once('tauri://created', () => { clearTimeout(timeout); resolve() })
    _agentWindow!.once('tauri://error', (e) => { clearTimeout(timeout); reject(new Error(String(e))) })
  })

  _agentWindow.once('tauri://destroyed', () => {
    _agentWindow = null
    emit('update:open', true)
  })

  emit('update:open', false)
}

async function closeAgentWindow() {
  try {
    const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow')
    const w = await WebviewWindow.getByLabel('agent')
    if (w) await w.close()
  } catch {}
  _agentWindow = null
  emit('update:open', true)
}

async function toggleFloat() {
  if (_isTauri) {
    // Desktop: use real OS window so it can move outside app bounds
    if (_agentWindow) {
      await closeAgentWindow()
    } else {
      try {
        await openAgentWindow()
      } catch (err) {
        console.error('Failed to open agent window:', err)
        _agentWindow = null
        // Tauri failed — fall through to in-app float
        _openInAppFloat()
      }
    }
  } else {
    // Browser: in-app draggable overlay
    if (isFloating.value) {
      isFloating.value = false
      emit('update:open', true)
    } else {
      _openInAppFloat()
    }
  }
}

function _openInAppFloat() {
  floatX.value = Math.max(0, window.innerWidth - 440)
  floatY.value = 80
  isFloating.value = true
}

// In-app drag (web fallback only)
function onHeaderMouseDown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  if (!isFloating.value) return
  _dragActive = true
  _dragOffX = e.clientX - floatX.value
  _dragOffY = e.clientY - floatY.value
  window.addEventListener('mousemove', _onDragMove)
  window.addEventListener('mouseup', _onDragUp, { once: true })
  e.preventDefault()
}

function _onDragMove(e: MouseEvent) {
  if (!_dragActive) return
  floatX.value = Math.max(0, Math.min(e.clientX - _dragOffX, window.innerWidth - 380))
  floatY.value = Math.max(0, Math.min(e.clientY - _dragOffY, window.innerHeight - 100))
}

function _onDragUp() {
  _dragActive = false
  window.removeEventListener('mousemove', _onDragMove)
}

// Standalone window: drag via Tauri OS-level API
function onHeaderMouseDown_standalone(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('button')) return
  import('@tauri-apps/api/window').then(({ getCurrentWindow }) => {
    getCurrentWindow().startDragging()
  })
}

function _headerMouseDown(e: MouseEvent) {
  if (isStandalone.value) {
    onHeaderMouseDown_standalone(e)
  } else {
    onHeaderMouseDown(e)
  }
}

// Standalone: dock back to main window
async function onDockBack() {
  const { getCurrentWindow } = await import('@tauri-apps/api/window')
  localStorage.setItem('agent-dock-back', Date.now().toString())
  await getCurrentWindow().close()
}

let _unlistenStorage: (() => void) | null = null

onMounted(async () => {
  if (isStandalone.value) {
    // Read session from URL params (passed by openAgentWindow)
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session')
    if (sid) await resumeSession(sid)
  } else {
    // Listen for dock-back signal from standalone window
    const handler = (e: StorageEvent) => {
      if (e.key === 'agent-dock-back' && e.newValue) {
        localStorage.removeItem('agent-dock-back')
        emit('update:open', true)
      }
    }
    window.addEventListener('storage', handler)
    _unlistenStorage = () => window.removeEventListener('storage', handler)
  }
})


const {
  messages, sending, pendingApproval,
  ragDocuments, ragLoading,
  sendMessage: agentSendMessage,
  sendApproval, abortSession,
  resumeSession,
  sessionId,
  fetchSessions: _fetchSessions,
  fetchRAGDocuments: _fetchRAGDocs,
  deleteRAGDocument,
  uploadRAGFile,
} = useAgentChat()

const { selection: editorSelection, content: editorContent, activeTab: editorActiveTab, reloadOpenTabs } = useEditor()

const { tabs: editorTabs, setActiveEdit, clearActiveEdit } = useEditorState()

const { rootDir, refresh: refreshFileTree } = useFileTree()

const workspaceName = computed(() => {
  if (!rootDir.value) return null
  return rootDir.value.split(/[\\/]/).filter(Boolean).pop() || rootDir.value
})

const tab = ref<'chat' | 'docs' | 'templates' | 'sessions'>('chat')
const input = ref('')
const agentInputEl = ref<HTMLInputElement | null>(null)
const messagesRef = ref<HTMLElement | null>(null)
const sessionListRef = ref<InstanceType<typeof AgentSessionList> | null>(null)
// 自动滚动：用户未手动上滚时保持跟底
const _userScrolledUp = ref(false)

function _scrollToBottom(smooth = false) {
  const el = messagesRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
}

function _onMessagesScroll() {
  const el = messagesRef.value
  if (!el) return
  // 距离底部 60px 以内视为"在底部"
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  _userScrolledUp.value = !atBottom
}
const sessions = ref<AgentSessionInfo[]>([])
const files = ref<{ name: string; path: string }[]>([])
const ragFileInput = ref<HTMLInputElement | null>(null)
const ragUploading = ref(false)
const ragUploadError = ref('')

const contextText = computed(() => {
  if (!editorActiveTab.value) return ''
  return editorSelection.value.text || editorContent.value
})

async function handleRagUpload() {
  const fileInput = ragFileInput.value
  if (!fileInput?.files?.length) return
  const file = fileInput.files[0]
  ragUploading.value = true
  ragUploadError.value = ''
  const result = await uploadRAGFile(file)
  ragUploading.value = false
  if (!result.ok) {
    ragUploadError.value = result.error || t('agent.uploadFailed')
    setTimeout(() => { ragUploadError.value = '' }, 4000)
  }
  fileInput.value = ''
}

// ── Tool descriptions ──
const TOOL_DESCRIPTIONS: Record<string, string> = {
  translate_text: t('agent.tool.translate_text'),
  parse_document: t('agent.tool.parse_document'),
  search_documents: t('agent.tool.search_documents'),
  read_argument_graph: t('agent.tool.read_argument_graph'),
  read_argument_ledger: t('agent.tool.read_argument_ledger'),
  crawl_arxiv: t('agent.tool.crawl_arxiv'),
  read_file: t('agent.tool.read_file'),
  write_file: t('agent.tool.write_file'),
  str_replace: t('agent.tool.str_replace'),
  grep_files: t('agent.tool.grep_files'),
  glob_files: t('agent.tool.glob_files'),
  list_directory: t('agent.tool.list_directory'),
  run_command: t('agent.tool.run_command'),
  git_op: t('agent.tool.git_op'),
  undo_last_change: t('agent.tool.undo_last_change'),
  export_pdf: t('agent.tool.export_pdf'),
  web_fetch: t('agent.tool.web_fetch'),
  web_search: t('agent.tool.web_search'),
}

function getToolDescription(toolName?: string): string {
  if (!toolName) return ''
  return TOOL_DESCRIPTIONS[toolName] || ''
}

function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args)
  if (!entries.length) return ''
  return entries
    .map(([k, v]) => {
      const val = typeof v === 'string' ? `"${v.length > 40 ? v.slice(0, 40) + '…' : v}"` : JSON.stringify(v)
      return `${k}: ${val}`
    })
    .join('\n')
}

function truncateResult(content: string): string {
  if (!content) return ''
  if (content.length <= 300) return content
  return content.slice(0, 300) + '…'
}

// ── Current status from streaming events ──
const currentStatus = computed(() => {
  const streaming = messages.value.find(m => m.isStreaming)
  if (!streaming) return ''
  if (pendingApproval.value) return t('agent.awaitingApproval', { tool: pendingApproval.value.tool_name })
  for (let i = streaming.events.length - 1; i >= 0; i--) {
    const evt = streaming.events[i]
    if (evt.type === 'thinking' || evt.type === 'thought') return 'Thinking... ' + (evt.content.length > 100 ? evt.content.slice(0, 100) + '...' : evt.content)
    if (evt.type === 'tool_call') return 'Calling ' + ((evt.metadata?.tool_name || evt.metadata?.tool || evt.content) as string)
    if (evt.type === 'tool_result') return 'Done: ' + ((evt.metadata?.tool_name || evt.metadata?.tool || 'tool') as string)
    if (evt.type === 'task_started') return 'Starting task: ' + (evt.metadata?.title || '')
    if (evt.type === 'task_done') return 'Task completed'
    if (evt.type === 'warning') return 'Warning: ' + evt.content
  }
  return ''
})

// ── Approval ──
const showInlineDiff = computed(() => {
  const p = pendingApproval.value
  if (!p) return false
  const tool = p.tool_name
  if (tool !== 'str_replace' && tool !== 'write_file') return false
  const filePath = (p.args?.file_path as string) || ''
  if (!filePath) return false
  return editorTabs.value.some(t => t.path === filePath)
})

async function handleApprovalDecision(decision: 'allow_once' | 'allow_session' | 'deny') {
  const pending = pendingApproval.value
  if (!pending) return
  await sendApproval(pending.event_id, decision)
}

// Route file-edit approvals to inline diff editor overlay
watch(pendingApproval, (p) => {
  if (p && showInlineDiff.value) {
    const preview = p.preview as Record<string, unknown> | undefined
    const args = p.args as Record<string, unknown> | undefined
    setActiveEdit({
      editId: p.event_id,
      eventId: p.event_id,
      sessionId: sessionId.value || '',
      operation: (p.tool_name === 'write_file' ? 'write_file' : 'str_replace') as 'str_replace' | 'write_file',
      filePath: (args?.file_path as string) || '',
      oldText: (preview?.old_text as string) ?? (args?.old_string as string) ?? '',
      newText: (preview?.new_text as string) ?? (args?.new_string as string) ?? (args?.content as string) ?? '',
    })
  } else {
    clearActiveEdit()
  }
})

// ── Sessions ──
async function refreshSessions() {
  sessions.value = await _fetchSessions()
  sessionListRef.value?.fetchSessions()
}

async function handleSessionResume(sessionId: string) {
  await resumeSession(sessionId)
  tab.value = 'chat'
  _userScrolledUp.value = false
  await nextTick()
  _scrollToBottom()
}

// ── Send message ──
async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''

  // Reset mid-stream file-write event counter for this new task.
  _lastSeenToolResultCount = 0

  // Pass file paths to agent — let it read with read_file tool
  let fullMsg = text
  if (files.value.length) {
    const pathList = files.value.map(f => `- ${f.path}`).join('\n')
    fullMsg = `${text}\n\n[${t('agent.attachedFilesHint')}\n${pathList}]`
    files.value = []
  }

  await agentSendMessage(
    fullMsg,
    contextText.value,
    '',
    rootDir.value || undefined,
    editorActiveTab.value?.path || undefined,
  )
  refreshFileTree()
  reloadOpenTabs()
  await nextTick()
  _scrollToBottom()
}

// ── File operations ─────────────────────────────────────────
async function attachFile() {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({
      multiple: true,
      filters: [{ name: 'Text', extensions: ['md','txt','tex','py','js','ts','json','yaml','yml','xml','html','css','csv','pdf'] }]
    })
    if (!selected) return
    const paths = (Array.isArray(selected) ? selected : [selected]) as string[]
    for (const p of paths) {
      const name = p.split(/[\\/]/).pop() || p
      if (files.value.some(f => f.name === name)) continue
      files.value.push({ name, path: p })
    }
  } catch { /* dialog not available */ }
}

function removeFile(name: string) {
  files.value = files.value.filter(f => f.name !== name)
}

async function fetchDocs() {
  await _fetchRAGDocs()
}

async function deleteDoc(id: string) {
  await deleteRAGDocument(id)
}

// ── Paper templates ──
const templates = ref<{ id: string; name: string; venue: string; description: string; icon: string }[]>([])
const templatesLoading = ref(false)
const previewingTemplate = ref<{ id: string; name: string; venue: string; description: string; icon: string } | null>(null)

async function loadPaperTemplates() {
  templatesLoading.value = true
  try {
    const resp = await fetch(`${API_BASE}/api/paper-assets/templates`)
    if (resp.ok) {
      const data = await resp.json()
      templates.value = data.templates || []
    }
  } catch (e) { console.warn('loadPaperTemplates failed:', e) }
  finally { templatesLoading.value = false }
}

async function ingestPaperAssets() {
  try {
    await fetch(`${API_BASE}/api/paper-assets/ingest`, { method: 'POST' })
    loadPaperTemplates()
  } catch (e) { console.warn('ingestPaperAssets failed:', e) }
}

function createFromTemplate(t: any) {
  tab.value = 'chat'
  fetch(`${API_BASE}/api/paper-scaffold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: t.id, title: '' }),
  }).then(r => r.json()).then(data => {
    if (data.markdown) {
      window.dispatchEvent(new CustomEvent('paper-scaffold', { detail: { markdown: data.markdown, templateId: t.id } }))
    }
  }).catch(() => {})
  previewingTemplate.value = null
}

// ── Watchers ──
watch(() => props.open, async (isOpen) => {
  if (isOpen) await fetchDocs()
})

watch(tab, (t) => {
  if (t === 'templates' && templates.value.length === 0) loadPaperTemplates()
})

// 流式输出自动跟底：监听 messages 深度变化，若用户没有手动上滚则自动滚底
watch(
  messages,
  async () => {
    if (_userScrolledUp.value) return
    await nextTick()
    _scrollToBottom()
  },
  { deep: true },
)

// 发送新消息时强制重置到底部（无论用户之前是否上滚）
watch(sending, (nowSending) => {
  if (nowSending) {
    _userScrolledUp.value = false
    nextTick(() => _scrollToBottom())
  }
})

// 审批弹出时停止自动滚底 — 让用户看清 tool_call 上下文
watch(pendingApproval, (val) => {
  if (val) _userScrolledUp.value = true
})

// Mid-stream refresh: when the Agent completes a file-write tool call, immediately
// refresh the file tree and reload any open Monaco tabs so the user sees changes
// without waiting for the full task to finish.
const _FILE_WRITE_TOOLS = new Set(['write_file', 'str_replace', 'create_file'])
let _lastSeenToolResultCount = 0

watch(
  messages,
  () => {
    if (!sending.value) return
    // Count tool_result events across all streaming messages for file-writing tools.
    let count = 0
    for (const msg of messages.value) {
      for (const evt of msg.events) {
        if (evt.type === 'tool_result' && _FILE_WRITE_TOOLS.has((evt.metadata?.tool_name as string) || '')) {
          count++
        }
      }
    }
    if (count > _lastSeenToolResultCount) {
      _lastSeenToolResultCount = count
      refreshFileTree()
      reloadOpenTabs()
    }
  },
  { deep: true },
)

onUnmounted(() => {
  window.removeEventListener('mousemove', _onDragMove)
  window.removeEventListener('mouseup', _onDragUp)
  _unlistenStorage?.()
  _unlistenStorage = null
})
</script>

<style scoped>
.agent-panel {
  position: fixed; top: 0; right: 0;
  width: min(420px, 100vw); height: calc(100vh - 62px);
  margin-top: 62px;
  background: var(--c-glass);
  border-left: none;
  box-shadow: -20px 0 80px rgba(0, 0, 0, 0.4), inset 1px 0 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(32px);
  -webkit-backdrop-filter: blur(32px);
  display: flex; flex-direction: column;
  z-index: 200;
  transform: translateX(100%);
  transition: transform var(--motion-page, 320ms) var(--ease-spring);
}
.agent-panel.open { transform: translateX(0); }

/* Standalone mode: rounded floating panel look */
.agent-panel.standalone {
  position: relative;
  width: 100%;
  height: 100vh;
  right: auto;
  top: auto;
  margin-top: 0;
  transform: none !important;
  border-radius: var(--radius-xl);
  border: 1px solid var(--c-glass-border);
  box-shadow: var(--elevation-4);
  overflow: hidden;
}

/* In-app floating mode: draggable overlay */
.agent-panel.floating {
  right: auto;
  top: auto;
  width: 400px;
  height: 560px;
  margin-top: 0;
  transform: none !important;
  border-radius: var(--radius-xl);
  border: 1px solid var(--c-glass-border);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255,255,255,0.06);
  overflow: hidden;
  z-index: 500;
}
.agent-header.draggable {
  cursor: grab;
  user-select: none;
}
.agent-header.draggable:active {
  cursor: grabbing;
}

.agent-header {
  display: flex; align-items: center; gap: 6px;
  padding: 16px 20px 12px;
  border-bottom: none;
  background: linear-gradient(to bottom, var(--c-surface-1) 0%, transparent 100%);
  flex-shrink: 0;
}

.agent-tabs {
  display: flex; gap: 4px; flex: 1;
  background: var(--c-surface-2);
  padding: 4px;
  border-radius: 12px;
}
.agent-tab {
  padding: 6px 14px; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 600; cursor: pointer;
  background: transparent; color: var(--c-text-2);
  transition: all var(--motion-fast);
  white-space: nowrap;
}
.agent-tab:hover { color: var(--c-text-0); }
.agent-tab.active {
  background: var(--c-surface-3);
  color: var(--c-text-0);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.agent-header-actions { display: flex; align-items: center; gap: 2px; flex-shrink: 0; }

.agent-hdr-btn {
  display: flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; border-radius: 4px;
  transition: all var(--motion-fast);
}
.agent-hdr-btn:hover { color: var(--c-text-0); background: var(--c-surface-2); }

.agent-close-btn {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center;
  transition: all var(--motion-fast);
}
.agent-close-btn:hover { color: var(--c-text-0); background: var(--c-surface-2); }

.agent-chat {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  background: linear-gradient(to bottom, transparent, rgba(0,0,0,0.1));
}
.agent-messages {
  flex: 1; overflow-y: auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 24px;
}
.agent-empty { text-align: center; color: var(--c-text-3); padding: 40px 20px; }
.agent-empty p:first-child {
  font-family: var(--font-serif);
  font-style: italic;
  font-size: 15px;
  color: var(--c-text-2);
}
.agent-empty .hint { font-size: 12px; }

.agent-msg { max-width: 92%; }
.agent-msg.user { align-self: flex-end; }
.agent-msg.assistant { align-self: flex-start; max-width: 100%; }

.agent-bubble {
  padding: 10px 14px; border-radius: 12px;
  font-size: 14px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word;
}
.agent-msg.user .agent-bubble {
  background: var(--c-accent); color: #fff;
  border-radius: 16px 16px 4px 16px;
  padding: 12px 18px;
  box-shadow: 0 8px 24px var(--accent-glow);
}
.agent-msg.assistant .agent-bubble {
  background: transparent; color: var(--c-text-0);
  padding: 4px 8px;
  border-radius: 0;
  font-size: 14.5px;
  line-height: 1.7;
}

/* Event stream — ink-styled cards */
.agent-event {
  font-size: 12px; padding: 8px 12px;
  margin-bottom: 8px; border-radius: 10px;
  background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 12px var(--c-shadow);
  position: relative;
  animation: evt-fade-in var(--motion-base) var(--ease-out);
}
@keyframes evt-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* @property enables smooth mask-image gradient interpolation */
@property --ink-stop {
  syntax: '<percentage>';
  inherits: false;
  initial-value: 0%;
}

.agent-event.thinking {
  --ink-stop: 100%;
  color: var(--c-text-2); display: flex; align-items: flex-start; gap: 6px;
  font-style: normal; border-left: 2px solid var(--accent-0);
  mask-image: linear-gradient(to bottom, #000 var(--ink-stop), transparent calc(var(--ink-stop) + 16px));
  -webkit-mask-image: linear-gradient(to bottom, #000 var(--ink-stop), transparent calc(var(--ink-stop) + 16px));
  animation: evt-ink-bleed 400ms var(--ease-out) both;
}
@keyframes evt-ink-bleed {
  from { --ink-stop: 0%; opacity: 0.3; }
  to   { --ink-stop: 100%; opacity: 1; }
}
.agent-event.tool-call {
  border-left: 2px solid #3b82f6; background: color-mix(in srgb, #3b82f6 6%, var(--c-surface-1));
  animation: evt-slide-in-left 240ms var(--ease-out);
}
@keyframes evt-slide-in-left {
  from { opacity: 0; transform: translateX(-16px); }
  to   { opacity: 1; transform: translateX(0); }
}
.agent-event.tool-result {
  border-left: 2px solid var(--c-success); background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
  animation: evt-scale-in 240ms var(--ease-spring);
}
@keyframes evt-scale-in {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
.agent-event.tool-result.evt-error {
  border-left: 2px solid var(--vermilion-0); background: color-mix(in srgb, var(--vermilion-0) 6%, var(--c-surface-1));
  animation: evt-shake 300ms var(--ease-out);
}
@keyframes evt-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-3px); }
  40% { transform: translateX(3px); }
  60% { transform: translateX(-1px); }
}

.evt-label {
  font-weight: 600; font-size: 11px; text-transform: uppercase;
  color: var(--c-text-2); flex-shrink: 0;
}
.evt-thinking-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: var(--accent-0); animation: dot-breathe 1.6s ease-in-out infinite;
}
@keyframes dot-breathe {
  0%, 100% { opacity: 0.3; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}
.evt-content-text { color: var(--c-text-2); }
.evt-tool-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.evt-tool-icon { font-size: 13px; flex-shrink: 0; }
.evt-tool-icon.success { color: var(--c-success); }
.evt-tool-icon.error { color: var(--c-danger); }
.evt-tool-name { font-weight: 600; color: var(--c-accent); font-size: 13px; }
.evt-tool-desc { font-size: 11px; color: var(--c-text-2); margin: 2px 0 5px 22px; }
.evt-tool-args {
  background: var(--c-surface-2); border-radius: 4px; padding: 5px 8px;
  margin-top: 4px; border: 1px solid var(--c-surface-3);
}
.evt-args-label { font-size: 10px; color: var(--c-text-3); text-transform: uppercase; font-weight: 600; margin-right: 6px; }
.evt-args-code { font-size: 11px; color: var(--c-text-2); white-space: pre-wrap; word-break: break-all; }
.evt-result-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.evt-result-tool { font-weight: 600; color: var(--c-text-2); font-size: 12px; }
.evt-duration { font-size: 11px; color: var(--c-text-3); margin-left: auto; }
.evt-result-preview { font-size: 11px; color: var(--c-text-2); line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow: hidden; }

/* Task lifecycle */
.agent-event.task-lifecycle {
  display: flex; align-items: center; gap: 6px;
  border-left: 2px solid var(--c-accent); background: color-mix(in srgb, var(--c-accent) 6%, var(--c-surface-1));
}
.agent-event.task-lifecycle.done {
  border-left-color: var(--c-success); background: color-mix(in srgb, var(--c-success) 6%, var(--c-surface-1));
}
.evt-lifecycle-icon { font-size: 14px; flex-shrink: 0; }
.evt-task-title { font-size: 13px; font-weight: 500; color: var(--c-text-0); }
.evt-task-id { font-size: 11px; color: var(--c-text-3); font-family: monospace; }
.evt-task-progress {
  font-size: 11px; color: var(--c-accent-hover);
  margin-left: auto; font-variant-numeric: tabular-nums; font-weight: 600;
}

/* Risk badge */
.evt-risk-badge { font-size: 9px; text-transform: uppercase; font-weight: 600; padding: 1px 5px; border-radius: 3px; }
.evt-risk-badge.risk-safe { background: rgba(74, 222, 128, 0.15); color: var(--c-success); }
.evt-risk-badge.risk-moderate { background: rgba(245, 158, 11, 0.15); color: var(--c-warn); }
.evt-risk-badge.risk-destructive { background: rgba(248, 113, 113, 0.15); color: var(--c-danger); }
.evt-risk-badge.risk-banned { background: var(--c-surface-0); color: var(--c-danger); }

/* Warning */
.agent-event.warning {
  display: flex; align-items: center; gap: 8px;
  border-left: 2px solid var(--c-warn);
  background: color-mix(in srgb, var(--c-warn) 6%, var(--c-surface-1));
}
.evt-warning-icon { font-size: 14px; flex-shrink: 0; color: var(--c-warn); }

.agent-sessions { flex: 1; overflow-y: auto; padding: 0; }

/* Thinking progress bar — scanning gradient across the top of the chat area */
.agent-thinking-bar {
  height: 2px;
  flex-shrink: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--c-accent) 45%,
    color-mix(in srgb, var(--c-accent) 50%, transparent) 60%,
    transparent 100%
  );
  background-size: 40% 100%;
  background-repeat: no-repeat;
  animation: thinking-scan 1.4s ease-in-out infinite;
}
@keyframes thinking-scan {
  0%   { background-position: -40% 0; }
  100% { background-position: 140% 0; }
}

.agent-status-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; margin-bottom: 8px;
  background: color-mix(in srgb, var(--c-accent) 12%, var(--c-surface-1));
  border: 1px solid color-mix(in srgb, var(--c-accent) 30%, transparent);
  border-radius: 20px; width: fit-content; max-width: 100%;
  position: relative; overflow: hidden;
}
.agent-status-bar::after {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.07) 50%, transparent 100%);
  background-size: 200% 100%;
  animation: shimmer-sweep 2s linear infinite;
  pointer-events: none;
}
@keyframes shimmer-sweep {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.agent-status-text { font-size: 12px; color: var(--c-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }

/* Three-dot wave — status bar */
.status-dots { display: flex; gap: 3px; align-items: center; flex-shrink: 0; }
.status-dots i {
  width: 4px; height: 4px; border-radius: 50%;
  background: var(--c-accent); display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.status-dots i:nth-child(2) { animation-delay: 0.15s; }
.status-dots i:nth-child(3) { animation-delay: 0.30s; }

/* Three-dot wave — streaming indicator */
.agent-streaming { display: flex; padding: 8px 14px; }
.dot-wave { display: flex; gap: 5px; align-items: center; }
.dot-wave i {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--c-accent); display: block;
  animation: wave-bounce 1.1s ease-in-out infinite;
}
.dot-wave i:nth-child(2) { animation-delay: 0.18s; }
.dot-wave i:nth-child(3) { animation-delay: 0.36s; }
@keyframes wave-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.25; }
  30%            { transform: translateY(-6px); opacity: 1; }
}

/* Input area — suspended inkstone */
.agent-input-area {
  display: flex; flex-direction: column; gap: 8px;
  padding: 16px 20px 24px;
  border-top: none;
  background: linear-gradient(to top, var(--c-surface-1) 40%, transparent 100%);
  position: relative;
}
.agent-context-note { width: 100%; color: var(--c-text-3); font-size: 11px; }
.agent-input-row {
  width: 100%; display: flex; gap: 6px; align-items: center;
  background: var(--c-surface-2);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  padding: 6px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.05);
  transition: all var(--motion-slow) var(--ease-out);
}
.agent-input-row:focus-within {
  border-color: rgba(91, 108, 255, 0.4);
  box-shadow: 0 16px 48px rgba(91, 108, 255, 0.15), inset 0 1px 1px rgba(255, 255, 255, 0.1);
  background: var(--c-surface-3);
}
.agent-input {
  flex: 1; padding: 8px 12px;
  border: none;
  background: transparent;
  color: var(--c-text-0); font-size: 14px; font-family: inherit;
  outline: none; box-shadow: none;
}
.agent-input:focus { border-color: transparent; }
.agent-input:disabled { opacity: 0.5; }
.agent-attach-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: transparent; color: var(--c-text-2);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: all 0.15s;
}
.agent-attach-btn:hover:not(:disabled) {
  background: var(--c-surface-2); color: var(--c-text-0);
}
.agent-attach-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.agent-attach-btn.voice-active {
  background: var(--c-accent); color: #fff;
  animation: voice-pulse 1.5s ease-in-out infinite;
}
@keyframes voice-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(var(--c-accent-rgb, 99,102,241), 0.4); }
  50% { box-shadow: 0 0 0 6px rgba(var(--c-accent-rgb, 99,102,241), 0); }
}
.agent-send-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  border: none;
  background: var(--c-accent); color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 12px var(--accent-glow);
  transition: background 0.2s, box-shadow 0.2s, opacity 0.15s;
}
.agent-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.agent-send-btn:not(:disabled):hover { opacity: 0.85; }
.agent-send-btn.stopping {
  background: var(--c-surface-3);
  box-shadow: 0 0 0 0 rgba(91,108,255,0);
  animation: stop-ring 1.6s ease-out infinite;
}
@keyframes stop-ring {
  0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--c-accent) 50%, transparent); }
  70%  { box-shadow: 0 0 0 8px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}

/* File attachments */
.agent-attachments {
  width: 100%; display: flex; gap: 6px; flex-wrap: wrap;
  padding: 6px 0;
}
.agent-file {
  display: flex; align-items: center; gap: 4px;
  background: var(--c-surface-2); border: 1px solid var(--c-surface-3);
  border-radius: 4px; padding: 3px 8px; font-size: 11px; color: var(--c-text-3);
}
.agent-file svg { flex-shrink: 0; }
.agent-file-remove {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; font-size: 14px; line-height: 1; padding: 0 2px;
}
.agent-file-remove:hover { color: var(--c-danger); }

/* Docs tab */
.agent-docs { flex: 1; overflow-y: auto; padding: 16px; }
.docs-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.docs-toolbar-actions { display: flex; gap: 6px; }
.docs-error { text-align: center; color: var(--c-danger); font-size: 12px; padding: 8px; background: var(--c-danger-bg); border-radius: 6px; margin-bottom: 8px; }
.docs-title { font-size: 13px; font-weight: 600; color: var(--c-text-0); }
.docs-loading, .docs-empty { text-align: center; color: var(--c-text-3); padding: 40px; }
.docs-list { display: flex; flex-direction: column; gap: 8px; }
.doc-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3); border-radius: 8px;
}
.doc-info { display: flex; flex-direction: column; gap: 2px; }
.doc-title { font-size: 13px; color: var(--c-text-0); }
.doc-meta { font-size: 11px; color: var(--c-text-3); }
.doc-del-btn {
  background: none; border: none; color: var(--c-text-3);
  cursor: pointer; padding: 4px; border-radius: 4px;
  display: flex; align-items: center;
}
.doc-del-btn:hover { color: var(--c-danger); background: var(--c-danger-bg); }

/* Templates tab */
.agent-templates { flex: 1; overflow-y: auto; padding: 16px; }
.template-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.template-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--c-surface-2);
  border: 1px solid var(--c-surface-3); border-radius: 8px;
  cursor: pointer; transition: all 0.15s;
}
.template-card:hover { border-color: var(--c-accent-hover); background: var(--c-accent-bg2); }
.template-icon { font-size: 24px; }
.template-info { display: flex; flex-direction: column; gap: 1px; }
.template-name { font-size: 13px; font-weight: 600; color: var(--c-text-0); }
.template-venue { font-size: 11px; color: var(--c-text-3); }
.template-preview {
  margin-top: 12px; padding: 12px;
  background: var(--c-surface-2); border: 1px solid var(--c-surface-3);
  border-radius: 8px;
}
.template-preview-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 14px; font-weight: 600; color: var(--c-text-0);
}
.template-preview-desc { font-size: 12px; color: var(--c-text-3); margin-top: 6px; line-height: 1.5; }

/* Buttons (docs/templates tabs) */
.btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border: none; border-radius: 6px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all 0.15s; font-family: inherit;
}
.btn.ghost { background: transparent; color: var(--c-text-2); }
.btn.ghost:hover { color: var(--c-accent-hover); }
.btn.ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.primary { background: var(--c-accent); color: #fff; }
.btn.primary:hover { opacity: 0.88; }

/* Workspace status bar */
.agent-workspace-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-size: 11px;
  border-bottom: 1px solid var(--c-glass-border);
  background: transparent;
}
.ws-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--c-text-muted);
  flex-shrink: 0;
}
.agent-workspace-bar.active .ws-dot { background: #4ade80; }
.ws-name { color: var(--c-text-secondary); font-family: var(--font-mono, monospace); }
.ws-name.muted { color: var(--c-text-muted); font-style: italic; }
.docs-subtitle {
  font-size: 11px;
  color: var(--c-text-muted);
  margin-top: 2px;
}
.hint.warn { color: var(--c-warn, #f59e0b); }
</style>
